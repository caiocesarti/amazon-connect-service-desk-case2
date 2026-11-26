---
trigger: always_on
description: Padrões de arquitetura, nomenclatura, segurança Zero-Leak e verificação obrigatória do projeto nuvemtech-service-desk.
---

# Padrões do Projeto — NuvemTech Service Desk (Amazon Connect)

Estas regras aplicam-se a todas as tarefas neste repositório (`nuvemtech-service-desk` / `amazon-connect-service-desk-case2`).

## 1. Stack Identificada e Versões Principais

- **Python**: `>=3.12` (alvo oficial `3.12` em `pyproject.toml`, AWS Lambda `python3.12`, Ruff, Mypy e CI).
  - **Runtime de aplicação**: `pyyaml>=6.0` (única dependência externa em `[project].dependencies`).
  - **AWS Lambda (`lambda/sd_fulfillment/`)**: Python 3.12 usando **exclusivamente stdlib + `boto3`** do runtime AWS (zero dependências externas empacotadas).
  - **API Serverless Vercel (`api/index.py`)**: `BaseHTTPRequestHandler` no runtime Python da Vercel, reutilizando `scripts/servir_local.py`.
  - **Scripts de automação (`scripts/*.py`)**: Python `>=3.12` (`argparse`, `pathlib`, `pyyaml>=6.0`, `jsonschema>=4.23`).
- **Front-end (`landing/`)**: HTML5, CSS3 (estilo inspirado em `shadcn/ui`) e JavaScript Vanilla (`"use strict"`, padrão IIFE). Não utiliza Node.js, npm nem frameworks JS; o build estático (`landing/dist/`) é gerado por `scripts/injetar_widget.py`.
- **Infraestrutura e Serviços AWS / Cloud**:
  - **AWS SAM / CloudFormation** (`infra/template.yaml`): Lambda `python3.12` (`arm64`), IAM de menor privilégio (`cases:CreateCase`), retenção CloudWatch Logs de 7 dias.
  - **Amazon Connect**: Contact Flows no schema `2019-10-30` (`connect/flows/*.json`), Connect Cases (`connect/cases/template-chamado.json`), Contact Lens (`connect/contact-lens/regras.json`) e configuração declarativa (`connect/recursos.yaml`).
  - **Amazon Lex V2** (`lex/bot-export.json`, `lex/slot-types.json`): bot `SD-ServiceDesk-Bot`, locale `pt_BR`, voz neural `Camila`, 6 intenções (`PasswordReset`, `NetworkIssue`, `HardwareRequest`, `ConsultarStatusChamado`, `FalarComAtendente`, `FallbackIntent`).
  - **Amazon Q in Connect**: 5 runbooks Markdown em `kb/KB-001` a `kb/KB-005`.
  - **Dataset e Contrato**: `data/service_desk.json` validado por JSON Schema Draft 2020-12 (`data/schema/service_desk.schema.json`).
  - **Vercel** (`vercel.json` v2): `buildCommand: "python3 scripts/injetar_widget.py"`, `outputDirectory: "landing/dist"` e headers rígidos de CSP e segurança.
- **Qualidade e Dev (`requirements-dev.txt`)**: `pytest>=8.3`, `pytest-cov>=5.0`, `jsonschema>=4.23`, `ruff>=0.8`, `mypy>=1.13`, `types-PyYAML>=6.0`, `pre-commit>=4.0`.

## 2. Arquitetura, Organização de Pastas e Nomenclatura

### Estrutura de Pastas
- `lambda/sd_fulfillment/`: núcleo de fulfillment Lex V2 (`handler.py`, `guardrails.py`, `busca.py`, `chamados.py`, `casos.py`, `respostas.py`, `config.py`).
- `api/index.py`: entrypoint serverless da Vercel (`/api/config`, `/api/lex` e entrega de `landing/dist`).
- `connect/`: recursos declarativos (`recursos.yaml`), Contact Flows (`flows/`), template Cases (`cases/`) e regras Contact Lens (`contact-lens/`).
- `lex/`: definição do bot (`bot-export.json`) e slot types (`slot-types.json`).
- `data/`: dataset fictício (`service_desk.json`) e contrato (`schema/service_desk.schema.json`).
- `kb/`: artigos operacionais (`KB-001` a `KB-005`) consumidos pelo Amazon Q in Connect.
- `landing/`: portal estático (`index.html`, `assets/css/`, `assets/js/`, `widget-snippet.example.html`).
- `infra/`: infraestrutura como código (`template.yaml` AWS SAM).
- `scripts/`: automação DevSecOps, validação, sanitização, empacotamento e servidor local.
- `tests/`: suíte Pytest cobrindo `api`, `scripts` e `lambda/sd_fulfillment`.
- `docs/`: documentação técnica (`01-arquitetura.md`, `02-passo-a-passo.md`, `03-testes-e-evidencias.md`), ADRs (`docs/adr/`), diagramas (`assets/`) e evidências sanitizadas (`img/`).

### Convenções Obrigatórias
- **Idioma**: código (módulos, funções, variáveis, docstrings), documentação (`README.md`, `docs/`, `kb/`) e commits em **Português (BR)**. Ao alterar a documentação principal, mantenha `README.en.md` sincronizado quando aplicável.
- **Prefixo `sd_` / `SD-` (ADR-002)**: atributos de contato/sessão usam prefixo `sd_`; flows, filas, bot e recursos usam prefixo `SD-`; protocolos seguem `SD-AAAAMMDD-XXXXXX`.
- **Roteamento por chave lógica (ADR-002)**: a Lambda **nunca** conhece ARNs ou IDs reais da instância Connect. Deve gravar `sd_fila_destino` exclusivamente com o enum em MAIÚSCULAS (`PRIORITARIA_P1`, `SEGURANCA`, `REDES`, `HARDWARE`, `GERAL_N1`), que o flow `SD-Transbordo-N1.json` compara. Qualquer alteração de fila exige atualização sincronizada na Lambda, em `connect/recursos.yaml` e em `connect/flows/SD-Transbordo-N1.json`.
- **Contrato de atributos `sd_*`**: todos os atributos trafegam como `string` (`"true"` / `"false"` para booleanos), conforme `docs/01-arquitetura.md`.
- **Fonte única de verdade no simulador**: `scripts/servir_local.py` e `api/index.py` expõem `/api/config` a partir dos arquivos versionados (`connect/recursos.yaml`, `connect/contact-lens/regras.json`, `lex/bot-export.json`). Não duplique regras de negócio no JavaScript de `landing/assets/js/`.
- **Zero dependências externas na Lambda**: não introduza bibliotecas de terceiros em `lambda/sd_fulfillment/`.
- **Estilo e Tipagem (`.editorconfig`, Ruff e Mypy)**:
  - Codificação UTF-8, quebra de linha LF e linha em branco final.
  - Python: `from __future__ import annotations`, 4 espaços, linha máxima de 100 caracteres, anotações de tipo completas (`mypy` com `check_untyped_defs = true`), aderência às regras Ruff (`E`, `F`, `W`, `I`, `B`, `UP`, `S`, `SIM`, `PL`).
  - Demais arquivos (JSON, YAML, HTML, CSS, JS, Markdown): indentação de 2 espaços.

## 3. Boas Práticas de Segurança (Política Zero-Leak — ADR-001)

- **Nunca expor segredos ou identificadores reais** em código, JSON/YAML, documentação, testes ou commits:
  - Proibido: Account ID AWS real (12 dígitos), ARNs reais, credenciais AWS (`AKIA…` / `ASIA…`, secret keys, session tokens), chaves privadas (`.pem`, `.key`, SSH), tokens (Vercel, GitHub), JWTs, aliases reais `https://<alias>.my.connect.aws`, `widgetId` ou `snippetId` reais.
  - Use sempre os placeholders padronizados: `000000000000`, `<ACCOUNT_ID>`, `<REGION>`, `<INSTANCE_ALIAS>`, `<WIDGET_ID>`, `<INSTANCE_ID>`, `<LEX_BOT_ID>`.
- **Respeitar arquivos sensíveis do `.gitignore`**: nunca versionar nem forçar (`git add -f`) `.env`, `.env.*` (exceto `.env.example`), `*.local.*` (ex.: `landing/widget-snippet.local.html`), `.aws/`, `.vercel/`, `exports/`, `*.raw.json`, `credentials*`, chaves ou `Case_*.pdf`. Não leia nem exponha o conteúdo de arquivos `.env` reais em respostas ou logs.
- **Sanitização de exports**: qualquer export obtido do console AWS (Connect/Lex) deve passar por `python scripts/sanitizar_export.py` antes de entrar no repositório.
- **Supressão e testes**: em testes unitários, construa segredos fictícios por concatenação (sem literais suspeitos). Só use `zero-leak:allow=REGRA` com justificativa clara em code review — e **nunca** para credenciais (regras de credenciais não aceitam supressão).
- **Validação de entradas, Guardrails e Zero-PII**:
  - `guardrails.avaliar_entrada` deve ser sempre executada antes da lógica de negócio em `lambda/sd_fulfillment/handler.py` (`EMERGENCIA`, `INJECAO`, `SENHA_EXPOSTA`, `PII`), e `guardrails.validar_resposta_segura` deve proteger saídas.
  - Logs estruturados (`_registrar_log_estruturado`) e `sd_resumo` devem ser estritamente **Zero-PII** (sem senhas, CPFs ou dados sensíveis).
  - Mantenha a validação de tamanho de payload (`LIMITE_CORPO_BYTES`), parsing JSON seguro e bloqueio de path traversal em `api/index.py` e `scripts/servir_local.py`.
  - Preserve os headers de segurança e a política CSP em `vercel.json`, bem como o bloqueio de crawlers e a cota FinOps em `landing/assets/js/widget-loader.template.js`.

## 4. Verificação Obrigatória Antes de Concluir Tarefas

Antes de finalizar qualquer tarefa que altere código, configurações, dataset, flows ou documentação, execute os comandos reais do projeto (com o ambiente virtual `.venv` ativo):

1. **Lint estático**: `ruff check .`
2. **Checagem de tipos**: `mypy lambda/sd_fulfillment scripts api`
3. **Auditoria Zero-Leak**: `python scripts/verificar_segredos.py`
4. **Validação de dataset e KB** (obrigatória ao alterar `data/` ou `kb/`): `python scripts/validar_dataset.py`
5. **Validação de Contact Flows e Lex V2** (obrigatória ao alterar `connect/` ou `lex/`): `python scripts/validar_flows.py`
6. **Testes e cobertura (`>= 90%`)**: `pytest`
7. **Builds locais** (quando alterar `lambda/sd_fulfillment/`, `data/`, `lex/`, `landing/` ou scripts de empacotamento):
   - `python scripts/empacotar_lambda.py`
   - `python scripts/gerar_pacote_lex.py`
   - `python scripts/injetar_widget.py`

Nunca considere uma tarefa concluída com falhas em qualquer verificação aplicável, nem mascare problemas enfraquecendo testes, cobertura ou regras do linter/Zero-Leak.
