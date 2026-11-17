"""Testes unitários de validar_flows.py e sanitizar_export.py (F3 e F4)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import gerar_pacote_lex as gpl
import sanitizar_export as se
import validar_flows as vf
import verificar_segredos as vs

CONTA_FALSA = "4111" + "22233344"
UUID_FALSO_1 = "11111111-2222-3333-4444-55555555555a"
UUID_FALSO_2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_flows_e_lex_oficiais_estao_validos(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert vf.validar_tudo() == []
    assert vf.main([]) == 0
    assert "[FLOWS] OK" in capsys.readouterr().out

    zip_lex = gpl.gerar_zip_import_lex(tmp_path / "lex.zip")
    assert zip_lex.is_file() and zip_lex.stat().st_size > 1000


def test_validador_detecta_transicao_orfa_e_falta_de_erro(tmp_path: Path) -> None:
    pasta_flows = tmp_path / "flows"
    pasta_flows.mkdir()

    flow_invalido = {
        "Version": "2018-01-01",
        "StartAction": "nao-existe",
        "Actions": [
            {
                "Identifier": "b1",
                "Type": "MessageParticipant",
                "Parameters": {"Text": "Oi"},
                "Transitions": {"NextAction": "fantasma"},
            },
            {
                "Identifier": "b2",
                "Type": "UpdateContactAttributes",
                "Parameters": {},
                "Transitions": {},
            },
        ],
    }
    arq = pasta_flows / "SD-Teste.json"
    arq.write_text(json.dumps(flow_invalido), encoding="utf-8")

    erros = vf.validar_flow_individual(arq)
    texto = "\n".join(erros)
    assert "Version deve ser '2019-10-30'" in texto
    assert "StartAction 'nao-existe' não existe" in texto
    assert "destino inexistente 'fantasma'" in texto
    assert "não possui porta Errors" in texto
    assert "não possui saída" in texto


def test_regras_especificas_entrada_transbordo_e_lex(tmp_path: Path) -> None:
    # Entrada principal adulterada
    entrada_real = json.loads(
        (vf.PASTA_FLOWS_PADRAO / "SD-Entrada-Principal.json").read_text(encoding="utf-8")
    )
    adulterada = copy.deepcopy(entrada_real)
    adulterada["Actions"][0]["Parameters"]["FlowLoggingBehavior"] = "Disabled"
    adulterada["Actions"][1]["Parameters"]["TextToSpeechVoice"] = "Ricardo"
    erros_ent = vf.validar_regras_entrada_principal(adulterada)
    assert any("Enabled" in e for e in erros_ent)
    assert any("Camila" in e for e in erros_ent)

    # Transbordo sem uma das filas
    trans_real = json.loads(
        (vf.PASTA_FLOWS_PADRAO / "SD-Transbordo-N1.json").read_text(encoding="utf-8")
    )
    trans_adult = copy.deepcopy(trans_real)
    trans_adult["Actions"][2]["Transitions"]["Conditions"].pop(0)
    erros_tr = vf.validar_regras_transbordo(trans_adult)
    assert any("PRIORITARIA_P1" in e for e in erros_tr)

    # Lex inválido
    pasta_lex = tmp_path / "lex"
    pasta_lex.mkdir()
    (pasta_lex / "slot-types.json").write_text('{"localeId": "en_US"}', encoding="utf-8")
    (pasta_lex / "bot-export.json").write_text(
        json.dumps(
            {
                "bot": {
                    "botLocales": [
                        {
                            "localeId": "pt_BR",
                            "voiceSettings": {"voiceId": "Vitoria", "engine": "standard"},
                            "intents": [{"intentName": "PasswordReset"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    erros_lex = vf.validar_lex(pasta_lex)
    assert len(erros_lex) == 3


def test_cli_validar_flows_retorna_1_e_2(tmp_path: Path) -> None:
    assert vf.main(["--flows", str(tmp_path / "nao_existe")]) == 1

    pasta = tmp_path / "flows"
    pasta.mkdir()
    for i in range(3):
        (pasta / f"f{i}.json").write_text("{corrompido", encoding="utf-8")
    assert vf.main(["--flows", str(pasta)]) == 2


def test_sanitizar_export_remove_arns_contas_e_urls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prefixo_inst = f"arn:aws:connect:us-east-1:{CONTA_FALSA}:instance/{UUID_FALSO_1}"
    bruto = (
        f'{{"queue": "{prefixo_inst}/queue/{UUID_FALSO_2}",\n'
        f' "flow": "{prefixo_inst}/contact-flow/{UUID_FALSO_2}",\n'
        f' "hours": "{prefixo_inst}/operating-hours/{UUID_FALSO_2}",\n'
        f' "lex": "arn:aws:lex:us-east-1:{CONTA_FALSA}:bot-alias/ABCDEFGHIJ/KLMNOPQRST",\n'
        f' "wisdom": "arn:aws:wisdom:us-east-1:{CONTA_FALSA}:assistant/{UUID_FALSO_1}",\n'
        f' "lambda": "arn:aws:lambda:us-east-1:{CONTA_FALSA}:function:sd-fulfillment",\n'
        f' "role": "arn:aws:iam::{CONTA_FALSA}:role/MinhaRole",\n'
        f' "url": "https://empresa-real-123.my.connect.aws/ccp-v2"}}'
    )
    arq_in = tmp_path / "bruto.json"
    arq_out = tmp_path / "limpo.json"
    arq_in.write_text(bruto, encoding="utf-8")

    assert se.main([str(arq_in), "-o", str(arq_out)]) == 0
    assert "[SANITIZAR] OK" in capsys.readouterr().out

    texto_limpo = arq_out.read_text(encoding="utf-8")
    assert CONTA_FALSA not in texto_limpo
    assert UUID_FALSO_1 not in texto_limpo
    assert "empresa-real-123" not in texto_limpo
    assert vs.analisar_texto(texto_limpo, "limpo.json") == []

    assert se.main([str(tmp_path / "inexistente.json")]) == 2
