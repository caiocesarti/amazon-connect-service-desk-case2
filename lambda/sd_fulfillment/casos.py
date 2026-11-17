"""Adapter de integração com o Amazon Connect Cases.

Opera em dois modos controlados por ``CASES_DRY_RUN``:
- ``CASES_DRY_RUN=true`` (padrão local e em testes): gera ID determinístico simulado
  ``case-sim-<hash>`` sem realizar chamadas de rede AWS.
- ``CASES_DRY_RUN=false`` (produção na AWS): invoca ``connectcases.create_case`` usando
  ``clientToken`` determinístico para garantir idempotência em retentativas.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from config import ConfigAmbiente, carregar_config


@dataclass(frozen=True)
class ResultadoCaso:
    """Retorno padronizado da criação de caso no Connect Cases."""

    case_id: str
    protocolo: str
    status_inicial: str
    modo_simulacao: bool


def _gerar_id_simulado(protocolo: str) -> str:
    sufixo = hashlib.sha256(protocolo.encode("utf-8")).hexdigest()[:10]
    return f"case-sim-{sufixo}"


def criar_caso_connect(
    *,
    protocolo: str,
    titulo: str,
    categoria: str,
    prioridade: str,
    resumo: str,
    status_inicial: str = "ABERTO",
    config: ConfigAmbiente | None = None,
    cliente_cases: Any | None = None,
) -> ResultadoCaso:
    """Cria um chamado no Amazon Connect Cases (ou simula em modo DRY_RUN)."""
    cfg = config or carregar_config()
    if cfg.cases_dry_run or cfg.cases_domain_id.startswith("<"):
        return ResultadoCaso(
            case_id=_gerar_id_simulado(protocolo),
            protocolo=protocolo,
            status_inicial=status_inicial,
            modo_simulacao=True,
        )

    if cliente_cases is None:  # pragma: no cover - instanciado apenas na AWS real
        import boto3  # noqa: PLC0415

        cliente_cases = boto3.client("connectcases", region_name=cfg.regiao)

    token_idempotencia = hashlib.sha256(f"case|{protocolo}".encode()).hexdigest()[:36]
    resposta = cliente_cases.create_case(
        domainId=cfg.cases_domain_id,
        templateId=cfg.cases_template_id,
        clientToken=token_idempotencia,
        fields=[
            {"id": "title", "value": {"stringValue": titulo[:100]}},
            {"id": "summary", "value": {"stringValue": resumo[:256]}},
            {"id": "sd_protocolo", "value": {"stringValue": protocolo}},
            {"id": "sd_categoria", "value": {"stringValue": categoria}},
            {"id": "sd_prioridade", "value": {"stringValue": prioridade}},
        ],
    )
    return ResultadoCaso(
        case_id=str(resposta["caseId"]),
        protocolo=protocolo,
        status_inicial=status_inicial,
        modo_simulacao=False,
    )
