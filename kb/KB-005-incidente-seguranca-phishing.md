# KB-005 — Resposta Imediata a Incidentes de Segurança, Phishing e Ransomware

- **Código:** KB-005
- **Categoria:** `ACESSO_SEGURANCA`
- **Prioridade padrão:** `P1` (Crítica — encaminhamento imediato para `SD-Fila-Prioritaria-P1`)
- **Público:** Todos os colaboradores e Equipe de Resposta a Incidentes (CSIRT / Segurança)
- **Última revisão:** 2026-11-15

## Gatilhos de emergência de segurança

Qualquer relato contendo sinais abaixo deve acionar o guardrail `EMERGENCIA` (`sd_guardrail_acionado=EMERGENCIA`), classificar a prioridade como **`P1`** e transferir sem demora para **`SD-Fila-Prioritaria-P1`** com `sd_motivo_transbordo=EMERGENCIA_SEGURANCA`:

- Tela de bloqueio pedindo resgate, arquivos criptografados com extensão desconhecida ou suspeita de **ransomware**;
- Clique em link suspeito ou digitação de credencial corporativa em página falsa (**phishing**);
- Aprovações de **MFA push** aparecendo no celular sem que o colaborador esteja tentando logar (*MFA fatigue*);
- Perda, furto ou roubo de notebook/celular corporativo desbloqueado;
- Suspeita de **vazamento de dados** ou acesso indevido a repositório/bucket corporativo.

## Orientações imediatas ao colaborador (enquanto aguarda o analista P1)

1. **Desconecte da rede imediatamente:** desligue o Wi-Fi e retire o cabo de rede (ou desconecte a docking station).
2. **NÃO desligue o computador da tomada nem feche a tampa (hibernação):** manter a máquina ligada preserva evidências em memória RAM para a análise forense do CSIRT.
3. **NÃO tente remover arquivos, rodar ferramentas por conta própria nem pagar qualquer valor solicitado.**
4. **Se informou sua senha em link suspeito:** avise o analista assim que atender para revogação imediata dos tokens SSO e sessões ativas.

## Ações proibidas no atendimento automatizado

- O bot **não deve fazer perguntas longas de triagem** diante de um gatilho de emergência: deve emitir a orientação de isolamento de rede acima, gravar `sd_prioridade=P1`, `sd_fila_destino=PRIORITARIA_P1` e transferir o contato imediatamente.
