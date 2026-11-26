# ADR-003 — Lambda Zero-Dependencies, Dataset Embarcado e Idempotência

- **Status:** Aceito
- **Data:** 2026-11-26
- **Escopo:** Backend Lambda (`lambda/sd_fulfillment/`) e Connect Cases

## Contexto

A função AWS Lambda `sd-fulfillment-servicedesk` executa no caminho crítico síncrono do Amazon
Lex V2 (chat e voz). Em um laboratório de estudos e portfólio, provisionar bancos gerenciados
(DynamoDB/RDS) ou empacotar bibliotecas de terceiros aumentaria custos recorrentes, tempo de
*cold start* e complexidade de empacotamento entre sistemas operacionais (Windows/Linux). Além
disso, retentativas de rede do Lex ou do Amazon Connect não podem gerar chamados duplicados no
Amazon Connect Cases.

## Decisão

1. **Zero dependências externas na Lambda (`stdlib` + `boto3` nativo):** `lambda/sd_fulfillment/`
   utiliza exclusivamente a biblioteca padrão do Python 3.12 (`arm64` no `infra/template.yaml`) e
   o `boto3` já presente no runtime AWS. O script `scripts/empacotar_lambda.py` gera um pacote ZIP
   determinístico (~23 KB) contendo apenas os módulos `.py` e `data/service_desk.json` em
   `dados/service_desk.json`, carregado em memória com cache LRU (`busca.carregar_dataset`).
2. **Protocolo e `clientToken` determinísticos (SHA-256):** `chamados.gerar_protocolo_deterministico`
   (`SD-AAAAMMDD-XXXXXX`) e `casos.criar_caso_connect` derivam identificadores determinísticos a
   partir da requisição para garantir idempotência em retentativas.
3. **Modo dual `CASES_DRY_RUN`:** com `CASES_DRY_RUN=true` (padrão local/CI) ou quando
   `CASES_DOMAIN_ID` contém placeholder (`<...>`), `casos.py` gera IDs simulados
   (`case-sim-<hash>`) sem chamadas AWS. Com `CASES_DRY_RUN=false`, invoca
   `connectcases.create_case` sob política IAM de menor privilégio (`cases:CreateCase`).

## Consequências

- ✅ *Cold start* mínimo, pacote determinístico multiplataforma e custo zero de banco de dados no
  laboratório.
- ✅ Alternância limpa entre execução local/CI e integração real com Connect Cases apenas por
  variáveis de ambiente, sem alterar código.
- ⚠️ Sem persistência transacional nem escrita concorrente sobre o dataset estático. Em produção,
  `busca.py` e `casos.py` seriam evoluídos para consultas reais ao diretório corporativo (AD/IdP),
  CMDB/ITSM e persistência em DynamoDB.
