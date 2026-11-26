---
description: Atualiza a documentação relevante do projeto refletindo as últimas mudanças sem alterar a lógica do código.
---

# Workflow `/documentar`

> **Restrição:** **nunca** altere a lógica de negócio, assinaturas funcionais ou comportamento do código. Modifique apenas arquivos de documentação (Markdown) e, quando estritamente necessário, docstrings ou comentários técnicos.

// turbo
1. Identifique as mudanças recentes no repositório para mapear o escopo da documentação:
   ```bash
   git status --short
   git diff --stat
   git log -n 5 --oneline
   ```

2. Inspecione o conteúdo das alterações (ou dos arquivos mencionados com `@`) e identifique quais documentos do repositório ficaram desatualizados:
   - `README.md` (e o espelho em inglês `README.en.md`, quando houver impacto na visão geral, estrutura ou comandos);
   - `docs/01-arquitetura.md` (contrato de atributos `sd_*`, matriz ITIL, guardrails ou diagramas Mermaid);
   - `docs/02-passo-a-passo.md` (etapas de provisionamento AWS/Vercel);
   - `docs/03-testes-e-evidencias.md` (casos de teste `CT-*` e evidências);
   - `docs/adr/` (registro ou atualização de decisões arquiteturais relevantes);
   - `kb/KB-001` a `kb/KB-005` (runbooks do Amazon Q in Connect);
   - Docstrings e comentários técnicos em módulos diretamente afetados.

3. Atualize somente a documentação pertinente às mudanças reais:
   - Mantenha o idioma padrão do projeto (**Português BR**, preservando inglês no `README.en.md`);
   - Cite apenas scripts, caminhos e comandos que existem de fato no repositório;
   - Respeite rigorosamente a Política Zero-Leak usando apenas placeholders (`000000000000`, `<ACCOUNT_ID>`, `<REGION>`, `<INSTANCE_ALIAS>`, `<WIDGET_ID>`).

// turbo
4. Valide Zero-Leak, integridade da base de conhecimento e lint (caso docstrings/comentários em Python tenham sido editados):
   ```bash
   python scripts/verificar_segredos.py
   python scripts/validar_dataset.py
   ruff check .
   ```

// turbo
5. Verifique o diff final para confirmar que nenhuma lógica de código foi modificada:
   ```bash
   git diff --stat
   ```

6. Apresente um resumo curto listando os arquivos atualizados e o que foi ajustado em cada um.
