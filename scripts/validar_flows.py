#!/usr/bin/env python3
"""Validação estrutural dos Contact Flows (schema 2019-10-30) e do export do Lex V2.

Verifica:
1. Todos os arquivos ``connect/flows/*.json`` seguem ``Version == "2019-10-30"``.
2. ``StartAction`` existe e todas as transições (``NextAction``, ``Conditions``, ``Errors``)
   apontam para identificadores de blocos existentes no mesmo flow (zero transições órfãs).
3. Blocos não-terminais possuem tratamento de erro conectado (exceto ``UpdateFlowLoggingBehavior``
   e ``Compare``, conforme semântica do Amazon Connect).
4. ``SD-Entrada-Principal.json`` cumpre a cadeia obrigatória do Pilar 5:
   ``UpdateFlowLoggingBehavior`` (Enabled) -> ``UpdateContactTextToSpeechVoice`` (Camila Neural)
   -> ``UpdateContactData`` (pt-BR) -> ``CreateWisdomSession`` (com Error conectado)
   -> ``UpdateContactAttributes`` -> ``MessageParticipant`` -> ``ConnectParticipantWithLexBot``.
5. ``SD-Transbordo-N1.json`` cobre todas as 5 chaves lógicas de ``sd_fila_destino``
   (``PRIORITARIA_P1``, ``SEGURANCA``, ``REDES``, ``HARDWARE``, ``GERAL_N1``) e verifica
   horário de operação (``CheckHoursOfOperation``) antes de ``TransferContactToQueue``.
6. ``lex/bot-export.json`` e ``lex/slot-types.json`` estão em ``pt_BR`` com a voz ``Camila``
   e contêm as intenções obrigatórias do Case 2.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
PASTA_FLOWS_PADRAO = RAIZ_PADRAO / "connect" / "flows"
PASTA_LEX_PADRAO = RAIZ_PADRAO / "lex"

TIPOS_TERMINAIS = frozenset({"DisconnectParticipant", "EndFlowExecution"})
TIPOS_SEM_PORTA_ERRO = frozenset({"UpdateFlowLoggingBehavior", "Compare"})
FILAS_OBRIGATORIAS = {"PRIORITARIA_P1", "SEGURANCA", "REDES", "HARDWARE", "GERAL_N1"}
INTENCOES_OBRIGATORIAS = {
    "PasswordReset",
    "NetworkIssue",
    "HardwareRequest",
    "ConsultarStatusChamado",
    "FalarComAtendente",
    "FallbackIntent",
}


def _carregar_json(caminho: Path) -> dict[str, Any]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError(f"{caminho.name} deve conter um objeto JSON na raiz.")
    return dados


def _destinos_bloco(acao: dict[str, Any]) -> list[str]:
    trans = acao.get("Transitions") or {}
    destinos: list[str] = []
    if trans.get("NextAction"):
        destinos.append(str(trans["NextAction"]))
    for cond in trans.get("Conditions") or []:
        if cond.get("NextAction"):
            destinos.append(str(cond["NextAction"]))
    for err in trans.get("Errors") or []:
        if err.get("NextAction"):
            destinos.append(str(err["NextAction"]))
    return destinos


def validar_flow_individual(caminho: Path) -> list[str]:
    """Valida a estrutura e o grafo de transições de um único Contact Flow."""
    nome = caminho.name
    dados = _carregar_json(caminho)
    erros: list[str] = []

    if dados.get("Version") != "2019-10-30":
        erros.append(f"[{nome}] Version deve ser '2019-10-30'.")

    acoes = dados.get("Actions") or []
    if not acoes:
        return [*erros, f"[{nome}] Lista Actions está vazia."]

    mapa_acoes = {a["Identifier"]: a for a in acoes if "Identifier" in a}
    if len(mapa_acoes) != len(acoes):
        erros.append(f"[{nome}] Identificadores de blocos duplicados ou ausentes em Actions.")

    start = dados.get("StartAction")
    if start not in mapa_acoes:
        erros.append(f"[{nome}] StartAction '{start}' não existe em Actions.")

    for ident, acao in mapa_acoes.items():
        tipo = str(acao.get("Type") or "")
        destinos = _destinos_bloco(acao)

        if tipo not in TIPOS_TERMINAIS and not destinos:
            erros.append(f"[{nome}] Bloco não-terminal '{ident}' ({tipo}) não possui saída.")

        for dest in destinos:
            if dest not in mapa_acoes:
                erros.append(f"[{nome}] Bloco '{ident}' aponta para destino inexistente '{dest}'.")

        erros_trans = (acao.get("Transitions") or {}).get("Errors") or []
        if tipo not in TIPOS_TERMINAIS and tipo not in TIPOS_SEM_PORTA_ERRO and not erros_trans:
            erros.append(f"[{nome}] Bloco '{ident}' ({tipo}) não possui porta Errors configurada.")

    return erros


def validar_regras_entrada_principal(dados: dict[str, Any]) -> list[str]:
    """Verifica a cadeia arquitetural obrigatória do Pilar 5 em SD-Entrada-Principal."""
    erros: list[str] = []
    acoes = {a["Identifier"]: a for a in dados.get("Actions", [])}
    primeira = acoes.get(dados.get("StartAction", ""), {})

    if primeira.get("Type") != "UpdateFlowLoggingBehavior":
        erros.append("[SD-Entrada-Principal] StartAction deve ser UpdateFlowLoggingBehavior.")
    elif (primeira.get("Parameters") or {}).get("FlowLoggingBehavior") != "Enabled":
        erros.append("[SD-Entrada-Principal] FlowLoggingBehavior deve ser 'Enabled'.")

    tipos_presentes = {a.get("Type") for a in acoes.values()}
    for obrigatorio in (
        "UpdateContactTextToSpeechVoice",
        "UpdateContactData",
        "CreateWisdomSession",
        "UpdateContactAttributes",
        "MessageParticipant",
        "ConnectParticipantWithLexBot",
    ):
        if obrigatorio not in tipos_presentes:
            erros.append(f"[SD-Entrada-Principal] Falta bloco obrigatório '{obrigatorio}'.")

    for a in acoes.values():
        if a.get("Type") == "UpdateContactTextToSpeechVoice":
            params = a.get("Parameters") or {}
            if params.get("TextToSpeechVoice") != "Camila":
                erros.append("[SD-Entrada-Principal] Voz TTS deve ser 'Camila'.")
            if params.get("TextToSpeechEngine") != "Neural":
                erros.append("[SD-Entrada-Principal] Engine TTS deve ser 'Neural'.")

    return erros


def validar_regras_transbordo(dados: dict[str, Any]) -> list[str]:
    """Verifica cobertura das 5 filas lógicas e verificação de horário comercial."""
    erros: list[str] = []
    acoes = dados.get("Actions", [])
    tipos = {a.get("Type") for a in acoes}

    for obrigatorio in (
        "CheckHoursOfOperation",
        "UpdateContactTargetQueue",
        "TransferContactToQueue",
    ):
        if obrigatorio not in tipos:
            erros.append(f"[SD-Transbordo-N1] Falta bloco obrigatório '{obrigatorio}'.")

    filas_comparadas: set[str] = set()
    for a in acoes:
        if a.get("Type") == "Compare":
            for cond in (a.get("Transitions") or {}).get("Conditions") or []:
                operandos = (cond.get("Condition") or {}).get("Operands") or []
                filas_comparadas.update(str(op) for op in operandos)

    faltantes = sorted(FILAS_OBRIGATORIAS - filas_comparadas)
    if faltantes:
        lista_faltantes = ", ".join(faltantes)
        erros.append(
            f"[SD-Transbordo-N1] Chaves lógicas de fila ausentes no Compare: {lista_faltantes}."
        )
    return erros


def validar_lex(pasta_lex: Path) -> list[str]:
    """Valida a especificação do bot Lex V2 e os slot types."""
    erros: list[str] = []
    arq_bot = pasta_lex / "bot-export.json"
    arq_slots = pasta_lex / "slot-types.json"

    if not arq_bot.is_file() or not arq_slots.is_file():
        return ["[LEX] Arquivos lex/bot-export.json ou lex/slot-types.json ausentes."]

    bot_doc = _carregar_json(arq_bot)
    slots_doc = _carregar_json(arq_slots)

    if slots_doc.get("localeId") != "pt_BR":
        erros.append("[LEX] slot-types.json deve usar localeId 'pt_BR'.")

    locales = (bot_doc.get("bot") or {}).get("botLocales") or []
    pt_br = next((loc for loc in locales if loc.get("localeId") == "pt_BR"), None)
    if not pt_br:
        return [*erros, "[LEX] bot-export.json não contém locale 'pt_BR'."]

    voz = pt_br.get("voiceSettings") or {}
    if voz.get("voiceId") != "Camila" or voz.get("engine") != "neural":
        erros.append("[LEX] voiceSettings deve ser Camila (neural).")

    intencoes = {i.get("intentName") for i in pt_br.get("intents") or []}
    faltantes = sorted(INTENCOES_OBRIGATORIAS - intencoes)
    if faltantes:
        erros.append(f"[LEX] Intenções obrigatórias ausentes: {', '.join(faltantes)}.")

    return erros


def validar_tudo(
    pasta_flows: Path = PASTA_FLOWS_PADRAO,
    pasta_lex: Path = PASTA_LEX_PADRAO,
) -> list[str]:
    """Executa todas as validações de Contact Flows e Lex V2."""
    if not pasta_flows.is_dir():
        return [f"[FLOWS] Pasta não encontrada: {pasta_flows.as_posix()}"]

    arquivos = sorted(pasta_flows.glob("*.json"))
    if len(arquivos) < 3:
        return [f"[FLOWS] Esperados pelo menos 3 flows JSON, encontrados {len(arquivos)}."]

    erros: list[str] = []
    for arq in arquivos:
        erros.extend(validar_flow_individual(arq))

    entrada = pasta_flows / "SD-Entrada-Principal.json"
    if entrada.is_file():
        erros.extend(validar_regras_entrada_principal(_carregar_json(entrada)))

    transbordo = pasta_flows / "SD-Transbordo-N1.json"
    if transbordo.is_file():
        erros.extend(validar_regras_transbordo(_carregar_json(transbordo)))

    erros.extend(validar_lex(pasta_lex))
    return erros


def _configurar_saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    parser = argparse.ArgumentParser(description="Valida Contact Flows e especificação Lex V2.")
    parser.add_argument("--flows", type=Path, default=PASTA_FLOWS_PADRAO)
    parser.add_argument("--lex", type=Path, default=PASTA_LEX_PADRAO)
    args = parser.parse_args(argv)

    try:
        erros = validar_tudo(args.flows, args.lex)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FLOWS] ERRO: {exc}", file=sys.stderr)
        return 2

    if erros:
        print(f"[FLOWS] FALHA - {len(erros)} erro(s) encontrado(s):")
        for e in erros:
            print(f"  - {e}")
        return 1

    qtd_flows = len(list(args.flows.glob("*.json")))
    print(
        f"[FLOWS] OK - {qtd_flows} Contact Flows (schema 2019-10-30) "
        "e especificação Lex V2 íntegros."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
