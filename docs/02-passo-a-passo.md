# 02 — Runbook Completo de Provisionamento na AWS e Vercel (Passo a Passo)

Este guia detalha **clique a clique** como provisionar 100% da solução **NuvemTech Service Desk (Case 2)** na região **`us-east-1` (N. Virginia)**, desde a criação da instância do Amazon Connect até o teste final de ponta a ponta no Chat, Voz WebRTC, Connect Cases e Contact Control Panel (CCP v2).

---

## Visão Geral da Ordem de Provisionamento

Para evitar que um recurso peça o ARN de outro que ainda não existe, siga exatamente esta ordem:

1. **Fase 1 — Instância do Amazon Connect, Customer Profiles, Cases e Contact Lens**
2. **Fase 2 — Amazon S3 e Amazon Q in Connect (Base de Conhecimento)**
3. **Fase 3 — AWS Lambda (`sd-fulfillment-servicedesk`) e Permissões IAM**
4. **Fase 4 — Amazon Lex V2 (`SD-ServiceDesk-Bot` em `pt_BR`) + Associação ao Connect**
5. **Fase 5 — Horário Comercial, 5 Filas Segmentadas, Routing Profile, Usuário e Regras do Contact Lens**
6. **Fase 6 — Importação, Religação e Publicação dos 4 Contact Flows**
7. **Fase 7 — Communications Widget e Deploy na Vercel (ou Teste Local)**
8. **Fase 8 — Teste Ponta a Ponta (Widget no Site ↔ Bot ↔ Connect Cases ↔ Analista no CCP v2)**
9. **Fase 9 — Supervisão de Métricas (FCR e TMA) e Teardown FinOps**

> **Região obrigatória em todas as abas do Console AWS:** selecione **`US East (N. Virginia) us-east-1`** no canto superior direito antes de começar.

---

## Fase 1 — Criar a Instância do Amazon Connect, Cases e Contact Lens

### 1.1 Criar a instância do Amazon Connect
1. No Console AWS (`us-east-1`), pesquise por **Amazon Connect** e clique em **Add an instance**.
2. **Step 1 — Set identity:**
   - Selecione **Store users in Amazon Connect**.
   - Em **Access URL**, digite um alias exclusivo (ex.: `nuvemtech-servicedesk-lab`).
   - Clique em **Next**.
3. **Step 2 — Add administrator:**
   - Selecione **Add a new admin** e preencha nome, usuário (ex.: `admin.connect`), senha forte e seu e-mail.
   - Clique em **Next**.
4. **Step 3 — Set telephony:**
   - Marque **Allow incoming calls** e **Allow outbound calls**.
   - Clique em **Next**.
5. **Step 4 — Data storage:**
   - Mantenha a opção padrão (o Connect criará automaticamente o bucket S3 e a chave KMS para gravações, transcrições do Contact Lens e relatórios).
   - Clique em **Next**.
6. **Step 5 — Review and create:**
   - Revise e clique em **Create instance**. Aguarde de 2 a 3 minutos até o status ficar **Active**.

### 1.2 Habilitar Contact Lens e Customer Profiles
1. Na lista de instâncias do Amazon Connect, clique no **Instance Alias** recém-criado (na coluna da AWS, não no link de login ainda).
2. No menu lateral esquerdo da instância (no Console AWS):
   - Clique em **Analytics tools**:
     - Marque **Enable Contact Lens** (transcrição e análise de sentimento para Voz e Chat).
     - Clique em **Save**.
   - Clique em **Customer profiles**:
     - Clique em **Enable Customer Profiles** → **Create new domain** → dê o nome `sd-customer-profiles-domain` → **Enable**.

### 1.3 Habilitar o Amazon Connect Cases e criar o Template de Chamado
1. Ainda no menu lateral da instância no Console AWS, clique em **Cases**:
   - Clique em **Enable Cases** → **Create a new domain** → nome: `sd-cases-domain` → **Save**.
2. Agora abra o painel da instância clicando em **Access URL** (`https://<INSTANCE_ALIAS>.my.connect.aws`) e faça login com o administrador criado no passo 1.1.
3. No menu lateral esquerdo do painel do Amazon Connect, vá em **Customer → Case fields** e clique em **Create field** para criar os 6 campos customizados de [`connect/cases/template-chamado.json`](../connect/cases/template-chamado.json):
   - `sd_protocolo` — Type: **Text**
   - `sd_categoria` — Type: **Single-select** → opções: `ACESSO_SEGURANCA`, `REDE_CONECTIVIDADE`, `HARDWARE`, `GERAL`
   - `sd_prioridade` — Type: **Single-select** → opções: `P1`, `P2`, `P3`, `P4`
   - `sd_matricula` — Type: **Text**
   - `sd_equipamento` — Type: **Text**
   - `sd_estoque_status` — Type: **Single-select** → opções: `DISPONIVEL`, `INDISPONIVEL`, `REQUER_APROVACAO`
4. Vá em **Customer → Case templates** → **Create template**:
   - **Template name:** `SD-Template-Chamado-TI`
   - Adicione os campos obrigatórios: `Title`, `Summary`, `sd_protocolo`, `sd_categoria`, `sd_prioridade` e os opcionais `sd_matricula`, `sd_equipamento`, `sd_estoque_status`.
   - Clique em **Save** e mude o status do template para **Active**.
5. **Anote dois IDs** para usar na Fase 3 (Lambda):
   - **`CASES_DOMAIN_ID`**: visível no Console AWS → Amazon Connect → sua instância → **Cases** (no final do ARN `.../domain/<CASES_DOMAIN_ID>`).
   - **`CASES_TEMPLATE_ID`**: visível na URL ao abrir o template `SD-Template-Chamado-TI` (ou via comando `aws connectcases list-templates --domain-id <CASES_DOMAIN_ID>`).

---

## Fase 2 — Amazon S3 e Amazon Q in Connect (Base de Conhecimento)

### 2.1 Criar o Bucket S3 com os artigos da KB
1. No Console AWS (`us-east-1`), abra **Amazon S3** → **Create bucket**:
   - **Bucket name:** `sd-kb-artigos-<SEU_ACCOUNT_ID>-us-east-1`
   - **Block Public Access:** mantenha **Block all public access** marcado.
   - **Bucket Versioning:** `Enable`.
   - **Default encryption:** `Server-side encryption with Amazon S3 managed keys (SSE-S3)`.
   - Clique em **Create bucket**.
2. Entre no bucket criado → **Upload** → **Add files** e envie os 5 arquivos da pasta [`kb/`](../kb/):
   - `KB-001-reset-senha-ad.md`
   - `KB-002-vpn-nao-conecta.md`
   - `KB-003-wifi-corporativo.md`
   - `KB-004-solicitacao-hardware.md`
   - `KB-005-incidente-seguranca-phishing.md`
   - Clique em **Upload**.

### 2.2 Configurar o Amazon Q in Connect (Wisdom)
1. Volte em **Amazon Connect** no Console AWS → clique na sua instância → menu lateral **Amazon Q in Connect**.
2. Clique em **Add domain**:
   - **Domain name:** `SD-Assistente-Q`
   - **Knowledge base name:** `SD-KB-Artigos-TI`
   - **Integration type:** selecione **Amazon S3** e escolha o bucket `sd-kb-artigos-<SEU_ACCOUNT_ID>-us-east-1`.
   - Clique em **Save**.

---

## Fase 3 — AWS Lambda (`sd-fulfillment-servicedesk`)

### 3.1 Gerar o pacote ZIP na sua máquina
No terminal, na raiz do repositório:
```bash
python scripts/empacotar_lambda.py
```
Isso gera o arquivo `dist/sd_fulfillment.zip` já com os módulos Python e `dados/service_desk.json` embutidos.

### 3.2 Criar a Função Lambda no Console AWS
1. Abra **AWS Lambda (`us-east-1`)** → **Create function**:
   - Selecione **Author from scratch**.
   - **Function name:** `sd-fulfillment-servicedesk`
   - **Runtime:** `Python 3.12`
   - **Architecture:** `arm64`
   - Em **Change default execution role**, selecione **Create a new role with basic Lambda permissions**.
   - Clique em **Create function**.
2. Na aba **Code**:
   - Clique em **Upload from** → **.zip file** → selecione `dist/sd_fulfillment.zip` → **Save**.
   - Em **Runtime settings**, verifique se o **Handler** está como `handler.lambda_handler` (se estiver `lambda_function.lambda_handler`, clique em **Edit** e mude para **`handler.lambda_handler`**).
3. Na aba **Configuration → General configuration** → **Edit**:
   - **Memory:** `256 MB`
   - **Timeout:** `0 min 10 sec`
   - Clique em **Save**.
4. Na aba **Configuration → Environment variables** → **Edit**, adicione:
   - `CASES_DOMAIN_ID` = cole o ID anotado na Fase 1.3
   - `CASES_TEMPLATE_ID` = cole o ID do template anotado na Fase 1.3
   - `CASES_DRY_RUN` = `true` *(Nota: mantenha `true` caso os IDs dos campos customizados gerados pelo Cases sejam UUIDs internos; mude para `false` quando mapear os IDs reais do domínio)*
   - `LOG_LEVEL` = `INFO`
   - Clique em **Save**.
5. *(Opcional — para `CASES_DRY_RUN=false`)* Na aba **Configuration → Permissions**, clique no nome da Role da Lambda → **Add permissions → Create inline policy (JSON)** e adicione permissão mínima para o Connect Cases:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "PermitirCriacaoCasosServiceDesk",
         "Effect": "Allow",
         "Action": [
           "cases:CreateCase",
           "cases:GetTemplate",
           "cases:ListFields"
         ],
         "Resource": "arn:aws:cases:us-east-1:*:domain/*"
       }
     ]
   }
   ```

### 3.3 Testar a Lambda direto no Console AWS
1. Na aba **Test** da Lambda, crie um evento `TestePasswordReset` com este JSON:
   ```json
   {
     "sessionId": "teste-console-001",
     "inputTranscript": "Esqueci minha senha",
     "inputMode": "Text",
     "sessionState": {
       "sessionAttributes": {},
       "intent": {
         "name": "PasswordReset",
         "slots": {
           "Matricula": {
             "shape": "Scalar",
             "value": { "originalValue": "NT1001", "interpretedValue": "NT1001" }
           },
           "PinVerificacao": {
             "shape": "Scalar",
             "value": { "originalValue": "4821", "interpretedValue": "4821" }
           }
         },
         "state": "InProgress"
       }
     }
   }
   ```
2. Clique em **Test**: o retorno deve ter `"state": "Fulfilled"`, `"sd_identidade_validada": "true"` e `"sd_fila_destino": "SEGURANCA"`.

---

## Fase 4 — Amazon Lex V2 (`SD-ServiceDesk-Bot` em `pt_BR`)

### 4.1 Criar o Bot e o Idioma `pt_BR`
1. No Console AWS (`us-east-1`), abra **Amazon Lex** (certifique-se de estar no console **V2**) → **Create bot**:
   - **Creation method:** *Create a blank bot*
   - **Bot name:** `SD-ServiceDesk-Bot`
   - **IAM permissions:** *Create a role with basic Amazon Lex permissions*
   - **Children's Online Privacy Protection Act (COPPA):** `No`
   - **Idle session timeout:** `5 minutes`
   - Clique em **Next**.
2. **Add language to bot:**
   - **Language:** `Portuguese (Brazil)`
   - **Voice interaction:** `Camila` (**Engine:** `Neural`)
   - **Intent classification confidence score threshold:** `0.40`
   - Clique em **Done**.

### 4.2 Criar os 6 Slot Types (Menu lateral: **Slot types**)
Use os valores de [`lex/slot-types.json`](../lex/slot-types.json):

1. **Add slot type → Add blank slot type:**
   - **`TipoProblemaRedeType`** (*Restrict to slot values and synonyms*):
     - `VPN` (sinônimos: `vpn`, `anyconnect`, `acesso remoto`, `vpn corporativa`)
     - `WIFI` (sinônimos: `wifi`, `wi-fi`, `rede sem fio`, `wireless`, `nuvemtech-corp`)
     - `SEM_INTERNET` (sinônimos: `sem internet`, `internet caiu`, `sem conexão`, `cabo de rede`, `fora do ar`)
     - `DNS` (sinônimos: `dns`, `intranet não abre`, `sistema interno não carrega`)
   - **`EscopoImpactoType`** (*Restrict to slot values and synonyms*):
     - `INDIVIDUAL` (sinônimos: `só eu`, `apenas eu`, `meu computador`, `individual`)
     - `SETOR` (sinônimos: `meu setor`, `minha equipe`, `andar inteiro`, `sala de reunião`, `sala de conselho`)
     - `UNIDADE` (sinônimos: `unidade inteira`, `prédio inteiro`, `filial toda`, `escritório inteiro`)
   - **`EquipamentoHardwareType`** (*Restrict to slot values and synonyms*):
     - Adicione os 12 códigos de [`lex/slot-types.json`](../lex/slot-types.json): `NOTEBOOK_PADRAO` (`notebook`, `laptop`), `NOTEBOOK_DEV` (`notebook dev`, `workstation`), `MONITOR_24` (`monitor`, `segunda tela`), `MONITOR_27` (`monitor 27`, `monitor 4k`), `HEADSET_USB` (`headset`, `fone de ouvido`), `TECLADO_ABNT2` (`teclado`), `MOUSE_ERGONOMICO` (`mouse`), `DOCKING_USBC` (`docking`), `WEBCAM_FHD` (`webcam`), `CELULAR_CORPORATIVO` (`celular`, `celular corporativo`), `TOKEN_YUBIKEY` (`token`, `yubikey`), `CARREGADOR_USBC` (`carregador`, `fonte`).
2. **Add slot type → Add regular expression slot type:**
   - **`MatriculaColaboradorType`** → Regex: `NT[0-9]{4}`
   - **`PinVerificacaoType`** → Regex: `[0-9]{4}`
   - **`ProtocoloChamadoType`** → Regex: `SD-[0-9]{8}-[A-F0-9]{6}`

### 4.3 Criar as Intenções (Menu lateral: **Intents**)
Para **todas** as intenções abaixo (incluindo `FallbackIntent`), role até o final da página da intenção:
- Em **Code hooks**, marque **Use a Lambda function for initialization and validation**.
- Em **Fulfillment → Advanced options**, marque **Use a Lambda function for fulfillment**.

Cadastre conforme [`lex/bot-export.json`](../lex/bot-export.json):

1. **`PasswordReset`**:
   - **Sample utterances:** `esqueci minha senha`, `preciso resetar minha senha`, `minha senha expirou`, `minha conta bloqueou no windows`, `não consigo logar no computador`, `quero redefinir a senha da matrícula {Matricula}`, `sou {NomeColaborador} e esqueci minha senha`.
   - **Slots:**
     - `Matricula` (`MatriculaColaboradorType`, Required) — Prompt: *"Informe sua matrícula corporativa no formato NT seguido de 4 dígitos (ex.: NT1001)."*
     - `PinVerificacao` (`PinVerificacaoType`, Required) — Prompt: *"Informe seu PIN de verificação de 4 dígitos (nunca digite sua senha)."*
     - `NomeColaborador` (`AMAZON.AlphaNumeric`, Optional).
2. **`NetworkIssue`**:
   - **Sample utterances:** `não consigo acessar a internet`, `estou sem internet`, `minha vpn não conecta`, `o wifi corporativo não funciona`, `estou com problema de {TipoProblemaRede}`, `sem conexão na matrícula {Matricula}`, `a rede caiu para {EscopoImpacto}`.
   - **Slots:**
     - `Matricula` (`MatriculaColaboradorType`, Required) — Prompt: *"Qual é a sua matrícula corporativa (ex.: NT1007)?"*
     - `TipoProblemaRede` (`TipoProblemaRedeType`, Required) — Prompt: *"O problema ocorre na VPN, no Wi-Fi corporativo ou você está totalmente sem internet?"*
     - `EscopoImpacto` (`EscopoImpactoType`, Required) — Prompt: *"A falha afeta apenas você, todo o seu setor ou a unidade inteira?"*
3. **`HardwareRequest`**:
   - **Sample utterances:** `preciso de um equipamento novo`, `quero solicitar um {Equipamento}`, `preciso trocar meu {Equipamento}`, `meu {Equipamento} quebrou`, `solicitar {Equipamento} para a matrícula {Matricula}`, `quero pedir um notebook novo`, `preciso de um monitor externo`, `solicitar celular corporativo`.
   - **Slots:**
     - `Matricula` (`MatriculaColaboradorType`, Required) — Prompt: *"Informe sua matrícula corporativa (ex.: NT1008)."*
     - `Equipamento` (`EquipamentoHardwareType`, Required) — Prompt: *"Qual equipamento do catálogo você precisa (ex.: notebook, monitor, headset, teclado, mouse, celular corporativo)?"*
4. **`ConsultarStatusChamado`**:
   - **Sample utterances:** `qual o status do meu chamado`, `consultar protocolo {Protocolo}`, `como está o chamado {Protocolo}`, `acompanhar meu pedido da matrícula {Matricula}`.
   - **Slots (opcionais — o `DialogCodeHook` da Lambda solicita quando necessário):** `Protocolo` (`ProtocoloChamadoType`), `Matricula` (`MatriculaColaboradorType`).
5. **`FalarComAtendente`**:
   - **Sample utterances:** `quero falar com um atendente`, `transferir para um analista`, `falar com suporte humano`, `me passa para um técnico`.

### 4.4 Build, Versão, Alias `SD-Live` e Vínculo com a Lambda e com o Connect
1. Clique no botão **Build** no canto superior direito e aguarde finalizar.
2. No menu lateral do bot, vá em **Bot versions** → **Create version** → **Create** (será criada a `Version 1`).
3. Vá em **Aliases** → **Create alias**:
   - **Alias name:** `SD-Live`
   - **Associate with a version:** `Version 1`
   - Clique em **Create**.
4. Entre no alias **`SD-Live`** → em **Languages**, clique em **Portuguese (Brazil)**:
   - **Source:** selecione **`sd-fulfillment-servicedesk`**
   - **Lambda function version or alias:** `$LATEST`
   - Clique em **Save** (o console do Lex adiciona automaticamente a permissão `lambda:InvokeFunction`).
5. Teste ali mesmo no botão **Test** do Lex digitando `"Esqueci minha senha, matrícula NT1001, PIN 4821"`.
6. **Vincular o Bot ao Amazon Connect:**
   - Volte no Console AWS → **Amazon Connect** → clique na sua instância → menu lateral **Flows**.
   - Na seção **Amazon Lex**, selecione:
     - **Bot:** `SD-ServiceDesk-Bot`
     - **Alias:** `SD-Live`
   - Clique em **+ Add Amazon Lex Bot**.

---

## Fase 5 — Horário Comercial, Filas Segmentadas, Routing Profile e Contact Lens

Abra o painel da instância do Amazon Connect (`https://<INSTANCE_ALIAS>.my.connect.aws`):

### 5.1 Criar o Horário de Operação (`SD-Horario-Comercial`)
1. Menu lateral → **Routing → Hours of operation** → **Add new hours**:
   - **Name:** `SD-Horario-Comercial`
   - **Time zone:** `America/Sao_Paulo`
   - Configure **Monday to Friday** das **08:00 AM** às **06:00 PM** (18:00).
   - *(Dica para testes fora do horário comercial: enquanto estiver testando à noite ou fim de semana, você pode ampliar temporariamente para 24h para testar o recebimento na fila humana no CCP v2).*
   - Clique em **Save**.

### 5.2 Criar as 5 Filas Segmentadas por Tipo de Incidente
Menu lateral → **Routing → Queues** → **Add new queue**. Crie as 5 filas abaixo usando `Hours of operation = SD-Horario-Comercial`:

| Nome Exato da Fila | Uso no Case 2 |
|---|---|
| `SD-Fila-Seguranca` | Reset de senha (`PasswordReset`), desbloqueio de conta AD e falha de validação |
| `SD-Fila-Redes` | Problemas de internet, Wi-Fi, VPN e DNS (`NetworkIssue`) |
| `SD-Fila-Hardware` | Solicitações de equipamentos sem estoque ou dúvidas logísticas (`HardwareRequest`) |
| `SD-Fila-Geral-N1` | Dúvidas gerais, `FalarComAtendente` e `FallbackIntent` |
| `SD-Fila-Prioritaria-P1` | Emergências CSIRT (ransomware/phishing), queda de unidade inteira e Diretoria VIP |

### 5.3 Criar o Routing Profile e Associar ao Usuário Analista
1. Menu lateral → **Users → Routing profiles** → **Add new profile**:
   - **Name:** `SD-RP-Analista-N1`
   - **Set channels and concurrency:** marque **Voice** (Maximum `1`) e **Chat** (Maximum `3`).
   - **Queues:** adicione as 5 filas criadas acima (`SD-Fila-Prioritaria-P1` com **Priority 1**, `SD-Fila-Seguranca` e `SD-Fila-Redes` com **Priority 2**, `SD-Fila-Hardware` com **Priority 3**, `SD-Fila-Geral-N1` com **Priority 4**, Delay `0` em todas).
   - **Default outbound queue:** `SD-Fila-Geral-N1`.
   - Clique em **Save**.
2. Vá em **Users → User management**:
   - Edite seu usuário administrador (ou crie `analista.lab`) e altere o **Routing Profile** dele para **`SD-RP-Analista-N1`** e garanta que **Security Profiles** contenha `Admin`, `Agent` e `CallCenterManager`.
   - Clique em **Save**.

### 5.4 Criar as Regras do Contact Lens (Sentimento e FCR)
1. Menu lateral → **Analytics and optimization → Rules** → **Create a rule** → **Conversational analytics**:
   - **Regra 1 (`SD-Regra-Sentimento-Negativo`):** When *Post-contact analysis is available* → Add condition *Sentiment* is `Negative` → Action: *Assign contact category* = `SENTIMENTO_CRITICO_COLABORADOR`.
   - **Regra 2 (`SD-Regra-Resolucao-Primeiro-Contato-FCR`):** When *Post-contact analysis is available* → Add condition *Words or phrases (exact match)*: `resolvido`, `funcionou perfeitamente`, `acesso restabelecido`, `chamado concluído` → Action: *Assign contact category* = `FCR_CONFIRMADO`.

---

## Fase 6 — Importar, Religar e Publicar os 4 Contact Flows

No painel do Amazon Connect, vá em **Routing → Flows**:

### 6.1 `SD-Erro-Generico` (1º a importar)
1. Clique em **Create flow** → no canto superior direito, clique na seta ao lado de *Save* → **Import flow (beta)**.
2. Selecione [`connect/flows/SD-Erro-Generico.json`](../connect/flows/SD-Erro-Generico.json) → **Import**.
3. Confira o nome no topo: **`SD-Erro-Generico`** → clique em **Publish**.

### 6.2 `SD-Sussurro-Agente` (2º a importar — Atenção ao tipo!)
1. Volte em **Routing → Flows**, clique na seta ao lado de **Create flow** e selecione **Create agent whisper flow**.
2. Clique na seta ao lado de *Save* → **Import flow (beta)** → selecione [`connect/flows/SD-Sussurro-Agente.json`](../connect/flows/SD-Sussurro-Agente.json).
3. Confira o nome: **`SD-Sussurro-Agente`** → clique em **Publish**.

### 6.3 `SD-Transbordo-N1` (3º a importar)
1. Vá em **Routing → Flows** → **Create flow** → **Import flow (beta)** → selecione [`connect/flows/SD-Transbordo-N1.json`](../connect/flows/SD-Transbordo-N1.json).
2. Como os ARNs no repositório usam placeholders Zero-Leak (`000000000000`), clique nos blocos abaixo no editor visual para selecionar os recursos reais da sua instância:
   - Bloco **Set whisper flow (`bloco-definir-sussurro-agente`):** selecione `To agent` → **`SD-Sussurro-Agente`**.
   - Os 5 blocos **Set working queue**:
     - `bloco-fila-prioritaria-p1` → selecione **`SD-Fila-Prioritaria-P1`**
     - `bloco-fila-seguranca` → selecione **`SD-Fila-Seguranca`**
     - `bloco-fila-redes` → selecione **`SD-Fila-Redes`**
     - `bloco-fila-hardware` → selecione **`SD-Fila-Hardware`**
     - `bloco-fila-geral-n1` → selecione **`SD-Fila-Geral-N1`**
   - Bloco **Check hours of operation (`bloco-verificar-horario-operacao`):** selecione **`SD-Horario-Comercial`**.
   - Bloco **Transfer to flow (`bloco-transferir-erro-generico`):** selecione **`SD-Erro-Generico`**.
3. Clique em **Save** e em **Publish**.

### 6.4 `SD-Entrada-Principal` (4º a importar)
1. Vá em **Routing → Flows** → **Create flow** → **Import flow (beta)** → selecione [`connect/flows/SD-Entrada-Principal.json`](../connect/flows/SD-Entrada-Principal.json).
2. Clique nos 4 blocos que referenciam recursos externos e selecione os da sua instância:
   - Bloco **Amazon Q in Connect (`bloco-init-q-in-connect`):** selecione o domínio **`SD-Assistente-Q`**.
   - Bloco **Get customer input (`bloco-lex-servicedesk`):** em *Amazon Lex bot*, selecione **`SD-ServiceDesk-Bot`** e alias **`SD-Live`**.
   - Bloco **Transfer to flow (`bloco-transferir-transbordo-n1`):** selecione **`SD-Transbordo-N1`**.
   - Bloco **Transfer to flow (`bloco-transferir-erro-generico`):** selecione **`SD-Erro-Generico`**.
3. Clique em **Save** e em **Publish**.

---

## Fase 7 — Configurar o Communications Widget e Publicar o Site

### 7.1 Publicar a Landing Page na Vercel (ou rodar localmente)
- **Opção A — Deploy na Vercel:**
  1. Suba o repositório para o seu GitHub (`git push`).
  2. Na Vercel, clique em **Add New → Project**, importe o repositório e mantenha as configurações detectadas pelo [`vercel.json`](../vercel.json).
  3. Faça o primeiro deploy e copie a URL pública gerada (ex.: `https://nuvemtech-service-desk.vercel.app`).
- **Opção B — Teste 100% na sua máquina (`localhost`):**
  - Você usará `http://localhost:8080` como domínio permitido no widget.

### 7.2 Criar o Communications Widget no Amazon Connect
1. No painel do Amazon Connect, vá em **Channels → Communication widgets** → **Add widget**:
   - **Name:** `SD-Widget-Portal-TI`
   - **Description:** `Widget omnichannel Central de TI NuvemTech`
   - **Contact flow:** selecione **`SD-Entrada-Principal`**
   - Marque **Add chat to website** e (opcionalmente) **Add web calling to website** para chamadas de voz via WebRTC.
   - Clique em **Save and continue**.
2. Em **Customize communication widget**, ajuste o título para `Central de TI NuvemTech` e clique em **Save and continue**.
3. Em **Add domain for communication widget (Allowed domains)**:
   - Adicione a URL da sua Vercel (`https://<seu-projeto>.vercel.app`) e/ou `http://localhost:8080`.
   - Desmarque *Require authentication (JWT)* para o ambiente de laboratório.
   - Clique em **Save and continue**.
4. Na tela final (**Widget script**), clique em **Copy script**.

### 7.3 Injetar o Snippet com Segurança (Zero-Leak)
- **Na Vercel:**
  1. Vá em **Project Settings → Environment Variables**.
  2. Crie a variável `CONNECT_WIDGET_SNIPPET` e cole o script copiado do Amazon Connect.
  3. Crie a variável `WIDGET_MAX_INTERACOES` com valor `5`.
  4. Clique em **Redeploy** no último deployment: o script `python3 scripts/injetar_widget.py` vai embutir o snippet em Base64 no `landing/dist/assets/js/widget-loader.js`.
- **Na sua máquina (`localhost`):**
  1. Crie o arquivo `landing/widget-snippet.local.html` (ele já é ignorado pelo `.gitignore`) e cole o script copiado.
  2. Rode no terminal:
     ```bash
     python scripts/injetar_widget.py
     python -m http.server 8080 --directory landing/dist
     ```
  3. Abra `http://localhost:8080` no navegador.

---

## Fase 8 — Teste Final Ponta a Ponta (Site ↔ Bot ↔ Cases ↔ CCP v2)

### 8.1 Preparar o Painel do Analista (CCP v2)
1. No painel do Amazon Connect, clique no ícone de **headset/telefone** no canto superior direito para abrir o **Contact Control Panel (CCP v2)** (ou acesse `https://<INSTANCE_ALIAS>.my.connect.aws/agent-app-v2`).
2. Mude o status do seu usuário no canto superior esquerdo do CCP de `Offline` para **`Available`**.

### 8.2 Executar os 3 Cenários do Case 2 no Widget do Site
Abra a sua Landing Page (na Vercel ou em `http://localhost:8080`) e clique no botão azul **"Iniciar Atendimento (Chat ou Voz)"**:

1. **Teste 1 — Reset de Senha (`PasswordReset` → `SD-Fila-Seguranca`):**
   - Clique no balão do widget no canto inferior direito para iniciar o chat.
   - Após a saudação da Central de TI, envie:
     ```text
     Esqueci minha senha, minha matrícula é NT1001 e meu PIN é 4821
     ```
   - **O que deve acontecer:**
     - O bot valida a matrícula `NT1001` (Ana) e o PIN `4821`, informa o protocolo `SD-AAAAMMDD-XXXXXX` e avisa que está transferindo para a **Fila de Segurança**.
     - No seu **CCP v2**, toca um novo atendimento de chat vindo da fila **`SD-Fila-Seguranca`**, anunciando o sussurro (`SD-Sussurro-Agente`) com prioridade `P3`, protocolo e resumo.
     - Aceite o chat, envie `"Olá Ana, seu link de redefinição foi liberado. Seu problema foi resolvido?"`, responda no widget `"Sim, resolvido, funcionou perfeitamente!"` e encerre o contato.

2. **Teste 2 — Problema de Rede (`NetworkIssue` → `SD-Fila-Redes`):**
   - Inicie um novo atendimento no widget e envie (por chat ou falando no microfone pela chamada web):
     ```text
     Não consigo acessar a internet, minha VPN não conecta, matrícula NT1007, afeta meu setor
     ```
   - **O que deve acontecer:**
     - O bot reconhece Marina (`NT1007`, filial Recife `REC`), detecta automaticamente o incidente massivo **`INC-0002`**, orienta usar o gateway `BR-Sudeste-Backup` e transfere para a **`SD-Fila-Redes`** com prioridade `P2`.
     - No CCP v2, o atendimento chega na **`SD-Fila-Redes`** com `sd_incidente_vinculado=INC-0002` e `sd_resumo` preenchidos.

3. **Teste 3 — Solicitação de Equipamento (`HardwareRequest` → Connect Cases):**
   - Inicie um novo atendimento no widget e envie:
     ```text
     Quero solicitar um notebook novo, minha matrícula é NT1008
     ```
   - **O que deve acontecer:**
     - O bot identifica Felipe (`NT1008`, filial Manaus `MAO`, sem técnico local), cria o chamado no **Connect Cases**, informa o ID do caso + protocolo + prazo de 7 dias úteis por logística expressa e encerra o autoatendimento com `sd_resolvido_bot=true` (contando diretamente para o **FCR** sem ocupar fila humana!).
   - Para testar o transbordo para a **`SD-Fila-Hardware`**, peça um item sem estoque:
     ```text
     Preciso de um monitor 27 4K, matrícula NT1009
     ```
     O bot avisa que `MONITOR_27` está sem saldo, sugere `MONITOR_24` e transfere para a **`SD-Fila-Hardware`**.

---

## Fase 9 — Conferir Métricas (FCR e TMA) e Desligar o Ambiente (Teardown)

### 9.1 Visualizar Transcrição, Sentimento, FCR e TMA
1. **Contact Search (Contact Lens):** no menu do Amazon Connect, vá em **Analytics and optimization → Contact search** e abra os contatos recém-encerrados. Você verá:
   - A transcrição completa em português;
   - A curva de sentimento do colaborador;
   - Todos os atributos `sd_*` (`sd_intencao`, `sd_prioridade`, `sd_fila_destino`, `sd_protocolo`, `sd_resolvido_bot`, `sd_resumo`);
   - A categoria `FCR_CONFIRMADO` aplicada pela regra do Contact Lens.
2. **Métricas do Supervisor (TMA e FCR):**
   - Vá em **Analytics and optimization → Real-time metrics → Queues** para ver os contatos atendidos em `SD-Fila-Seguranca`, `SD-Fila-Redes` e `SD-Fila-Hardware` e a coluna **AHT (Average Handle Time / TMA)**.

### 9.2 Teardown FinOps (Zerar Custos após o Estudo)
Quando finalizar os testes e capturar os prints (lembre-se de ocultar os 12 dígitos da conta AWS nos prints!), exclua os recursos nesta ordem:
1. **Amazon Connect:** exclua a instância em **Amazon Connect → selecionar instância → Delete** (remove também Cases, Q in Connect e Contact Lens vinculados).
2. **Amazon Lex V2:** exclua o bot `SD-ServiceDesk-Bot`.
3. **AWS Lambda + CloudWatch:** exclua a função `sd-fulfillment-servicedesk` e o log group `/aws/lambda/sd-fulfillment-servicedesk`.
4. **Amazon S3:** esvazie e exclua o bucket `sd-kb-artigos-<SEU_ACCOUNT_ID>-us-east-1` e o bucket automático `amazon-connect-*`.
