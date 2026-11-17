# ADR-001 — Política Zero-Leak em camadas

- **Status:** Aceito
- **Data:** 2026-11-15
- **Fase:** F0

## Contexto

O repositório será público, como portfólio. Projetos com Amazon Connect produzem muitos
identificadores sensíveis: ARNs de instância, filas e flows, Account ID, IDs do bot Lex, além do
snippet do widget e dos tokens da Vercel. Os exports do console trazem tudo isso embutido, e
um único commit descuidado expõe a conta.

## Decisão

Adotar **defesa em profundidade** com quatro camadas:

1. **Prevenção estrutural:** valores reais só existem em arquivos ignorados (`.env`,
   `*.local.*`) ou em variáveis de ambiente da Vercel e do GitHub. Os templates usam placeholders
   padronizados: `000000000000`, `<ACCOUNT_ID>`, `<REGION>`, `<INSTANCE_ALIAS>`, `<WIDGET_ID>`.
2. **Hook local:** `scripts/verificar_segredos.py --staged` lê o conteúdo **do índice** (e não da
   cópia de trabalho), então o que é auditado é exatamente o que será commitado.
3. **CI:** o mesmo scanner roda na árvore inteira, e o **gitleaks** varre o histórico completo.
4. **Sanitização de exports:** `scripts/sanitizar_export.py` (a partir da F4) troca IDs reais
   por placeholders.

O scanner é **próprio** (stdlib, sem dependências) para que haja regras específicas do domínio,
que ferramentas genéricas não conhecem:

- Account ID dentro de nomes de bucket e de ARNs;
- `widgetId` e `snippetId` do Communications Widget;
- variáveis sensíveis em arquivos `.env*` com valor real;
- arquivos proibidos rastreados por `git add -f`.

## Consequências

- ✅ Os achados são exibidos **mascarados**, e o relatório nunca reimprime o segredo.
- ✅ A supressão inline `zero-leak:allow=REGRA` é auditável no code review e **não vale** para
  credenciais (AKIA/ASIA, secret key, chave privada, tokens GitHub e Vercel).
- ⚠️ A regra de 12 dígitos pode gerar falso positivo, por exemplo com timestamps compactos.
  Nesses casos a supressão justificada resolve.
- ⚠️ Os testes montam segredos falsos por concatenação, para que nenhum literal suspeito exista
  no repositório.
