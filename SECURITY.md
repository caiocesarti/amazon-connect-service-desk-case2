# Política de Segurança — Zero-Leak

Este repositório é um **projeto de estudos e portfólio**. Ele foi desenhado para ser público
sem expor nenhum dado da conta AWS, da instância do Amazon Connect ou da Vercel.

## O que nunca pode ser versionado

| Item | Exemplo do que é proibido | Use no lugar |
|---|---|---|
| Account ID da AWS | qualquer número real de 12 dígitos | `000000000000` ou `<ACCOUNT_ID>` |
| ARNs reais | `arn:aws:connect:us-east-1:<conta real>:instance/...` | `arn:aws:connect:<REGION>:000000000000:instance/<INSTANCE_ID>` |
| Credenciais AWS | chaves `AKIA…` / `ASIA…`, secret keys, session tokens | perfis do AWS CLI / IAM Identity Center |
| Tokens | Vercel, GitHub, JWT do widget | variáveis de ambiente / GitHub Secrets |
| Snippet do widget | `widgetId` e `snippetId` reais | `landing/widget-snippet.local.html` (ignorado) ou `CONNECT_WIDGET_SNIPPET` na Vercel |
| Alias real da instância | URL `https://<alias>.my.connect.aws` | `<INSTANCE_ALIAS>` |

## Camadas de proteção

1. **`.gitignore`**: bloqueia `.env`, `*.local.*`, `.vercel/`, chaves e exports brutos.
2. **Hook pre-commit**: `scripts/verificar_segredos.py --staged` audita exatamente o que vai ser commitado.
3. **CI (GitHub Actions)**: o mesmo scanner roda na árvore inteira, e o **gitleaks** varre todo o histórico.
4. **Sanitização de exports**: flows e bots exportados do console passam por `scripts/sanitizar_export.py` antes de entrar no repositório.

## Se um segredo vazar

1. **Revogue ou rotacione a credencial imediatamente** (IAM, Vercel, GitHub). Apagar o commit não basta, porque o valor continua em forks, caches e no histórico.
2. Reescreva o histórico (`git filter-repo`) só depois da rotação.
3. Revise o AWS CloudTrail e o AWS Billing atrás de uso indevido.

## Reportar um problema

Abra uma *issue* **sem incluir o valor exposto**. Indique só o arquivo e o commit.
