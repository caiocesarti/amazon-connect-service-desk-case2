"""Servidor local do laboratório: landing estática + API do simulador (Lex/Lambda reais).

Endpoints (somente ``127.0.0.1``):
- ``GET  /api/config``: filas, regras do Contact Lens, métricas e intenções lidas dos arquivos
  versionados (``connect/recursos.yaml``, ``connect/contact-lens/regras.json``,
  ``lex/bot-export.json``). Nenhum dado de regra é duplicado no front-end.
- ``POST /api/lex``: evento Lex V2 -> ``handler.lambda_handler`` real (``CASES_DRY_RUN=true``),
  devolvendo a resposta da Lambda e o bloco ``flow`` (fila, Case) que o Contact Flow produziria.

Todo conteúdo é servido com ``Cache-Control: no-store`` para que ``F5`` traga sempre o build novo.
Uso: ``python scripts/servir_local.py [--porta 8080] [--sem-build]``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
PASTA_LAMBDA = RAIZ / "lambda" / "sd_fulfillment"
LIMITE_CORPO_BYTES = 64 * 1024
INTENCOES_ROTEAVEIS = ("PasswordReset", "NetworkIssue", "HardwareRequest", "FalarComAtendente")


def _garantir_lambda_no_path() -> None:
    os.environ.setdefault("CASES_DRY_RUN", "true")
    if str(PASTA_LAMBDA) not in sys.path:
        sys.path.insert(0, str(PASTA_LAMBDA))


def carregar_config_simulacao(raiz: Path = RAIZ) -> dict[str, Any]:
    """Monta a configuração do simulador exclusivamente a partir dos arquivos do repositório."""
    import yaml  # noqa: PLC0415

    _garantir_lambda_no_path()
    import chamados  # noqa: PLC0415

    recursos = yaml.safe_load((raiz / "connect" / "recursos.yaml").read_text(encoding="utf-8"))
    regras = json.loads(
        (raiz / "connect" / "contact-lens" / "regras.json").read_text(encoding="utf-8")
    )
    bot = json.loads((raiz / "lex" / "bot-export.json").read_text(encoding="utf-8"))["bot"]
    tipos_slot = json.loads((raiz / "lex" / "slot-types.json").read_text(encoding="utf-8"))
    slot_types = {
        t["slotTypeName"]: [
            {"valor": v["sampleValue"]["value"], "sinonimos": [s["value"] for s in v["synonyms"]]}
            for v in t["slotTypeValues"]
        ]
        for t in tipos_slot["slotTypes"]
        if t.get("slotTypeValues")
    }

    filas = {
        f["chave_logica"]: {"nome": f["nome"], "descricao": f["descricao"]}
        for f in recursos["filas"]
    }
    intents = []
    for intent in bot["botLocales"][0]["intents"]:
        slots = [
            {
                "nome": s["slotName"],
                "tipo": s["slotTypeName"],
                "obrigatorio": s["valueElicitationSetting"].get("slotConstraint") == "Required",
            }
            for s in intent.get("slots", [])
        ]
        intents.append(
            {
                "nome": intent["intentName"],
                "exemplos": [u["utterance"] for u in intent.get("sampleUtterances", [])],
                "slots": slots,
            }
        )
    roteamento = {
        nome: chamados.determinar_fila_destino(nome, "P3") for nome in INTENCOES_ROTEAVEIS
    }
    roteamento["P1"] = chamados.determinar_fila_destino("PasswordReset", "P1")
    return {
        "filas": filas,
        "roteamento": roteamento,
        "metricas": {m["sigla"]: m for m in recursos["metricas_supervisor"]},
        "contact_lens": regras,
        "intents": intents,
        "slot_types": slot_types,
        "nlu_threshold": bot["botLocales"][0]["nluConfidenceThreshold"],
    }


def invocar_lambda(evento: dict[str, Any]) -> dict[str, Any]:
    """Executa a Lambda real e acrescenta o bloco ``flow`` calculado a partir dos ``sd_*``."""
    _garantir_lambda_no_path()
    import casos  # noqa: PLC0415
    import handler  # noqa: PLC0415

    resposta = handler.lambda_handler(evento, None)
    estado = resposta.get("sessionState", {})
    attrs = estado.get("sessionAttributes", {})
    fechado = estado.get("dialogAction", {}).get("type") == "Close"

    flow: dict[str, Any] = {"encerrado": fechado}
    protocolo = attrs.get("sd_protocolo")
    if fechado and protocolo and attrs.get("sd_proxima_acao") in {"TRANSBORDO", "CRIAR_CASO"}:
        titulo = f"{attrs.get('sd_intencao', 'Contato')} - {attrs.get('sd_matricula', 'N/D')}"
        caso_id = attrs.get("sd_caso_id")
        if not caso_id:
            caso = casos.criar_caso_connect(
                protocolo=protocolo,
                titulo=titulo,
                categoria=attrs.get("sd_categoria", "GERAL"),
                prioridade=attrs.get("sd_prioridade", "P3"),
                resumo=attrs.get("sd_resumo", ""),
            )
            caso_id = caso.case_id
        flow["caso"] = {
            "case_id": caso_id,
            "protocolo": protocolo,
            "template": "SD-Template-Chamado-TI",
            "campos": {
                "title": titulo,
                "summary": attrs.get("sd_resumo", ""),
                "sd_protocolo": protocolo,
                "sd_categoria": attrs.get("sd_categoria", "GERAL"),
                "sd_prioridade": attrs.get("sd_prioridade", "P3"),
                "sd_matricula": attrs.get("sd_matricula", ""),
                "sd_fila_destino": attrs.get("sd_fila_destino", ""),
            },
        }
    resposta["flow"] = flow
    return resposta


class ManipuladorSimulador(SimpleHTTPRequestHandler):
    """Arquivos estáticos sem cache + API JSON do simulador."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write(f"[SIM] {self.address_string()} {format % args}\n")

    def _responder_json(self, status: int, corpo: dict[str, Any]) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] == "/api/config":
            self._responder_json(200, carregar_config_simulacao())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/api/lex":
            self._responder_json(404, {"erro": "rota inexistente"})
            return
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._responder_json(400, {"erro": "Content-Length inválido"})
            return
        if tamanho <= 0 or tamanho > LIMITE_CORPO_BYTES:
            self._responder_json(413, {"erro": "corpo ausente ou acima do limite"})
            return
        try:
            evento = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if not isinstance(evento, dict):
                raise ValueError("evento deve ser um objeto JSON")
        except (ValueError, UnicodeDecodeError) as exc:
            self._responder_json(400, {"erro": f"JSON inválido: {exc}"})
            return
        self._responder_json(200, invocar_lambda(evento))


def criar_servidor(porta: int, dist: Path) -> ThreadingHTTPServer:
    """Cria o servidor vinculado apenas ao loopback."""
    manipulador = partial(ManipuladorSimulador, directory=str(dist))
    return ThreadingHTTPServer(("127.0.0.1", porta), manipulador)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--porta", type=int, default=8080)
    parser.add_argument("--sem-build", action="store_true", help="não regenera landing/dist")
    args = parser.parse_args(argv)

    import injetar_widget  # noqa: PLC0415

    dist = injetar_widget.PASTA_DIST_PADRAO
    if not args.sem_build:
        injetar_widget.gerar_build_landing()
    servidor = criar_servidor(args.porta, dist)
    print(f"[SIM] Laboratório em http://localhost:{args.porta}  (Ctrl+C para encerrar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        print("\n[SIM] Encerrado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
