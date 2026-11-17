#!/usr/bin/env python3
"""Validação estrutural, referencial e de casos de borda do dataset Service Desk.

Verifica:
1. Conformidade com o JSON Schema (Draft 2020-12) em ``data/schema/service_desk.schema.json``.
2. Unicidade de chaves primárias (unidades, matrículas, e-mails, itens de catálogo,
   incidentes e protocolos de chamados).
3. Integridade referencial entre colaboradores, unidades, catálogo, incidentes e chamados.
4. Presença obrigatória dos casos de borda pedagógicos exigidos pelo Case 2:
   - colaborador INATIVO (desligado) e colaborador BLOQUEADO;
   - colaboradores homônimos (mesmo primeiro nome + último sobrenome) para desambiguação;
   - colaborador VIP da Diretoria;
   - unidade sem técnico presencial (0 técnicos) e unidade com apenas 1 técnico;
   - item de catálogo sem estoque (0), item com alternativa sugerida e item que requer aprovação;
   - chamado resolvido, em atendimento, aguardando estoque, aguardando aprovação e cancelado;
   - 5 artigos Markdown na pasta ``kb/`` com cabeçalho e seções mínimas.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
CAMINHO_DATASET_PADRAO = RAIZ_PADRAO / "data" / "service_desk.json"
CAMINHO_SCHEMA_PADRAO = RAIZ_PADRAO / "data" / "schema" / "service_desk.schema.json"
PASTA_KB_PADRAO = RAIZ_PADRAO / "kb"


def carregar_json(caminho: Path) -> dict[str, Any]:
    """Lê um arquivo JSON UTF-8 e garante que a raiz é um objeto."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError(f"O arquivo {caminho} deve conter um objeto JSON na raiz.")
    return dados


def validar_schema(dados: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Valida ``dados`` contra ``schema`` usando JSON Schema Draft 2020-12."""
    validador = Draft202012Validator(schema)
    erros: list[str] = []
    for erro in sorted(validador.iter_errors(dados), key=lambda e: list(e.absolute_path)):
        caminho = ".".join(str(p) for p in erro.absolute_path) or "<raiz>"
        erros.append(f"[SCHEMA] {caminho}: {erro.message}")
    return erros


def _duplicados(valores: list[str]) -> list[str]:
    contagem = Counter(valores)
    return sorted(k for k, n in contagem.items() if n > 1)


def _chave_homonimo(nome_completo: str) -> str:
    partes = [p.lower() for p in nome_completo.split() if p]
    return f"{partes[0]} {partes[-1]}" if len(partes) >= 2 else nome_completo.lower()


def validar_unicidade(dados: dict[str, Any]) -> list[str]:
    """Checa chaves únicas nas cinco coleções principais."""
    erros: list[str] = []
    colecoes = (
        ("unidades.codigo", [u["codigo"] for u in dados.get("unidades", [])]),
        ("colaboradores.matricula", [c["matricula"] for c in dados.get("colaboradores", [])]),
        ("colaboradores.email", [c["email"] for c in dados.get("colaboradores", [])]),
        ("catalogo_hardware.codigo", [i["codigo"] for i in dados.get("catalogo_hardware", [])]),
        ("incidentes_ativos.id", [inc["id"] for inc in dados.get("incidentes_ativos", [])]),
        ("chamados.protocolo", [ch["protocolo"] for ch in dados.get("chamados", [])]),
    )
    for rotulo, lista in colecoes:
        dups = _duplicados(lista)
        if dups:
            erros.append(f"[UNICIDADE] Valores duplicados em {rotulo}: {', '.join(dups)}")
    return erros


def _validar_chamados(
    chamados: list[dict[str, Any]], set_matriculas: set[str], set_catalogo: set[str]
) -> list[str]:
    erros: list[str] = []
    for ch in chamados:
        if ch["matricula"] not in set_matriculas:
            erros.append(
                f"[REFERENCIA] Chamado {ch['protocolo']} referencia matrícula "
                f"inexistente '{ch['matricula']}'."
            )
        eq = ch.get("equipamento")
        if eq is not None and eq not in set_catalogo:
            erros.append(
                f"[REFERENCIA] Chamado {ch['protocolo']} referencia equipamento inexistente '{eq}'."
            )
        if ch["intencao"] == "HardwareRequest" and not eq:
            erros.append(
                f"[COERENCIA] Chamado {ch['protocolo']} (HardwareRequest) "
                "deve informar equipamento."
            )
    return erros


def validar_unicidade_e_referencias(dados: dict[str, Any]) -> list[str]:
    """Checa chaves únicas e chaves estrangeiras entre coleções."""
    erros = validar_unicidade(dados)
    unidades = dados.get("unidades", [])
    colaboradores = dados.get("colaboradores", [])
    catalogo = dados.get("catalogo_hardware", [])
    incidentes = dados.get("incidentes_ativos", [])

    set_unidades = {u["codigo"] for u in unidades}
    set_matriculas = {c["matricula"] for c in colaboradores}
    set_catalogo = {i["codigo"] for i in catalogo}

    for u in unidades:
        if (u["tecnicos_presenciais"] > 0) != bool(u["suporte_local"]):
            erros.append(
                f"[COERENCIA] Unidade {u['codigo']} tem tecnicos_presenciais="
                f"{u['tecnicos_presenciais']} incompatível com suporte_local={u['suporte_local']}."
            )

    for col in colaboradores:
        if col["unidade"] not in set_unidades:
            erros.append(
                f"[REFERENCIA] Colaborador {col['matricula']} referencia unidade "
                f"inexistente '{col['unidade']}'."
            )
        if not col["nome_completo"].startswith(col["primeiro_nome"]):
            erros.append(
                f"[COERENCIA] Colaborador {col['matricula']} tem primeiro_nome "
                f"'{col['primeiro_nome']}' divergente de '{col['nome_completo']}'."
            )

    for item in catalogo:
        alt = item.get("alternativa_sugerida")
        if alt is not None and alt not in set_catalogo:
            erros.append(
                f"[REFERENCIA] Item {item['codigo']} sugere alternativa inexistente '{alt}'."
            )
        if alt == item["codigo"]:
            erros.append(
                f"[COERENCIA] Item {item['codigo']} não pode sugerir a si mesmo como alternativa."
            )

    for inc in incidentes:
        for uf_cod in inc["unidades_afetadas"]:
            if uf_cod not in set_unidades:
                erros.append(
                    f"[REFERENCIA] Incidente {inc['id']} referencia unidade inexistente '{uf_cod}'."
                )

    erros.extend(_validar_chamados(dados.get("chamados", []), set_matriculas, set_catalogo))
    return erros


def validar_casos_de_borda(dados: dict[str, Any]) -> list[str]:
    """Garante que todos os casos de borda pedagógicos estão presentes no dataset."""
    erros: list[str] = []
    unidades = dados.get("unidades", [])
    colaboradores = dados.get("colaboradores", [])
    catalogo = dados.get("catalogo_hardware", [])
    chamados = dados.get("chamados", [])

    if not any(u["tecnicos_presenciais"] == 0 for u in unidades):
        erros.append("[BORDA] Falta unidade sem técnico presencial (tecnicos_presenciais == 0).")
    if not any(u["tecnicos_presenciais"] == 1 for u in unidades):
        erros.append("[BORDA] Falta unidade com apenas 1 técnico presencial.")

    status_contas = {c["status_conta"] for c in colaboradores}
    for st in ("ATIVO", "BLOQUEADO", "INATIVO"):
        if st not in status_contas:
            erros.append(f"[BORDA] Falta colaborador com status_conta == '{st}'.")

    if not any(c["vip_diretoria"] for c in colaboradores):
        erros.append("[BORDA] Falta colaborador VIP da Diretoria (vip_diretoria == true).")

    chaves_nomes = [_chave_homonimo(c["nome_completo"]) for c in colaboradores]
    if not _duplicados(chaves_nomes):
        erros.append(
            "[BORDA] Falta par de colaboradores homônimos (mesmo primeiro nome e último sobrenome)."
        )

    if not any(i["estoque_disponivel"] == 0 for i in catalogo):
        erros.append("[BORDA] Falta item de catálogo com estoque_disponivel == 0.")
    if not any(i["requer_aprovacao_gestor"] for i in catalogo):
        erros.append("[BORDA] Falta item de catálogo que requer aprovação do gestor.")
    if not any(i.get("alternativa_sugerida") for i in catalogo):
        erros.append("[BORDA] Falta item de catálogo com alternativa_sugerida preenchida.")

    status_chamados = {ch["status"] for ch in chamados}
    for st_ch in (
        "ABERTO",
        "EM_ATENDIMENTO",
        "AGUARDANDO_APROVACAO",
        "AGUARDANDO_ESTOQUE",
        "ENVIADO_LOGISTICA",
        "RESOLVIDO",
        "CANCELADO",
    ):
        if st_ch not in status_chamados:
            erros.append(f"[BORDA] Falta chamado exemplificando o status '{st_ch}'.")

    return erros


def validar_kb(pasta_kb: Path) -> list[str]:
    """Garante que existem pelo menos 5 artigos Markdown íntegros na pasta ``kb/``."""
    if not pasta_kb.is_dir():
        return [f"[KB] Pasta de base de conhecimento não encontrada: {pasta_kb.as_posix()}"]

    arquivos = sorted(pasta_kb.glob("KB-*.md"))
    erros: list[str] = []
    if len(arquivos) < 5:
        erros.append(f"[KB] Esperados pelo menos 5 artigos KB-*.md, encontrados {len(arquivos)}.")

    for arq in arquivos:
        texto = arq.read_text(encoding="utf-8").strip()
        if not texto.startswith("# KB-"):
            erros.append(f"[KB] {arq.name}: deve iniciar com título '# KB-...'.")
        if "## " not in texto:
            erros.append(f"[KB] {arq.name}: deve possuir pelo menos uma seção '## '.")
    return erros


def validar_tudo(
    caminho_dataset: Path = CAMINHO_DATASET_PADRAO,
    caminho_schema: Path = CAMINHO_SCHEMA_PADRAO,
    pasta_kb: Path | None = PASTA_KB_PADRAO,
) -> list[str]:
    """Executa todas as validações e devolve a lista consolidada de erros."""
    dados = carregar_json(caminho_dataset)
    schema = carregar_json(caminho_schema)

    erros = validar_schema(dados, schema)
    if not erros:
        erros.extend(validar_unicidade_e_referencias(dados))
        erros.extend(validar_casos_de_borda(dados))
    if pasta_kb is not None:
        erros.extend(validar_kb(pasta_kb))
    return erros


def _configurar_saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    parser = argparse.ArgumentParser(
        description="Valida o dataset simulado e os artigos de KB do NuvemTech Service Desk."
    )
    parser.add_argument(
        "--dataset", type=Path, default=CAMINHO_DATASET_PADRAO, help="Caminho do service_desk.json"
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=CAMINHO_SCHEMA_PADRAO,
        help="Caminho do service_desk.schema.json",
    )
    parser.add_argument(
        "--kb", type=Path, default=PASTA_KB_PADRAO, help="Pasta com os artigos Markdown da KB"
    )
    parser.add_argument(
        "--sem-kb", action="store_true", help="Valida apenas o dataset JSON (ignora pasta kb/)"
    )
    args = parser.parse_args(argv)

    try:
        erros = validar_tudo(
            caminho_dataset=args.dataset,
            caminho_schema=args.schema,
            pasta_kb=None if args.sem_kb else args.kb,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[DATASET] ERRO de leitura/formato: {exc}", file=sys.stderr)
        return 2

    if erros:
        print(f"[DATASET] FALHA - {len(erros)} inconsistência(s) encontrada(s):")
        for erro in erros:
            print(f"  - {erro}")
        return 1

    dados = carregar_json(args.dataset)
    print(
        "[DATASET] OK - "
        f"{len(dados['colaboradores'])} colaboradores, "
        f"{len(dados['unidades'])} unidades, "
        f"{len(dados['catalogo_hardware'])} itens de catálogo, "
        f"{len(dados['incidentes_ativos'])} incidentes ativos e "
        f"{len(dados['chamados'])} chamados validados com sucesso."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
