"""Testes da auditoria Zero-Leak.

Todos os "segredos" são montados em tempo de execução por concatenação, para
que nenhum valor que pareça real exista literalmente no repositório (nem para
o nosso scanner, nem para o gitleaks no CI).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import verificar_segredos as vs

# --------------------------------------------------------------------------- #
# Valores falsos construídos dinamicamente
# --------------------------------------------------------------------------- #
AKIA_FALSA = "AKIA" + "ZQ7X" + "WERTYUIOP234"
ASIA_FALSA = "ASIA" + "ZQ7X" + "WERTYUIOP234"
SECRET_FALSO = "wJalr" + "Q" * 30 + "K7MDE"
CONTA_FALSA = "4111" + "22233344"
GITHUB_FALSO = "ghp" + "_" + "a1B2" * 9
VERCEL_FALSO = "Ab3dEf6hIj" + "9kLm2nOp5qRs8t"
WIDGET_FALSO = "8f2c1a9e" + "-3b4d-4e5f-9a0b-1c2d3e4f5a6b"
SNIPPET_FALSO = "QVFJREFI" + "aGVsbG8gd29ybGQ="
JWT_FALSO = (
    "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTYifQ" + "." + "c2lnbmF0dXJhX2Zha2U"
)


def linha_widget(widget_id: str) -> str:
    """Última linha do snippet oficial, montada sem formar o padrão literal no fonte."""
    return "})(window, document, 'amazon_" + "connect', '" + widget_id + "');"


def linha_snippet_id(snippet_id: str) -> str:
    return "amazon_connect('snippet" + "Id', '" + snippet_id + "');"


def regras(achados: list[vs.Achado]) -> list[str]:
    return [a.regra for a in achados]


# --------------------------------------------------------------------------- #
# Credenciais
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("chave", [AKIA_FALSA, ASIA_FALSA])
def test_detecta_access_key_id(chave: str) -> None:
    achados = vs.analisar_texto(f'aws_key = "{chave}"', "app.py")
    assert "AWS_ACCESS_KEY_ID" in regras(achados)


def test_access_key_dentro_de_palavra_maior_nao_e_falso_positivo() -> None:
    assert vs.analisar_texto(f"X{AKIA_FALSA}9", "app.py") == []


def test_detecta_secret_access_key() -> None:
    achados = vs.analisar_texto(f"aws_secret_access_key = {SECRET_FALSO}", "config.ini")
    assert regras(achados) == ["AWS_SECRET_ACCESS_KEY"]


def test_detecta_chave_privada() -> None:
    cabecalho = "-----BEGIN " + "RSA PRIVATE KEY-----"
    assert regras(vs.analisar_texto(cabecalho, "chave.txt")) == ["PRIVATE_KEY"]


def test_detecta_token_github() -> None:
    assert regras(vs.analisar_texto(f"token: {GITHUB_FALSO}", "ci.yml")) == ["GITHUB_TOKEN"]


def test_detecta_token_vercel_e_aceita_placeholder() -> None:
    assert regras(vs.analisar_texto(f'VERCEL_TOKEN: "{VERCEL_FALSO}"', "deploy.yml")) == [
        "VERCEL_TOKEN"
    ]
    assert vs.analisar_texto("VERCEL_TOKEN: <VERCEL_TOKEN>", "deploy.yml") == []


def test_detecta_jwt() -> None:
    assert regras(vs.analisar_texto(f"Authorization: Bearer {JWT_FALSO}", "x.http")) == ["JWT"]


# --------------------------------------------------------------------------- #
# Account ID e ARNs
# --------------------------------------------------------------------------- #
def test_arn_com_conta_real_gera_um_unico_achado() -> None:
    arn = f"arn:aws:connect:us-east-1:{CONTA_FALSA}:instance/abc"
    assert regras(vs.analisar_texto(arn, "flow.json")) == ["AWS_ARN_CONTA_REAL"]


@pytest.mark.parametrize(
    "arn",
    [
        "arn:aws:connect:us-east-1:000000000000:instance/<INSTANCE_ID>",
        "arn:aws:connect:<REGION>:<ACCOUNT_ID>:instance/<INSTANCE_ID>",
        "arn:aws:lambda:us-east-1:000000000000:function:sd-fulfillment-servicedesk",
    ],
)
def test_arn_com_placeholder_e_aceito(arn: str) -> None:
    assert vs.analisar_texto(arn, "flow.json") == []


def test_conta_em_nome_de_bucket_e_detectada() -> None:
    texto = f"KB_BUCKET=sd-kb-artigos-{CONTA_FALSA}-us-east-1"
    assert regras(vs.analisar_texto(texto, "config.py")) == ["AWS_ACCOUNT_ID"]


@pytest.mark.parametrize(
    "texto",
    [
        "telefone: +551133334444",  # 12 dígitos após '+': telefone, não conta
        "epoch_ms: 1763202468000",  # 13 dígitos
        "valor: 0.123456789012",  # decimal
        "protocolo: SD-20261115-4F9A2C",
    ],
)
def test_numeros_que_nao_sao_conta(texto: str) -> None:
    assert vs.analisar_texto(texto, "dados.json") == []


# --------------------------------------------------------------------------- #
# Widget do Amazon Connect
# --------------------------------------------------------------------------- #
def test_detecta_widget_id_e_snippet_reais() -> None:
    texto = linha_widget(WIDGET_FALSO) + "\n" + linha_snippet_id(SNIPPET_FALSO)
    assert regras(vs.analisar_texto(texto, "index.html")) == [
        "CONNECT_WIDGET_ID",
        "CONNECT_SNIPPET_ID",
    ]


def test_widget_com_placeholders_e_aceito() -> None:
    texto = linha_widget("<WIDGET_ID>") + "\n" + linha_snippet_id("<SNIPPET_ID>")
    assert vs.analisar_texto(texto, "widget-snippet.example.html") == []


# --------------------------------------------------------------------------- #
# Segredo genérico e arquivos .env
# --------------------------------------------------------------------------- #
def test_detecta_senha_literal() -> None:
    texto = '"password": "S3nh@Forte' + '2026!"'
    assert regras(vs.analisar_texto(texto, "config.json")) == ["SEGREDO_GENERICO"]


@pytest.mark.parametrize(
    "texto",
    [
        'GUARDRAIL_SENHA = "SENHA_EXPOSTA"',  # constante/enum
        '"password_intent": "PasswordReset"',  # nome de intenção Lex
        '"token' + '_bucket": "sd-kb-artigos-v2"',  # slug de recurso (concatenado p/ gitleaks)
        'api_key = os.environ["SD_API_KEY_NAME"]',  # leitura de env, não literal
        '"secret": "${{ secrets.VERCEL_TOKEN }}"',  # referência de CI
    ],
)
def test_segredo_generico_sem_falso_positivo(texto: str) -> None:
    assert vs.analisar_texto(texto, "codigo.py") == []


def test_env_com_valor_real_e_placeholders() -> None:
    texto = (
        "DB_PASSWORD=minhasenha\n"
        "VERCEL_TOKEN=<VERCEL_TOKEN>\n"
        "CONNECT_WIDGET_SNIPPET=\n"
        "AWS_REGION=us-east-1\n"
        "SD_API_TOKEN=${SD_API_TOKEN}  # injetado no CI\n"
    )
    achados = vs.analisar_texto(texto, ".env.example")
    assert [(a.regra, a.linha) for a in achados] == [("ENV_VALOR_REAL", 1)]


def test_regra_env_so_vale_para_arquivos_env() -> None:
    assert vs.analisar_texto("DB_PASSWORD=minhasenha", "README.md") == []


# --------------------------------------------------------------------------- #
# Supressão e mascaramento
# --------------------------------------------------------------------------- #
def test_supressao_vale_apenas_para_a_regra_indicada() -> None:
    linha = f"id = {CONTA_FALSA}"
    assert vs.analisar_texto(f"{linha}  # zero-leak:allow=AWS_ACCOUNT_ID", "a.py") == []
    assert regras(vs.analisar_texto(f"{linha}  # zero-leak:allow=JWT", "a.py")) == [
        "AWS_ACCOUNT_ID"
    ]


def test_credenciais_nao_aceitam_supressao() -> None:
    texto = f"{AKIA_FALSA}  # zero-leak:allow=AWS_ACCESS_KEY_ID"
    assert regras(vs.analisar_texto(texto, "a.py")) == ["AWS_ACCESS_KEY_ID"]


def test_relatorio_nunca_exibe_o_segredo_completo() -> None:
    achados = vs.analisar_texto(f"k={AKIA_FALSA}\ns={GITHUB_FALSO}", "a.py")
    relatorio = vs.formatar_relatorio(achados, 1)
    assert AKIA_FALSA not in relatorio
    assert GITHUB_FALSO not in relatorio
    assert "AKIA********" in relatorio


@pytest.mark.parametrize("valor,esperado", [("123456789", "12******** (9 chars)")])
def test_mascarar_valores_curtos(valor: str, esperado: str) -> None:
    assert vs.mascarar(valor) == esperado


# --------------------------------------------------------------------------- #
# Arquivos proibidos
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "caminho",
    [
        ".env",
        ".env.local",
        "landing/widget-snippet.local.html",
        "certs/servidor.pem",
        ".vercel/project.json",
        ".aws/config",
        "downloads/credentials.csv",
        "rootkey_accessKeys.csv",
    ],
)
def test_arquivos_proibidos(caminho: str) -> None:
    achado = vs.verificar_nome(caminho)
    assert achado is not None and achado.regra == "ARQUIVO_PROIBIDO"


@pytest.mark.parametrize(
    "caminho",
    [".env.example", "landing/widget-snippet.example.html", "src/monkey.py", "docs/keys.md"],
)
def test_arquivos_permitidos(caminho: str) -> None:
    assert vs.verificar_nome(caminho) is None


# --------------------------------------------------------------------------- #
# CLI (modo caminhos)
# --------------------------------------------------------------------------- #
def test_cli_pasta_limpa_retorna_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "ok.py").write_text('REGIAO = "us-east-1"\n', encoding="utf-8")
    assert vs.main([str(tmp_path)]) == 0
    assert "OK" in capsys.readouterr().out


def test_cli_pasta_com_segredo_retorna_um_em_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "vazou.py").write_text(f"KEY = '{AKIA_FALSA}'\n", encoding="utf-8")
    assert vs.main([str(tmp_path), "--json"]) == 1
    saida = json.loads(capsys.readouterr().out)
    assert saida["ok"] is False
    assert saida["achados"][0]["regra"] == "AWS_ACCESS_KEY_ID"
    assert AKIA_FALSA not in json.dumps(saida)


def test_cli_ignora_binarios(tmp_path: Path) -> None:
    (tmp_path / "imagem.png").write_bytes(b"\x89PNG\x00\x00" + AKIA_FALSA.encode())
    assert vs.main([str(tmp_path)]) == 0


def test_cli_ignora_diretorios_de_ambiente(tmp_path: Path) -> None:
    pasta = tmp_path / ".venv" / "lib"
    pasta.mkdir(parents=True)
    (pasta / "pacote.py").write_text(f"K='{AKIA_FALSA}'", encoding="utf-8")
    assert vs.main([str(tmp_path)]) == 0


# --------------------------------------------------------------------------- #
# Integração com git
# --------------------------------------------------------------------------- #
requer_git = pytest.mark.skipif(shutil.which("git") is None, reason="git não instalado")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("*.local.*\n.env\n", encoding="utf-8")
    return tmp_path


@requer_git
def test_git_arquivo_local_ignorado_nao_e_auditado(repo: Path) -> None:
    snippet = repo / "widget-snippet.local.html"
    snippet.write_text(linha_widget(WIDGET_FALSO), encoding="utf-8")
    assert vs.main(["--raiz", str(repo)]) == 0


@requer_git
def test_git_arquivo_local_forcado_e_bloqueado(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snippet = repo / "widget-snippet.local.html"
    snippet.write_text(linha_widget(WIDGET_FALSO), encoding="utf-8")
    _git(repo, "add", "-f", snippet.name)
    assert vs.main(["--raiz", str(repo)]) == 1
    saida = capsys.readouterr().out
    assert "ARQUIVO_PROIBIDO" in saida and "CONNECT_WIDGET_ID" in saida


@requer_git
def test_git_staged_audita_o_indice_e_nao_a_copia_de_trabalho(repo: Path) -> None:
    arquivo = repo / "config.py"
    arquivo.write_text(f'CONTA = "{CONTA_FALSA}"\n', encoding="utf-8")
    _git(repo, "add", "config.py")
    arquivo.write_text('CONTA = "000000000000"\n', encoding="utf-8")  # corrigido só no disco
    assert vs.main(["--staged", "--raiz", str(repo)]) == 1
    _git(repo, "add", "config.py")
    assert vs.main(["--staged", "--raiz", str(repo)]) == 0


def test_staged_fora_de_repositorio_retorna_erro(tmp_path: Path) -> None:
    assert vs.main(["--staged", "--raiz", str(tmp_path)]) == 2


# --------------------------------------------------------------------------- #
# Meta-teste: o próprio repositório precisa estar limpo
# --------------------------------------------------------------------------- #
def test_repositorio_atual_esta_limpo(capsys: pytest.CaptureFixture[str]) -> None:
    codigo = vs.main(["--raiz", str(vs.RAIZ_PADRAO)])
    assert codigo == 0, capsys.readouterr().out
