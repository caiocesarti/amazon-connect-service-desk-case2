/**
 * Simulador de Contato — Amazon Connect Service Desk (Case 2)
 *
 * Papéis simulados no navegador:
 *   - Lex V2 (NLU): classifica a intenção por similaridade com os `sampleUtterances` do
 *     lex/bot-export.json (servidos por /api/config) e conduz a elicitação de slots.
 *   - Contact Flow SD-Entrada-Principal: define atributos, roteia para a fila e cria o Case.
 *   - Contact Lens: sentimento por turno (léxico pt-BR) + regras de connect/contact-lens/regras.json.
 *
 * O fulfillment NÃO é simulado: cada turno chama POST /api/lex, que executa a Lambda real
 * (lambda/sd_fulfillment/handler.py). Filas, regras e metas vêm dos arquivos versionados.
 * Métricas ficam apenas em memória (reprodutível); TMA = tempo real de relógio da sessão.
 */
(function () {
  "use strict";

  /* ------------------------------ utilidades ------------------------------ */
  function $(id) {
    return document.getElementById(id);
  }
  function esc(t) {
    return String(t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function norm(t) {
    return String(t || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }
  function sleep(ms) {
    return new Promise(function (r) {
      window.setTimeout(r, ms);
    });
  }
  function fmtDur(ms) {
    var s = ms / 1000;
    var m = Math.floor(s / 60);
    var resto = s - m * 60;
    return String(m).padStart(2, "0") + ":" + resto.toFixed(1).padStart(4, "0");
  }
  function fmtSeg(s) {
    var m = Math.floor(s / 60);
    return String(m).padStart(2, "0") + "m " + String(Math.round(s % 60)).padStart(2, "0") + "s";
  }

  var RE_MATRICULA = /\bNT\d{4}\b/i;
  var RE_PIN = /\b\d{4}\b/;
  var PASSO_MS = 220;

  /* ------------------------------ estado ------------------------------ */
  var CFG = null;
  var sessao = null;
  var contador = 0;
  var cronometroId = null;
  var ocupado = false;
  var cancelarCenario = false;
  var ultimaFala = "";
  var metricas = novasMetricas();

  function novasMetricas() {
    return {
      fechadas: 4,
      fcr: 3,
      duracoesMs: [92000, 114000, 88000, 138000],
      porFila: {
        SEGURANCA: 2,
        REDES: 1,
        HARDWARE: 1,
        GERAL_N1: 0,
        PRIORITARIA_P1: 0
      },
      cases: [
        {
          protocolo: "SD-20261115-4F9A2C",
          campos: {
            title: "Diagnóstico de Rede e VPN (NT1007)",
            sd_categoria: "REDE_CONECTIVIDADE",
            sd_prioridade: "P2",
            sd_fila_destino: "REDES",
            summary: "Marina (NT1007, REC) — Instabilidade na VPN corporativa vinculada ao incidente INC-0002."
          }
        },
        {
          protocolo: "SD-20261114-1A2B3C",
          campos: {
            title: "Solicitação de Equipamento (NT1001)",
            sd_categoria: "HARDWARE",
            sd_prioridade: "P4",
            sd_fila_destino: "HARDWARE",
            summary: "Ana (NT1001, SPO) — Pedido de Headset USB entregue no posto de trabalho."
          }
        }
      ],
      ultimoSentimento: null
    };
  }

  var CENARIOS = {
    PasswordReset: ["esqueci minha senha", "NT1001", "4821"],
    NetworkIssue: ["estou sem internet", "NT1011 toda a filial esta sem internet"],
    HardwareRequest: ["quero solicitar um headset", "NT1001"],
    Consulta: ["consultar protocolo SD-20261115-4F9A2C"],
    Emergencia: [
      "NT1002 cliquei em um link suspeito de phishing e meu notebook esta travado, e urgente"
    ],
    Atendente: ["quero falar com um atendente, ninguem resolve meu problema, isso e um absurdo"]
  };

  /* ------------------------------ Lex NLU (simulado) ------------------------------ */
  var REFORCOS = {
    PasswordReset: ["senha", "password", "bloqueou", "expirou"],
    NetworkIssue: ["internet", "vpn", "wi-fi", "wifi", "rede", "conectar"],
    HardwareRequest: ["notebook", "monitor", "headset", "equipamento", "teclado", "mouse", "yubikey"],
    ConsultarStatusChamado: ["protocolo", "chamado", "status", "pedido"],
    FalarComAtendente: ["atendente", "humano", "analista", "tecnico", "suporte humano"]
  };

  function tokens(t) {
    return norm(t)
      .replace(/\{[^}]*\}/g, " ")
      .split(/[^a-z0-9-]+/)
      .filter(function (w) {
        return w.length > 2;
      });
  }

  function classificar(texto) {
    var tt = tokens(texto);
    var melhor = { nome: "FallbackIntent", confianca: 0.3 };
    CFG.intents.forEach(function (it) {
      if (it.nome === "FallbackIntent") {
        return;
      }
      var maxSim = 0;
      it.exemplos.forEach(function (ex) {
        var te = tokens(ex);
        if (!te.length) {
          return;
        }
        var acertos = te.filter(function (w) {
          return tt.indexOf(w) !== -1;
        }).length;
        maxSim = Math.max(maxSim, acertos / te.length);
      });
      var n = norm(texto);
      var reforco = (REFORCOS[it.nome] || []).some(function (k) {
        return n.indexOf(k) !== -1;
      });
      var conf = Math.min(0.99, 0.35 + maxSim * 0.55 + (reforco ? 0.25 : 0));
      if (conf > melhor.confianca) {
        melhor = { nome: it.nome, confianca: conf };
      }
    });
    if (melhor.confianca < CFG.nlu_threshold) {
      return { nome: "FallbackIntent", confianca: melhor.confianca };
    }
    return melhor;
  }

  /* Slots enumerados (lex/slot-types.json): resolve sinônimos citados na própria frase. */
  function extrairSlots(nomeIntent, texto) {
    var slots = {};
    var intent = CFG.intents.filter(function (i) {
      return i.nome === nomeIntent;
    })[0];
    if (!intent) {
      return slots;
    }
    var n = norm(texto);
    intent.slots.forEach(function (s) {
      var valores = CFG.slot_types[s.tipo];
      if (!valores) {
        return;
      }
      var melhorValor = null;
      var melhorTam = 0;
      valores.forEach(function (v) {
        v.sinonimos.concat([v.valor]).forEach(function (sin) {
          var ns = norm(sin);
          if (ns.length > melhorTam && n.indexOf(ns) !== -1) {
            melhorTam = ns.length;
            melhorValor = v.valor;
          }
        });
      });
      if (melhorValor) {
        slots[s.nome] = {
          shape: "Scalar",
          value: { originalValue: melhorValor, interpretedValue: melhorValor, resolvedValues: [melhorValor] }
        };
      }
    });
    return slots;
  }

  /* ------------------------------ Contact Lens (simulado) ------------------------------ */
  var LEXICO = [
    ["ninguem resolve", -3],
    ["absurdo", -3],
    ["inaceitavel", -3],
    ["pessimo", -3],
    ["irritado", -2],
    ["parado", -2],
    ["nao funciona", -2],
    ["grave", -2],
    ["vazou", -2],
    ["urgente", -1],
    ["nao consigo", -1],
    ["demora", -1],
    ["caiu", -1],
    ["bloqueou", -1],
    ["travado", -1],
    ["funcionou", 3],
    ["perfeito", 3],
    ["otimo", 3],
    ["resolvido", 3],
    ["obrigad", 2],
    ["valeu", 2]
  ];

  function pontuarSentimento(texto) {
    var n = norm(texto);
    var s = 0;
    LEXICO.forEach(function (p) {
      if (n.indexOf(p[0]) !== -1) {
        s += p[1];
      }
    });
    return Math.max(-5, Math.min(5, s));
  }

  function rotuloSentimento(score) {
    if (score <= -2) {
      return { txt: "Crítico", cls: "alerta", icone: "🔴" };
    }
    if (score >= 2) {
      return { txt: "Satisfeito", cls: "verde", icone: "🟢" };
    }
    return { txt: "Neutro", cls: "ciano", icone: "🔵" };
  }

  function avaliarRegras(sess) {
    var disparadas = [];
    var textoTodo = norm(
      sess.transcricao
        .map(function (l) {
          return l.texto;
        })
        .join(" ")
    );
    var mediaCliente = sess.scores.length
      ? sess.scores.reduce(function (a, b) {
          return a + b;
        }, 0) / sess.scores.length
      : 0;
    (CFG.contact_lens.regras || []).forEach(function (r) {
      var acao = (r.acoes || [])
        .map(function (a) {
          return a.categoria || a.tipo;
        })
        .join(", ");
      if (r.condicao && r.condicao.sentimentoCliente === "NEGATIVE") {
        if (mediaCliente <= r.condicao.scoreMaximo) {
          disparadas.push({ nome: r.nome, acao: acao });
        }
      } else if (r.palavrasChave) {
        var achou = r.palavrasChave.some(function (k) {
          return textoTodo.indexOf(norm(k)) !== -1;
        });
        if (achou) {
          disparadas.push({ nome: r.nome, acao: acao });
        }
      }
    });
    return { media: mediaCliente, regras: disparadas };
  }

  /* ------------------------------ renderização: timeline ------------------------------ */
  function limparTimeline() {
    $("lista-timeline").innerHTML = "";
  }

  async function passo(titulo, detalhe, tipo, duracao) {
    var li = document.createElement("li");
    li.className = "passo " + (tipo || "ok");
    li.innerHTML =
      '<span class="passo-marca" aria-hidden="true"></span><div class="passo-corpo"><strong>' +
      titulo +
      "</strong>" +
      (detalhe ? "<small>" + detalhe + "</small>" : "") +
      "</div>" +
      (duracao ? '<span class="passo-tempo">' + duracao + "</span>" : "");
    var lista = $("lista-timeline");
    lista.appendChild(li);
    lista.scrollTop = lista.scrollHeight;
    await sleep(PASSO_MS);
    return li;
  }

  function iniciarCronometro() {
    pararCronometro();
    cronometroId = window.setInterval(function () {
      if (sessao && !sessao.fechada) {
        $("cronometro").textContent = fmtDur(performance.now() - sessao.t0);
      }
    }, 100);
  }
  function pararCronometro() {
    if (cronometroId) {
      window.clearInterval(cronometroId);
      cronometroId = null;
    }
  }

  /* ------------------------------ renderização: painéis ------------------------------ */
  var NOMES_EQUIPES = {
    SEGURANCA: { nome: "Identidade & Acessos", escopo: "Senhas AD, SSO e MFA" },
    REDES: { nome: "Infraestrutura & Redes", escopo: "VPN, Wi-Fi e Conectividade" },
    HARDWARE: { nome: "Suporte a Equipamentos", escopo: "Notebooks e Periféricos" },
    GERAL_N1: { nome: "Atendimento Geral N1", escopo: "Suporte Técnico de 1º Nível" },
    PRIORITARIA_P1: { nome: "Plantão Crítico (P1 / VIP)", escopo: "Incidentes Graves e Diretoria" }
  };

  function renderFilas(ativa, regra) {
    var grade = $("grade-filas");
    var html = "";
    Object.keys(CFG.filas).forEach(function (chave) {
      var f = CFG.filas[chave];
      var amigavel = NOMES_EQUIPES[chave] || { nome: f.nome, escopo: f.descricao };
      html +=
        '<div class="item-fila' +
        (ativa === chave ? " ativa" : "") +
        '"><div class="fila-info"><strong>' +
        esc(amigavel.nome) +
        "</strong><small>" +
        esc(amigavel.escopo) +
        '</small></div><span class="badge-fila">' +
        (metricas.porFila[chave] || 0) +
        "</span></div>";
    });
    grade.innerHTML = html;
    $("regra-roteamento").textContent =
      regra || "Selecione ou digite uma solicitação ao lado para iniciar.";
  }

  var NOMES_CATEGORIAS = {
    ACESSO_SEGURANCA: "Acesso & Segurança",
    REDE_CONECTIVIDADE: "Redes & Conectividade",
    HARDWARE: "Equipamentos & Periféricos",
    GERAL: "Suporte Geral"
  };

  var NOMES_INTENTS_TITULO = {
    PasswordReset: "Redefinição de Senha Corporativa",
    NetworkIssue: "Diagnóstico de Rede e VPN",
    HardwareRequest: "Solicitação de Equipamento",
    ConsultarStatusChamado: "Consulta de Protocolo",
    FalarComAtendente: "Atendimento com Analista N1",
    FallbackIntent: "Solicitação de Suporte"
  };

  function formatarTituloCaso(tituloRaw) {
    var partes = String(tituloRaw || "").split(" - ");
    var intentOuTexto = partes[0] || "";
    var amigavel = NOMES_INTENTS_TITULO[intentOuTexto] || intentOuTexto;
    return partes.length > 1 ? amigavel + " (" + partes.slice(1).join(" - ") + ")" : amigavel;
  }

  function formatarResumoCaso(resumoRaw) {
    return String(resumoRaw || "")
      .replace(/^\[P\d\]\s*/i, "")
      .replace(/\s*-\s*(PasswordReset|NetworkIssue|HardwareRequest|ConsultarStatusChamado|FalarComAtendente|FallbackIntent):\s*/g, " — ")
      .replace(/HEADSET_USB/g, "Headset USB")
      .replace(/NOTEBOOK_PADRAO/g, "Notebook Corporativo 14\"")
      .replace(/NOTEBOOK_DEV/g, "Notebook Dev")
      .replace(/MONITOR_24/g, "Monitor 24\"")
      .replace(/MONITOR_27/g, "Monitor 27\" 4K")
      .replace(/TOKEN_YUBIKEY/g, "Chave YubiKey")
      .replace(/DISPONIVEL/g, "em estoque")
      .replace(/INDISPONIVEL/g, "sem estoque")
      .replace(/ENTREGA_PRESENCIAL_LOCAL/g, "entrega local")
      .replace(/REMESSA_LOGISTICA/g, "envio expresso")
      .replace(/status=ATIVO,\s*/g, "")
      .replace(/SLA=(\d+)d/g, "prazo de $1 dia(s) útil(eis)");
  }
  function limparJargaoMsg(texto) {
    return String(texto || "")
      .replace(/no Connect Cases!/g, "na Central de TI!")
      .replace(/\s*\|\s*Caso:\s*case-sim-[a-z0-9]+/gi, "")
      .replace(/Caso:\s*case-sim-[a-z0-9]+\s*\|\s*/gi, "")
      .replace(/Status:\s*ABERTO/g, "Status: Em andamento");
  }

  function renderCases() {
    var el = $("lista-chamados-container");
    var contColab = $("contador-meus-chamados");
    var badgeTab = $("badge-chamados-tab");
    if (contColab) {
      contColab.textContent = metricas.cases.length + " aberto(s)";
    }
    if (badgeTab) {
      badgeTab.textContent = String(metricas.cases.length);
    }
    if (!metricas.cases.length) {
      el.innerHTML =
        '<p class="vazio">Você ainda não possui solicitações abertas nesta sessão. Use o chat ao lado para iniciar.</p>';
    } else {
      el.innerHTML = metricas.cases
        .map(function (c) {
          var eq = NOMES_EQUIPES[c.campos.sd_fila_destino];
          var nomeEq = eq ? eq.nome : "Suporte N1";
          var catAmigavel = NOMES_CATEGORIAS[c.campos.sd_categoria] || c.campos.sd_categoria;
          var tituloAmigavel = formatarTituloCaso(c.campos.title);
          return (
            '<div class="item-chamado">' +
            '<div class="item-chamado-topo"><strong>' +
            esc(tituloAmigavel) +
            '</strong><span class="tag-status-chamado">Em andamento</span></div>' +
            '<p class="item-chamado-resumo">' +
            esc(formatarResumoCaso(c.campos.summary || "")) +
            "</p>" +
            '<div class="item-chamado-meta">' +
            "<span>Protocolo: <code>" +
            esc(c.protocolo) +
            "</code></span>" +
            "<span>Categoria: <strong>" +
            esc(catAmigavel) +
            "</strong></span>" +
            "<span>Prioridade: <strong>" +
            esc(c.campos.sd_prioridade) +
            "</strong></span>" +
            "<span>Equipe: <strong>" +
            esc(nomeEq) +
            "</strong></span>" +
            "</div></div>"
          );
        })
        .join("");
    }
    $("kpi-cases-total").textContent = String(metricas.cases.length);
    if (metricas.cases.length) {
      $("kpi-cases-prioridade").textContent =
        "Prioridade " + metricas.cases[0].campos.sd_prioridade;
    } else {
      $("kpi-cases-prioridade").textContent = "Hoje";
    }
  }

  function renderLens(sess) {
    var linhas = sess ? sess.transcricao : [];
    $("lens-transcricao").innerHTML = linhas.length
      ? linhas
          .map(function (l) {
            var r = rotuloSentimento(l.score);
            return (
              '<li><span class="lens-papel">' +
              esc(l.papel) +
              "</span><span class=\"lens-texto\">" +
              esc(l.texto) +
              "</span>" +
              (l.papel === "Cliente"
                ? '<span class="lens-sent ' + r.cls + '">' + r.icone + " " + l.score.toFixed(0) + "</span>"
                : "") +
              "</li>"
            );
          })
          .join("")
      : '<li class="vazio">Inicie uma conversa no Portal do Colaborador para acompanhar a transcrição em tempo real.</li>';
    var lista = $("lens-transcricao");
    lista.scrollTop = lista.scrollHeight;

    if (!sess || !sess.scores.length) {
      return;
    }
    var av = avaliarRegras(sess);
    var rot = rotuloSentimento(av.media);
    var pct = Math.round(((av.media + 5) / 10) * 100);
    var fill = $("barra-sentimento-fill");
    fill.style.width = pct + "%";
    fill.style.background =
      rot.cls === "alerta"
        ? "linear-gradient(90deg,#ef4444,#f59e0b)"
        : rot.cls === "verde"
          ? "linear-gradient(90deg,#4f46e5,#10b981)"
          : "linear-gradient(90deg,#4f46e5,#06b6d4)";
    $("lens-valor").textContent = rot.icone + " " + rot.txt;
    $("lens-regras").innerHTML = av.regras.length
      ? av.regras
          .map(function (r) {
            return "<li>Notificação de qualidade: <strong>" + esc(r.acao) + "</strong></li>";
          })
          .join("")
      : "";
    sess.avaliacao = av;
    $("kpi-sentimento-valor").textContent = rot.txt;
    var badge = $("kpi-sentimento-badge");
    badge.textContent = "Índice " + (av.media >= 0 ? "+" : "") + av.media.toFixed(1);
    badge.className = "tag-kpi " + (rot.cls === "verde" ? "" : rot.cls);
  }

  function renderKpis() {
    var m = metricas;
    var metaFcr = CFG.metricas.FCR.meta_percentual;
    var metaTma = CFG.metricas.TMA.meta_chat_segundos;
    if (m.fechadas === 0) {
      $("kpi-fcr-valor").textContent = "—";
      $("kpi-fcr-detalhe").textContent = "Nenhum atendimento finalizado";
      $("kpi-tma-valor").textContent = "—";
      $("kpi-tma-detalhe").textContent = "Tempo médio de resolução";
    } else {
      var pct = (m.fcr / m.fechadas) * 100;
      var media =
        m.duracoesMs.reduce(function (a, b) {
          return a + b;
        }, 0) /
        m.duracoesMs.length /
        1000;
      $("kpi-fcr-valor").textContent = pct.toFixed(1).replace(".", ",") + "%";
      $("kpi-fcr-detalhe").textContent =
        m.fcr + " de " + m.fechadas + " resolvidos no 1º contato";
      $("kpi-tma-valor").textContent = fmtSeg(media);
      $("kpi-tma-detalhe").textContent = m.fechadas + " atendimento(s) concluído(s)";
      $("kpi-fcr-tag").className = "tag-kpi " + (pct >= metaFcr ? "" : "alerta");
      $("kpi-tma-tag").className = "tag-kpi " + (media <= metaTma ? "" : "alerta");
    }
    $("kpi-fcr-tag").textContent = "Meta ≥ " + metaFcr + "%";
    $("kpi-tma-tag").textContent = "Meta ≤ " + fmtSeg(metaTma);
  }

  /* ------------------------------ chat ------------------------------ */
  function hora() {
    var d = new Date();
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }

  function bolha(remetente, html, extra) {
    var div = document.createElement("div");
    div.className = "msg-bolha " + (remetente === "bot" ? "msg-bot" : "msg-user");
    div.innerHTML =
      '<div class="msg-cabecalho"><strong>' +
      (remetente === "bot" ? "Suporte de TI" : "Você") +
      "</strong><span>" +
      hora() +
      '</span></div><div class="msg-texto">' +
      html +
      "</div>" +
      (extra ? '<div class="msg-card-protocolo">' + extra + "</div>" : "");
    var area = $("console-mensagens");
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
  }

  function falar(texto) {
    ultimaFala = texto;
    if (!("speechSynthesis" in window) || $("visor-voz-webrtc").classList.contains("oculto")) {
      return;
    }
    try {
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(texto);
      u.lang = "pt-BR";
      window.speechSynthesis.speak(u);
    } catch (_) {
      /* autoplay bloqueado */
    }
  }

  function modoVoz() {
    return $("tab-modo-voz").classList.contains("ativo");
  }

  /* ------------------------------ API ------------------------------ */
  async function chamarLambda(evento) {
    var t = performance.now();
    var resp = await fetch("/api/lex", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(evento)
    });
    if (!resp.ok) {
      throw new Error("HTTP " + resp.status);
    }
    var json = await resp.json();
    json._ms = Math.round(performance.now() - t);
    return json;
  }

  function textoMensagens(resp) {
    return (resp.messages || [])
      .map(function (m) {
        return m.content || "";
      })
      .filter(Boolean)
      .join(" ");
  }

  /* ------------------------------ fluxo de um turno ------------------------------ */
  function novaSessao() {
    contador += 1;
    sessao = {
      id: "sim-" + Date.now() + "-" + contador,
      numero: contador,
      t0: performance.now(),
      intent: null,
      slots: {},
      attrs: {},
      elicit: null,
      transcricao: [],
      scores: [],
      fechada: false
    };
    return sessao;
  }

  var ROTULO_INTENT = {
    PasswordReset: "Redefinição de Senha & Acesso",
    NetworkIssue: "Conectividade & VPN",
    HardwareRequest: "Solicitação de Equipamento",
    ConsultarStatusChamado: "Consulta de Protocolo",
    FalarComAtendente: "Atendimento com Analista",
    FallbackIntent: "Triagem Geral"
  };

  async function enviar(textoOriginal) {
    var texto = (textoOriginal || "").trim();
    if (!texto || ocupado || !CFG) {
      return;
    }
    ocupado = true;
    try {
      if (!sessao || sessao.fechada) {
        limparTimeline();
        novaSessao();
        iniciarCronometro();
        renderLens(null);
        $("lens-regras").innerHTML = "";
        await passo(
          "Atendimento #" + sessao.numero + " iniciado",
          "Canal: " + (modoVoz() ? "Voz" : "Chat"),
          "ok"
        );
      }

      var mascarado = sessao.elicit === "PinVerificacao" ? "••••" : texto;
      bolha("user", esc(mascarado));
      var s = pontuarSentimento(texto);
      sessao.scores.push(s);
      sessao.transcricao.push({ papel: "Cliente", texto: mascarado, score: s });
      renderLens(sessao);

      /* --- Classificação da solicitação e dados informados --- */
      if (sessao.elicit) {
        var preenchido = false;
        if (sessao.elicit === "PinVerificacao" && RE_PIN.test(texto)) {
          sessao.slots.PinVerificacao = {
            shape: "Scalar",
            value: { originalValue: texto.match(RE_PIN)[0], interpretedValue: texto.match(RE_PIN)[0], resolvedValues: [texto.match(RE_PIN)[0]] }
          };
          preenchido = true;
        } else if (sessao.elicit === "Matricula" && RE_MATRICULA.test(texto)) {
          var mat = texto.match(RE_MATRICULA)[0].toUpperCase();
          sessao.slots.Matricula = { shape: "Scalar", value: { originalValue: mat, interpretedValue: mat, resolvedValues: [mat] } };
          preenchido = true;
        }
        if (!preenchido) {
          var alt = classificar(texto);
          if (alt.nome !== "FallbackIntent" && alt.nome !== sessao.intent) {
            sessao.intent = alt.nome;
            sessao.slots = extrairSlots(alt.nome, texto);
            sessao.elicit = null;
            await passo("Assunto atualizado", ROTULO_INTENT[alt.nome] || alt.nome, "ok");
          }
        } else {
          await passo(
            "Informação validada",
            sessao.elicit === "PinVerificacao" ? "PIN de segurança confirmado" : "Matrícula identificada",
            "ok"
          );
        }
      } else {
        var cls = classificar(texto);
        sessao.intent = cls.nome;
        sessao.slots = extrairSlots(cls.nome, texto);
        await passo(
          "Assunto identificado",
          ROTULO_INTENT[cls.nome] || cls.nome,
          cls.nome === "FallbackIntent" ? "aviso" : "ok"
        );
      }

      /* --- Processamento no backend --- */
      var evento = {
        sessionId: sessao.id,
        inputTranscript: texto,
        inputMode: modoVoz() ? "Speech" : "Text",
        sessionState: {
          sessionAttributes: sessao.attrs,
          intent: { name: sessao.intent, slots: sessao.slots, state: "InProgress" }
        }
      };
      var resp;
      try {
        resp = await chamarLambda(evento);
      } catch (err) {
        await passo("Serviço temporariamente indisponível", esc(err.message), "erro");
        bolha("bot", "Não foi possível processar sua solicitação neste momento.");
        return;
      }
      var estado = resp.sessionState || {};
      sessao.attrs = estado.sessionAttributes || {};
      sessao.slots = (estado.intent && estado.intent.slots) || {};
      var a = sessao.attrs;
      await passo(
        "Validação cadastral concluída",
        a.sd_colaborador_nome ? "Colaborador: " + esc(a.sd_colaborador_nome) + " (" + esc(a.sd_matricula) + ")" : "Verificando dados",
        a.sd_guardrail_acionado && a.sd_guardrail_acionado !== "NENHUM" ? "aviso" : "ok",
        resp._ms + " ms"
      );

      var msgBot = limparJargaoMsg(textoMensagens(resp));
      var tipo = (estado.dialogAction || {}).type;
      var extra = "";
      if (a.sd_protocolo) {
        extra = "Protocolo <code>" + esc(a.sd_protocolo) + "</code> &bull; Prioridade <strong>" + esc(a.sd_prioridade || "-") + "</strong>";
      }
      bolha("bot", esc(msgBot), extra);
      sessao.transcricao.push({ papel: "Bot", texto: msgBot, score: 0 });
      renderLens(sessao);
      falar(msgBot);

      if (tipo === "ElicitSlot") {
        sessao.elicit = estado.dialogAction.slotToElicit;
        await passo(
          "Aguardando confirmação",
          sessao.elicit === "PinVerificacao" ? "Solicitado PIN de 4 dígitos" : "Solicitada matrícula corporativa",
          "pend"
        );
        return;
      }
      sessao.elicit = null;
      await finalizarContato(resp);
    } finally {
      ocupado = false;
    }
  }

  async function finalizarContato(resp) {
    var a = sessao.attrs;
    var fluxo = resp.flow || {};
    var filaChave = a.sd_fila_destino;
    var fila = CFG.filas[filaChave];
    var eq = NOMES_EQUIPES[filaChave];
    var nomeEquipe = eq ? eq.nome : fila ? fila.nome : "Suporte N1";

    if (fila) {
      var regra =
        a.sd_prioridade === "P1"
          ? "Prioridade Crítica P1 → " + nomeEquipe
          : (ROTULO_INTENT[a.sd_intencao] || "Solicitação") + " → " + nomeEquipe;
      metricas.porFila[filaChave] = (metricas.porFila[filaChave] || 0) + 1;
      renderFilas(filaChave, regra);
      await passo("Encaminhado para equipe", esc(nomeEquipe), "ok");
    }

    if (fluxo.caso) {
      metricas.cases.unshift(fluxo.caso);
      renderCases();
      await passo(
        "Chamado registrado",
        "Protocolo <code>" + esc(fluxo.caso.protocolo) + "</code> • Prioridade " + esc(fluxo.caso.campos.sd_prioridade),
        "ok"
      );
    }

    var resolvido = a.sd_resolvido_bot === "true";
    sessao.fechada = true;
    pararCronometro();
    var dur = performance.now() - sessao.t0;
    $("cronometro").textContent = fmtDur(dur);
    metricas.fechadas += 1;
    metricas.duracoesMs.push(dur);
    if (resolvido) {
      metricas.fcr += 1;
    }
    renderLens(sessao);
    renderKpis();
    await passo(
      resolvido ? "Resolvido no 1º contato" : "Atendimento transferido para especialista",
      "Duração: " + fmtDur(dur),
      "ok"
    );
  }

  /* ------------------------------ cenários ------------------------------ */
  async function rodarCenario(nome) {
    var turnos = CENARIOS[nome];
    if (!turnos || ocupado) {
      return;
    }
    sessao = null;
    for (var i = 0; i < turnos.length; i++) {
      if (cancelarCenario) {
        return;
      }
      await enviar(turnos[i]);
      await sleep(450);
    }
  }

  async function rodarTodos() {
    if (ocupado) {
      return;
    }
    cancelarCenario = false;
    var nomes = Object.keys(CENARIOS);
    for (var i = 0; i < nomes.length; i++) {
      if (cancelarCenario) {
        return;
      }
      await rodarCenario(nomes[i]);
      await sleep(600);
    }
  }

  function reiniciar() {
    cancelarCenario = true;
    pararCronometro();
    sessao = null;
    ocupado = false;
    metricas = novasMetricas();
    limparTimeline();
    $("console-mensagens").innerHTML = "";
    $("cronometro").textContent = "00:00.0";
    $("kpi-sentimento-valor").textContent = "Neutro";
    $("kpi-sentimento-badge").textContent = "Tempo real";
    $("lens-valor").textContent = "Aguardando";
    $("barra-sentimento-fill").style.width = "50%";
    $("lens-regras").innerHTML = "";
    renderLens(null);
    renderFilas(null, null);
    renderCases();
    renderKpis();
    boasVindas();
  }

  function boasVindas() {
    bolha(
      "bot",
      "Olá! Como posso ajudar você hoje? Selecione uma opção rápida acima (como <strong>Redefinir senha</strong>, <strong>Problema de rede</strong> ou <strong>Solicitar equipamento</strong>) ou descreva sua necessidade abaixo."
    );
  }

  /* ------------------------------ inicialização ------------------------------ */
  async function iniciar() {
    var chip = $("status-api");
    try {
      var r = await fetch("/api/config");
      if (!r.ok) {
        throw new Error("HTTP " + r.status);
      }
      CFG = await r.json();
      chip.innerHTML = '<span class="ponto-online"></span> Atendimento Online';
    } catch (err) {
      chip.textContent = "Serviço Indisponível";
      $("console-mensagens").innerHTML =
        '<div class="msg-bolha msg-bot"><div class="msg-texto">Não foi possível conectar ao serviço de atendimento local.</div></div>';
      return;
    }

    renderFilas(null, null);
    renderCases();
    renderLens(null);
    renderKpis();
    boasVindas();

    $("form-console-chat").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var v = $("input-console-msg").value;
      $("input-console-msg").value = "";
      enviar(v);
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-prompt-inicial]"), function (b) {
      b.addEventListener("click", function () {
        enviar(b.getAttribute("data-prompt-inicial"));
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-cenario]"), function (b) {
      b.addEventListener("click", function () {
        cancelarCenario = false;
        rodarCenario(b.getAttribute("data-cenario"));
      });
    });
    $("btn-rodar-todos").addEventListener("click", rodarTodos);
    $("btn-novo-contato").addEventListener("click", function () {
      if (!ocupado) {
        sessao = null;
        pararCronometro();
        limparTimeline();
        $("console-mensagens").innerHTML = "";
        $("cronometro").textContent = "00:00.0";
        renderLens(null);
        boasVindas();
      }
    });
    $("btn-reiniciar").addEventListener("click", reiniciar);

    $("tab-modo-chat").addEventListener("click", function () {
      $("tab-modo-chat").classList.add("ativo");
      $("tab-modo-voz").classList.remove("ativo");
      $("visor-voz-webrtc").classList.add("oculto");
    });
    $("tab-modo-voz").addEventListener("click", function () {
      $("tab-modo-voz").classList.add("ativo");
      $("tab-modo-chat").classList.remove("ativo");
      $("visor-voz-webrtc").classList.remove("oculto");
    });
    $("btn-ouvir-ultima").addEventListener("click", function () {
      if (ultimaFala && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        var u = new SpeechSynthesisUtterance(ultimaFala);
        u.lang = "pt-BR";
        window.speechSynthesis.speak(u);
      }
    });

    /* Alternância de Persona: Portal do Colaborador vs. Painel do Supervisor */
    var btnVisaoColab = $("btn-visao-colaborador");
    var btnVisaoSup = $("btn-visao-supervisor");
    var secColab = $("secao-colaborador");
    var secSup = $("secao-supervisor");
    if (btnVisaoColab && btnVisaoSup && secColab && secSup) {
      btnVisaoColab.addEventListener("click", function () {
        btnVisaoColab.classList.add("ativo");
        btnVisaoColab.setAttribute("aria-selected", "true");
        btnVisaoSup.classList.remove("ativo");
        btnVisaoSup.setAttribute("aria-selected", "false");
        secColab.classList.remove("oculto");
        secSup.classList.add("oculto");
      });
      btnVisaoSup.addEventListener("click", function () {
        btnVisaoSup.classList.add("ativo");
        btnVisaoSup.setAttribute("aria-selected", "true");
        btnVisaoColab.classList.remove("ativo");
        btnVisaoColab.setAttribute("aria-selected", "false");
        secSup.classList.remove("oculto");
        secColab.classList.add("oculto");
      });
    }
  }

  iniciar();
})();
