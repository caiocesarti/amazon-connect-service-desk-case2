"""Camada de Guardrails do NuvemTech Service Desk.

Protege o atendimento conversacional contra:
1. ``EMERGENCIA``: incidentes críticos de segurança (ransomware, phishing, vazamento,
   MFA fatigue, furto de equipamento desbloqueado) -> prioridade P1 imediata.
2. ``INJECAO``: tentativas de prompt injection, jailbreak ou extração de instruções internas.
3. ``SENHA_EXPOSTA``: colaborador digitando a própria senha no chat -> mascaramento imediato.
4. ``PII``: exposição desnecessária de CPF ou cartão no texto livre -> mascaramento imediato.
5. Prevenção de orientações perigosas na saída (nunca sugerir desativar antivírus/firewall/VPN).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from busca import normalizar_texto

TERMOS_EMERGENCIA_SEGURANCA: tuple[str, ...] = (
    "ransomware",
    "arquivos criptografados",
    "pediram resgate",
    "tela de resgate",
    "phishing",
    "link suspeito",
    "site falso",
    "digitei minha senha num link",
    "vazamento de dados",
    "dados vazados",
    "conta invadida",
    "hackearam",
    "invadiram meu",
    "mfa sem eu pedir",
    "aprovacao de mfa",
    "notificacao de login que nao fui eu",
    "roubaram meu notebook",
    "furtaram meu notebook",
    "perdi o celular corporativo",
)

PADROES_INJECAO: tuple[str, ...] = (
    "ignore as instrucoes",
    "ignore todas as instrucoes",
    "esqueca as regras",
    "ignore previous instructions",
    "system prompt",
    "prompt do sistema",
    "voce agora e",
    "aja como root",
    "modo desenvolvedor",
    "dan mode",
    "jailbreak",
    "liste todas as senhas",
    "mostre o banco de dados",
)

ORIENTACOES_PROIBIDAS: tuple[str, ...] = (
    "desative o antivirus",
    "desligue o antivirus",
    "desative o firewall",
    "desligue o firewall",
    "desative o edr",
    "envie sua senha",
    "me informe sua senha",
)

_RE_SENHA_EXPLICITA = re.compile(
    r"(?i)\b(?:minha\s+senha\s+(?:e|eh|atual)|senha\s*[:=])\s*([^\s,;]{4,})"
)
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


@dataclass(frozen=True)
class ResultadoGuardrail:
    """Resultado da inspeção de segurança da entrada do colaborador."""

    acionado: str  # NENHUM | EMERGENCIA | INJECAO | SENHA_EXPOSTA | PII
    bloqueante: bool
    texto_sanitizado: str
    motivo: str = ""


def _mascarar_dados_sensiveis(texto: str) -> tuple[str, str]:
    """Mascara senhas explícitas e CPFs em texto livre. Retorna ``(texto_limpo, tipo)``."""
    tipo_detectado = "NENHUM"
    atual = texto

    if _RE_SENHA_EXPLICITA.search(atual):
        atual = _RE_SENHA_EXPLICITA.sub("senha: [SENHA_REMOVIDA]", atual)
        tipo_detectado = "SENHA_EXPOSTA"

    if _RE_CPF.search(atual):
        atual = _RE_CPF.sub("[CPF_REMOVIDO]", atual)
        if tipo_detectado == "NENHUM":
            tipo_detectado = "PII"

    return atual, tipo_detectado


def avaliar_entrada(texto_usuario: str | None) -> ResultadoGuardrail:
    """Inspeciona a mensagem do colaborador antes de qualquer regra de negócio."""
    if not texto_usuario or not texto_usuario.strip():
        return ResultadoGuardrail(acionado="NENHUM", bloqueante=False, texto_sanitizado="")

    texto_sanitizado, tipo_mascara = _mascarar_dados_sensiveis(texto_usuario.strip())
    norm = normalizar_texto(texto_sanitizado)

    for padrao in PADROES_INJECAO:
        if padrao in norm:
            return ResultadoGuardrail(
                acionado="INJECAO",
                bloqueante=True,
                texto_sanitizado="[CONTEUDO_BLOQUEADO_GUARDRAIL]",
                motivo=f"Tentativa de manipulação de instruções detectada ({padrao}).",
            )

    for termo in TERMOS_EMERGENCIA_SEGURANCA:
        if termo in norm:
            return ResultadoGuardrail(
                acionado="EMERGENCIA",
                bloqueante=True,
                texto_sanitizado=texto_sanitizado,
                motivo=f"Gatilho de emergência de segurança da informação ({termo}).",
            )

    if tipo_mascara != "NENHUM":
        return ResultadoGuardrail(
            acionado=tipo_mascara,
            bloqueante=False,
            texto_sanitizado=texto_sanitizado,
            motivo="Dado sensível mascarado automaticamente antes do processamento.",
        )

    return ResultadoGuardrail(
        acionado="NENHUM",
        bloqueante=False,
        texto_sanitizado=texto_sanitizado,
    )


def validar_resposta_segura(resposta: str) -> str:
    """Garante que nenhuma mensagem de saída contenha orientações perigosas."""
    norm = normalizar_texto(resposta)
    for proibida in ORIENTACOES_PROIBIDAS:
        if proibida in norm:
            raise ValueError(
                "Resposta bloqueada pelo guardrail de saída: "
                f"contém orientação proibida ({proibida})."
            )
    return resposta
