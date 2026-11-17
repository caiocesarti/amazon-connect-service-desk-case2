# ADR-002 — Convenções de nomenclatura e roteamento por chave lógica

- **Status:** Aceito
- **Data:** 2026-11-15
- **Fase:** F0

## Contexto

O template de estudos original usava o prefixo `gm_` / `GM-` (Guia Médico). Este projeto
implementa o **Case 2 (Service Desk de TI)**. Além disso, a Lambda precisa dizer ao flow
para qual fila transferir o contato, e não deve conhecer ARNs.

## Decisão

1. **Prefixo `sd_` / `SD-`** para atributos de contato, flows, filas e demais recursos
   (`sd-fulfillment-servicedesk`, `SD-Fila-Redes`, `SD-Entrada-Principal`...).
2. **Roteamento por chave lógica:** a Lambda grava `sd_fila_destino` com um enum
   (`SEGURANCA`, `REDES`, `HARDWARE`, `GERAL_N1`, `PRIORITARIA_P1`). O flow `SD-Transbordo-N1`
   compara esse valor e escolhe a fila no bloco *Set working queue*. Assim, ARNs e IDs de fila
   **só existem dentro da instância**.
3. Os valores de atributos são strings, os enums ficam em MAIÚSCULAS e os booleanos são
   `"true"` / `"false"`. O contrato completo está em `docs/01-arquitetura.md`.

## Consequências

- ✅ O código da Lambda não depende da instância, porque o mesmo pacote serve para qualquer conta.
- ✅ Nada de Zero-Leak a resolver na Lambda: não há ARN para vazar.
- ⚠️ Uma fila nova exige mudar o enum na Lambda **e** um ramo novo no flow, e o
  `validar_flows.py` (F4) vai checar se os dois lados estão coerentes.
