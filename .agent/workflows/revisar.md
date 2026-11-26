---
description: Realiza code review rigoroso do git diff atual focando em bugs, segurança, performance, tipagem e aderência às regras do projeto, listando achados por severidade.
---

# Workflow `/revisar`

> **Restrição:** este workflow é somente de revisão técnica. **Não** edite arquivos nem faça commits; reporte os achados para decisão do usuário.

// turbo
1. Inspecione o estado do repositório e colete o diff completo (alterações não staged e staged):
   ```bash
   git status --short
   git diff
   git diff --cached
   ```

// turbo
2. Execute as verificações estáticas e de segurança automatizadas para embasar o review:
   ```bash
   ruff check .
   mypy lambda/sd_fulfillment scripts api
   python scripts/verificar_segredos.py
   ```

3. Leia `.agent/rules/padroes-projeto.md` e os trechos completos necessários dos arquivos alterados para avaliar o contexto além do diff isolado.

4. Analise rigorosamente todas as mudanças nos cinco critérios abaixo:
   - **Bugs e Regressões**: lógica condicional, casos de borda (`INATIVO`, `BLOQUEADO`, homônimos, sem estoque, limites de PIN), contrato `sd_*` (valores sempre `string`) e consistência entre Lambda, Flows (`2019-10-30`), Lex V2 e dataset.
   - **Segurança**: Política Zero-Leak (ADR-001), ausência de Account IDs/ARNs/tokens/snippets reais, respeito a `.env` e `*.local.*`, integridade dos Guardrails (`guardrails.py`), logs/resumos Zero-PII, validação de entrada (`api/index.py`, `scripts/servir_local.py`) e CSP (`vercel.json`).
   - **Performance e FinOps**: ausência de dependências externas na Lambda (`stdlib` + `boto3`), eficiência de leitura/I/O, limites de corpo HTTP e proteções FinOps do widget (`landing/assets/js/widget-loader.template.js`).
   - **Tipagem e Qualidade**: conformidade com `mypy`, `ruff`, `from __future__ import annotations`, ausência de duplicação de regras no front-end e adequação dos testes (`tests/` com cobertura `>= 90%`).
   - **Aderência às Regras do Projeto**: conformidade com `.agent/rules/padroes-projeto.md`, ADR-001, ADR-002 e `.editorconfig`.

5. Apresente o parecer organizado por severidade:
   - **CRÍTICA** (falha de segurança, vazamento Zero-Leak, quebra de produção/contrato)
   - **ALTA** (bug provável, regressão funcional, falha de validação/tipagem)
   - **MÉDIA** (performance, manutenibilidade, cobertura insuficiente, desvio de convenção)
   - **BAIXA** (melhorias pontuais de clareza ou estilo)

   Para cada achado, informe **arquivo e linha**, **descrição do problema**, **impacto** e **correção sugerida**. Se nenhum problema for encontrado, informe isso explicitamente e cite os checks verificados.
