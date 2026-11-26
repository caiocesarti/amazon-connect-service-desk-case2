---
description: Identifica arquivos alterados, executa lint, type-check, validações, testes e builds reais do projeto, corrige apenas a causa raiz de falhas e revalida.
---

# Workflow `/testar`

> **Ambiente:** execute os comandos abaixo com o ambiente virtual `.venv` do projeto ativo (no Windows `.venv\Scripts\activate`; no Linux/macOS `source .venv/bin/activate`).

// turbo
1. Identifique os arquivos alterados e pendentes no repositório:
   ```bash
   git status --short
   git diff --name-only
   ```

// turbo
2. Execute o lint estático com Ruff:
   ```bash
   ruff check .
   ```

// turbo
3. Execute a checagem estática de tipos com Mypy:
   ```bash
   mypy lambda/sd_fulfillment scripts api
   ```

// turbo
4. Execute a auditoria DevSecOps Zero-Leak e as validações estruturais de dataset, KB, Contact Flows e Lex V2:
   ```bash
   python scripts/verificar_segredos.py
   python scripts/validar_dataset.py
   python scripts/validar_flows.py
   ```

// turbo
5. Execute a suíte completa de testes unitários e cobertura mínima (`>= 90%`):
   ```bash
   pytest
   ```

6. Se houver alterações em `lambda/sd_fulfillment/`, `data/`, `lex/`, `landing/` ou nos scripts de empacotamento, valide também os builds locais equivalentes ao CI:
   ```bash
   python scripts/empacotar_lambda.py
   python scripts/gerar_pacote_lex.py
   python scripts/injetar_widget.py
   ```

7. Caso qualquer verificação falhe, diagnostique e corrija **apenas a causa raiz** do problema:
   - Não remova, pule (`skip`/`xfail`) nem enfraqueça testes válidos;
   - Não reduza `--cov-fail-under=90` nem desabilite regras do Ruff/Mypy sem justificativa técnica;
   - Nunca adicione `zero-leak:allow=` para contornar dados reais (substitua por placeholders).

// turbo
8. Após aplicar correções, reexecute a bateria de validação para confirmar tudo verde:
   ```bash
   ruff check . && mypy lambda/sd_fulfillment scripts api && python scripts/verificar_segredos.py && python scripts/validar_dataset.py && python scripts/validar_flows.py && pytest
   ```

9. Apresente um resumo conciso com o status de cada verificação, a cobertura obtida no `pytest` e as correções aplicadas (se houver).
