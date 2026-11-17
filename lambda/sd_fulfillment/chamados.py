"""Regras de negócio ITIL, protocolo determinístico e montagem de contexto ``sd_*``."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from config import TAMANHO_MAX_RESUMO
from guardrails import _mascarar_dados_sensiveis

_MAPA_INTL_CATEGORIA: dict[str, str] = {
    "PasswordReset": "ACESSO_SEGURANCA",
    "NetworkIssue": "REDE_CONECTIVIDADE",
    "HardwareRequest": "HARDWARE",
    "ConsultarStatusChamado": "GERAL",
    "FalarComAtendente": "GERAL",
    "FallbackIntent": "GERAL",
}

_ORDEM_PRIORIDADE: tuple[str, ...] = ("P1", "P2", "P3", "P4")


def categorizar_intencao(intencao: str) -> str:
    """Traduz o nome da intenção Lex na categoria padronizada ``sd_categoria``."""
    return _MAPA_INTL_CATEGORIA.get(intencao, "GERAL")


def _elevar_um_nivel(prioridade: str) -> str:
    idx = _ORDEM_PRIORIDADE.index(prioridade) if prioridade in _ORDEM_PRIORIDADE else 2
    return _ORDEM_PRIORIDADE[max(0, idx - 1)]


def calcular_prioridade_itil(
    intencao: str,
    impacto: str = "INDIVIDUAL",
    vip_diretoria: bool = False,
    status_conta: str = "ATIVO",
    emergencia: bool = False,
    incidente_vinculado: bool = False,
) -> str:
    """Calcula a prioridade ITIL (``P1`` a ``P4``) combinando impacto, urgência e perfil."""
    if emergencia or impacto == "UNIDADE":
        return "P1"

    if intencao == "PasswordReset":
        base = "P2" if status_conta in {"BLOQUEADO", "INATIVO"} else "P3"
    elif intencao == "NetworkIssue":
        base = "P2" if (impacto == "SETOR" or incidente_vinculado) else "P3"
    elif intencao == "HardwareRequest":
        base = "P3"
    else:
        base = "P4"

    if vip_diretoria:
        return _elevar_um_nivel(base)
    return base


def determinar_fila_destino(
    intencao: str,
    prioridade: str,
    emergencia: bool = False,
) -> str:
    """Retorna a chave lógica ``sd_fila_destino`` (sem ARNs no código)."""
    if emergencia or prioridade == "P1":
        return "PRIORITARIA_P1"
    if intencao == "PasswordReset":
        return "SEGURANCA"
    if intencao == "NetworkIssue":
        return "REDES"
    if intencao == "HardwareRequest":
        return "HARDWARE"
    return "GERAL_N1"


def gerar_protocolo_deterministico(
    matricula: str,
    intencao: str,
    detalhe: str = "",
    data_ref: str | None = None,
) -> str:
    """Gera protocolo determinístico ``SD-AAAAMMDD-XXXXXX`` via SHA-256."""
    dia = data_ref or datetime.now(tz=UTC).strftime("%Y%m%d")
    semente = f"{dia}|{matricula.strip().upper()}|{intencao.strip()}|{detalhe.strip().upper()}"
    digest = hashlib.sha256(semente.encode("utf-8")).hexdigest()[:6].upper()
    return f"SD-{dia}-{digest}"


def avaliar_solicitacao_hardware(
    item: dict[str, Any],
    unidade: dict[str, Any] | None,
) -> dict[str, Any]:
    """Avalia estoque, necessidade de aprovação e SLA logístico por unidade."""
    estoque = int(item.get("estoque_disponivel", 0))
    requer_aprovacao = bool(item.get("requer_aprovacao_gestor", False))

    if estoque <= 0:
        estoque_status = "INDISPONIVEL"
        status_caso = "AGUARDANDO_ESTOQUE"
    elif requer_aprovacao:
        estoque_status = "REQUER_APROVACAO"
        status_caso = "AGUARDANDO_APROVACAO"
    else:
        estoque_status = "DISPONIVEL"
        status_caso = "ABERTO"

    prazo_item = int(item.get("prazo_padrao_dias", 2))
    sla_unidade = int(unidade.get("sla_hardware_dias_uteis", 2)) if unidade else 2
    suporte_local = bool(unidade.get("suporte_local", True)) if unidade else True
    tecnicos = int(unidade.get("tecnicos_presenciais", 2)) if unidade else 2

    prazo_final = max(prazo_item, sla_unidade)
    if not suporte_local:
        modalidade_entrega = "ENVIO_LOGISTICA_EXPRESSA"
    elif tecnicos == 1:
        modalidade_entrega = "AGENDAMENTO_TECNICO_UNICO"
    else:
        modalidade_entrega = "ENTREGA_PRESENCIAL_LOCAL"

    return {
        "equipamento": item["codigo"],
        "nome_equipamento": item["nome"],
        "estoque_status": estoque_status,
        "status_caso": status_caso,
        "alternativa_sugerida": item.get("alternativa_sugerida"),
        "prazo_dias_uteis": prazo_final,
        "modalidade_entrega": modalidade_entrega,
    }


def montar_resumo_contexto(
    colaborador: dict[str, Any] | None,
    intencao: str,
    prioridade: str,
    detalhe: str,
    incidente_id: str | None = None,
) -> str:
    """Monta ``sd_resumo`` conciso (máx. 256 chars) e sem PII para o CCP v2."""
    detalhe_limpo, _ = _mascarar_dados_sensiveis(detalhe.strip())
    if colaborador:
        ident = (
            f"{colaborador['primeiro_nome']} "
            f"({colaborador['matricula']}, {colaborador['unidade']})"
        )
    else:
        ident = "Colaborador não identificado"

    partes = [f"[{prioridade}] {ident} - {intencao}: {detalhe_limpo}"]
    if incidente_id:
        partes.append(f"Incidente vinculado: {incidente_id}.")

    texto = " ".join(partes)
    if len(texto) <= TAMANHO_MAX_RESUMO:
        return texto
    return texto[: TAMANHO_MAX_RESUMO - 3].rstrip() + "..."
