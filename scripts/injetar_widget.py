#!/usr/bin/env python3
"""Gera o build estático ``landing/dist/`` com o Communications Widget e a camada FinOps.

Ordem de precedência para obter o snippet do widget (Zero-Leak):
1. Variável de ambiente ``CONNECT_WIDGET_SNIPPET`` (usada no deploy da Vercel).
2. Arquivo local ``landing/widget-snippet.local.html`` (ignorado pelo git).
3. Fallback para ``landing/widget-snippet.example.html`` (modo demonstração/CI com placeholders).

O snippet é codificado em Base64 e injetado em ``landing/dist/assets/js/widget-loader.js``
junto com o limite FinOps ``WIDGET_MAX_INTERACOES`` (default: 5).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import os
import shutil
import sys
from pathlib import Path

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
PASTA_LANDING_PADRAO = RAIZ_PADRAO / "landing"
PASTA_DIST_PADRAO = PASTA_LANDING_PADRAO / "dist"


def resolver_snippet(pasta_landing: Path, env_snippet: str | None = None) -> tuple[str, str]:
    """Devolve ``(conteudo_snippet, origem_utilizada)``."""
    valor_env = (
        env_snippet if env_snippet is not None else os.environ.get("CONNECT_WIDGET_SNIPPET", "")
    ).strip()
    if valor_env:
        return valor_env, "env:CONNECT_WIDGET_SNIPPET"

    arq_local = pasta_landing / "widget-snippet.local.html"
    if arq_local.is_file():
        texto = arq_local.read_text(encoding="utf-8").strip()
        if texto:
            return texto, "arquivo:widget-snippet.local.html"

    arq_exemplo = pasta_landing / "widget-snippet.example.html"
    if arq_exemplo.is_file():
        return (
            arq_exemplo.read_text(encoding="utf-8").strip(),
            "fallback:widget-snippet.example.html",
        )

    raise FileNotFoundError(
        f"Nenhum snippet encontrado em {pasta_landing.as_posix()} (nem example.html)."
    )


def gerar_build_landing(
    pasta_landing: Path = PASTA_LANDING_PADRAO,
    pasta_dist: Path = PASTA_DIST_PADRAO,
    max_interacoes: int = 5,
    env_snippet: str | None = None,
) -> dict[str, str]:
    """Monta ``landing/dist/`` com o carregador FinOps configurado."""
    arq_index = pasta_landing / "index.html"
    arq_css = pasta_landing / "assets" / "css" / "style.css"
    arq_acess = pasta_landing / "assets" / "js" / "acessibilidade.js"
    arq_template = pasta_landing / "assets" / "js" / "widget-loader.template.js"

    for obrigatorio in (arq_index, arq_css, arq_acess, arq_template):
        if not obrigatorio.is_file():
            raise FileNotFoundError(f"Arquivo obrigatório ausente: {obrigatorio.as_posix()}")

    snippet_html, origem = resolver_snippet(pasta_landing, env_snippet=env_snippet)
    snippet_b64 = base64.b64encode(snippet_html.encode("utf-8")).decode("ascii")

    if pasta_dist.exists():
        shutil.rmtree(pasta_dist)

    (pasta_dist / "assets" / "css").mkdir(parents=True, exist_ok=True)
    (pasta_dist / "assets" / "js").mkdir(parents=True, exist_ok=True)

    shutil.copy2(arq_index, pasta_dist / "index.html")
    shutil.copy2(arq_css, pasta_dist / "assets" / "css" / "style.css")
    shutil.copy2(arq_acess, pasta_dist / "assets" / "js" / "acessibilidade.js")
    for extra_js in sorted((pasta_landing / "assets" / "js").glob("*.js")):
        if extra_js.name not in {"acessibilidade.js", "widget-loader.js"}:
            shutil.copy2(extra_js, pasta_dist / "assets" / "js" / extra_js.name)

    loader_js = arq_template.read_text(encoding="utf-8")
    loader_js = loader_js.replace("__SD_WIDGET_MAX_INTERACOES__", str(max(1, int(max_interacoes))))
    loader_js = loader_js.replace("__SD_WIDGET_SNIPPET_B64__", snippet_b64)
    (pasta_dist / "assets" / "js" / "widget-loader.js").write_text(loader_js, encoding="utf-8")

    return {
        "origem_snippet": origem,
        "destino": pasta_dist.as_posix(),
        "max_interacoes": str(max(1, int(max_interacoes))),
    }


def _configurar_saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    max_env = int(os.environ.get("WIDGET_MAX_INTERACOES", "5") or "5")
    parser = argparse.ArgumentParser(
        description="Injeta o Communications Widget e a camada FinOps em landing/dist/."
    )
    parser.add_argument("--landing", type=Path, default=PASTA_LANDING_PADRAO)
    parser.add_argument("--dist", type=Path, default=PASTA_DIST_PADRAO)
    parser.add_argument("--max-interacoes", type=int, default=max_env)
    args = parser.parse_args(argv)

    try:
        info = gerar_build_landing(
            pasta_landing=args.landing,
            pasta_dist=args.dist,
            max_interacoes=args.max_interacoes,
        )
    except (OSError, ValueError) as exc:
        print(f"[WIDGET] ERRO: {exc}", file=sys.stderr)
        return 2

    print(
        f"[WIDGET] OK - build gerado em {info['destino']} "
        f"(origem={info['origem_snippet']}, max_interacoes={info['max_interacoes']})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
