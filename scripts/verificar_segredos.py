#!/usr/bin/env python3
"""Auditoria Zero-Leak do repositório NuvemTech Service Desk.

Detecta segredos e identificadores reais (AWS, Vercel, Amazon Connect, GitHub)
antes que sejam versionados. No lugar de valores reais, use os placeholders
padronizados do projeto:

    000000000000 | <ACCOUNT_ID> | <REGION> | <INSTANCE_ALIAS> | <WIDGET_ID>

Modos de uso:
    python scripts/verificar_segredos.py               # versionados + novos não ignorados
    python scripts/verificar_segredos.py --staged      # apenas o conteúdo do stage (pre-commit)
    python scripts/verificar_segredos.py arq1 pasta2   # caminhos específicos
    python scripts/verificar_segredos.py --json        # saída estruturada (CI)

Supressão pontual (sempre justificada em code review): inclua na mesma linha
``zero-leak:allow=ID_DA_REGRA``. Regras de credenciais NÃO aceitam supressão.

Códigos de saída: 0 = limpo | 1 = achados | 2 = erro de execução.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
CONTA_PLACEHOLDER = "000000000000"
TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024
BYTES_SONDA_BINARIO = 8192
DIRETORIOS_IGNORADOS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "dist",
}

ORIENTACAO = (
    "Substitua os valores por placeholders (000000000000, <ACCOUNT_ID>, <REGION>, "
    "<INSTANCE_ALIAS>, <WIDGET_ID>) ou mova-os para arquivos *.local.* / .env (ignorados). "
    "Se uma credencial real foi exposta, REVOGUE/ROTACIONE imediatamente: "
    "remover do commit não basta."
)

# --------------------------------------------------------------------------- #
# Placeholders e heurísticas
# --------------------------------------------------------------------------- #
_RE_PLACEHOLDER = re.compile(
    r"""^(?:
        <[A-Za-z0-9_\-]+>               # <ACCOUNT_ID>, <WIDGET_ID>
      | \$\{\{?[^}]+\}?\}               # ${VAR} ou ${{ secrets.X }}
      | \{\{[^}]+\}\}                   # {{ var }}
      | 0{12}                           # 000000000000
      | [xX*]{4,}                       # xxxx / ****
      | changeme | change-me | placeholder
      | (?:your|seu|sua)[-_].*          # your-token, seu_token
    )$""",
    re.VERBOSE | re.IGNORECASE,
)
_RE_IDENTIFICADOR = re.compile(r"^[A-Za-z_]+$")  # CONSTANTE, CamelCase, snake
_RE_SLUG = re.compile(r"^[a-z0-9]+(?:[-_.][a-z0-9]+)+$")  # sd-kb-artigos-v2
_SIMBOLOS = set("/+=!@#$%^&*")


def eh_placeholder(valor: str) -> bool:
    """True quando o valor é vazio ou um placeholder aceito pela política."""
    v = valor.strip().strip("'\"")
    return v == "" or bool(_RE_PLACEHOLDER.match(v))


def parece_segredo(valor: str) -> bool:
    """Heurística para valores literais atribuídos a chaves sensíveis."""
    v = valor.strip()
    if eh_placeholder(v) or _RE_IDENTIFICADOR.match(v) or _RE_SLUG.match(v):
        return False
    tem_digito = any(c.isdigit() for c in v)
    tem_letra = any(c.isalpha() for c in v)
    tem_simbolo = any(c in _SIMBOLOS for c in v)
    return (tem_digito and tem_letra) or (tem_simbolo and len(v) >= 16)


def mascarar(valor: str) -> str:
    """Nunca exibe o segredo completo: só um prefixo curto e o tamanho."""
    v = valor.strip()
    visivel = 4 if len(v) >= 16 else 2
    return f"{v[:visivel]}{'*' * 8} ({len(v)} chars)"


def _conta_real(valor: str) -> bool:
    return valor != CONTA_PLACEHOLDER


def _nao_placeholder(valor: str) -> bool:
    return not eh_placeholder(valor)


# --------------------------------------------------------------------------- #
# Regras
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Regra:
    id: str
    severidade: str
    descricao: str
    padrao: re.Pattern[str]
    grupo: int = 0
    validar: Callable[[str], bool] | None = None
    permite_supressao: bool = True


@dataclass(frozen=True)
class Achado:
    arquivo: str
    linha: int
    coluna: int
    regra: str
    severidade: str
    descricao: str
    trecho: str  # sempre mascarado


# Ordem importa: regras mais específicas/severas primeiro (vencem sobreposição).
REGRAS: tuple[Regra, ...] = (
    Regra(
        "AWS_ACCESS_KEY_ID",
        "CRITICO",
        "Access Key ID da AWS (AKIA/ASIA/...)",
        re.compile(
            r"(?<![A-Z0-9])((?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)"
            r"[A-Z0-9]{16})(?![A-Z0-9])"
        ),
        1,
        None,
        False,
    ),
    Regra(
        "AWS_SECRET_ACCESS_KEY",
        "CRITICO",
        "Secret Access Key da AWS",
        re.compile(
            r"(?i)(?:aws_?secret_?(?:access_?)?key|secret_?access_?key)[\"']?\s*[:=]\s*"
            r"[\"']?([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])"
        ),
        1,
        _nao_placeholder,
        False,
    ),
    Regra(
        "AWS_SESSION_TOKEN",
        "CRITICO",
        "Session Token temporário da AWS",
        re.compile(r"(?i)aws_?session_?token[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{100,})"),
        1,
        None,
        False,
    ),
    Regra(
        "PRIVATE_KEY",
        "CRITICO",
        "Chave privada (PEM/OpenSSH)",
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
        0,
        None,
        False,
    ),
    Regra(
        "GITHUB_TOKEN",
        "CRITICO",
        "Token pessoal/OAuth do GitHub",
        re.compile(r"(?<![A-Za-z0-9_])(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
        1,
        None,
        False,
    ),
    Regra(
        "VERCEL_TOKEN",
        "CRITICO",
        "Token de API da Vercel",
        re.compile(
            r"(?i)vercel[_-]?(?:api[_-]?|access[_-]?)?token[\"']?\s*[:=]\s*"
            r"[\"']?([A-Za-z0-9_\-]{20,})"
        ),
        1,
        _nao_placeholder,
        False,
    ),
    Regra(
        "AWS_ARN_CONTA_REAL",
        "ALTO",
        "ARN com Account ID real (use 000000000000 ou <ACCOUNT_ID>)",
        re.compile(r"arn:aws[a-z\-]*:[a-z0-9\-]+:[a-z0-9\-]*:(\d{12}):"),
        1,
        _conta_real,
    ),
    Regra(
        "AWS_ACCOUNT_ID",
        "ALTO",
        "Número de 12 dígitos (possível Account ID da AWS)",
        re.compile(r"(?<![\w+.])(\d{12})(?!\w)"),
        1,
        _conta_real,
    ),
    Regra(
        "CONNECT_WIDGET_ID",
        "ALTO",
        "Widget ID real do Amazon Connect (use <WIDGET_ID>)",
        re.compile(r"[\"']amazon_connect[\"']\s*,\s*[\"']([^\"']+)[\"']"),
        1,
        _nao_placeholder,
    ),
    Regra(
        "CONNECT_SNIPPET_ID",
        "ALTO",
        "snippetId real do widget do Amazon Connect",
        re.compile(r"[\"']snippetId[\"']\s*,\s*[\"']([^\"']+)[\"']"),
        1,
        _nao_placeholder,
    ),
    Regra(
        "JWT",
        "ALTO",
        "JSON Web Token literal",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    Regra(
        "SEGREDO_GENERICO",
        "MEDIO",
        "Valor literal atribuído a chave sensível (secret/token/senha)",
        re.compile(
            r"(?i)[\w-]*(?:secret|token|password|passwd|senha|api[_-]?key|private[_-]?key)[\w-]*"
            r"[\"']?\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']"
        ),
        1,
        parece_segredo,
    ),
)
IDS_REGRAS = {r.id for r in REGRAS} | {"ENV_VALOR_REAL", "ARQUIVO_PROIBIDO"}

_RE_ENV = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|SENHA|API_KEY|"
    r"ACCESS_KEY|PRIVATE_KEY|SNIPPET)[A-Za-z0-9_]*)\s*=\s*(.*?)\s*$",
    re.IGNORECASE,
)
_RE_SUPRESSAO = re.compile(r"zero-leak:allow=([A-Z0-9_,]+)")

_PADROES_PROIBIDOS: tuple[tuple[str, str], ...] = (
    ("*.local.*", "Arquivo local (ex.: widget-snippet.local.html) não pode ser versionado"),
    ("*.pem", "Certificado/chave privada"),
    ("*.key", "Chave privada"),
    ("*.p12", "Keystore PKCS#12"),
    ("*.pfx", "Keystore PKCS#12"),
    ("id_rsa*", "Chave SSH"),
    ("id_ed25519*", "Chave SSH"),
    ("credentials", "Arquivo de credenciais da AWS CLI"),
    ("credentials.csv", "Credenciais exportadas do console IAM"),
    ("*accesskeys*.csv", "Access keys exportadas do console IAM"),
)


# --------------------------------------------------------------------------- #
# Análise
# --------------------------------------------------------------------------- #
def _eh_arquivo_env(caminho: str) -> bool:
    nome = PurePosixPath(caminho.replace("\\", "/")).name
    return nome.startswith(".env") or nome.endswith(".env")


def _sobrepoe(span: tuple[int, int], ocupados: list[tuple[int, int]]) -> bool:
    return any(span[0] < fim and inicio < span[1] for inicio, fim in ocupados)


def _suprimidas(linha: str) -> set[str]:
    m = _RE_SUPRESSAO.search(linha)
    return set(m.group(1).split(",")) if m else set()


def analisar_texto(texto: str, caminho: str) -> list[Achado]:
    """Aplica todas as regras de conteúdo a um texto e devolve os achados."""
    achados: list[Achado] = []
    env = _eh_arquivo_env(caminho)

    for num, linha in enumerate(texto.splitlines(), start=1):
        suprimidas = _suprimidas(linha)
        ocupados: list[tuple[int, int]] = []

        for regra in REGRAS:
            for m in regra.padrao.finditer(linha):
                valor = m.group(regra.grupo)
                span = m.span(regra.grupo)
                if regra.validar and not regra.validar(valor):
                    continue
                if _sobrepoe(span, ocupados):
                    continue
                ocupados.append(span)
                if regra.permite_supressao and regra.id in suprimidas:
                    continue
                achados.append(
                    Achado(
                        caminho,
                        num,
                        span[0] + 1,
                        regra.id,
                        regra.severidade,
                        regra.descricao,
                        mascarar(valor),
                    )
                )

        if env and "ENV_VALOR_REAL" not in suprimidas:
            m_env = _RE_ENV.match(linha)
            if m_env:
                valor = re.split(r"\s+#", m_env.group(2), maxsplit=1)[0].strip().strip("'\"")
                span = m_env.span(2)
                if not eh_placeholder(valor) and not _sobrepoe(span, ocupados):
                    achados.append(
                        Achado(
                            caminho,
                            num,
                            span[0] + 1,
                            "ENV_VALOR_REAL",
                            "ALTO",
                            f"Variável sensível '{m_env.group(1)}' com valor real "
                            "(use placeholder)",
                            mascarar(valor),
                        )
                    )
    return achados


def verificar_nome(caminho: str) -> Achado | None:
    """Bloqueia arquivos que nunca devem entrar no repositório."""
    p = PurePosixPath(caminho.replace("\\", "/"))
    nome = p.name.lower()
    pastas = {parte.lower() for parte in p.parts[:-1]}

    motivo: str | None = None
    if ".aws" in pastas:
        motivo = "Configuração local da AWS CLI"
    elif ".vercel" in pastas:
        motivo = "Metadados locais da Vercel (.vercel/) contêm IDs de projeto/org"
    elif nome == ".env" or (nome.startswith(".env.") and nome != ".env.example"):
        motivo = "Arquivo .env com valores reais (versione apenas .env.example)"
    else:
        for padrao, descricao in _PADROES_PROIBIDOS:
            if fnmatch.fnmatch(nome, padrao):
                motivo = descricao
                break

    if motivo is None:
        return None
    return Achado(str(p), 0, 0, "ARQUIVO_PROIBIDO", "CRITICO", motivo, p.name)


def _decodificar(conteudo: bytes) -> str | None:
    """Devolve texto ou None se o arquivo for binário/grande demais."""
    if len(conteudo) > TAMANHO_MAXIMO_BYTES or b"\x00" in conteudo[:BYTES_SONDA_BINARIO]:
        return None
    return conteudo.decode("utf-8", errors="replace")


def auditar(itens: Iterable[tuple[str, Callable[[], bytes]]]) -> tuple[list[Achado], int]:
    """Audita pares (caminho, leitor_de_bytes). Retorna (achados, arquivos_analisados)."""
    achados: list[Achado] = []
    total = 0
    for caminho, ler in itens:
        total += 1
        proibido = verificar_nome(caminho)
        if proibido:
            achados.append(proibido)
        texto = _decodificar(ler())
        if texto is not None:
            achados.extend(analisar_texto(texto, caminho))
    return achados, total


# --------------------------------------------------------------------------- #
# Coleta de arquivos
# --------------------------------------------------------------------------- #
def _git(raiz: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, check=True).stdout


def eh_repositorio_git(raiz: Path) -> bool:
    if shutil.which("git") is None:
        return False
    proc = subprocess.run(
        ["git", "-C", str(raiz), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _dividir_z(saida: bytes) -> list[str]:
    return [p for p in saida.decode("utf-8").split("\0") if p]


def _leitor_disco(caminho: Path) -> Callable[[], bytes]:
    return caminho.read_bytes


def _leitor_staged(topo: Path, nome: str) -> Callable[[], bytes]:
    def _ler() -> bytes:
        return _git(topo, "show", f":{nome}")

    return _ler


def itens_repositorio(raiz: Path) -> Iterator[tuple[str, Callable[[], bytes]]]:
    """Arquivos versionados + novos não ignorados (inclui forçados com add -f)."""
    nomes = _dividir_z(_git(raiz, "ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    for nome in sorted(set(nomes)):
        caminho = raiz / nome
        if caminho.is_file():
            yield nome, _leitor_disco(caminho)


def itens_staged(raiz: Path) -> Iterator[tuple[str, Callable[[], bytes]]]:
    """Conteúdo exatamente como está no índice (o que será commitado)."""
    topo = Path(_git(raiz, "rev-parse", "--show-toplevel").decode("utf-8").strip())
    nomes = _dividir_z(_git(topo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"))
    for nome in nomes:
        yield nome, _leitor_staged(topo, nome)


def itens_caminhos(caminhos: Iterable[str]) -> Iterator[tuple[str, Callable[[], bytes]]]:
    for bruto in caminhos:
        base = Path(bruto)
        if base.is_file():
            yield base.as_posix(), _leitor_disco(base)
            continue
        for pasta, subpastas, arquivos in os.walk(base):
            subpastas[:] = sorted(d for d in subpastas if d not in DIRETORIOS_IGNORADOS)
            for nome in sorted(arquivos):
                caminho = Path(pasta) / nome
                yield caminho.as_posix(), _leitor_disco(caminho)


# --------------------------------------------------------------------------- #
# Relatório e CLI
# --------------------------------------------------------------------------- #
def formatar_relatorio(achados: list[Achado], total: int) -> str:
    if not achados:
        return f"[ZERO-LEAK] OK - {total} arquivo(s) auditado(s), nenhum segredo encontrado."
    arquivos = len({a.arquivo for a in achados})
    linhas = [
        f"[ZERO-LEAK] FALHA - {len(achados)} achado(s) em {arquivos} arquivo(s) "
        f"({total} auditado(s)):"
    ]
    for a in sorted(achados, key=lambda x: (x.arquivo, x.linha, x.coluna)):
        local = a.arquivo if a.linha == 0 else f"{a.arquivo}:{a.linha}:{a.coluna}"
        linhas.append(f"  {a.severidade:<8} {a.regra:<22} {local}")
        linhas.append(f"           {a.descricao} -> {a.trecho}")
    linhas.append("")
    linhas.append(ORIENTACAO)
    return "\n".join(linhas)


def _configurar_saida_utf8() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):  # stream não reconfigurável
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    parser = argparse.ArgumentParser(description="Auditoria Zero-Leak (segredos e IDs reais).")
    parser.add_argument("caminhos", nargs="*", help="Arquivos/pastas específicos (opcional).")
    parser.add_argument("--staged", action="store_true", help="Audita somente o stage do git.")
    parser.add_argument("--json", action="store_true", help="Saída em JSON.")
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO, help="Raiz do repositório.")
    args = parser.parse_args(argv)

    try:
        if args.caminhos:
            itens = itens_caminhos(args.caminhos)
        elif args.staged:
            if not eh_repositorio_git(args.raiz):
                print("[ZERO-LEAK] ERRO - --staged exige um repositório git.", file=sys.stderr)
                return 2
            itens = itens_staged(args.raiz)
        elif eh_repositorio_git(args.raiz):
            itens = itens_repositorio(args.raiz)
        else:
            itens = itens_caminhos([str(args.raiz)])
        achados, total = auditar(itens)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[ZERO-LEAK] ERRO de execução: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not achados,
                    "arquivos_auditados": total,
                    "achados": [asdict(a) for a in achados],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(formatar_relatorio(achados, total))
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
