<p align="center">
  <img src="docs/assets/banner-header-service-desk.svg" alt="NuvemTech Service Desk — Cloud Call Center no Amazon Connect" width="100%" />
</p>

<h1 align="center">NuvemTech Service Desk — Estudo Amazon Connect Omnichannel</h1>

<p align="center">
  <a href="https://amazon-connect-service-desk-case2.vercel.app/"><img src="https://img.shields.io/badge/Lab%20Demo-Vercel-10B981?style=for-the-badge&logo=vercel&logoColor=white" alt="Lab Demo" /></a>
  <a href="https://github.com/caiocesarti/amazon-connect-service-desk-case2/actions/workflows/ci.yml"><img src="https://github.com/caiocesarti/amazon-connect-service-desk-case2/actions/workflows/ci.yml/badge.svg?style=for-the-badge" alt="CI/CD Status" /></a>
  <img src="https://img.shields.io/badge/Status-Projeto%20de%20Estudo-F59E0B?style=for-the-badge" alt="Projeto de Estudo" />
  <img src="https://img.shields.io/badge/AWS-Amazon%20Connect-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white" alt="AWS" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Amazon%20Lex%20V2-pt__BR%20%7C%20Camila-4F46E5?style=for-the-badge" alt="Lex" />
  <img src="https://img.shields.io/badge/Coverage-94.9%25-2EA44F?style=for-the-badge" alt="Tests" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License" />
</p>

<p align="center">
  <strong>🌐 Idioma / Language:</strong> <strong>Português (BR)</strong> · <a href="README.en.md">English</a>
</p>

> **⚠️ Aviso — Projeto de Estudo (Não pronto para produção):**  
> Este repositório tem finalidade **exclusivamente educacional e de portfólio**, criado para praticar a integração entre **Amazon Connect**, **Amazon Lex V2**, **AWS Lambda (Python 3.12)**, **Connect Cases** e **Contact Lens**. **Ele NÃO está pronto para uso em produção:** utiliza um conjunto de dados estático fictício (*NuvemTech Soluções S.A.* em `data/service_desk.json`), sem banco de dados persistente, sem autenticação corporativa (SSO/IAM Identity Center), sem criptografia de sessão produtiva ou hardening de infraestrutura para carga real.

Protótipo de laboratório de um **Service Desk Interno de TI Omnichannel (Chat Web & Voz pt-BR)** acompanhado de uma interface web de demonstração (*Portal do Colaborador* e *Painel do Supervisor*) e scripts de automação/validação local. **Demo do laboratório (Vercel):** [amazon-connect-service-desk-case2.vercel.app](https://amazon-connect-service-desk-case2.vercel.app/).

---

## 1. Arquitetura AWS da Solução

![Arquitetura AWS NuvemTech Service Desk](docs/assets/arquitetura-aws-connect.svg)

---

## 2. Fluxo Conversacional & Sequência Omnichannel (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    actor Colab as Colaborador (Chat / Voz)
    participant Flow as Amazon Connect<br/>(SD-Entrada-Principal)
    participant Lex as Amazon Lex V2<br/>(pt_BR · Camila Neural)
    participant Lambda as AWS Lambda<br/>(sd_fulfillment)
    participant Cases as Connect Cases<br/>(SD-Template-Chamado-TI)
    participant Filas as Filas Segmentadas<br/>(SD-Fila-*)
    participant Lens as Contact Lens &<br/>Supervisor (FCR / TMA)

    Colab->>Flow: Inicia atendimento (Portal Web ou Voz WebRTC)
    Flow->>Lex: Encaminha turno com idioma pt-BR e voz Camila
    Lex->>Lambda: Invoca fulfillment (intenção + slots)
    Lambda->>Lambda: Executa Guardrails (CSIRT P1, Anti-Injeção, PII)
    alt Slot obrigatório ausente (Matrícula ou PIN)
        Lambda-->>Lex: ElicitSlot (solicita dado ao colaborador)
        Lex-->>Colab: Pergunta matrícula NTxxxx ou PIN de 4 dígitos
        Colab->>Lex: Informa dado solicitado
        Lex->>Lambda: Reenvia turno validado
    end
    Lambda->>Cases: Cria chamado idempotente (Categoria + Prioridade P1–P4)
    Lambda-->>Flow: Retorna atributos sd_* (fila, protocolo, sd_resolvido_bot)
    alt Resolvido pelo Bot (FCR)
        Flow-->>Colab: Entrega protocolo e confirmação de resolução
    else Transbordo para Especialista
        Flow->>Filas: Roteia automaticamente (Segurança / Redes / Hardware / Geral N1 / P1)
        Filas-->>Colab: Conecta ao analista com Sussurro (SD-Sussurro-Agente)
    end
    Flow->>Lens: Transcreve (redigindo PII/PIN), pontua sentimento e atualiza FCR/TMA
```

### Árvore de Decisão de Roteamento por Intenção e Criticidade

```mermaid
flowchart TD
    Inicio["Contato Recebido<br/>(Chat Web ou Voz)"] --> Guardrail{"Guardrail de Segurança<br/>(Phishing / Ransomware / VIP)?"}
    Guardrail -- "Sim (Crítico)" --> FilaP1["🚨 SD-Fila-Prioritaria-P1<br/>(Prioridade P1)"]
    Guardrail -- "Não" --> Lex{"Intenção Detectada<br/>(Amazon Lex V2)"}
    Lex -- "PasswordReset" --> FilaSec["🔐 SD-Fila-Seguranca<br/>(Identidade & Acessos)"]
    Lex -- "NetworkIssue" --> FilaRedes["🌐 SD-Fila-Redes<br/>(VPN, Wi-Fi, MPLS)"]
    Lex -- "HardwareRequest" --> FilaHw["💻 SD-Fila-Hardware<br/>(Equipamentos & Estoque)"]
    Lex -- "FalarComAtendente / Fallback" --> FilaN1["👤 SD-Fila-Geral-N1<br/>(Suporte N1)"]
```

---

## 3. Entregáveis Implementados (Matriz 1:1)

| # | Entregável Esperado | Implementação Técnica no Repositório |
|---|---|---|
| **1** | **Fluxo no Amazon Connect com $\ge$ 3 intenções no Amazon Lex (`PasswordReset`, `NetworkIssue`, `HardwareRequest`)** | Contact Flow [`SD-Entrada-Principal.json`](connect/flows/SD-Entrada-Principal.json) integrado ao bot [`lex/bot-export.json`](lex/bot-export.json) (`pt_BR`, voz neural `Camila`, 6 intenções e tipos de slots em [`lex/slot-types.json`](lex/slot-types.json)) e pacote de importação gerado por [`scripts/gerar_pacote_lex.py`](scripts/gerar_pacote_lex.py). |
| **2** | **Filas segmentadas por tipo de incidente com roteamento automático** | 5 filas declaradas em [`connect/recursos.yaml`](connect/recursos.yaml) (`SD-Fila-Seguranca`, `SD-Fila-Redes`, `SD-Fila-Hardware`, `SD-Fila-Geral-N1`, `SD-Fila-Prioritaria-P1`), lógica de roteamento em [`lambda/sd_fulfillment/chamados.py`](lambda/sd_fulfillment/chamados.py) e transferência contextual em [`SD-Transbordo-N1.json`](connect/flows/SD-Transbordo-N1.json) + [`SD-Sussurro-Agente.json`](connect/flows/SD-Sussurro-Agente.json). |
| **3** | **Integração com Connect Cases (criação automática, categoria e prioridade)** | Adapter idempotente [`lambda/sd_fulfillment/casos.py`](lambda/sd_fulfillment/casos.py) com matriz de prioridade ITIL (`P1`–`P4`) e schema [`connect/cases/template-chamado.json`](connect/cases/template-chamado.json). |
| **4** | **Contact Lens para transcrição e análise de sentimento** | Regras de sentimento negativo (alerta EventBridge ao supervisor), detecção P1 em tempo real, redação de PII/PIN e confirmação de FCR em [`connect/contact-lens/regras.json`](connect/contact-lens/regras.json). |
| **5** | **Métricas de FCR e TMA disponíveis para o supervisor** | Metas e rastreamento (`sd_resolvido_bot`) em [`connect/recursos.yaml`](connect/recursos.yaml), visualização em tempo real no **Painel do Supervisor** em [`landing/index.html`](landing/index.html) e roteiro de verificação em [`docs/03-testes-e-evidencias.md`](docs/03-testes-e-evidencias.md). |
| **+** | **Recursos Adicionais do Laboratório** | Portal de estudo estilo `shadcn/ui` ([`landing/`](landing/)) com limite de interações FinOps ([`scripts/injetar_widget.py`](scripts/injetar_widget.py)), 5 runbooks em [`kb/`](kb/) para Amazon Q in Connect, scanner [`scripts/verificar_segredos.py`](scripts/verificar_segredos.py) e CI/CD ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). |

---

## 4. Estrutura do Repositório

```text
amazon-connect-service-desk-case2/
├── .github/workflows/ci.yml            # Pipeline CI: Ruff, Mypy, Zero-Leak, Validações, Pytest >=90% e Gitleaks
├── README.md                           # Documentação principal do projeto (pt-BR)
├── README.en.md                        # English version of the project README
├── SECURITY.md                         # Política DevSecOps Zero-Leak
├── api/index.py                        # Entrypoint HTTP serverless da Vercel (estáticos + /api/config + /api/lex)
├── connect/
│   ├── cases/template-chamado.json     # Template de campos do Amazon Connect Cases
│   ├── contact-lens/regras.json        # Regras de transcrição, redação PII e análise de sentimento
│   ├── flows/                          # 4 Contact Flows (schema 2019-10-30 com layout visual)
│   └── recursos.yaml                   # Filas, horário comercial, routing profile e metas FCR/TMA
├── data/
│   ├── schema/service_desk.schema.json # Contrato JSON Schema Draft 2020-12
│   └── service_desk.json               # Dataset simulado (30 colaboradores, 8 filiais, 12 itens HW, incidentes)
├── docs/
│   ├── assets/                         # Banner do header e diagrama SVG da arquitetura AWS
│   ├── img/                            # Capturas sanitizadas do console AWS, CCP e Portal
│   ├── adr/                            # Architecture Decision Records (ADR-001, ADR-002)
│   ├── 01-arquitetura.md               # Arquitetura detalhada, contrato sd_* e guardrails
│   ├── 02-passo-a-passo.md             # Guia de provisionamento AWS + Vercel
│   └── 03-testes-e-evidencias.md       # Roteiro de testes E2E (CT-01 a CT-14) e evidências
├── infra/template.yaml                 # Template AWS SAM (Lambda Python 3.12, IAM least privilege, Logs 7d)
├── kb/                                 # 5 artigos operacionais (KB-001 a KB-005) para Amazon Q in Connect
├── lambda/sd_fulfillment/              # Backend Python 3.12 (stdlib + boto3, zero deps externas)
├── landing/                            # Portal Web (Portal do Colaborador + Painel do Supervisor)
├── lex/                                # Definição do bot pt_BR e tipos de slots
├── scripts/                            # Automação DevSecOps, empacotamento e servidor local do laboratório
├── tests/                              # Suíte Pytest (91 testes, >94% de cobertura incl. api/)
└── vercel.json                         # CSP (Amazon Connect, CloudFront, Chime WebRTC) e saída estática
```

---

## 5. Como Executar e Testar no Laboratório Local

### Pré-requisitos
- Python 3.12+

### Passo a passo

```bash
# 1. Criar ambiente virtual e instalar dependências de desenvolvimento
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install

# 2. Executar lint, tipagem estática, auditoria Zero-Leak, validações e testes (91 testes)
ruff check .
mypy lambda/sd_fulfillment scripts api
python scripts/verificar_segredos.py
python scripts/validar_dataset.py
python scripts/validar_flows.py
pytest

# 3. Subir o Laboratório Local (Portal Web + Backend Lambda simulado)
python scripts/servir_local.py --porta 8080
```

Acesse **[http://localhost:8080](http://localhost:8080)** para explorar os fluxos implementados:
1. No **Portal do Colaborador**, teste os fluxos **`🔑 Esqueci minha senha`** (`PasswordReset` — matrícula `NT1001`, PIN `4821`), **`🌐 Sem internet / VPN`** (`NetworkIssue` — matrícula `NT1011`) e **`💻 Solicitar equipamento`** (`HardwareRequest` — matrícula `NT1001`).
2. Observe os chamados de exemplo criados em **Minhas Solicitações** com protocolo, categoria, prioridade e fila de destino.
3. Alterne para o **Painel do Supervisor** no topo da barra de navegação para acompanhar os indicadores simulados de **FCR (%)**, **TMA**, **Roteamento por Equipe** e **Transcrição & Sentimento** — ou clique em **`▶ Simular fila de atendimentos`** para executar os 6 cenários em sequência.

---

## 6. Evidências do Laboratório (AWS Sandbox + Portal)

> Capturas obtidas durante os testes em conta sandbox da AWS (`us-west-2`), integrando o portal web, o Amazon Lex V2, a Lambda Python, chamadas WebRTC e o recebimento no Contact Control Panel (CCP):

| Portal do Colaborador (`Atendimento Online`) | Painel do Supervisor (`FCR` & `TMA`) |
|---|---|
| ![Portal do Colaborador Online](docs/img/01-portal-colaborador-online.png) | ![Painel do Supervisor](docs/img/02-painel-supervisor-fcr-tma.png) |

| Transbordo no Lab (Widget → CCP) | Chamada de Voz WebRTC (`Web Calling`) |
|---|---|
| ![CCP ao vivo](docs/img/06-ccp-transbordo-ao-vivo.png) | ![Chamada WebRTC ativa](docs/img/07-widget-chamada-voz-webrtc.png) |

| Intenções no Amazon Lex V2 | Filas Segmentadas no Connect |
|---|---|
| ![Lex V2 Intents](docs/img/03-lex-v2-intents.png) | ![Filas no Amazon Connect](docs/img/04-connect-filas-roteamento.png) |

Veja todas as 9 capturas do laboratório em **[docs/03-testes-e-evidencias.md](docs/03-testes-e-evidencias.md#5-galeria-de-evidências-do-laboratório-aws-sandbox-ccp-e-portal)**.

---

## 7. Documentação Complementar

- **[docs/01-arquitetura.md](docs/01-arquitetura.md)** — Contrato de atributos `sd_*`, matriz ITIL e guardrails.
- **[docs/02-passo-a-passo.md](docs/02-passo-a-passo.md)** — Provisionamento completo na AWS (`S3` → `Lambda` → `Lex V2` → `Connect` → `Vercel`).
- **[docs/03-testes-e-evidencias.md](docs/03-testes-e-evidencias.md)** — Casos de teste ponta a ponta (`CT-01` a `CT-14`) e galeria de evidências.
- **[SECURITY.md](SECURITY.md)** — Política DevSecOps Zero-Leak.

---

## 8. Licença

Distribuído sob a licença [MIT](LICENSE).
