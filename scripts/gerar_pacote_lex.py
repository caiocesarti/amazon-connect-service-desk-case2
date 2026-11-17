#!/usr/bin/env python3
"""Gera o arquivo ``dist/SD-ServiceDesk-Bot-LexImport.zip`` no formato nativo do Amazon Lex V2.

Permite importar o bot ``SD-ServiceDesk-Bot`` (locale ``pt_BR``, voz neural ``Camila``,
6 Slot Types e 6 Intenções) com 1 clique no Console AWS (Amazon Lex V2 -> Bots -> Action -> Import),
eliminando a digitação manual de dezenas de utterances e slots.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_BOT_EXPORT = RAIZ / "lex" / "bot-export.json"
CAMINHO_SLOT_TYPES = RAIZ / "lex" / "slot-types.json"
DESTINO_ZIP = RAIZ / "dist" / "SD-ServiceDesk-Bot-LexImport.zip"
TIMESTAMP = (2026, 11, 15, 0, 0, 0)


def _id_deterministico(semente: str) -> str:
    """Gera identificador alfanumérico de 10 caracteres exigido pelo formato de export do Lex V2."""
    import hashlib  # noqa: PLC0415

    alfabeto = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digest = hashlib.sha256(semente.encode("utf-8")).digest()
    return "".join(alfabeto[b % len(alfabeto)] for b in digest[:10])


def _escrever_json(zf: zipfile.ZipFile, caminho_interno: str, dados: dict[str, Any]) -> None:
    info = zipfile.ZipInfo(filename=caminho_interno, date_time=TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
    zf.writestr(info, conteudo)


def _montar_slot_type_lex(st: dict[str, Any]) -> dict[str, Any]:
    nome = st["slotTypeName"]
    estrategia = st["valueSelectionStrategy"]
    if estrategia == "REGEX_FILTER" and "regexFilter" in st:
        return {
            "name": nome,
            "identifier": _id_deterministico(f"slottype|{nome}"),
            "description": st.get("description", ""),
            "slotTypeValues": None,
            "parentSlotTypeSignature": "AMAZON.AlphaNumeric",
            "valueSelectionSetting": {
                "resolutionStrategy": "ORIGINAL_VALUE",
                "regexFilter": st["regexFilter"],
            },
        }
    return {
        "name": nome,
        "identifier": _id_deterministico(f"slottype|{nome}"),
        "description": st.get("description", ""),
        "slotTypeValues": st.get("slotTypeValues"),
        "parentSlotTypeSignature": None,
        "valueSelectionSetting": {"resolutionStrategy": estrategia},
    }


def _montar_slot_intencao(intencao_nome: str, slot: dict[str, Any]) -> tuple[dict[str, Any], str]:
    nome_slot = slot["slotName"]
    slot_id = _id_deterministico(f"slot|{intencao_nome}|{nome_slot}")
    vel = slot.get("valueElicitationSetting", {})
    constraint = vel.get("slotConstraint", "Optional")

    grupos = (vel.get("promptSpecification") or {}).get("messageGroups") or [{}]
    msg_obj = grupos[0].get("message") or {}
    prompt_msg = (msg_obj.get("plainTextMessage") or {}).get(
        "value"
    ) or f"Informe o valor para {nome_slot}."

    slot_doc: dict[str, Any] = {
        "name": nome_slot,
        "identifier": slot_id,
        "description": None,
        "slotTypeName": slot["slotTypeName"],
        "obfuscationSetting": None,
        "valueElicitationSetting": {
            "slotCaptureSetting": None,
            "slotConstraint": constraint,
            "promptSpecification": {
                "allowInterrupt": True,
                "maxRetries": 2,
                "messageSelectionStrategy": "Random",
                "messageGroupsList": [
                    {
                        "message": {
                            "plainTextMessage": {"value": prompt_msg},
                            "customPayload": None,
                            "ssmlMessage": None,
                            "imageResponseCard": None,
                        },
                        "variations": None,
                    }
                ],
                "promptAttemptsSpecification": {
                    "Initial": {
                        "allowInterrupt": True,
                        "allowedInputTypes": {
                            "allowAudioInput": True,
                            "allowDTMFInput": True,
                        },
                        "audioAndDTMFInputSpecification": {
                            "startTimeoutMs": 4000,
                            "audioSpecification": {"endTimeoutMs": 640, "maxLengthMs": 15000},
                            "dtmfSpecification": {
                                "deletionCharacter": "*",
                                "endCharacter": "#",
                                "endTimeoutMs": 5000,
                                "maxLength": 513,
                            },
                        },
                        "textInputSpecification": {"startTimeoutMs": 30000},
                    }
                },
            },
        },
        "multipleValuesSetting": None,
    }
    return slot_doc, nome_slot


def _montar_intent_lex(intent: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    nome = intent["intentName"]
    eh_fallback = nome == "FallbackIntent"
    slots_docs: list[dict[str, Any]] = []
    prioridades: list[dict[str, Any]] = []

    for ordem, sl in enumerate(intent.get("slots", []), start=1):
        s_doc, s_nome = _montar_slot_intencao(nome, sl)
        slots_docs.append(s_doc)
        prioridades.append({"priority": ordem, "slotName": s_nome})

    intent_doc = {
        "name": nome,
        "identifier": "FALLBCKINT" if eh_fallback else _id_deterministico(f"intent|{nome}"),
        "description": intent.get("description", ""),
        "parentIntentSignature": "AMAZON.FallbackIntent" if eh_fallback else None,
        "sampleUtterances": None if eh_fallback else intent.get("sampleUtterances", []),
        "intentConfirmationSetting": None,
        "intentClosingSetting": None,
        "initialResponseSetting": None,
        "inputContexts": None,
        "outputContexts": None,
        "kendraConfiguration": None,
        "dialogCodeHook": {"enabled": True},
        "fulfillmentCodeHook": {
            "enabled": True,
            "isActive": True,
            "fulfillmentUpdatesSpecification": None,
            "postFulfillmentStatusSpecification": None,
        },
        "slotPriorities": prioridades,
    }
    return intent_doc, slots_docs


def gerar_zip_import_lex(destino: Path = DESTINO_ZIP) -> Path:
    bot_spec = json.loads(CAMINHO_BOT_EXPORT.read_text(encoding="utf-8"))
    slots_spec = json.loads(CAMINHO_SLOT_TYPES.read_text(encoding="utf-8"))
    locale_spec = bot_spec["bot"]["botLocales"][0]
    pref = "SD-ServiceDesk-Bot/BotLocales/pt_BR"

    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        _escrever_json(
            zf,
            "Manifest.json",
            {"metaData": {"schemaVersion": "1", "fileFormat": "LexJson", "resourceType": "BOT"}},
        )
        _escrever_json(
            zf,
            "SD-ServiceDesk-Bot/Bot.json",
            {
                "name": "SD-ServiceDesk-Bot",
                "identifier": _id_deterministico("bot|SD-ServiceDesk-Bot"),
                "version": "DRAFT",
                "description": bot_spec["bot"]["description"],
                "dataPrivacy": {"childDirected": False},
                "idleSessionTTLInSeconds": 300,
            },
        )
        _escrever_json(
            zf,
            f"{pref}/BotLocale.json",
            {
                "name": "Portuguese (Brazil)",
                "identifier": "pt_BR",
                "version": None,
                "description": locale_spec["description"],
                "voiceSettings": {"voiceId": "Camila", "engine": "neural"},
                "nluConfidenceThreshold": 0.4,
            },
        )
        for st in slots_spec["slotTypes"]:
            st_doc = _montar_slot_type_lex(st)
            _escrever_json(zf, f"{pref}/SlotTypes/{st['slotTypeName']}/SlotType.json", st_doc)

        for intent in locale_spec["intents"]:
            nome_it = intent["intentName"]
            it_doc, slots_docs = _montar_intent_lex(intent)
            _escrever_json(zf, f"{pref}/Intents/{nome_it}/Intent.json", it_doc)
            for s_doc in slots_docs:
                _escrever_json(
                    zf,
                    f"{pref}/Intents/{nome_it}/Slots/{s_doc['name']}/Slot.json",
                    s_doc,
                )

    return destino


if __name__ == "__main__":
    arq = gerar_zip_import_lex()
    print(f"[LEX-IMPORT] OK - {arq.as_posix()} ({arq.stat().st_size / 1024:.1f} KB)")
