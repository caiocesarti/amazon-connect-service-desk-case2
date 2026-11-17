"""Camada de consulta, normalização de texto e resolução de sinônimos no dataset."""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from config import resolver_caminho_dataset

_RE_ESPACOS = re.compile(r"\s+")
_RE_NAO_ALFANUM = re.compile(r"[^a-z0-9\s_-]")
_RE_MATRICULA = re.compile(r"\b(NT\d{4})\b", re.IGNORECASE)
_RE_PROTOCOLO = re.compile(r"\b(SD-\d{8}-[A-F0-9]{6})\b", re.IGNORECASE)

SINONIMOS_SUBCATEGORIA_REDE: dict[str, tuple[str, ...]] = {
    "VPN": ("vpn", "anyconnect", "tunel", "remoto", "home office", "gateway"),
    "WIFI": ("wifi", "wi-fi", "wireless", "rede sem fio", "ssid", "nuvemtech-corp"),
    "DNS": ("dns", "intranet", "sistema interno", "nao resolve", "nome de dominio"),
    "SEM_INTERNET": (
        "sem internet",
        "internet caiu",
        "nao navega",
        "sem rede",
        "fora do ar",
        "cabo de rede",
        "conexao caiu",
    ),
}

SINONIMOS_IMPACTO: dict[str, tuple[str, ...]] = {
    "UNIDADE": (
        "unidade",
        "predio inteiro",
        "filial inteira",
        "escritorio inteiro",
        "todo o predio",
        "empresa toda",
    ),
    "SETOR": (
        "setor",
        "equipe",
        "meu time",
        "andar inteiro",
        "sala de reuniao",
        "sala de conselho",
        "varias pessoas",
        "todo o setor",
    ),
    "INDIVIDUAL": (
        "individual",
        "so eu",
        "apenas eu",
        "minha maquina",
        "meu computador",
        "so comigo",
    ),
}


def normalizar_texto(texto: str | None) -> str:
    """Remove acentos, converte para minúsculas e colapsa espaços."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    limpo = _RE_NAO_ALFANUM.sub(" ", sem_acento.lower())
    return _RE_ESPACOS.sub(" ", limpo).strip()


@functools.lru_cache(maxsize=4)
def _carregar_dataset_cache(caminho_str: str) -> dict[str, Any]:
    caminho = Path(caminho_str)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError("Dataset inválido: esperado objeto JSON na raiz.")
    return dados


def carregar_dataset(caminho: Path | None = None) -> dict[str, Any]:
    """Carrega o dataset em memória com cache LRU."""
    alvo = caminho or resolver_caminho_dataset()
    return _carregar_dataset_cache(str(alvo.resolve()))


def extrair_matricula(texto: str | None) -> str | None:
    """Extrai uma matrícula no formato ``NTxxxx`` de qualquer texto."""
    if not texto:
        return None
    m = _RE_MATRICULA.search(texto)
    return m.group(1).upper() if m else None


def extrair_protocolo(texto: str | None) -> str | None:
    """Extrai um protocolo no formato ``SD-AAAAMMDD-XXXXXX`` de qualquer texto."""
    if not texto:
        return None
    m = _RE_PROTOCOLO.search(texto)
    return m.group(1).upper() if m else None


def buscar_colaborador_por_matricula(
    matricula: str | None, dados: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Retorna o colaborador correspondente à matrícula exata (case-insensitive)."""
    if not matricula:
        return None
    ds = dados or carregar_dataset()
    alvo = matricula.strip().upper()
    for col in ds.get("colaboradores", []):
        if col["matricula"].upper() == alvo:
            return col
    return None


def buscar_colaboradores_por_nome(
    nome: str | None, dados: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Busca colaboradores por nome completo, primeiro+último nome ou primeiro nome."""
    termo = normalizar_texto(nome)
    if not termo:
        return []
    ds = dados or carregar_dataset()
    colaboradores = ds.get("colaboradores", [])

    exatos = [c for c in colaboradores if normalizar_texto(c["nome_completo"]) == termo]
    if exatos:
        return exatos

    partes_termo = termo.split()
    resultados: list[dict[str, Any]] = []
    for col in colaboradores:
        partes_col = normalizar_texto(col["nome_completo"]).split()
        chave_curta = f"{partes_col[0]} {partes_col[-1]}" if len(partes_col) >= 2 else partes_col[0]
        if termo == chave_curta or all(p in partes_col for p in partes_termo):
            resultados.append(col)
    return resultados


def buscar_unidade(
    codigo_ou_cidade: str | None, dados: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Localiza uma unidade pelo código de 3 letras (ex.: ``REC``) ou pelo nome da cidade."""
    if not codigo_ou_cidade:
        return None
    ds = dados or carregar_dataset()
    bruto = codigo_ou_cidade.strip().upper()
    termo = normalizar_texto(codigo_ou_cidade)
    for u in ds.get("unidades", []):
        if u["codigo"] == bruto or normalizar_texto(u["cidade"]) == termo:
            return u
    return None


def buscar_item_catalogo(
    termo_equipamento: str | None, dados: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Resolve código exato ou sinônimo coloquial para um item do catálogo de hardware."""
    if not termo_equipamento:
        return None
    ds = dados or carregar_dataset()
    bruto = termo_equipamento.strip().upper().replace(" ", "_")
    termo = normalizar_texto(termo_equipamento)

    catalogo = ds.get("catalogo_hardware", [])
    for item in catalogo:
        if item["codigo"] == bruto:
            return item

    for item in catalogo:
        sinonimos_norm = [normalizar_texto(s) for s in item.get("sinonimos", [])]
        if termo in sinonimos_norm or termo == normalizar_texto(item["nome"]):
            return item

    for item in catalogo:
        sinonimos_norm = [normalizar_texto(s) for s in item.get("sinonimos", [])]
        if any(s in termo or termo in s for s in sinonimos_norm if len(s) >= 4):
            return item
    return None


def inferir_subcategoria_rede(texto: str | None) -> str:
    """Classifica o relato de rede em ``VPN``, ``WIFI``, ``DNS`` ou ``SEM_INTERNET``."""
    norm = normalizar_texto(texto)
    if not norm:
        return "SEM_INTERNET"
    bruto = norm.upper()
    if bruto in {"VPN", "WIFI", "DNS", "SEM_INTERNET"}:
        return bruto
    for subcat, palavras in SINONIMOS_SUBCATEGORIA_REDE.items():
        if any(normalizar_texto(p) in norm for p in palavras):
            return subcat
    return "SEM_INTERNET"


def inferir_impacto(texto: str | None) -> str:
    """Classifica o escopo de impacto em ``INDIVIDUAL``, ``SETOR`` ou ``UNIDADE``."""
    norm = normalizar_texto(texto)
    if not norm:
        return "INDIVIDUAL"
    bruto = norm.upper()
    if bruto in {"INDIVIDUAL", "SETOR", "UNIDADE"}:
        return bruto
    for impacto, palavras in SINONIMOS_IMPACTO.items():
        if any(normalizar_texto(p) in norm for p in palavras):
            return impacto
    return "INDIVIDUAL"


def buscar_incidente_ativo(
    unidade: str | None,
    categoria: str | None = None,
    subcategoria: str | None = None,
    dados: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Verifica se há incidente massivo em andamento ou monitoramento para a unidade."""
    if not unidade:
        return None
    ds = dados or carregar_dataset()
    cod_uf = unidade.strip().upper()
    for inc in ds.get("incidentes_ativos", []):
        if inc.get("status") == "RESOLVIDO":
            continue
        if cod_uf not in inc.get("unidades_afetadas", []):
            continue
        if categoria and inc.get("categoria") != categoria:
            continue
        if subcategoria and inc.get("subcategoria") != subcategoria:
            continue
        return inc
    return None


def buscar_chamado_por_protocolo(
    protocolo: str | None, dados: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Localiza um chamado pelo protocolo determinístico ``SD-AAAAMMDD-XXXXXX``."""
    if not protocolo:
        return None
    ds = dados or carregar_dataset()
    alvo = protocolo.strip().upper()
    for ch in ds.get("chamados", []):
        if ch["protocolo"].upper() == alvo:
            return ch
    return None


def listar_chamados_por_matricula(
    matricula: str | None, dados: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Lista todos os chamados de um colaborador ordenados do mais recente ao mais antigo."""
    if not matricula:
        return []
    ds = dados or carregar_dataset()
    alvo = matricula.strip().upper()
    encontrados = [c for c in ds.get("chamados", []) if c["matricula"].upper() == alvo]
    return sorted(encontrados, key=lambda c: c.get("atualizado_em", ""), reverse=True)
