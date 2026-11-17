"""Roteador principal de eventos do Amazon Lex V2 para o NuvemTech Service Desk.

Suporta ``DialogCodeHook`` (validação progressiva de slots e guardrails) e
``FulfillmentCodeHook`` (categorização ITIL, criação de caso no Connect Cases,
consulta de status e preparação do contrato de sessão ``sd_*`` para o Connect).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import busca
import casos
import chamados
import guardrails
import respostas
from config import MAX_TENTATIVAS_VALIDACAO

logger = logging.getLogger("sd_fulfillment")
if not logger.handlers:
    logger.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Utilitários do protocolo de resposta do Amazon Lex V2
# --------------------------------------------------------------------------- #
def _ler_slot(slots: dict[str, Any] | None, nome: str) -> str | None:
    if not slots or nome not in slots or slots[nome] is None:
        return None
    valor_obj = slots[nome].get("value") or {}
    interpretado = valor_obj.get("interpretedValue") or valor_obj.get("originalValue")
    return str(interpretado).strip() if interpretado else None


def _definir_slot(slots: dict[str, Any], nome: str, valor: str | None) -> None:
    if valor is None:
        slots[nome] = None
    else:
        slots[nome] = {
            "shape": "Scalar",
            "value": {"originalValue": valor, "interpretedValue": valor, "resolvedValues": [valor]},
        }


def _canal_evento(evento: dict[str, Any], sess_attrs: dict[str, str]) -> str:
    if sess_attrs.get("sd_canal") in {"VOICE", "CHAT"}:
        return sess_attrs["sd_canal"]
    modo = str(evento.get("inputMode", "Text")).upper()
    return "VOICE" if modo == "SPEECH" else "CHAT"


def _atributos_base(sess_attrs: dict[str, str], canal: str, intencao: str) -> dict[str, str]:
    attrs = dict(sess_attrs)
    attrs.setdefault("sd_versao_fluxo", "v1.0.0")
    attrs["sd_canal"] = canal
    attrs.setdefault("sd_idioma", "pt-BR")
    attrs["sd_intencao"] = intencao
    attrs["sd_categoria"] = chamados.categorizar_intencao(intencao)
    attrs.setdefault("sd_guardrail_acionado", "NENHUM")
    attrs.setdefault("sd_tentativas_validacao", "0")
    attrs.setdefault("sd_identidade_validada", "false")
    attrs.setdefault("sd_resolvido_bot", "false")
    return attrs


def _resposta_elicit_slot(
    intencao_nome: str,
    slots: dict[str, Any],
    slot_alvo: str,
    sess_attrs: dict[str, str],
    msg_chat: str,
    msg_voz: str | None = None,
) -> dict[str, Any]:
    canal = sess_attrs.get("sd_canal", "CHAT")
    return {
        "sessionState": {
            "sessionAttributes": sess_attrs,
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot_alvo},
            "intent": {"name": intencao_nome, "slots": slots, "state": "InProgress"},
        },
        "messages": respostas.montar_mensagens_lex(msg_chat, msg_voz, canal),
    }


def _resposta_close(
    intencao_nome: str,
    slots: dict[str, Any],
    sess_attrs: dict[str, str],
    msg_chat: str,
    msg_voz: str | None = None,
    estado: str = "Fulfilled",
) -> dict[str, Any]:
    canal = sess_attrs.get("sd_canal", "CHAT")
    return {
        "sessionState": {
            "sessionAttributes": sess_attrs,
            "dialogAction": {"type": "Close"},
            "intent": {"name": intencao_nome, "slots": slots, "state": estado},
        },
        "messages": respostas.montar_mensagens_lex(msg_chat, msg_voz, canal),
    }


# --------------------------------------------------------------------------- #
# Identificação e validação do colaborador
# --------------------------------------------------------------------------- #
def _preencher_atributos_colaborador(
    sess_attrs: dict[str, str], colaborador: dict[str, Any]
) -> None:
    sess_attrs["sd_matricula"] = colaborador["matricula"]
    sess_attrs["sd_colaborador_nome"] = colaborador["primeiro_nome"]
    sess_attrs["sd_unidade"] = colaborador["unidade"]


def _resolver_colaborador(
    slots: dict[str, Any], texto_entrada: str, sess_attrs: dict[str, str]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Localiza colaborador por slot/sessão/texto ou devolve lista de homônimos."""
    matricula = (
        _ler_slot(slots, "Matricula")
        or sess_attrs.get("sd_matricula")
        or busca.extrair_matricula(texto_entrada)
    )
    if matricula:
        col = busca.buscar_colaborador_por_matricula(matricula)
        if col:
            _definir_slot(slots, "Matricula", col["matricula"])
            return col, [col]

    nome_slot = _ler_slot(slots, "NomeColaborador")
    if nome_slot:
        candidatos = busca.buscar_colaboradores_por_nome(nome_slot)
        if len(candidatos) == 1:
            _definir_slot(slots, "Matricula", candidatos[0]["matricula"])
            return candidatos[0], candidatos
        if len(candidatos) > 1:
            return None, candidatos

    return None, []


# --------------------------------------------------------------------------- #
# Handlers por intenção
# --------------------------------------------------------------------------- #
def _tratar_password_reset(
    intencao_nome: str,
    slots: dict[str, Any],
    texto_entrada: str,
    sess_attrs: dict[str, str],
) -> dict[str, Any]:
    sess_attrs["sd_subcategoria"] = "SENHA_AD"
    sess_attrs["sd_impacto"] = "INDIVIDUAL"

    colaborador, candidatos = _resolver_colaborador(slots, texto_entrada, sess_attrs)
    if not colaborador:
        chat, voz = respostas.msg_solicitar_matricula(candidatos if len(candidatos) > 1 else None)
        return _resposta_elicit_slot(intencao_nome, slots, "Matricula", sess_attrs, chat, voz)

    _preencher_atributos_colaborador(sess_attrs, colaborador)

    if colaborador["status_conta"] == "INATIVO":
        protocolo = chamados.gerar_protocolo_deterministico(
            colaborador["matricula"], intencao_nome, "CONTA_INATIVA"
        )
        prioridade = chamados.calcular_prioridade_itil(
            intencao_nome, status_conta="INATIVO", vip_diretoria=colaborador["vip_diretoria"]
        )
        sess_attrs.update(
            {
                "sd_identidade_validada": "false",
                "sd_prioridade": prioridade,
                "sd_protocolo": protocolo,
                "sd_proxima_acao": "TRANSBORDO",
                "sd_fila_destino": "SEGURANCA",
                "sd_motivo_transbordo": "FALHA_VALIDACAO",
                "sd_resumo": chamados.montar_resumo_contexto(
                    colaborador, intencao_nome, prioridade, "Tentativa de reset em conta INATIVA."
                ),
            }
        )
        chat, voz = respostas.msg_reset_senha(colaborador, protocolo, prioridade)
        return _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)

    pin_informado = _ler_slot(slots, "PinVerificacao")
    if not pin_informado:
        chat, voz = respostas.msg_solicitar_pin(colaborador["primeiro_nome"])
        return _resposta_elicit_slot(intencao_nome, slots, "PinVerificacao", sess_attrs, chat, voz)

    if pin_informado != colaborador["pin_verificacao"]:
        tentativas = int(sess_attrs.get("sd_tentativas_validacao", "0")) + 1
        sess_attrs["sd_tentativas_validacao"] = str(tentativas)
        _definir_slot(slots, "PinVerificacao", None)

        if tentativas >= MAX_TENTATIVAS_VALIDACAO:
            protocolo = chamados.gerar_protocolo_deterministico(
                colaborador["matricula"], intencao_nome, "PIN_EXCEDIDO"
            )
            sess_attrs.update(
                {
                    "sd_identidade_validada": "false",
                    "sd_prioridade": "P2",
                    "sd_protocolo": protocolo,
                    "sd_proxima_acao": "TRANSBORDO",
                    "sd_fila_destino": "SEGURANCA",
                    "sd_motivo_transbordo": "FALHA_VALIDACAO",
                    "sd_resumo": chamados.montar_resumo_contexto(
                        colaborador,
                        intencao_nome,
                        "P2",
                        f"Excedeu {MAX_TENTATIVAS_VALIDACAO} tentativas de PIN.",
                    ),
                }
            )
            chat = (
                f"{colaborador['primeiro_nome']}, o PIN informado não confere após "
                f"{MAX_TENTATIVAS_VALIDACAO} tentativas. Por segurança, gerei o protocolo "
                f"{protocolo} e estou transferindo você para a Fila de Segurança validar sua "
                "identidade com um analista."
            )
            return _resposta_close(intencao_nome, slots, sess_attrs, chat, chat)

        restantes = MAX_TENTATIVAS_VALIDACAO - tentativas
        chat = (
            f"O PIN informado não confere (restam {restantes} tentativa(s)). "
            "Por favor, informe novamente seu PIN de verificação de 4 dígitos."
        )
        return _resposta_elicit_slot(intencao_nome, slots, "PinVerificacao", sess_attrs, chat, chat)

    # Identidade validada com sucesso
    sess_attrs["sd_identidade_validada"] = "true"
    incidente = busca.buscar_incidente_ativo(
        colaborador["unidade"], categoria="ACESSO_SEGURANCA", subcategoria="SENHA_AD"
    )
    prioridade = chamados.calcular_prioridade_itil(
        intencao_nome,
        vip_diretoria=colaborador["vip_diretoria"],
        status_conta=colaborador["status_conta"],
        incidente_vinculado=incidente is not None,
    )
    fila = chamados.determinar_fila_destino(intencao_nome, prioridade)
    protocolo = chamados.gerar_protocolo_deterministico(
        colaborador["matricula"], intencao_nome, colaborador["status_conta"]
    )
    if incidente:
        sess_attrs["sd_incidente_vinculado"] = incidente["id"]

    sess_attrs.update(
        {
            "sd_prioridade": prioridade,
            "sd_protocolo": protocolo,
            "sd_proxima_acao": "TRANSBORDO",
            "sd_fila_destino": fila,
            "sd_motivo_transbordo": "ROTEAMENTO_INTENCAO",
            "sd_resumo": chamados.montar_resumo_contexto(
                colaborador,
                intencao_nome,
                prioridade,
                f"Reset de senha AD (status={colaborador['status_conta']}, identidade validada).",
                incidente["id"] if incidente else None,
            ),
        }
    )
    chat, voz = respostas.msg_reset_senha(colaborador, protocolo, prioridade, incidente)
    return _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)


def _tratar_network_issue(
    intencao_nome: str,
    slots: dict[str, Any],
    texto_entrada: str,
    sess_attrs: dict[str, str],
) -> dict[str, Any]:
    colaborador, candidatos = _resolver_colaborador(slots, texto_entrada, sess_attrs)
    if not colaborador:
        chat, voz = respostas.msg_solicitar_matricula(candidatos if len(candidatos) > 1 else None)
        return _resposta_elicit_slot(intencao_nome, slots, "Matricula", sess_attrs, chat, voz)

    _preencher_atributos_colaborador(sess_attrs, colaborador)

    subcat_bruta = _ler_slot(slots, "TipoProblemaRede") or texto_entrada
    subcategoria = busca.inferir_subcategoria_rede(subcat_bruta)
    _definir_slot(slots, "TipoProblemaRede", subcategoria)

    impacto_bruto = _ler_slot(slots, "EscopoImpacto") or texto_entrada
    impacto = busca.inferir_impacto(impacto_bruto)
    _definir_slot(slots, "EscopoImpacto", impacto)

    incidente = busca.buscar_incidente_ativo(
        colaborador["unidade"], categoria="REDE_CONECTIVIDADE", subcategoria=subcategoria
    ) or busca.buscar_incidente_ativo(colaborador["unidade"], categoria="REDE_CONECTIVIDADE")

    prioridade = chamados.calcular_prioridade_itil(
        intencao_nome,
        impacto=impacto,
        vip_diretoria=colaborador["vip_diretoria"],
        incidente_vinculado=incidente is not None,
    )
    fila = chamados.determinar_fila_destino(intencao_nome, prioridade)
    protocolo = chamados.gerar_protocolo_deterministico(
        colaborador["matricula"], intencao_nome, f"{subcategoria}:{impacto}"
    )

    if incidente:
        sess_attrs["sd_incidente_vinculado"] = incidente["id"]

    sess_attrs.update(
        {
            "sd_subcategoria": subcategoria,
            "sd_impacto": impacto,
            "sd_prioridade": prioridade,
            "sd_protocolo": protocolo,
            "sd_proxima_acao": "TRANSBORDO",
            "sd_fila_destino": fila,
            "sd_motivo_transbordo": "ROTEAMENTO_INTENCAO",
            "sd_resumo": chamados.montar_resumo_contexto(
                colaborador,
                intencao_nome,
                prioridade,
                f"Falha de rede ({subcategoria}, impacto={impacto}).",
                incidente["id"] if incidente else None,
            ),
        }
    )
    chat, voz = respostas.msg_problema_rede(
        colaborador, subcategoria, impacto, prioridade, protocolo, incidente
    )
    return _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)


def _tratar_hardware_request(
    intencao_nome: str,
    slots: dict[str, Any],
    texto_entrada: str,
    sess_attrs: dict[str, str],
) -> dict[str, Any]:
    colaborador, candidatos = _resolver_colaborador(slots, texto_entrada, sess_attrs)
    if not colaborador:
        chat, voz = respostas.msg_solicitar_matricula(candidatos if len(candidatos) > 1 else None)
        return _resposta_elicit_slot(intencao_nome, slots, "Matricula", sess_attrs, chat, voz)

    _preencher_atributos_colaborador(sess_attrs, colaborador)

    termo_eq = _ler_slot(slots, "Equipamento") or texto_entrada
    item = busca.buscar_item_catalogo(termo_eq)
    if not item:
        chat = (
            f"{colaborador['primeiro_nome']}, qual equipamento do catálogo você deseja solicitar? "
            "(Exemplos: Notebook Padrão, Notebook Dev, Monitor 24, Monitor 27 4K, Headset USB, "
            "Teclado, Mouse, Docking USB-C, Webcam, Celular Corporativo ou YubiKey)."
        )
        voz = (
            f"{colaborador['primeiro_nome']}, qual equipamento você deseja solicitar? "
            "Por exemplo: notebook, monitor, headset, teclado, mouse ou celular corporativo."
        )
        return _resposta_elicit_slot(intencao_nome, slots, "Equipamento", sess_attrs, chat, voz)

    _definir_slot(slots, "Equipamento", item["codigo"])
    unidade = busca.buscar_unidade(colaborador["unidade"])
    avaliacao = chamados.avaliar_solicitacao_hardware(item, unidade)

    prioridade = chamados.calcular_prioridade_itil(
        intencao_nome, vip_diretoria=colaborador["vip_diretoria"]
    )
    protocolo = chamados.gerar_protocolo_deterministico(
        colaborador["matricula"], intencao_nome, item["codigo"]
    )
    resumo = chamados.montar_resumo_contexto(
        colaborador,
        intencao_nome,
        prioridade,
        f"Pedido de {item['codigo']} ({avaliacao['estoque_status']}, "
        f"SLA={avaliacao['prazo_dias_uteis']}d, {avaliacao['modalidade_entrega']}).",
    )
    caso = casos.criar_caso_connect(
        protocolo=protocolo,
        titulo=f"Solicitação de {item['nome']} - {colaborador['matricula']}",
        categoria="HARDWARE",
        prioridade=prioridade,
        resumo=resumo,
        status_inicial=avaliacao["status_caso"],
    )

    sem_estoque = avaliacao["estoque_status"] == "INDISPONIVEL"
    sess_attrs.update(
        {
            "sd_subcategoria": item["categoria"],
            "sd_impacto": "INDIVIDUAL",
            "sd_equipamento": item["codigo"],
            "sd_estoque_status": avaliacao["estoque_status"],
            "sd_prioridade": prioridade,
            "sd_protocolo": protocolo,
            "sd_caso_id": caso.case_id,
            "sd_proxima_acao": "TRANSBORDO" if sem_estoque else "CRIAR_CASO",
            "sd_fila_destino": "HARDWARE",
            "sd_motivo_transbordo": "SEM_ESTOQUE" if sem_estoque else "ROTEAMENTO_INTENCAO",
            "sd_resolvido_bot": "false" if sem_estoque else "true",
            "sd_resumo": resumo,
        }
    )
    chat, voz = respostas.msg_solicitacao_hardware(
        colaborador, avaliacao, protocolo, caso.case_id, prioridade
    )
    return _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)


def _tratar_consulta_status(
    intencao_nome: str,
    slots: dict[str, Any],
    texto_entrada: str,
    sess_attrs: dict[str, str],
) -> dict[str, Any]:
    protocolo = _ler_slot(slots, "Protocolo") or busca.extrair_protocolo(texto_entrada)
    matricula = (
        _ler_slot(slots, "Matricula")
        or sess_attrs.get("sd_matricula")
        or busca.extrair_matricula(texto_entrada)
    )

    chamado: dict[str, Any] | None = None
    referencia = protocolo or matricula or ""

    if protocolo:
        _definir_slot(slots, "Protocolo", protocolo)
        chamado = busca.buscar_chamado_por_protocolo(protocolo)
    elif matricula:
        _definir_slot(slots, "Matricula", matricula)
        encontrados = busca.listar_chamados_por_matricula(matricula)
        chamado = encontrados[0] if encontrados else None
    else:
        chat = (
            "Para consultar o andamento, informe o número do protocolo "
            "(formato SD-AAAAMMDD-XXXXXX) ou sua matrícula (formato NTxxxx)."
        )
        return _resposta_elicit_slot(intencao_nome, slots, "Protocolo", sess_attrs, chat, chat)

    if chamado:
        sess_attrs.update(
            {
                "sd_protocolo": chamado["protocolo"],
                "sd_matricula": chamado["matricula"],
                "sd_prioridade": chamado["prioridade"],
                "sd_fila_destino": chamado["fila_destino"],
                "sd_proxima_acao": "ENCERRAR",
                "sd_resolvido_bot": "true",
                "sd_resumo": chamado["resumo"],
            }
        )
    else:
        sess_attrs.update(
            {
                "sd_proxima_acao": "ENCERRAR",
                "sd_resolvido_bot": "false",
                "sd_resumo": f"Consulta sem resultado para referência '{referencia}'.",
            }
        )

    chat, voz = respostas.msg_status_chamado(chamado, referencia)
    return _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)


def _tratar_transbordo_direto(
    intencao_nome: str,
    slots: dict[str, Any],
    texto_entrada: str,
    sess_attrs: dict[str, str],
) -> dict[str, Any]:
    colaborador, _ = _resolver_colaborador(slots, texto_entrada, sess_attrs)
    if colaborador:
        _preencher_atributos_colaborador(sess_attrs, colaborador)

    motivo = (
        "SOLICITACAO_COLABORADOR" if intencao_nome == "FalarComAtendente" else "BAIXA_CONFIANCA"
    )
    prioridade = "P2" if (colaborador and colaborador.get("vip_diretoria")) else "P3"
    sess_attrs.update(
        {
            "sd_prioridade": prioridade,
            "sd_proxima_acao": "TRANSBORDO",
            "sd_fila_destino": "GERAL_N1",
            "sd_motivo_transbordo": motivo,
            "sd_resolvido_bot": "false",
            "sd_resumo": chamados.montar_resumo_contexto(
                colaborador,
                intencao_nome,
                prioridade,
                texto_entrada or "Solicitação de atendimento humano N1.",
            ),
        }
    )
    chat = (
        "Compreendido! Estou transferindo você para um analista do Service Desk N1 e "
        "já encaminhei o histórico desta conversa para agilizar seu atendimento."
    )
    return _resposta_close(intencao_nome, slots, sess_attrs, chat, chat)


_HANDLERS_INTENCAO = {
    "PasswordReset": _tratar_password_reset,
    "NetworkIssue": _tratar_network_issue,
    "HardwareRequest": _tratar_hardware_request,
    "ConsultarStatusChamado": _tratar_consulta_status,
}


# --------------------------------------------------------------------------- #
# Entrypoint AWS Lambda
# --------------------------------------------------------------------------- #
def _registrar_log_estruturado(
    evento: dict[str, Any],
    resposta: dict[str, Any],
    intencao_nome: str,
    latencia_ms: float,
) -> None:
    """Emite log JSON estruturado sem dados pessoais (Zero-PII) para CloudWatch."""
    sess_state = resposta.get("sessionState") or {}
    attrs = sess_state.get("sessionAttributes") or {}
    dialog = sess_state.get("dialogAction") or {}
    payload = {
        "evento": "lex_fulfillment",
        "session_id": str(evento.get("sessionId") or "")[:24],
        "canal": attrs.get("sd_canal", ""),
        "intencao": intencao_nome,
        "dialog_action": dialog.get("type", ""),
        "fila_destino": attrs.get("sd_fila_destino", ""),
        "prioridade": attrs.get("sd_prioridade", ""),
        "proxima_acao": attrs.get("sd_proxima_acao", ""),
        "resolvido_bot": attrs.get("sd_resolvido_bot", ""),
        "guardrail": attrs.get("sd_guardrail_acionado", "NENHUM"),
        "latencia_ms": round(latencia_ms, 2),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _executar_roteamento(evento: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    session_state = evento.get("sessionState") or {}
    sess_in = session_state.get("sessionAttributes") or {}
    intent_obj = session_state.get("intent") or {}
    intencao_nome = str(intent_obj.get("name") or "FallbackIntent")
    slots: dict[str, Any] = dict(intent_obj.get("slots") or {})
    texto_bruto = str(evento.get("inputTranscript") or "")

    canal = _canal_evento(evento, sess_in)
    sess_attrs = _atributos_base(sess_in, canal, intencao_nome)

    # 1. Camada de Guardrails (sempre executada primeiro)
    avaliacao_gr = guardrails.avaliar_entrada(texto_bruto)
    if avaliacao_gr.acionado != "NENHUM":
        sess_attrs["sd_guardrail_acionado"] = avaliacao_gr.acionado

    if avaliacao_gr.acionado == "EMERGENCIA":
        colaborador, _ = _resolver_colaborador(slots, avaliacao_gr.texto_sanitizado, sess_attrs)
        if colaborador:
            _preencher_atributos_colaborador(sess_attrs, colaborador)
        matricula_ref = colaborador["matricula"] if colaborador else "ANON0000"
        protocolo = chamados.gerar_protocolo_deterministico(
            matricula_ref, "EmergenciaSeguranca", avaliacao_gr.motivo
        )
        sess_attrs.update(
            {
                "sd_categoria": "ACESSO_SEGURANCA",
                "sd_prioridade": "P1",
                "sd_protocolo": protocolo,
                "sd_proxima_acao": "TRANSBORDO",
                "sd_fila_destino": "PRIORITARIA_P1",
                "sd_motivo_transbordo": "EMERGENCIA_SEGURANCA",
                "sd_resolvido_bot": "false",
                "sd_resumo": chamados.montar_resumo_contexto(
                    colaborador,
                    intencao_nome,
                    "P1",
                    f"EMERGÊNCIA CSIRT: {avaliacao_gr.texto_sanitizado}",
                ),
            }
        )
        chat, voz = respostas.msg_emergencia_seguranca()
        return intencao_nome, _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)

    if avaliacao_gr.acionado == "INJECAO":
        sess_attrs.update(
            {
                "sd_prioridade": "P4",
                "sd_proxima_acao": "ENCERRAR",
                "sd_resolvido_bot": "false",
                "sd_resumo": "Interação bloqueada pelo guardrail anti-injeção.",
            }
        )
        chat, voz = respostas.msg_bloqueio_injecao()
        return intencao_nome, _resposta_close(intencao_nome, slots, sess_attrs, chat, voz)

    # 2. Roteamento por intenção via tabela de despacho
    fn_handler = _HANDLERS_INTENCAO.get(intencao_nome, _tratar_transbordo_direto)
    return intencao_nome, fn_handler(
        intencao_nome, slots, avaliacao_gr.texto_sanitizado, sess_attrs
    )


def lambda_handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    """Entrypoint oficial AWS Lambda para eventos do Amazon Lex V2."""
    del contexto  # não utilizado; mantido pela assinatura padrão da AWS Lambda
    inicio = time.perf_counter()
    intencao_nome, resposta = _executar_roteamento(evento)
    latencia_ms = (time.perf_counter() - inicio) * 1000
    _registrar_log_estruturado(evento, resposta, intencao_nome, latencia_ms)
    return resposta
