"""Configurações e constantes do contrato de sessão ``sd_*``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ_PACOTE = Path(__file__).resolve().parent
CAMINHO_DADOS_EMBARCADO = RAIZ_PACOTE / "dados" / "service_desk.json"
CAMINHO_DADOS_REPOSITORIO = RAIZ_PACOTE.parent.parent / "data" / "service_desk.json"

MAX_TENTATIVAS_VALIDACAO = 3
TAMANHO_MAX_RESUMO = 256

FILAS_VALIDAS = frozenset({"SEGURANCA", "REDES", "HARDWARE", "GERAL_N1", "PRIORITARIA_P1"})
INTENCOES_CONHECIDAS = frozenset(
    {
        "PasswordReset",
        "NetworkIssue",
        "HardwareRequest",
        "ConsultarStatusChamado",
        "FalarComAtendente",
        "FallbackIntent",
    }
)


@dataclass(frozen=True)
class ConfigAmbiente:
    """Parâmetros lidos de variáveis de ambiente com defaults seguros para laboratório."""

    regiao: str
    cases_domain_id: str
    cases_template_id: str
    cases_dry_run: bool
    log_level: str


def carregar_config() -> ConfigAmbiente:
    """Lê variáveis de ambiente em tempo de execução."""
    dry_run_str = os.environ.get("CASES_DRY_RUN", "true").strip().lower()
    return ConfigAmbiente(
        regiao=os.environ.get("AWS_REGION", "us-east-1").strip(),
        cases_domain_id=os.environ.get("CASES_DOMAIN_ID", "<CASES_DOMAIN_ID>").strip(),
        cases_template_id=os.environ.get("CASES_TEMPLATE_ID", "<CASES_TEMPLATE_ID>").strip(),
        cases_dry_run=dry_run_str not in {"false", "0", "no"},
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
    )


def resolver_caminho_dataset() -> Path:
    """Usa o dataset empacotado na Lambda ou faz fallback para ``data/service_desk.json``."""
    env_custom = os.environ.get("SD_DATASET_PATH")
    if env_custom:
        return Path(env_custom)
    if CAMINHO_DADOS_EMBARCADO.is_file():
        return CAMINHO_DADOS_EMBARCADO
    return CAMINHO_DADOS_REPOSITORIO
