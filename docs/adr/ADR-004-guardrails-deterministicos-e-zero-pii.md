# ADR-004 — Guardrails Determinísticos Pré-Negócio e Logs Zero-PII

- **Status:** Aceito
- **Data:** 2026-11-26
- **Escopo:** Segurança Conversacional (`guardrails.py`), Respostas e Observabilidade

## Contexto

Um Service Desk de TI recebe entradas de alto risco: incidentes críticos de segurança (ransomware,
phishing, *MFA fatigue*, furto de equipamento), tentativas de *prompt injection* e exposição
acidental de senhas ou CPFs pelo próprio colaborador. Delegar essa primeira barreira a um LLM
introduziria latência extra em voz/chat, custo variável por turno e comportamento não
determinístico difícil de auditar.

## Decisão

1. **Barreira determinística antes da lógica de negócio (`lambda/sd_fulfillment/guardrails.py`):**
   `guardrails.avaliar_entrada` é executada obrigatoriamente no início de
   `handler._executar_roteamento`, antes de qualquer intenção ou leitura de cadastro, seguindo ordem
   de precedência fixa:
   - `INJECAO`: bloqueio imediato com resposta institucional neutra (`ENCERRAR`);
   - `EMERGENCIA`: prioridade `P1`, orientações da `KB-005` (isolar da rede sem desligar da tomada)
     e transbordo imediato para `PRIORITARIA_P1`;
   - `SENHA_EXPOSTA` e `PII`: mascaramento in-line (`[SENHA_REMOVIDA]` / `[CPF_REMOVIDO]`) antes de
     propagar o texto ao restante do fluxo.
2. **Guardrail de saída:** `guardrails.validar_resposta_segura` (executada por
   `respostas.montar_mensagens_lex`) impede a emissão de orientações proibidas (como desativar
   antivírus, firewall ou EDR).
3. **Observabilidade Zero-PII:** `handler._registrar_log_estruturado` grava JSON estruturado no
   CloudWatch (retenção de 7 dias em `infra/template.yaml`) apenas com metadados operacionais
   (`intencao`, `fila_destino`, `prioridade`, `guardrail`, `latencia_ms`), sem matrícula, nome,
   PIN, senha ou CPF. `chamados.montar_resumo_contexto` remascara defensivamente `sd_resumo`
   (limite de 256 caracteres), e a política de redação de PII/PIN para o Contact Lens fica
   especificada declarativamente em `connect/contact-lens/regras.json`.

## Consequências

- ✅ Latência desprezível, custo zero de inferência adicional e 100% de cobertura determinística
  em `tests/test_lambda_fulfillment.py`.
- ✅ Redução direta do risco de vazamento de credenciais ou dados pessoais em logs CloudWatch e no
  sussurro ao analista (CCP v2).
- ⚠️ Regras léxicas e regex têm cobertura limitada para paráfrases inéditas ou ofuscação criativa.
  Em produção, esta camada permaneceria como primeira linha *fail-fast* combinada a um
  classificador semântico (ex.: Amazon Bedrock Guardrails).
