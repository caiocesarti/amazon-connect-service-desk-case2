"""Entrypoint Vercel: serve a UI estatica (landing/dist) e a API (/api/config, /api/lex)."""

from __future__ import annotations

import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SCRIPTS = RAIZ / "scripts"
PASTA_DIST = RAIZ / "landing" / "dist"
if str(PASTA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PASTA_SCRIPTS))

import servir_local as sl  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801
    """Handler HTTP nativo do runtime Python da Vercel."""

    def _responder_json(self, status: int, corpo: dict[str, Any]) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(dados)

    def _servir_estatico(self, rota: str) -> bool:
        relativo = "index.html" if rota in {"/", "/index.html", ""} else rota.lstrip("/")
        alvo = (PASTA_DIST / relativo).resolve()
        if not str(alvo).startswith(str(PASTA_DIST.resolve())) or not alvo.is_file():
            return False
        tipo, _ = mimetypes.guess_type(str(alvo))
        if alvo.suffix == ".js":
            tipo = "application/javascript; charset=utf-8"
        elif alvo.suffix == ".css":
            tipo = "text/css; charset=utf-8"
        elif alvo.suffix == ".html":
            tipo = "text/html; charset=utf-8"
        dados = alvo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(dados)
        return True

    def do_GET(self) -> None:  # noqa: N802
        rota = self.path.split("?")[0]
        if rota == "/api/config":
            self._responder_json(200, sl.carregar_config_simulacao(RAIZ))
            return
        if self._servir_estatico(rota):
            return
        self._responder_json(404, {"erro": "rota nao encontrada"})

    def do_POST(self) -> None:  # noqa: N802
        rota = self.path.split("?")[0]
        if rota != "/api/lex":
            self._responder_json(404, {"erro": "rota nao encontrada"})
            return
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0 or tamanho > sl.LIMITE_CORPO_BYTES:
            self._responder_json(413, {"erro": "corpo ausente ou acima do limite"})
            return
        try:
            evento = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if not isinstance(evento, dict):
                raise ValueError("evento deve ser um objeto JSON")
        except (ValueError, UnicodeDecodeError) as exc:
            self._responder_json(400, {"erro": f"JSON invalido: {exc}"})
            return
        self._responder_json(200, sl.invocar_lambda(evento))
