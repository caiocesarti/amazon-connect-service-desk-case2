"""Testes unitários do injetor FinOps do widget e da configuração Vercel CSP (F5)."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import pytest

import injetar_widget as iw


def test_build_landing_padrao_usa_fallback_example(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copia_landing = tmp_path / "landing"
    shutil.copytree(
        iw.PASTA_LANDING_PADRAO,
        copia_landing,
        ignore=shutil.ignore_patterns("dist", "widget-snippet.local.html"),
    )
    dist = tmp_path / "dist"
    assert (
        iw.main(
            [
                "--landing",
                str(copia_landing),
                "--dist",
                str(dist),
                "--max-interacoes",
                "4",
            ]
        )
        == 0
    )
    saida = capsys.readouterr().out
    assert "fallback:widget-snippet.example.html" in saida

    loader = (dist / "assets" / "js" / "widget-loader.js").read_text(encoding="utf-8")
    assert 'Number("4")' in loader
    assert "__SD_WIDGET_SNIPPET_B64__" not in loader
    assert "navigator.webdriver" in loader
    assert "localStorage" in loader


def test_precedencia_env_e_arquivo_local(tmp_path: Path) -> None:
    copia_landing = tmp_path / "landing"
    shutil.copytree(iw.PASTA_LANDING_PADRAO, copia_landing, ignore=shutil.ignore_patterns("dist"))

    # 1. Arquivo local vence o example.html
    arq_local = copia_landing / "widget-snippet.local.html"
    arq_local.write_text("<script>/* snippet-local-teste */</script>", encoding="utf-8")
    dist_local = tmp_path / "dist_local"
    info_local = iw.gerar_build_landing(copia_landing, dist_local)
    assert info_local["origem_snippet"] == "arquivo:widget-snippet.local.html"

    loader_local = (dist_local / "assets" / "js" / "widget-loader.js").read_text(encoding="utf-8")
    b64_local = base64.b64encode(b"<script>/* snippet-local-teste */</script>").decode("ascii")
    assert b64_local in loader_local

    # 2. Variável de ambiente vence o arquivo local
    dist_env = tmp_path / "dist_env"
    info_env = iw.gerar_build_landing(
        copia_landing, dist_env, env_snippet="<script>/* snippet-env */</script>"
    )
    assert info_env["origem_snippet"] == "env:CONNECT_WIDGET_SNIPPET"


def test_erro_quando_landing_incompleta(tmp_path: Path) -> None:
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    assert iw.main(["--landing", str(vazia), "--dist", str(tmp_path / "out")]) == 2

    with pytest.raises(FileNotFoundError):
        iw.resolver_snippet(vazia)


def test_vercel_json_contem_headers_csp_connect_e_chime_webrtc() -> None:
    arq_vercel = iw.RAIZ_PADRAO / "vercel.json"
    dados = json.loads(arq_vercel.read_text(encoding="utf-8"))
    assert dados["outputDirectory"] == "landing/dist"

    headers_map = {h["key"]: h["value"] for h in dados["headers"][0]["headers"]}
    csp = headers_map["Content-Security-Policy"]
    for dominio_obrigatorio in (
        "https://*.my.connect.aws",
        "https://*.amazonaws.com",
        "https://*.cloudfront.net",
        "https://*.chime.aws",
        "https://*.sdkassets.chime.aws",
        "wss://*.chime.aws",
    ):
        assert dominio_obrigatorio in csp
