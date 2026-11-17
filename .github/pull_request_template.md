## Descrição

<!-- Resumo objetivo do que mudou e o motivo técnico da alteração. -->

## Checklist Zero-Leak

- [ ] `python scripts/verificar_segredos.py` passou localmente
- [ ] Nenhum Account ID real, ARN real, chave AKIA/ASIA, token Vercel ou snippet do widget
- [ ] Exports do console (flows/bot) passaram por `scripts/sanitizar_export.py`
- [ ] Prints em `docs/img/` sem IDs, e-mails, telefones ou URLs de instância visíveis
- [ ] Qualquer `zero-leak:allow=` adicionado está justificado abaixo

## Qualidade e Testes

- [ ] `ruff check .` verde
- [ ] `mypy lambda/sd_fulfillment scripts api` verde
- [ ] `pytest` verde (cobertura >= 90%)
- [ ] Evidências atualizadas em `docs/03-testes-e-evidencias.md` (se aplicável)
