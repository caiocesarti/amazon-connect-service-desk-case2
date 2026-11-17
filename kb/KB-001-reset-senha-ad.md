# KB-001 — Redefinição de Senha Corporativa (Active Directory e SSO)

- **Código:** KB-001
- **Categoria:** `ACESSO_SEGURANCA`
- **Subcategoria:** `SENHA_AD`
- **Público:** Colaboradores e Analistas N1
- **Última revisão:** 2026-11-15

## Quando usar este procedimento

Use este guia quando o colaborador relatar:
- Esquecimento da senha do Windows, Active Directory (AD) ou portal Single Sign-On (SSO);
- Senha expirada após o ciclo de 90 dias;
- Conta bloqueada após 5 tentativas consecutivas incorretas.

## Política de segurança obrigatória

> **ATENÇÃO:** O Service Desk (bot ou analista humano) **NUNCA solicita a senha atual** nem envia senhas definitivas por chat, e-mail ou telefone. Toda troca gera uma credencial temporária de uso único no primeiro login.

Requisitos da nova senha:
- Mínimo de **12 caracteres**;
- Pelo menos 1 letra maiúscula, 1 minúscula, 1 número e 1 símbolo;
- Não pode reutilizar nenhuma das últimas 10 senhas nem conter o nome ou matrícula (`NTxxxx`).

## Passo a passo para o colaborador (autoatendimento com conta ativa)

1. Informe sua **matrícula** (formato `NT` seguido de 4 dígitos, ex.: `NT1001`) e o **PIN de verificação de 4 dígitos** ao assistente virtual.
2. Caso a identidade seja validada e a conta esteja com status `ATIVO`, o atendimento é encaminhado à fila `SD-Fila-Seguranca` com a validação já concluída (`sd_identidade_validada=true`).
3. Após receber o link de redefinição no aplicativo corporativo autenticado por MFA, defina a nova senha e aguarde até **5 minutos** para replicação entre os controladores de domínio (até **15 minutos** caso haja alerta de lentidão de sincronização na unidade).

## Casos que exigem atuação exclusiva da Fila de Segurança (`SD-Fila-Seguranca`)

| Situação | Status no diretório | Prioridade | Ação do Analista N1 |
|---|---|---|---|
| Conta bloqueada por tentativas | `BLOQUEADO` | `P2` | Confirmar com o colaborador se as tentativas foram feitas por ele; desbloquear no AD e forçar troca no próximo logon |
| Colaborador com cadastro inativo/desligado | `INATIVO` | `P2` | **Não redefinir nem desbloquear.** Registrar tentativa e validar vínculo com o RH |
| Falha no PIN após 3 tentativas | Qualquer | `P2` | Realizar confirmação por vídeo ou com o gestor imediato antes do desbloqueio |
| Suspeita de comprometimento de credencial | Qualquer | `P1` | Revogar sessões SSO ativas, resetar MFA e transferir imediatamente para `SD-Fila-Prioritaria-P1` |
