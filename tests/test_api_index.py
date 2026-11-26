"""Testes unitários do entrypoint serverless da Vercel (api/index.py)."""

from __future__ import annotations

import http.client
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import api.index as api_index
import pytest


@pytest.fixture
def servidor_vercel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    dist = tmp_path / "dist"
    (dist / "assets" / "css").mkdir(parents=True)
    (dist / "assets" / "js").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>NuvemTech</body></html>", encoding="utf-8")
    (dist / "assets" / "css" / "style.css").write_text("body { color: #fff; }", encoding="utf-8")
    (dist / "assets" / "js" / "app.js").write_text("console.log('ok');", encoding="utf-8")
    (dist / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    # Diretório irmão com mesmo prefixo para validar proteção contra prefix-traversal
    irmao = tmp_path / "dist_privado"
    irmao.mkdir()
    (irmao / "segredo.txt").write_text("nao-expor", encoding="utf-8")

    monkeypatch.setattr(api_index, "PASTA_DIST", dist)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), api_index.handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(url: str) -> tuple[int, str, bytes]:
    try:
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def _post(url: str, corpo: bytes) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, data=corpo, method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_vercel_serve_estaticos_e_bloqueia_path_traversal(servidor_vercel: str) -> None:
    st, ctype, body = _get(f"{servidor_vercel}/")
    assert st == 200 and "text/html" in ctype and b"NuvemTech" in body

    st_css, ctype_css, _ = _get(f"{servidor_vercel}/assets/css/style.css")
    assert st_css == 200 and "text/css" in ctype_css

    st_js, ctype_js, _ = _get(f"{servidor_vercel}/assets/js/app.js")
    assert st_js == 200 and "javascript" in ctype_js

    st_txt, ctype_txt, _ = _get(f"{servidor_vercel}/robots.txt")
    assert st_txt == 200 and "text/plain" in ctype_txt

    st_404, _, erro_404 = _get(f"{servidor_vercel}/inexistente.html")
    assert st_404 == 404 and json.loads(erro_404)["erro"] == "rota nao encontrada"

    st_trav, _, _ = _get(f"{servidor_vercel}/../../pyproject.toml")
    assert st_trav == 404

    st_irmao, _, _ = _get(f"{servidor_vercel}/../dist_privado/segredo.txt")
    assert st_irmao == 404


def test_vercel_api_config_lex_e_tratamento_erros(servidor_vercel: str) -> None:
    st_cfg, ctype_cfg, body_cfg = _get(f"{servidor_vercel}/api/config")
    assert st_cfg == 200 and "application/json" in ctype_cfg
    assert "filas" in json.loads(body_cfg)

    evento = {
        "sessionId": "vercel-e2e",
        "inputTranscript": "esqueci minha senha",
        "sessionState": {"intent": {"name": "PasswordReset", "slots": {}}},
    }
    st_lex, resp_lex = _post(f"{servidor_vercel}/api/lex", json.dumps(evento).encode())
    assert st_lex == 200
    assert resp_lex["sessionState"]["dialogAction"]["slotToElicit"] == "Matricula"

    assert _post(f"{servidor_vercel}/api/outra", b"{}")[0] == 404
    assert _post(f"{servidor_vercel}/api/lex", b"{quebrado")[0] == 400
    assert _post(f"{servidor_vercel}/api/lex", b"[1, 2]")[0] == 400
    assert _post(f"{servidor_vercel}/api/lex", b"")[0] == 413

    partes = urllib.parse.urlparse(servidor_vercel)
    conn = http.client.HTTPConnection(partes.hostname or "127.0.0.1", partes.port or 80)
    try:
        conn.request("POST", "/api/lex", body=b"{}", headers={"Content-Length": "invalido"})
        resp_bad = conn.getresponse()
        assert resp_bad.status == 400
    finally:
        conn.close()
