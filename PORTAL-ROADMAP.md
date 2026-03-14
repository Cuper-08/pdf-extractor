# Apex Extractor Pro — Portal SaaS: Roadmap Completo de Construção

> **Objetivo:** Transformar o app desktop em um portal web com extração flexível via IA, modelo de assinatura mensal, servindo qualquer nicho que trabalhe com PDFs.

---

## Visão Geral do Produto

O usuário acessa o portal, descreve em linguagem natural o que quer extrair ("quero o CNPJ das partes, valor do contrato e data de assinatura"), faz upload do PDF e recebe um Excel/CSV com os dados estruturados.

**Diferencial:** Sem templates manuais. Sem configuração técnica. A IA entende o pedido e gera a lógica de extração automaticamente.

---

## Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Backend API | FastAPI (Python) | Já existe em `/pdf-extractor/`, 80% reutilizável |
| Processamento PDF | PyMuPDF (fitz) | Já em uso, funciona muito bem |
| IA de Extração | Google Gemini Flash | Já integrado, custo ultra-baixo (~R$0,20/1000 pgs) |
| Banco de Dados | Supabase (PostgreSQL) | Já integrado para licenças |
| Autenticação | Supabase Auth | Nativo no Supabase, gratuito |
| Frontend | HTML/JS + Tailwind CSS | Simples e rápido para MVP; migrar para Next.js depois |
| Pagamentos | Mercado Pago | Melhor para Brasil (PIX, cartão, boleto) |
| Deploy | Coolify | Já configurado e funcionando |
| Armazenamento temp | Supabase Storage | Para PDFs durante processamento (deletar após conclusão) |

---

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────┐
│                     PORTAL WEB                          │
│  [Upload PDF] + [Descrever o que extrair] + [Extrair]   │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND                        │
│                                                         │
│  POST /generate-schema  ──►  Layer 1 (Meta-IA)          │
│    Descrição natural  ──►  System Prompt customizado     │
│                                                         │
│  POST /extract-custom   ──►  Layer 2 (Extração)         │
│    PDF + system_prompt  ──►  Job ID (async)              │
│                                                         │
│  GET  /job/{id}         ──►  Status do job              │
│  GET  /job/{id}/download ──► Excel/CSV (streaming)      │
│  GET  /usage            ──►  Páginas usadas no mês      │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐        ┌─────────────────────────┐
│  GEMINI FLASH    │        │       SUPABASE           │
│  API (Google)    │        │                         │
│                  │        │  extraction_jobs        │
│  Layer 1:        │        │  user_usage             │
│  Gera prompts    │        │  pdf_documents          │
│                  │        │  pdf_chunks             │
│  Layer 2:        │        │  users (Auth)           │
│  Extrai dados    │        │  subscriptions          │
└──────────────────┘        └─────────────────────────┘
```

---

## Como Funciona a Extração em 2 Camadas

### Layer 1 — Gerador de Schema (novo)
```
Input:  "Quero extrair CNPJ das partes, valor do contrato, data de assinatura"
           │
           ▼
    Gemini recebe um meta-prompt que instrui:
    "Transforme esse pedido em um system prompt de extração que gera
     uma tabela Markdown com as colunas certas"
           │
           ▼
Output: System prompt customizado para ESSE tipo de documento
        + Lista de colunas: ["CNPJ", "Parte", "Valor", "Data"]
```

### Layer 2 — Extração (já existe, 80% do código atual)
```
Input:  PDF + system_prompt gerado pela Layer 1
           │
           ▼
    smart_split() → chunks de ~10k chars com quebra natural
           │
           ▼
    extract_from_gemini() com o prompt customizado [PARALELO]
           │
           ▼
    parse_markdown_table_to_dicts()
    consolidar_projetos() (deduplicação)
    expandir_por_autor() (1 linha por entidade)
           │
           ▼
Output: Excel/CSV para download
```

---

## Fases de Construção

---

### FASE 1 — Fundação do Backend (Semana 1)

**Objetivo:** API funcionando localmente com extração flexível.

#### 1.1 Criar estrutura do novo backend

```
portal-backend/
├── main.py              ← FastAPI principal
├── extraction/
│   ├── __init__.py
│   ├── gemini.py        ← extract_from_gemini() + _get_gemini_model() (do extrator_standalone.py)
│   ├── chunker.py       ← smart_split() (do pdf-extractor/main.py)
│   ├── parser.py        ← parse_markdown_table_to_dicts() + consolidar_projetos() + expandir_por_autor()
│   └── schema_gen.py    ← NOVO: Layer 1, meta-prompt para gerar system prompts
├── database/
│   ├── __init__.py
│   └── supabase.py      ← supabase_insert() + helpers (do pdf-extractor/main.py)
├── auth/
│   └── middleware.py    ← Validação de JWT do Supabase Auth
├── billing/
│   └── usage.py         ← Controle de páginas consumidas por usuário/mês
├── requirements.txt
└── Dockerfile
```

#### 1.2 Código reutilizado do projeto atual (copiar e adaptar)

| De (arquivo atual) | Para (novo backend) | Mudança necessária |
|---|---|---|
| `extrator_standalone.py:119-154` | `extraction/gemini.py` (SYSTEM_PROMPT) | Usar como exemplo no meta-prompt |
| `extrator_standalone.py:157-206` | `extraction/gemini.py` | Converter `requests` → `httpx.AsyncClient` |
| `extrator_standalone.py:240-278` | `extraction/parser.py` | Copiar direto |
| `extrator_standalone.py:286-313` | `extraction/parser.py` | Copiar direto |
| `extrator_standalone.py:316-358` | `extraction/parser.py` | Copiar direto |
| `pdf-extractor/main.py:30-52` | `extraction/chunker.py` | Copiar direto |
| `pdf-extractor/main.py:55-61` | `database/supabase.py` | Copiar direto |

#### 1.3 Novo componente: `extraction/schema_gen.py`

```python
META_PROMPT = """
Você é um especialista em análise de documentos estruturados.
O usuário quer extrair informações específicas de documentos PDF.

Pedido do usuário: {user_request}

Gere um system prompt de extração que:
1. Define exatamente quais campos extrair (que serão as colunas da tabela Markdown)
2. Instrui o modelo a retornar EXCLUSIVAMENTE uma tabela Markdown com essas colunas
3. Instrui a deixar células vazias quando o dado não existir (nunca inventar)
4. Define quantas linhas por registro (ex: 1 contrato com 2 partes = 2 linhas)
5. Instrui a ignorar cabeçalhos, rodapés e numeração de página
6. É escrito em português

Retorne SOMENTE o texto do system prompt, sem explicação adicional.
"""

async def generate_extraction_schema(user_request: str, api_key: str) -> dict:
    """Layer 1: converte descrição natural → system_prompt + column_names"""
    ...
    return {"system_prompt": "...", "column_names": ["Col1", "Col2", "Col3"]}
```

#### 1.4 Endpoints FastAPI a criar

```python
# Autenticação: todos os endpoints exigem Bearer token do Supabase Auth

POST /generate-schema
  Body: { "description": "quero CNPJ, valor e data" }
  Response: { "system_prompt": "...", "column_names": ["CNPJ", "Valor", "Data"], "preview": "..." }

POST /extract
  Body: multipart/form-data
    - file: PDF
    - system_prompt: string (gerado pelo /generate-schema)
    - column_names: JSON array
  Response: { "job_id": "uuid", "status": "queued", "total_pages": 42 }

GET /job/{job_id}
  Response: { "status": "processing|done|error", "progress": 0.75, "pages_processed": 31 }

GET /job/{job_id}/download?format=xlsx|csv
  Response: arquivo para download (streaming)

GET /usage
  Response: { "plan": "pro", "pages_used": 4200, "pages_limit": 15000, "reset_date": "2026-04-01" }
```

---

### FASE 2 — Banco de Dados (Semana 1)

**Objetivo:** Criar schema no Supabase para o portal.

#### 2.1 Tabelas a criar no Supabase (projeto novo ou existente)

```sql
-- Assinaturas (ligado ao Supabase Auth user_id)
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  plan TEXT NOT NULL DEFAULT 'free',  -- free | starter | pro | empresa
  pages_limit INT NOT NULL DEFAULT 300,
  status TEXT NOT NULL DEFAULT 'active',  -- active | cancelled | past_due
  mercadopago_subscription_id TEXT,
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Controle de uso mensal
CREATE TABLE user_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  month TEXT NOT NULL,  -- "2026-03"
  pages_processed INT NOT NULL DEFAULT 0,
  jobs_count INT NOT NULL DEFAULT 0,
  UNIQUE(user_id, month)
);

-- Jobs de extração
CREATE TABLE extraction_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued',  -- queued | processing | done | error
  description TEXT,            -- pedido original do usuário em linguagem natural
  system_prompt TEXT,          -- prompt gerado pela Layer 1
  column_names JSONB,          -- ["CNPJ", "Valor", "Data"]
  original_filename TEXT,
  total_pages INT,
  pages_processed INT DEFAULT 0,
  result_path TEXT,            -- caminho no Supabase Storage
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);

-- Chunks de processamento (fila async)
CREATE TABLE job_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES extraction_jobs(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  chunk_text TEXT NOT NULL,
  estimated_pages TEXT,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | done | error
  retry_count INT DEFAULT 0,
  result_json JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

#### 2.2 Row Level Security (RLS)

```sql
-- Usuário só vê seus próprios dados
ALTER TABLE extraction_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own jobs" ON extraction_jobs
  FOR ALL USING (auth.uid() = user_id);

-- Mesmo para as outras tabelas
ALTER TABLE user_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own usage" ON user_usage
  FOR ALL USING (auth.uid() = user_id);
```

---

### FASE 3 — Frontend MVP (Semana 2)

**Objetivo:** Interface web funcional (sem perfumaria, foco em fluxo).

#### 3.1 Páginas necessárias

```
/                    ← Landing page (CTA: "Comece grátis")
/app                 ← Painel principal (login obrigatório)
/app/nova-extracao  ← Formulário: descrever + upload + iniciar
/app/jobs            ← Histórico de extrações
/app/planos          ← Upgrade de plano
/login               ← Login/Cadastro (Supabase Auth UI)
```

#### 3.2 Fluxo da página `/app/nova-extracao`

```
┌────────────────────────────────────────────────┐
│  Passo 1: O que você quer extrair?             │
│  ┌──────────────────────────────────────────┐  │
│  │ Ex: "Quero o CNPJ das partes, valor do  │  │
│  │ contrato e data de assinatura"           │  │
│  └──────────────────────────────────────────┘  │
│  [Gerar Schema] ──► mostra preview das colunas │
│                                                 │
│  Passo 2: Faça upload do PDF                   │
│  ┌──────────────────────────────────────────┐  │
│  │         Arraste o PDF aqui               │  │
│  │         ou clique para selecionar        │  │
│  └──────────────────────────────────────────┘  │
│  Arquivo: contrato_empresa.pdf (42 páginas)     │
│  Páginas disponíveis: 11.800 / 15.000          │
│                                                 │
│  [INICIAR EXTRAÇÃO]                            │
└────────────────────────────────────────────────┘
```

#### 3.3 Componentes de UI a construir

- **SchemaPreview**: mostra as colunas geradas após o `/generate-schema` (ex: `[CNPJ] [Valor] [Data]`)
- **ProgressBar**: polling no `GET /job/{id}` a cada 2s para atualizar progresso
- **UsageMeter**: barra mostrando páginas usadas vs. limite do plano
- **JobHistoryTable**: lista de jobs com status, data, botão de download

#### 3.4 Tecnologia do frontend

- **MVP**: HTML + Alpine.js + Tailwind CSS (deploy estático no Coolify ou Netlify)
- **v2**: Migrar para Next.js quando tiver tráfego real
- **Supabase JS Client**: para Auth (login/logout/session) e chamadas diretas ao Supabase

---

### FASE 4 — Autenticação e Controle de Acesso (Semana 2)

**Objetivo:** Login funcional, planos controlados, limite de páginas aplicado.

#### 4.1 Supabase Auth

- Habilitar providers: **Email/Senha** + **Google OAuth** (opcional)
- Configurar redirect URLs no Coolify
- No backend FastAPI: validar JWT em todo endpoint com middleware

```python
# auth/middleware.py
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token = Depends(security)):
    # Validar JWT do Supabase
    # Retornar user_id
    ...
```

#### 4.2 Lógica de limite de uso

```python
# billing/usage.py
async def check_and_deduct_pages(user_id: str, pages: int):
    usage = await get_monthly_usage(user_id)
    subscription = await get_subscription(user_id)

    if usage.pages_processed + pages > subscription.pages_limit:
        raise HTTPException(429, "Limite de páginas do plano atingido")

    await increment_usage(user_id, pages)
```

---

### FASE 5 — Pagamentos (Semana 3)

**Objetivo:** Usuário consegue assinar, pagar e ter o plano ativado automaticamente.

#### 5.1 Mercado Pago (recomendado para Brasil)

- Criar conta Mercado Pago Business
- Usar **Mercado Pago Subscriptions API** (suporte a recorrência automática)
- Aceita: cartão de crédito, PIX (manual), boleto

#### 5.2 Webhook de pagamento

```python
POST /webhook/mercadopago
  → Recebe evento "payment.approved" ou "subscription.cancelled"
  → Atualiza tabela subscriptions no Supabase
  → Envia e-mail de confirmação (opcional: via Resend.com)
```

#### 5.3 Planos e preços a cadastrar no MP

| Plano | Preço/mês | Páginas/mês | ID Supabase |
|---|---|---|---|
| Starter | R$47 | 3.000 | `starter` |
| Pro | R$97 | 15.000 | `pro` |
| Empresa | R$297 | 80.000 | `empresa` |

---

### FASE 6 — Landing Page (Semana 3)

**Objetivo:** Página de conversão que explica o produto e converte visitante em trial.

#### 6.1 Estrutura da landing page

```
[Header] Logo + "Comece grátis" (CTA)

[Hero]
  Headline: "Extraia qualquer dado de qualquer PDF em segundos"
  Subheadline: "Descreva o que quer extrair. Nossa IA faz o resto."
  [Demo animado: usuário digita, IA extrai, Excel aparece]
  CTA: "Testar grátis — 300 páginas sem cartão de crédito"

[Como funciona — 3 passos]
  1. Descreva o que quer extrair (linguagem natural)
  2. Faça upload do PDF
  3. Baixe o Excel/CSV

[Casos de uso]
  → Pesquisadores: "Extraia autores e e-mails de anais de congressos"
  → Advogados: "Extraia partes, valores e datas de contratos"
  → RH: "Extraia dados de currículos em massa"
  → Contabilidade: "Extraia CNPJ, valores e datas de notas fiscais"

[Preços]
  Free | Starter R$47 | Pro R$97 | Empresa R$297

[LGPD / Privacidade]
  "PDFs processados e deletados imediatamente. Zero armazenamento de documentos."

[CTA final]
  "Comece grátis agora — sem cartão de crédito"

[Footer] Links legais
```

---

### FASE 7 — Deploy e Infraestrutura (Semana 3-4)

**Objetivo:** Tudo rodando em produção no Coolify.

#### 7.1 Serviços a deployar no Coolify

```
portal-backend      → FastAPI (Docker)
portal-frontend     → HTML estático (Nginx) ou Next.js
```

#### 7.2 Variáveis de ambiente necessárias

```env
# Gemini
GEMINI_API_KEY=AIzaSy...          # Chave da plataforma (não do usuário)

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...       # Service key (acesso admin ao DB)
SUPABASE_ANON_KEY=eyJ...          # Para Supabase Storage

# Mercado Pago
MP_ACCESS_TOKEN=TEST-xxx          # ou PROD-xxx em produção
MP_WEBHOOK_SECRET=xxx

# App
SECRET_KEY=xxx                    # Para assinar tokens internos
FRONTEND_URL=https://apexextractor.com.br
```

#### 7.3 Configuração de domínio

- Registrar domínio (sugestão: `apexextractor.com.br` ou `extratordepdf.com.br`)
- Apontar DNS para Coolify
- Certificado SSL automático via Let's Encrypt (Coolify faz isso)

---

### FASE 8 — Segurança e LGPD (Semana 4)

**Objetivo:** Garantir compliance e remover objeções de clientes sensíveis à privacidade.

#### 8.1 Medidas de segurança

- [ ] PDFs deletados do Supabase Storage imediatamente após extração
- [ ] Chunks de texto deletados após job concluído (ou em até 24h)
- [ ] HTTPS obrigatório em todos os endpoints
- [ ] Rate limiting: máximo 10 requests/min por IP no `/extract`
- [ ] Validação de tipo de arquivo: aceitar SOMENTE `.pdf`
- [ ] Limite de tamanho de upload: máximo 50MB por arquivo
- [ ] Logs sem conteúdo de documentos (só metadados: tamanho, páginas, job_id)

#### 8.2 Política de privacidade

- Criar página `/privacidade` com:
  - Dados coletados: e-mail, histórico de jobs (sem conteúdo)
  - Retenção: documentos deletados após processamento
  - Base legal LGPD: execução de contrato
  - Contato do DPO (você)

---

## Checklist Completo de Implementação

### Backend
- [ ] Criar estrutura `portal-backend/`
- [ ] Copiar e adaptar funções de extração do `extrator_standalone.py`
- [ ] Copiar `smart_split()` e `supabase_insert()` do `pdf-extractor/main.py`
- [ ] Implementar `schema_gen.py` (Layer 1 — meta-prompt)
- [ ] Implementar `POST /generate-schema`
- [ ] Implementar `POST /extract` (async com fila Supabase)
- [ ] Implementar `GET /job/{id}` (polling de status)
- [ ] Implementar `GET /job/{id}/download` (Excel/CSV em BytesIO)
- [ ] Implementar `GET /usage`
- [ ] Implementar middleware de autenticação JWT (Supabase Auth)
- [ ] Implementar controle de limite de páginas por plano
- [ ] Implementar `POST /webhook/mercadopago`
- [ ] Testes: extrair PDF de contrato, anais, currículo, NF

### Banco de Dados (Supabase)
- [ ] Criar tabela `subscriptions`
- [ ] Criar tabela `user_usage`
- [ ] Criar tabela `extraction_jobs`
- [ ] Criar tabela `job_chunks`
- [ ] Configurar RLS em todas as tabelas
- [ ] Ativar Supabase Auth (email + Google)
- [ ] Criar bucket no Supabase Storage para PDFs temporários

### Frontend
- [ ] Criar landing page com os 4 casos de uso
- [ ] Criar página de login/cadastro
- [ ] Criar `/app` — painel principal
- [ ] Criar `/app/nova-extracao` — formulário
- [ ] Criar `/app/jobs` — histórico
- [ ] Criar `/app/planos` — upgrade
- [ ] Implementar polling de status do job
- [ ] Implementar download de resultado
- [ ] Responsivo para mobile

### Pagamentos
- [ ] Criar conta Mercado Pago Business
- [ ] Criar planos de assinatura no MP
- [ ] Integrar botão de checkout
- [ ] Implementar e testar webhook
- [ ] Testar fluxo completo: pagar → plano ativado

### Deploy
- [ ] Criar `Dockerfile` para `portal-backend`
- [ ] Configurar projeto no Coolify
- [ ] Configurar variáveis de ambiente
- [ ] Registrar domínio e configurar DNS
- [ ] SSL automático
- [ ] Testar deploy completo

### Segurança e Legal
- [ ] Implementar deleção automática de PDFs após extração
- [ ] Rate limiting nos endpoints
- [ ] Criar página de Política de Privacidade
- [ ] Criar Termos de Uso
- [ ] Testar upload de arquivo não-PDF (deve rejeitar)

---

## Precificação Final

| Plano | Preço/mês | Páginas/mês | Tamanho máx/arquivo | Destaque |
|---|---|---|---|---|
| **Free Trial** | R$0 | 300 | 50 páginas | Sem cartão, sempre disponível |
| **Starter** | R$47 | 3.000 | 300 páginas | Para uso esporádico |
| **Pro** | R$97 | 15.000 | 1.000 páginas | Para uso frequente |
| **Empresa** | R$297 | 80.000 | Ilimitado | API access + suporte WhatsApp |

**Desconto anual:** pague 10 meses, use 12 (2 meses grátis).

**Custo real de API por plano:**
- Starter: ~R$1,10/mês → margem ~97%
- Pro: ~R$5,50/mês → margem ~94%
- Empresa: ~R$29/mês → margem ~90%

---

## Go-to-Market

### Semana 1–4: Beta fechado
1. Convidar cliente atual (anais de congresso) para testar extração flexível
2. Recrutar 5 beta users de nichos diferentes (2 advogados, 2 RH, 1 contabilidade)
3. Coletar feedback: a Layer 1 gera bons prompts? A extração é precisa?
4. Ajustar o meta-prompt com base nos casos reais

### Semana 5–8: Lançamento
1. Gravar demo de 2 minutos (contrato PDF → CNPJ+partes+valor em 30 segundos)
2. Postar demo no LinkedIn com copy para cada nicho (3 posts separados)
3. Entrar em grupos do Facebook:
   - Pesquisadores: grupos de pós-graduação, grupos de secretárias de congressos
   - Advogados: "Advogados do Brasil", "OAB Digital"
   - RH: "RH e Recrutamento Brasil", "Gestão de Pessoas"
4. Oferecer Free Trial sem cartão (reduz atrito)

### Copy para advogados (testar nos grupos)
> "Você advogado que analisa dezenas de contratos por semana: e se você pudesse extrair automaticamente as partes, CNPJ, valores e datas de qualquer contrato PDF em segundos?
> Sem digitar nada. Você descreve o que quer, a IA extrai.
> PDFs processados e deletados imediatamente — zero armazenamento, LGPD compliant.
> **Teste grátis, sem cartão de crédito:** [link]"

### Mercados prioritários

| # | Segmento | Dor | Abordagem |
|---|---|---|---|
| 1 | Pesquisadores/pós-grad | Extrair dados de anais (validado) | Extensão do produto atual |
| 2 | RH/Recrutamento | Dados de CVs em massa | Demo com CV real |
| 3 | Contabilidade | NF, CNPJ, valores | Demo com nota fiscal |
| 4 | Advogados | Partes, valores, datas de contratos | Foco em LGPD compliance |
| 5 | Imobiliário | Escrituras, registros | Demo com escritura |

---

## Ordem de Execução (Resumo)

```
Semana 1:
  └── Backend: estrutura + extração flexível funcionando localmente
  └── Supabase: schema criado e testado

Semana 2:
  └── Frontend MVP: fluxo completo funcionando (feio mas funcional)
  └── Auth: login com email funcionando

Semana 3:
  └── Pagamentos: Mercado Pago integrado e testado
  └── Landing page: online com vídeo demo
  └── Deploy: tudo rodando no Coolify com domínio próprio

Semana 4:
  └── Segurança: deleção de PDFs, rate limiting, LGPD
  └── Beta: 5 usuários testando
  └── Ajustes com base no feedback

Semana 5+:
  └── Lançamento público
  └── Campanhas LinkedIn e Facebook
  └── Iterar com base em métricas de conversão
```
