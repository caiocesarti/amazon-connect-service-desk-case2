"""Testes unitários do validador de dataset e base de conhecimento (F1)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import validar_dataset as vd


@pytest.fixture
def dados_validos() -> dict:
    return vd.carregar_json(vd.CAMINHO_DATASET_PADRAO)


@pytest.fixture
def schema_valido() -> dict:
    return vd.carregar_json(vd.CAMINHO_SCHEMA_PADRAO)


def test_dataset_oficial_e_kb_estao_integros() -> None:
    assert vd.validar_tudo() == []


def test_cli_dataset_oficial_retorna_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert vd.main([]) == 0
    saida = capsys.readouterr().out
    assert "[DATASET] OK" in saida
    assert "30 colaboradores" in saida


def test_carregar_json_rejeita_raiz_nao_objeto(tmp_path: Path) -> None:
    arq = tmp_path / "lista.json"
    arq.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="objeto JSON"):
        vd.carregar_json(arq)


def test_schema_detecta_matricula_invalida(dados_validos: dict, schema_valido: dict) -> None:
    copia = copy.deepcopy(dados_validos)
    copia["colaboradores"][0]["matricula"] = "INVALIDA"
    erros = vd.validar_schema(copia, schema_valido)
    assert any("[SCHEMA]" in e and "matricula" in e for e in erros)


def test_detecta_duplicidade_e_referencia_quebrada(dados_validos: dict) -> None:
    copia = copy.deepcopy(dados_validos)
    copia["colaboradores"][1]["matricula"] = copia["colaboradores"][0]["matricula"]
    copia["colaboradores"][2]["unidade"] = "XXX"
    copia["colaboradores"][3]["primeiro_nome"] = "Zelda"
    copia["unidades"][0]["suporte_local"] = False
    copia["catalogo_hardware"][0]["alternativa_sugerida"] = "NAO_EXISTE"
    copia["catalogo_hardware"][1]["alternativa_sugerida"] = copia["catalogo_hardware"][1]["codigo"]
    copia["incidentes_ativos"][0]["unidades_afetadas"] = ["ZZZ"]
    copia["chamados"][0]["matricula"] = "NT9999"
    copia["chamados"][0]["equipamento"] = "ITEM_FANTASMA"
    copia["chamados"][3]["equipamento"] = None

    erros = vd.validar_unicidade_e_referencias(copia)
    texto = "\n".join(erros)
    assert "[UNICIDADE]" in texto
    assert "unidade inexistente 'XXX'" in texto
    assert "divergente" in texto
    assert "incompatível com suporte_local" in texto
    assert "alternativa inexistente 'NAO_EXISTE'" in texto
    assert "não pode sugerir a si mesmo" in texto
    assert "unidade inexistente 'ZZZ'" in texto
    assert "matrícula inexistente 'NT9999'" in texto
    assert "equipamento inexistente 'ITEM_FANTASMA'" in texto
    assert "(HardwareRequest) deve informar equipamento" in texto


def test_detecta_ausencia_de_casos_de_borda(dados_validos: dict) -> None:
    copia = copy.deepcopy(dados_validos)
    for u in copia["unidades"]:
        u["tecnicos_presenciais"] = 2
        u["suporte_local"] = True
    for idx, c in enumerate(copia["colaboradores"]):
        c["status_conta"] = "ATIVO"
        c["vip_diretoria"] = False
        c["nome_completo"] = f"Pessoa{idx} Sobrenome{idx}"
        c["primeiro_nome"] = f"Pessoa{idx}"
    for item in copia["catalogo_hardware"]:
        item["estoque_disponivel"] = 5
        item["requer_aprovacao_gestor"] = False
        item["alternativa_sugerida"] = None
    for ch in copia["chamados"]:
        ch["status"] = "ABERTO"

    erros = vd.validar_casos_de_borda(copia)
    texto = "\n".join(erros)
    assert "tecnicos_presenciais == 0" in texto
    assert "apenas 1 técnico" in texto
    assert "BLOQUEADO" in texto and "INATIVO" in texto
    assert "VIP da Diretoria" in texto
    assert "homônimos" in texto
    assert "estoque_disponivel == 0" in texto
    assert "aprovação do gestor" in texto
    assert "alternativa_sugerida" in texto
    assert "CANCELADO" in texto


def test_validar_kb_detecta_pasta_inexistente_e_artigo_incompleto(tmp_path: Path) -> None:
    assert "[KB] Pasta" in vd.validar_kb(tmp_path / "nao_existe")[0]

    pasta = tmp_path / "kb"
    pasta.mkdir()
    (pasta / "KB-001-teste.md").write_text("Sem titulo padrao", encoding="utf-8")
    erros = vd.validar_kb(pasta)
    assert len(erros) == 3


def test_cli_retorna_1_quando_ha_erros_e_2_quando_json_invalido(
    tmp_path: Path, dados_validos: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    copia = copy.deepcopy(dados_validos)
    copia["colaboradores"][0]["matricula"] = "ERRADA"
    arq_ruim = tmp_path / "ruim.json"
    arq_ruim.write_text(json.dumps(copia), encoding="utf-8")

    assert vd.main(["--dataset", str(arq_ruim), "--sem-kb"]) == 1
    assert "[DATASET] FALHA" in capsys.readouterr().out

    arq_corrompido = tmp_path / "corrompido.json"
    arq_corrompido.write_text("{invalido", encoding="utf-8")
    assert vd.main(["--dataset", str(arq_corrompido), "--sem-kb"]) == 2
