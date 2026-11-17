# KB-004 — Solicitação, Substituição e Entrega de Equipamentos (Hardware)

- **Código:** KB-004
- **Categoria:** `HARDWARE`
- **Público:** Colaboradores, Gestores e Equipe de Field Service (`SD-Fila-Hardware`)
- **Última revisão:** 2026-11-15

## Fluxo automático no Amazon Connect Cases

Toda solicitação de equipamento (`HardwareRequest`) gera automaticamente um registro no **Amazon Connect Cases** contendo:
- Protocolo determinístico no formato `SD-AAAAMMDD-XXXXXX`;
- Código do equipamento no catálogo homologado (`sd_equipamento`);
- Status de disponibilidade no estoque (`DISPONIVEL`, `INDISPONIVEL` ou `REQUER_APROVACAO`);
- Unidade de entrega e prazo estimado em dias úteis conforme a presença de suporte local.

## Regras por tipo de item do catálogo

1. **Itens de aprovação automática com estoque (`DISPONIVEL`):**
   - Exemplos: `NOTEBOOK_PADRAO`, `MONITOR_24`, `HEADSET_USB`, `TECLADO_ABNT2`, `MOUSE_ERGONOMICO`, `WEBCAM_FHD`, `TOKEN_YUBIKEY`, `CARREGADOR_USBC`.
   - O caso já nasce com status `ABERTO` e segue direto para separação na `SD-Fila-Hardware`.
2. **Itens que exigem aprovação do gestor (`REQUER_APROVACAO`):**
   - Exemplos: `NOTEBOOK_DEV` (Workstation 32 GB), `MONITOR_27` (4K) e `CELULAR_CORPORATIVO`.
   - O caso é criado com status `AGUARDANDO_APROVACAO`. Se houver item equivalente imediato (ex.: `NOTEBOOK_PADRAO` ou `MONITOR_24`), o bot informa a alternativa ao colaborador.
3. **Itens temporariamente sem saldo (`INDISPONIVEL`):**
   - Exemplos atuais no dataset: `MONITOR_27` e `DOCKING_USBC`.
   - O bot **não promete entrega imediata**: informa a alternativa em estoque (`MONITOR_24` ou `CARREGADOR_USBC`) e registra o caso em `AGUARDANDO_ESTOQUE` ou encaminha para `SD-Fila-Hardware` com motivo `SEM_ESTOQUE`.

## Prazos de entrega (SLA) por unidade

| Unidade | Suporte presencial | Técnicos locais | SLA de entrega/preparo | Modalidade |
|---|---|---|---|---|
| `SPO` (São Paulo) | Sim | 6 | 1 dia útil | Retirada no balcão Tech Bar ou entrega na mesa |
| `RJO`, `BHZ` | Sim | 2 a 3 | 2 dias úteis | Entrega presencial pelo técnico local |
| `REC`, `POA` | Sim | 2 | 3 dias úteis | Entrega presencial pelo técnico local |
| `CWB`, `BSB` | Sim (capacidade reduzida) | **1** | **4 dias úteis** | Agendamento com o único técnico presencial da filial |
| `MAO` (Manaus) | **Não** | **0** | **7 dias úteis** | Envio por logística expressa a partir de `SPO` com etiqueta de retorno |
