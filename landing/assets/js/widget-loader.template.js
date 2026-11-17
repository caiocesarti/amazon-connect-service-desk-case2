/**
 * Camada FinOps e carregador sob demanda do Communications Widget do Amazon Connect.
 *
 * Proteções implementadas (Pilar 6):
 * 1. Bloqueio automático de web crawlers / navegadores automatizados (navigator.webdriver
 *    e user-agents de robôs de indexação) para evitar sessões fantasma no Connect/Lex.
 * 2. Limite de inicializações por navegador persistido em localStorage (sd_widget_interacoes_v1)
 *    para proteger a cota de laboratório AWS durante os testes.
 * 3. O snippet real é injetado em tempo de build por scripts/injetar_widget.py no marcador
 *    __SD_WIDGET_SNIPPET_B64__ (nunca versionado com IDs reais no repositório).
 */
(function () {
  "use strict";

  var CHAVE_CONTADOR = "sd_widget_interacoes_v1";
  var MAX_INTERACOES = Number("__SD_WIDGET_MAX_INTERACOES__") || 5;
  var SNIPPET_BASE64 = "__SD_WIDGET_SNIPPET_B64__";

  var btnIniciar = document.getElementById("btn-iniciar-atendimento");
  var btnResetarCota = document.getElementById("btn-resetar-cota");
  var elAviso = document.getElementById("aviso-widget");
  var elContador = document.getElementById("contador-finops");
  var elStatusTopo = document.getElementById("status-finops-topo");
  var widgetJaCarregado = false;

  function ehAmbienteAutomatizado() {
    if (typeof navigator === "undefined") {
      return true;
    }
    if (navigator.webdriver === true) {
      return true;
    }
    var ua = (navigator.userAgent || "").toLowerCase();
    var padroesBot = [" headlesschrome", "bot/", "crawler", "spider", "lighthouse", "slurp"];
    for (var i = 0; i < padroesBot.length; i++) {
      if (ua.indexOf(padroesBot[i]) !== -1) {
        return true;
      }
    }
    return false;
  }

  function lerContador() {
    try {
      var bruto = window.localStorage.getItem(CHAVE_CONTADOR);
      var n = parseInt(bruto || "0", 10);
      return isNaN(n) || n < 0 ? 0 : n;
    } catch (_) {
      return 0;
    }
  }

  function gravarContador(valor) {
    try {
      window.localStorage.setItem(CHAVE_CONTADOR, String(valor));
    } catch (_) {
      /* storage indisponível */
    }
  }

  function atualizarPainelCota() {
    var usadas = lerContador();
    if (elContador) {
      elContador.textContent = usadas + " / " + MAX_INTERACOES + " sessões utilizadas";
    }
  }

  function decodificarSnippet(b64) {
    if (!b64 || b64.indexOf("__SD_WIDGET_") === 0) {
      return "";
    }
    try {
      return decodeURIComponent(escape(window.atob(b64)));
    } catch (_) {
      return "";
    }
  }

  function injetarHtmlSnippet(htmlSnippet) {
    var container = document.getElementById("connect-widget-container");
    if (!container) {
      return false;
    }
    var temp = document.createElement("div");
    temp.innerHTML = htmlSnippet;
    var scripts = temp.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      var novoScript = document.createElement("script");
      if (scripts[i].src) {
        novoScript.src = scripts[i].src;
        novoScript.async = true;
      } else {
        novoScript.textContent = scripts[i].textContent;
      }
      container.appendChild(novoScript);
    }
    return true;
  }

  function carregarWidgetSobDemanda() {
    if (ehAmbienteAutomatizado()) {
      if (elAviso) {
        elAviso.textContent =
          "Proteção FinOps: carregamento do widget bloqueado em navegador automatizado (navigator.webdriver).";
      }
      if (elStatusTopo) {
        elStatusTopo.textContent = "FinOps: Bot bloqueado";
      }
      return;
    }

    var usadas = lerContador();
    if (usadas >= MAX_INTERACOES) {
      if (elAviso) {
        elAviso.textContent =
          "Limite FinOps atingido (" +
          MAX_INTERACOES +
          " sessões neste navegador). Use o botão 'Reiniciar contador local de testes' no rodapé caso esteja realizando novos testes.";
      }
      return;
    }

    if (widgetJaCarregado) {
      if (elAviso) {
        elAviso.textContent = "O widget do Amazon Connect já está ativo no canto inferior direito.";
      }
      return;
    }

    var snippetHtml = decodificarSnippet(SNIPPET_BASE64);
    if (!snippetHtml || snippetHtml.indexOf("<WIDGET_ID>") !== -1) {
      gravarContador(usadas + 1);
      atualizarPainelCota();
      if (elAviso) {
        elAviso.textContent =
          "Modo demonstração (placeholder <WIDGET_ID>): configure CONNECT_WIDGET_SNIPPET na Vercel ou landing/widget-snippet.local.html para conectar à instância real.";
      }
      return;
    }

    if (injetarHtmlSnippet(snippetHtml)) {
      widgetJaCarregado = true;
      gravarContador(usadas + 1);
      atualizarPainelCota();
      if (elAviso) {
        elAviso.textContent =
          "Widget do Amazon Connect carregado! Use o ícone no canto inferior direito para Chat ou Chamada Web.";
      }
    }
  }

  atualizarPainelCota();

  if (btnIniciar) {
    btnIniciar.addEventListener("click", carregarWidgetSobDemanda);
  }

  if (btnResetarCota) {
    btnResetarCota.addEventListener("click", function () {
      gravarContador(0);
      atualizarPainelCota();
      if (elAviso) {
        elAviso.textContent = "Contador local de sessões FinOps reiniciado para 0.";
      }
    });
  }
})();
