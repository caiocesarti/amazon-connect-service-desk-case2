# Bot Conversacional Amazon Lex V2 — `SD-ServiceDesk-Bot`

Especificação do bot de triagem do **NuvemTech Service Desk** (Case 2 — Chat Online + Voz).

- **Nome do Bot:** `SD-ServiceDesk-Bot`
- **Alias de Produção:** `SD-Live`
- **Locale:** `pt_BR`
- **Voz Neural (Amazon Polly):** `Camila` (`engine: neural`)
- **NLU Confidence Threshold:** `0.40`
- **Lambda Code Hook (`DialogCodeHook` + `FulfillmentCodeHook`):** `sd-fulfillment-servicedesk`

## Matriz de Intenções, Slots e Roteamento

| Intenção | Categoria (`sd_categoria`) | Slots Obrigatórios | Slots Opcionais | Fila Padrão (`sd_fila_destino`) |
|---|---|---|---|---|
| `PasswordReset` | `ACESSO_SEGURANCA` | `Matricula`, `PinVerificacao` | `NomeColaborador` | `SEGURANCA` |
| `NetworkIssue` | `REDE_CONECTIVIDADE` | `Matricula`, `TipoProblemaRede`, `EscopoImpacto` | `NomeColaborador` | `REDES` (ou `PRIORITARIA_P1` se impacto=`UNIDADE` / VIP) |
| `HardwareRequest` | `HARDWARE` | `Matricula`, `Equipamento` | `NomeColaborador` | `HARDWARE` (com abertura automática no Connect Cases) |
| `ConsultarStatusChamado` | `GERAL` | *(Protocolo ou Matricula via DialogCodeHook)* | `Protocolo`, `Matricula` | Retenção no bot (`sd_resolvido_bot=true`) |
| `FalarComAtendente` | `GERAL` | — | `Matricula`, `NomeColaborador` | `GERAL_N1` |
| `FallbackIntent` | `GERAL` | — | — | `GERAL_N1` (`sd_motivo_transbordo=BAIXA_CONFIANCA`) |

> **Nota sobre Guardrails:** Qualquer entrada contendo gatilho de incidente crítico de segurança (ransomware, phishing, vazamento, MFA não solicitado) intercepta imediatamente qualquer intenção no `DialogCodeHook`, classifica `sd_prioridade=P1` e roteia para `PRIORITARIA_P1`.
