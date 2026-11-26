---
description: Analisa arquivos mencionados com @ ou requisitos informados, mapeia impactos no repositório e gera um plano de implementação detalhado sem editar código.
---

# Workflow `/planejar`

> **Restrição:** este workflow é somente de análise e planejamento. **Não** crie nem edite arquivos de código ou configuração durante sua execução.

// turbo
1. Inspecione o estado atual do repositório e carregue as regras do projeto:
   ```bash
   git status --short
   ```
   Leia `.agent/rules/padroes-projeto.md` para garantir aderência às convenções e restrições do repositório.

2. Leia integralmente os arquivos mencionados pelo usuário com `@` ou, se houver apenas um requisito em texto, localize os arquivos relevantes em `lambda/sd_fulfillment/`, `api/`, `scripts/`, `connect/`, `lex/`, `data/`, `kb/`, `landing/`, `infra/` e `tests/`.

3. Mapeie impactos técnicos e dependências cruzadas:
   - **Contrato `sd_*` e ADRs**: verifique impactos em `docs/01-arquitetura.md`, `docs/adr/ADR-001-politica-zero-leak.md` e `docs/adr/ADR-002-nomenclatura-e-roteamento.md`.
   - **Coerência entre camadas**: confirme se a mudança exige sincronização entre Lambda (`config.py`/`chamados.py`/`handler.py`), Contact Flows (`connect/flows/*.json`), Lex V2 (`lex/*.json`), `connect/recursos.yaml`, dataset/schema (`data/`) e simulador (`scripts/servir_local.py`, `api/index.py`, `landing/`).
   - **Segurança e FinOps**: identifique riscos de Zero-Leak, Guardrails (`guardrails.py`), Zero-PII, validação de entrada ou CSP (`vercel.json`).
   - **Testes e cobertura**: mapeie quais arquivos em `tests/` precisam de casos novos ou atualizados para manter a cobertura `>= 90%`.

4. Apresente um **Plano de Implementação** claro e objetivo contendo:
   - Escopo e objetivo da mudança;
   - Lista de arquivos a criar, editar ou remover (com o papel de cada alteração);
   - Ordem recomendada de execução;
   - Riscos, casos de borda e cuidados de segurança (Zero-Leak / Guardrails);
   - Comandos reais de validação a executar após a implementação (`ruff check .`, `mypy lambda/sd_fulfillment scripts api`, `python scripts/verificar_segredos.py`, `python scripts/validar_dataset.py`, `python scripts/validar_flows.py`, `pytest` e builds aplicáveis).

5. Encerre aguardando a aprovação explícita do usuário antes de fazer qualquer alteração no código.
