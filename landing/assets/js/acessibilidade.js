/**
 * Acessibilidade WCAG 2.1 AA: alto contraste e escala tipográfica persistidos em localStorage.
 */
(function () {
  "use strict";

  var CHAVE_CONTRASTE = "sd_acess_contraste";
  var CHAVE_FONTE = "sd_acess_escala_fonte";
  var ESCALA_MIN = 0.9;
  var ESCALA_MAX = 1.25;
  var PASSO_ESCALA = 0.08;

  var docEl = document.documentElement;
  var btnContraste = document.getElementById("btn-alto-contraste");

  function ler(chave, padrao) {
    try {
      return window.localStorage.getItem(chave) || padrao;
    } catch (_) {
      return padrao;
    }
  }

  function gravar(chave, valor) {
    try {
      window.localStorage.setItem(chave, String(valor));
    } catch (_) {
      /* storage indisponível */
    }
  }

  function aplicarContraste(modo) {
    var alto = modo === "alto";
    docEl.setAttribute("data-contraste", alto ? "alto" : "padrao");
    if (btnContraste) {
      btnContraste.setAttribute("aria-pressed", alto ? "true" : "false");
    }
    gravar(CHAVE_CONTRASTE, alto ? "alto" : "padrao");
  }

  function aplicarEscala(valor) {
    var num = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, Number(valor) || 1));
    var arred = Math.round(num * 100) / 100;
    docEl.style.setProperty("--escala-fonte", String(arred));
    gravar(CHAVE_FONTE, String(arred));
  }

  function ligar(id, fn) {
    var el = document.getElementById(id);
    if (el) {
      el.addEventListener("click", fn);
    }
  }

  aplicarContraste(ler(CHAVE_CONTRASTE, "padrao"));
  aplicarEscala(parseFloat(ler(CHAVE_FONTE, "1")));

  ligar("btn-alto-contraste", function () {
    aplicarContraste(docEl.getAttribute("data-contraste") === "alto" ? "padrao" : "alto");
  });
  ligar("btn-diminuir-fonte", function () {
    aplicarEscala((parseFloat(ler(CHAVE_FONTE, "1")) || 1) - PASSO_ESCALA);
  });
  ligar("btn-resetar-fonte", function () {
    aplicarEscala(1);
  });
  ligar("btn-aumentar-fonte", function () {
    aplicarEscala((parseFloat(ler(CHAVE_FONTE, "1")) || 1) + PASSO_ESCALA);
  });
})();
