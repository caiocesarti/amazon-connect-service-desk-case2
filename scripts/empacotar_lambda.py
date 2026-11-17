#!/usr/bin/env python3
"""Gera o pacote determinístico ``dist/sd_fulfillment.zip`` para deploy no AWS Lambda.

Copia os módulos de ``lambda/sd_fulfillment/*.py`` para a raiz do arquivo ZIP e
inclui ``data/service_desk.json`` em ``dados/service_desk.json`` dentro do pacote,
garantindo que a função Lambda rode em Python 3.12 sem dependências externas.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import zipfile
from pathlib import Path

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
PASTA_LAMBDA_PADRAO = RAIZ_PADRAO / "lambda" / "sd_fulfillment"
CAMINHO_DATASET_PADRAO = RAIZ_PADRAO / "data" / "service_desk.json"
DESTINO_ZIP_PADRAO = RAIZ_PADRAO / "dist" / "sd_fulfillment.zip"
TIMESTAMP_DETERMINISTICO = (2026, 11, 15, 0, 0, 0)


def _adicionar_entrada(zf: zipfile.ZipFile, arcname: str, conteudo: bytes) -> None:
    info = zipfile.ZipInfo(filename=arcname, date_time=TIMESTAMP_DETERMINISTICO)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, conteudo)


def empacotar_lambda(
    pasta_lambda: Path = PASTA_LAMBDA_PADRAO,
    caminho_dataset: Path = CAMINHO_DATASET_PADRAO,
    destino_zip: Path = DESTINO_ZIP_PADRAO,
) -> Path:
    """Empacota os fontes da Lambda + dataset em um ZIP reproduzível."""
    if not pasta_lambda.is_dir():
        raise FileNotFoundError(f"Pasta da Lambda não encontrada: {pasta_lambda}")
    if not caminho_dataset.is_file():
        raise FileNotFoundError(f"Dataset não encontrado: {caminho_dataset}")

    arquivos_py = sorted(pasta_lambda.glob("*.py"))
    if not arquivos_py:
        raise ValueError(f"Nenhum arquivo .py encontrado em {pasta_lambda}")

    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arq in arquivos_py:
            _adicionar_entrada(zf, arq.name, arq.read_bytes())
        _adicionar_entrada(zf, "dados/service_desk.json", caminho_dataset.read_bytes())

    return destino_zip


def _configurar_saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    parser = argparse.ArgumentParser(description="Empacota a Lambda sd-fulfillment-servicedesk.")
    parser.add_argument("--origem", type=Path, default=PASTA_LAMBDA_PADRAO)
    parser.add_argument("--dataset", type=Path, default=CAMINHO_DATASET_PADRAO)
    parser.add_argument("--saida", type=Path, default=DESTINO_ZIP_PADRAO)
    args = parser.parse_args(argv)

    try:
        zip_gerado = empacotar_lambda(args.origem, args.dataset, args.saida)
    except (OSError, ValueError) as exc:
        print(f"[PACOTE] ERRO: {exc}", file=sys.stderr)
        return 2

    tamanho_kb = zip_gerado.stat().st_size / 1024
    print(f"[PACOTE] OK - {zip_gerado.as_posix()} ({tamanho_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
