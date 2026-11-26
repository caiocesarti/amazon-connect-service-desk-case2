# ADR-005 — Governança FinOps do Widget Público e Fonte Única de Verdade

- **Status:** Aceito
- **Data:** 2026-11-26
- **Escopo:** Portal Web (`landing/`), API Vercel (`api/index.py`) e Simulador Local

## Contexto

Expor um portal de demonstração público na Vercel conectado ao Amazon Connect gera dois riscos
práticos: (1) consumo abusivo de cota AWS por crawlers, navegadores automatizados ou abertura
repetida do Communications Widget; e (2) divergência (*drift*) entre a interface de demonstração e
o comportamento real da Lambda, dos Contact Flows e do Contact Lens quando regras de negócio são
duplicadas no JavaScript do front-end.

## Decisão

1. **Camada FinOps e injeção em build-time (`scripts/injetar_widget.py` +
   `landing/assets/js/widget-loader.template.js`):** o snippet real do widget nunca é versionado —
   é lido de `CONNECT_WIDGET_SNIPPET` na Vercel ou de `landing/widget-snippet.local.html`
   (ignorado pelo `.gitignore`), com fallback para `landing/widget-snippet.example.html`. O build
   injeta o snippet em Base64 em `landing/dist/`, e o carregador só inicializa o widget sob demanda
   após bloquear automação (`navigator.webdriver` / user-agents de robôs) e aplicar teto de
   interações por navegador (`WIDGET_MAX_INTERACOES`, padrão `5`, em `localStorage`), reforçado por
   headers CSP e `Permissions-Policy` em `vercel.json`.
2. **Fonte única de verdade no simulador (`scripts/servir_local.py` e `api/index.py`):**
   - `GET /api/config` lê filas, metas FCR/TMA, regras do Contact Lens, intenções e *slot types*
     diretamente de `connect/recursos.yaml`, `connect/contact-lens/regras.json`,
     `lex/bot-export.json` e `lex/slot-types.json`.
   - `POST /api/lex` executa o `handler.lambda_handler` real em modo `CASES_DRY_RUN=true`, sem
     reimplementar lógica de fulfillment em `landing/assets/js/simulador.js`.
3. **Front-end estático sem pipeline Node.js:** HTML5, CSS3 e JavaScript Vanilla (`"use strict"`,
   IIFE), mantendo o build unificado em Python (`python3 scripts/injetar_widget.py`).

## Consequências

- ✅ Protege a conta de laboratório contra sessões fantasma de crawlers e preserva a política
  Zero-Leak no deploy público da Vercel.
- ✅ Elimina *drift* entre o portal demonstrativo e os artefatos reais do Amazon Connect/Lex/Lambda.
- ⚠️ A cota em `localStorage` é uma barreira leve de cliente (pode ser limpa manualmente no
  navegador). Em produção, o controle seria reforçado com autenticação JWT no widget do Amazon
  Connect e *rate limiting* na borda (WAF).
