"""Construção de respostas humanizadas para Chat (texto) e Voz (SSML Amazon Polly Camila)."""

from __future__ import annotations

import html
from typing import Any

from guardrails import validar_resposta_segura


def _para_ssml(texto_voz: str) -> str:
    """Envolve o texto em tags ``<speak>`` escapando caracteres especiais XML."""
    escapado = html.escape(texto_voz, quote=False)
    return f"<speak>{escapado}</speak>"


def montar_mensagens_lex(
    texto_chat: str,
    texto_voz: str | None = None,
    canal: str = "CHAT",
) -> list[dict[str, str]]:
    """Devolve a lista ``messages`` do Lex V2 adaptada ao canal (``CHAT`` ou ``VOICE``)."""
    validar_resposta_segura(texto_chat)
    fala = texto_voz or texto_chat
    validar_resposta_segura(fala)

    if canal.upper() == "VOICE":
        return [
            {"contentType": "SSML", "content": _para_ssml(fala)},
            {"contentType": "PlainText", "content": texto_chat},
        ]
    return [{"contentType": "PlainText", "content": texto_chat}]


def msg_emergencia_seguranca() -> tuple[str, str]:
    """Mensagem crítica baseada na KB-005 para incidentes de segurança P1."""
    chat = (
        "🚨 ALERTA DE SEGURANÇA (Prioridade P1): Identifiquei um possível incidente crítico. "
        "Por favor, siga imediatamente estes passos enquanto transfiro você para a equipe de "
        "Resposta a Incidentes:\n"
        "1. Desconecte o computador do Wi-Fi e retire o cabo de rede agora.\n"
        "2. NÃO desligue o computador da tomada para preservar evidências em memória.\n"
        "3. Não clique em novos links nem tente remover arquivos por conta própria.\n"
        "Estou transferindo seu atendimento com prioridade máxima."
    )
    voz = (
        "Atenção. Identifiquei um alerta crítico de segurança. "
        "Desconecte imediatamente seu computador do Wi-Fi e retire o cabo de rede, "
        "mas não desligue o equipamento da tomada. "
        "Estou transferindo você agora para a fila prioritária de segurança."
    )
    return chat, voz


def msg_bloqueio_injecao() -> tuple[str, str]:
    """Mensagem neutra para tentativas de prompt injection."""
    chat = (
        "Sou o assistente virtual do Service Desk de TI da NuvemTech e atuo exclusivamente "
        "com suporte técnico corporativo (redefinição de senha, conectividade de rede, "
        "solicitação de equipamentos e consulta de chamados). Como posso ajudar você hoje?"
    )
    return chat, chat


def msg_solicitar_matricula(homonimos: list[dict[str, Any]] | None = None) -> tuple[str, str]:
    """Solicita matrícula (incluindo explicação quando há homônimos)."""
    if homonimos and len(homonimos) > 1:
        unidades = ", ".join(sorted({c["unidade"] for c in homonimos}))
        chat = (
            f"Encontrei {len(homonimos)} colaboradores com esse nome nas unidades ({unidades}). "
            "Para identificar seu cadastro com segurança, informe sua matrícula no formato "
            "NT seguido de 4 números (por exemplo, NT1001)."
        )
        voz = (
            f"Encontrei {len(homonimos)} cadastros com esse nome. "
            "Por favor, informe sua matrícula começando com N T e quatro números."
        )
        return chat, voz

    chat = (
        "Para continuar, informe sua matrícula corporativa no formato NT seguido de 4 dígitos "
        "(exemplo: NT1001)."
    )
    voz = "Por favor, informe sua matrícula corporativa, começando com N T e quatro números."
    return chat, voz


def msg_solicitar_pin(primeiro_nome: str) -> tuple[str, str]:
    """Solicita o PIN de verificação de 4 dígitos."""
    chat = (
        f"Olá, {primeiro_nome}! Para validar sua identidade, informe seu PIN de verificação "
        "de 4 dígitos. Lembrete: nunca digite sua senha corporativa no chat."
    )
    voz = (
        f"Olá, {primeiro_nome}. Para validar sua identidade, digite ou fale seu PIN "
        "de verificação de quatro dígitos. Nunca informe sua senha."
    )
    return chat, voz


def msg_reset_senha(
    colaborador: dict[str, Any],
    protocolo: str,
    prioridade: str,
    incidente: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Mensagem final para o fluxo ``PasswordReset``."""
    nome = colaborador["primeiro_nome"]
    status = colaborador["status_conta"]

    if status == "INATIVO":
        chat = (
            f"{nome}, identifiquei que a matrícula {colaborador['matricula']} consta como "
            f"inativa no diretório corporativo. Registrei o protocolo {protocolo} ({prioridade}) "
            "e estou transferindo você para a Fila de Segurança para verificação junto ao RH."
        )
        voz = (
            f"{nome}, sua matrícula consta como inativa no diretório. "
            f"Anote o protocolo {protocolo}. Vou transferir você para a equipe de segurança."
        )
        return chat, voz

    if status == "BLOQUEADO":
        extra_inc = f" Nota: {incidente['orientacao_colaborador']}" if incidente else ""
        chat = (
            f"{nome}, sua identidade foi validada! Sua conta está com bloqueio preventivo no "
            f"Active Directory. Gerei o protocolo {protocolo} com prioridade {prioridade} e "
            "estou transferindo você para a Fila de Segurança realizar o desbloqueio imediato."
            f"{extra_inc}"
        )
        voz = (
            f"{nome}, identidade validada. Sua conta está bloqueada no diretório. "
            f"Protocolo {protocolo}, prioridade {prioridade}. "
            "Transferindo agora para a fila de segurança."
        )
        return chat, voz

    extra_inc = f"\nℹ️ Aviso da unidade: {incidente['orientacao_colaborador']}" if incidente else ""
    chat = (
        f"Perfeito, {nome}! Sua identidade foi validada com sucesso. "
        f"Registrei o chamado {protocolo} (prioridade {prioridade}) e estou encaminhando seu "
        "atendimento para a Fila de Segurança concluir a redefinição de senha com contexto "
        f"completo.{extra_inc}"
    )
    voz = (
        f"Perfeito, {nome}. Identidade validada e chamado {protocolo} registrado. "
        "Estou transferindo você para a fila de segurança concluir a redefinição."
    )
    return chat, voz


def msg_problema_rede(
    colaborador: dict[str, Any] | None,
    subcategoria: str,
    impacto: str,
    prioridade: str,
    protocolo: str,
    incidente: dict[str, Any] | None,
) -> tuple[str, str]:
    """Mensagem contextualizada para ``NetworkIssue``."""
    saudacao = f"{colaborador['primeiro_nome']}, " if colaborador else ""
    if incidente:
        chat = (
            f"{saudacao}identifiquei que sua unidade já possui o incidente massivo "
            f"{incidente['id']} ({incidente['titulo']}) em tratamento com previsão para "
            f"{incidente['previsao_normalizacao']}.\n"
            f"💡 Orientação imediata: {incidente['orientacao_colaborador']}\n"
            f"Vinculei seu relato ao protocolo {protocolo} (prioridade {prioridade}) e estou "
            "encaminhando você para a Fila de Redes com todo o contexto."
        )
        voz = (
            f"{saudacao}sua unidade já possui o incidente {incidente['id']} em tratamento. "
            f"{incidente['orientacao_colaborador']} "
            f"Seu protocolo é {protocolo}. Vou transferir você para a fila de redes."
        )
        return chat, voz

    chat = (
        f"{saudacao}registrei seu relato de conectividade ({subcategoria}, impacto {impacto}) "
        f"sob o protocolo {protocolo} com prioridade {prioridade}. "
        "Estou direcionando você para a Fila de Redes já com o diagnóstico inicial anexado."
    )
    voz = (
        f"{saudacao}registrei seu chamado de rede no protocolo {protocolo} com prioridade "
        f"{prioridade}. Estou transferindo você para a equipe de redes."
    )
    return chat, voz


def msg_solicitacao_hardware(
    colaborador: dict[str, Any],
    avaliacao: dict[str, Any],
    protocolo: str,
    case_id: str,
    prioridade: str,
) -> tuple[str, str]:
    """Mensagem detalhada para ``HardwareRequest`` com dados do Connect Cases."""
    nome = colaborador["primeiro_nome"]
    item_nome = avaliacao["nome_equipamento"]
    status_est = avaliacao["estoque_status"]
    prazo = avaliacao["prazo_dias_uteis"]
    modalidade = avaliacao["modalidade_entrega"]
    alt = avaliacao.get("alternativa_sugerida")

    detalhe_entrega = {
        "ENVIO_LOGISTICA_EXPRESSA": (
            f"Como sua unidade ({colaborador['unidade']}) não possui técnico presencial, "
            f"o envio será feito por logística expressa (prazo estimado: {prazo} dias úteis)."
        ),
        "AGENDAMENTO_TECNICO_UNICO": (
            f"Sua unidade ({colaborador['unidade']}) conta com 1 técnico presencial; "
            f"o atendimento será agendado em até {prazo} dias úteis."
        ),
        "ENTREGA_PRESENCIAL_LOCAL": (
            f"Prazo estimado na unidade {colaborador['unidade']}: {prazo} dia(s) útil(eis)."
        ),
    }[modalidade]

    if status_est == "INDISPONIVEL":
        texto_alt = f" Temos o item alternativo '{alt}' para pronta entrega." if alt else ""
        chat = (
            f"{nome}, abri o caso {case_id} (protocolo {protocolo}, prioridade {prioridade}) "
            f"para '{item_nome}'. No momento este modelo está sem estoque imediato "
            f"(status: AGUARDANDO_ESTOQUE).{texto_alt} {detalhe_entrega} "
            "Vou encaminhar você para a Fila de Hardware caso queira aprovar o item alternativo."
        )
        voz = (
            f"{nome}, abri o caso no protocolo {protocolo} para {item_nome}, que está sem "
            "estoque imediato. Vou transferir você para a equipe de hardware avaliar a alternativa."
        )
        return chat, voz

    if status_est == "REQUER_APROVACAO":
        chat = (
            f"{nome}, criei automaticamente o caso {case_id} no Connect Cases "
            f"(protocolo {protocolo}, prioridade {prioridade}) para '{item_nome}'. "
            "Este equipamento requer aprovação do seu gestor imediato "
            f"(status inicial: AGUARDANDO_APROVACAO). {detalhe_entrega}"
        )
        voz = (
            f"{nome}, criei o caso no protocolo {protocolo} para {item_nome}. "
            f"O pedido aguarda aprovação do seu gestor e tem prazo de {prazo} dias úteis."
        )
        return chat, voz

    chat = (
        f"{nome}, sua solicitação de '{item_nome}' foi registrada com sucesso no Connect Cases! "
        f"Caso: {case_id} | Protocolo: {protocolo} | Prioridade: {prioridade} | "
        f"Status: ABERTO (em estoque). {detalhe_entrega}"
    )
    voz = (
        f"{nome}, sua solicitação de {item_nome} foi aberta no protocolo {protocolo}. "
        f"O item está em estoque com prazo estimado de {prazo} dias úteis."
    )
    return chat, voz


def msg_status_chamado(chamado: dict[str, Any] | None, referencia: str) -> tuple[str, str]:
    """Mensagem anti-alucinação para ``ConsultarStatusChamado``."""
    if not chamado:
        chat = (
            f"Não encontrei nenhum chamado com a referência '{referencia}' na base do "
            "Service Desk. Por segurança, não estimo status de protocolos não localizados. "
            "Verifique o código no formato SD-AAAAMMDD-XXXXXX ou peça para falar com um analista."
        )
        voz = (
            f"Não localizei nenhum chamado com a referência {referencia}. "
            "Por favor, confira o número do protocolo ou peça para falar com um analista."
        )
        return chat, voz

    chat = (
        f"📋 Status do chamado {chamado['protocolo']}:\n"
        f"- Status atual: {chamado['status']}\n"
        f"- Categoria: {chamado['categoria']} (Prioridade {chamado['prioridade']})\n"
        f"- Fila responsável: {chamado['fila_destino']}\n"
        f"- Resumo: {chamado['resumo']}"
    )
    voz = (
        f"O chamado {chamado['protocolo']} está com status {chamado['status']}, "
        f"prioridade {chamado['prioridade']}, na fila {chamado['fila_destino']}. "
        f"Resumo: {chamado['resumo']}"
    )
    return chat, voz
