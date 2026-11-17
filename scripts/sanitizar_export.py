#!/usr/bin/env python3
"""Sanitizador automático de exports do console AWS (Amazon Connect e Amazon Lex V2).

Substitui ARNs, Account IDs de 12 dígitos, UUIDs de instâncias/filas/flows/horas de
operação, IDs de bots Lex e aliases de instância por placeholders padronizados da
política Zero-Leak antes de versionar qualquer arquivo exportado do console.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from pathlib import Path

_RE_ARN_CONNECT_QUEUE = re.compile(
    r"arn:aws:connect:[a-z0-9-]+:\d{12}:instance/[0-9a-f-]{36}/queue/[0-9a-f-]{36}",
    re.IGNORECASE,
)
_RE_ARN_CONNECT_FLOW = re.compile(
    r"arn:aws:connect:[a-z0-9-]+:\d{12}:instance/[0-9a-f-]{36}/contact-flow/[0-9a-f-]{36}",
    re.IGNORECASE,
)
_RE_ARN_CONNECT_HOURS = re.compile(
    r"arn:aws:connect:[a-z0-9-]+:\d{12}:instance/[0-9a-f-]{36}/operating-hours/[0-9a-f-]{36}",
    re.IGNORECASE,
)
_RE_ARN_CONNECT_INSTANCE = re.compile(
    r"arn:aws:connect:[a-z0-9-]+:\d{12}:instance/[0-9a-f-]{36}",
    re.IGNORECASE,
)
_RE_ARN_LEX_ALIAS = re.compile(
    r"arn:aws:lex:[a-z0-9-]+:\d{12}:bot-alias/[A-Z0-9]{10}/[A-Z0-9]{10}",
    re.IGNORECASE,
)
_RE_ARN_WISDOM = re.compile(
    r"arn:aws:wisdom:[a-z0-9-]+:\d{12}:assistant/[0-9a-f-]{36}",
    re.IGNORECASE,
)
_RE_ARN_LAMBDA = re.compile(
    r"arn:aws:lambda:[a-z0-9-]+:\d{12}:function:([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_RE_ARN_CONTA_GENERICA = re.compile(r"(arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:)\d{12}(:)")
_RE_CONTA_12_DIGITOS = re.compile(r"(?<![\w+.])\d{12}(?!\w)")
_RE_URL_CONNECT = re.compile(r"https://[a-z0-9-]+\.my\.connect\.aws", re.IGNORECASE)


def sanitizar_conteudo(texto: str) -> str:
    """Aplica todas as regras de substituição Zero-Leak em um texto exportado."""
    atual = _RE_ARN_CONNECT_QUEUE.sub(
        "arn:aws:connect:<REGION>:000000000000:instance/<INSTANCE_ID>/queue/<QUEUE_ID>",
        texto,
    )
    atual = _RE_ARN_CONNECT_FLOW.sub(
        "arn:aws:connect:<REGION>:000000000000:instance/<INSTANCE_ID>/contact-flow/<FLOW_ID>",
        atual,
    )
    atual = _RE_ARN_CONNECT_HOURS.sub(
        "arn:aws:connect:<REGION>:000000000000:instance/<INSTANCE_ID>/operating-hours/<HOURS_ID>",
        atual,
    )
    atual = _RE_ARN_CONNECT_INSTANCE.sub(
        "arn:aws:connect:<REGION>:000000000000:instance/<INSTANCE_ID>", atual
    )
    atual = _RE_ARN_LEX_ALIAS.sub(
        "arn:aws:lex:<REGION>:000000000000:bot-alias/<LEX_BOT_ID>/<LEX_BOT_ALIAS_ID>", atual
    )
    atual = _RE_ARN_WISDOM.sub(
        "arn:aws:wisdom:<REGION>:000000000000:assistant/<Q_ASSISTANT_ID>", atual
    )
    atual = _RE_ARN_LAMBDA.sub(r"arn:aws:lambda:<REGION>:000000000000:function:\1", atual)
    atual = _RE_ARN_CONTA_GENERICA.sub(r"\g<1>000000000000\g<2>", atual)
    atual = _RE_CONTA_12_DIGITOS.sub("000000000000", atual)
    return _RE_URL_CONNECT.sub("https://<INSTANCE_ALIAS>.my.connect.aws", atual)


def sanitizar_arquivo(origem: Path, destino: Path | None = None) -> Path:
    """Lê ``origem``, sanitiza o conteúdo e grava em ``destino`` (ou in-place)."""
    saida = destino or origem
    limpo = sanitizar_conteudo(origem.read_text(encoding="utf-8"))
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(limpo, encoding="utf-8")
    return saida


def _configurar_saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    parser = argparse.ArgumentParser(description="Sanitiza exports brutos do console AWS.")
    parser.add_argument("entrada", type=Path, help="Arquivo exportado a sanitizar.")
    parser.add_argument("-o", "--saida", type=Path, default=None, help="Arquivo de destino.")
    args = parser.parse_args(argv)

    try:
        alvo = sanitizar_arquivo(args.entrada, args.saida)
    except OSError as exc:
        print(f"[SANITIZAR] ERRO: {exc}", file=sys.stderr)
        return 2

    print(f"[SANITIZAR] OK - arquivo sanitizado em {alvo.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
