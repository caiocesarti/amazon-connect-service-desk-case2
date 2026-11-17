# KB-003 — Conectividade Wi-Fi Corporativa e Rede Cabeada nos Escritórios

- **Código:** KB-003
- **Categoria:** `REDE_CONECTIVIDADE`
- **Subcategoria:** `WIFI`
- **Público:** Colaboradores presenciais e Analistas de Redes
- **Última revisão:** 2026-11-15

## Redes sem fio oficiais nos escritórios NuvemTech

| SSID | Finalidade | Autenticação |
|---|---|---|
| `NuvemTech-Corp` | Notebooks e celulares corporativos homologados | WPA3-Enterprise (802.1X via certificado da máquina + usuário AD) |
| `NuvemTech-Visitantes` | Visitantes e dispositivos pessoais (isolada da intranet) | Portal cativo com voucher diário |

## Passos de resolução rápida

1. **Confirmar o SSID correto:** equipamentos corporativos ligados em `NuvemTech-Visitantes` **não acessam** servidores internos, repositórios git ou impressoras de andar. Reconecte ao SSID `NuvemTech-Corp`.
2. **Troca recente de senha do AD:** caso tenha redefinido a senha nas últimas 24 horas, clique em *Esquecer esta rede* em `NuvemTech-Corp` e autentique novamente com a nova credencial.
3. **Renovação de IP e DNS:** caso conecte ao Wi-Fi com o aviso *"Conectado, sem internet"*, desconecte e reconecte o Wi-Fi ou conecte o cabo na docking station da mesa para testar se a falha é apenas no Access Point do andar.

## Tratamento por escopo de impacto

- **Impacto `INDIVIDUAL`:** o colaborador é o único afetado na mesa → priorizar como `P3` e encaminhar para `SD-Fila-Redes`.
- **Impacto `SETOR`:** várias pessoas do mesmo andar ou sala de reunião sem conexão → priorizar como `P2` (ou `P1` se envolver sala de conselho/Diretoria) e informar o andar/sala no resumo do chamado (`sd_resumo`).
- **Impacto `UNIDADE`:** queda geral do link da filial → verificar `incidentes_ativos` (ex.: `INC-0001` em Porto Alegre) e classificar como `P1` na fila `SD-Fila-Prioritaria-P1`.
