# KB-002 — Diagnóstico de VPN Corporativa (NuvemTech Zero Trust / AnyConnect)

- **Código:** KB-002
- **Categoria:** `REDE_CONECTIVIDADE`
- **Subcategoria:** `VPN`
- **Público:** Colaboradores em trabalho remoto/híbrido e Analistas de Redes
- **Última revisão:** 2026-11-15

## Sintomas cobertos

- Mensagem *"Connection attempt has timed out"* ou *"Unable to contact gateway"*;
- Queda recorrente do túnel VPN a cada poucos minutos;
- Autenticação MFA aceita, mas sem acesso aos sistemas internos (`*.intranet.nuvemtech.com.br`).

## Verificação imediata de incidente massivo

Antes de iniciar o troubleshooting individual, consulte se a unidade do colaborador possui incidente aberto:
- Se houver incidente ativo na unidade (ex.: `INC-0002` no concentrador regional Nordeste `VPN-NE`), oriente o colaborador a selecionar o perfil de contingência **`BR-Sudeste-Backup`** na lista de gateways do cliente VPN.

## Checklist de primeiro contato (Colaborador / Bot)

1. **Testar acesso externo:** confirme se sites públicos carregam normalmente. Se não carregarem, o problema é na internet local (`SEM_INTERNET`), não no concentrador VPN.
2. **Trocar o gateway:** no cliente VPN, alterne do gateway regional para **`BR-Sudeste-Backup`** e tente reconectar.
3. **Validar relógio do sistema:** diferenças maiores que 30 segundos impedem a validação do token TOTP/MFA.
4. **Conflito de rede local:** redes domésticas usando a faixa `10.200.0.0/16` conflitam com a sub-rede interna da NuvemTech; teste roteando pelo 4G/5G para isolar o problema.

## O que NUNCA orientar (Guardrail de Segurança)

- **Nunca** peça ao colaborador para desativar o firewall corporativo, o agente EDR/antivírus ou o proxy de inspeção TLS.
- **Nunca** recomende VPNs pessoais ou gratuitas de terceiros.

## Critérios de priorização e escalonamento (`SD-Fila-Redes`)

| Escopo do impacto | Prioridade | Fila de destino |
|---|---|---|
| Apenas 1 colaborador em home office (`INDIVIDUAL`) | `P3` | `SD-Fila-Redes` |
| Todo um setor/equipe ou colaborador da Diretoria (`SETOR` / VIP) | `P2` | `SD-Fila-Redes` |
| Unidade inteira parada ou indisponibilidade total de link (`UNIDADE`) | `P1` | `SD-Fila-Prioritaria-P1` |
