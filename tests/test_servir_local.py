"""Testes do servidor local do simulador: config, cenários guiados na Lambda real e API HTTP."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

import servir_local as sl

RAIZ = Path(__file__).resolve().parent.parent


def _slot(valor: str) -> dict[str, Any]:
    return {
        "shape": "Scalar",
        "value": {"originalValue": valor, "interpretedValue": valor, "resolvedValues": [valor]},
    }


def _turno(
    sessao: dict[str, Any], intencao: str, texto: str, slots: dict[str, Any] | None = None
) -> dict[str, Any]:
    evento = {
        "sessionId": "t",
        "inputTranscript": texto,
        "inputMode": "Text",
        "sessionState": {
            "sessionAttributes": sessao.get("attrs", {}),
            "intent": {
                "name": intencao,
                "slots": slots or sessao.get("slots", {}),
                "state": "InProgress",
            },
        },
    }
    resp = sl.invocar_lambda(evento)
    estado = resp["sessionState"]
    sessao["attrs"] = estado["sessionAttributes"]
    sessao["slots"] = estado["intent"]["slots"]
    return resp


def test_config_vem_dos_arquivos_versionados() -> None:
    cfg = sl.carregar_config_simulacao()
    recursos = yaml.safe_load((RAIZ / "connect" / "recursos.yaml").read_text(encoding="utf-8"))
    assert {f["nome"] for f in cfg["filas"].values()} == {f["nome"] for f in recursos["filas"]}
    assert cfg["roteamento"]["PasswordReset"] == "SEGURANCA"
    assert cfg["roteamento"]["NetworkIssue"] == "REDES"
    assert cfg["roteamento"]["HardwareRequest"] == "HARDWARE"
    assert cfg["roteamento"]["FalarComAtendente"] == "GERAL_N1"
    assert cfg["roteamento"]["P1"] == "PRIORITARIA_P1"
    nomes = {i["nome"] for i in cfg["intents"]}
    assert {"PasswordReset", "NetworkIssue", "HardwareRequest"} <= nomes
    assert cfg["metricas"]["FCR"]["meta_percentual"] == 70
    assert cfg["contact_lens"]["regras"]


def test_password_reset_elicita_matricula_e_pin_e_roteia_para_seguranca() -> None:
    s: dict[str, Any] = {}
    r1 = _turno(s, "PasswordReset", "esqueci minha senha")
    assert r1["sessionState"]["dialogAction"]["slotToElicit"] == "Matricula"
    r2 = _turno(s, "PasswordReset", "NT1001", {"Matricula": _slot("NT1001")})
    assert r2["sessionState"]["dialogAction"]["slotToElicit"] == "PinVerificacao"
    slots = dict(s["slots"], PinVerificacao=_slot("4821"))
    r3 = _turno(s, "PasswordReset", "4821", slots)
    attrs = r3["sessionState"]["sessionAttributes"]
    assert r3["flow"]["encerrado"] is True
    assert attrs["sd_fila_destino"] == "SEGURANCA"
    assert attrs["sd_identidade_validada"] == "true"
    caso = r3["flow"]["caso"]
    assert caso["campos"]["sd_prioridade"] == attrs["sd_prioridade"]
    assert caso["case_id"].startswith("case-sim-")


def test_network_issue_filial_com_incidente_roteia_para_redes() -> None:
    s: dict[str, Any] = {}
    _turno(s, "NetworkIssue", "estou sem internet")
    r = _turno(s, "NetworkIssue", "NT1011 toda a filial esta sem internet")
    attrs = r["sessionState"]["sessionAttributes"]
    assert attrs["sd_fila_destino"] == "REDES"
    assert attrs["sd_incidente_vinculado"] == "INC-0001"
    assert r["flow"]["caso"]["campos"]["sd_categoria"] == "REDE_CONECTIVIDADE"


def test_hardware_com_estoque_e_resolvido_pelo_bot_com_case() -> None:
    s: dict[str, Any] = {}
    _turno(
        s,
        "HardwareRequest",
        "quero solicitar um headset",
        {"Equipamento": _slot("HEADSET_USB")},
    )
    r = _turno(s, "HardwareRequest", "NT1001")
    attrs = r["sessionState"]["sessionAttributes"]
    assert attrs["sd_resolvido_bot"] == "true"
    assert attrs["sd_fila_destino"] == "HARDWARE"
    assert r["flow"]["caso"]["case_id"] == attrs["sd_caso_id"]


def test_emergencia_vai_para_fila_prioritaria_p1() -> None:
    s: dict[str, Any] = {}
    r = _turno(s, "FallbackIntent", "NT1002 cliquei em um link suspeito de phishing, urgente")
    attrs = r["sessionState"]["sessionAttributes"]
    assert attrs["sd_prioridade"] == "P1"
    assert attrs["sd_fila_destino"] == "PRIORITARIA_P1"
    assert attrs["sd_resolvido_bot"] == "false"


def test_consulta_de_protocolo_resolve_sem_case() -> None:
    s: dict[str, Any] = {}
    r = _turno(s, "ConsultarStatusChamado", "consultar protocolo SD-20261115-4F9A2C")
    attrs = r["sessionState"]["sessionAttributes"]
    assert attrs["sd_resolvido_bot"] == "true"
    assert "caso" not in r["flow"]


def test_transbordo_direto_vai_para_geral_n1() -> None:
    s: dict[str, Any] = {}
    r = _turno(s, "FalarComAtendente", "quero falar com um atendente")
    assert r["sessionState"]["sessionAttributes"]["sd_fila_destino"] == "GERAL_N1"
    assert "caso" not in r["flow"]  # transbordo direto não gera protocolo nem Case


@pytest.fixture
def servidor(tmp_path: Path) -> Iterator[str]:
    (tmp_path / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    srv = sl.criar_servidor(0, tmp_path)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _post(url: str, corpo: bytes) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, data=corpo, method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_api_http_config_lex_e_erros(servidor: str) -> None:
    with urllib.request.urlopen(f"{servidor}/api/config") as resp:  # noqa: S310
        assert resp.headers["Cache-Control"].startswith("no-store")
        assert "filas" in json.loads(resp.read())
    with urllib.request.urlopen(f"{servidor}/") as resp:  # noqa: S310
        assert resp.headers["Cache-Control"].startswith("no-store")
        assert b"ok" in resp.read()

    evento = {
        "sessionId": "x",
        "inputTranscript": "quero falar com um atendente",
        "sessionState": {"intent": {"name": "FalarComAtendente", "slots": {}}},
    }
    status, corpo = _post(f"{servidor}/api/lex", json.dumps(evento).encode())
    assert status == 200 and corpo["flow"]["encerrado"] is True

    assert _post(f"{servidor}/api/lex", b"{nao-json")[0] == 400
    assert _post(f"{servidor}/api/lex", b"[1]")[0] == 400
    assert _post(f"{servidor}/api/lex", b"")[0] == 413
    assert _post(f"{servidor}/api/outra", b"{}")[0] == 404
