# Brief Lovable.dev — Apex Extractor Portal

## Como usar este documento
1. Cole o conteúdo da seção **PROMPT PARA LOVABLE** direto no chat do Lovable.dev
2. Depois use as seções de **Integração** para conectar ao backend

---

## PROMPT PARA LOVABLE (copie tudo abaixo até a linha de corte)

---

Build a SaaS web app called **Apex Extractor** — an AI-powered PDF data extraction portal.

**Overview:** Users describe in natural language what data they want to extract from PDF files, the AI generates the extraction logic automatically, and returns a formatted Excel spreadsheet. No coding required.

**Tech stack:**
- React + TypeScript + Tailwind CSS + shadcn/ui
- Supabase Auth (email + magic link)
- Stripe for payments (Checkout + Customer Portal)
- Backend API: environment variable `VITE_API_URL` (FastAPI, already built)

---

### Pages & Routing

**1. Landing Page (`/`)**
- Hero section: headline "Extraia qualquer dado de PDFs com IA — sem programar" + subheadline
- **Video Demo**: Embed um vídeo curto (ou placeholder estilizado) mostrando o produto funcionando em 30s logo abaixo ou ao lado do Hero. Isso aumenta drasticamente a conversão!
- 3-step how it works: "Descreva → Envie o PDF → Baixe o Excel"
- **Aviso Crítico na Landing**: Perto da área de upload e no how-it-works, adicione um banner ou warning: *"Nota: Suportamos apenas PDFs digitais (gerados por computador). Scans ou imagens digitalizadas não são suportados no momento."*
- Features grid (6 boxes): Flexível via IA, Qualquer formato PDF, Excel formatado, Resultado em segundos, 100% seguro (PDF deletado após extração), Plataforma em nuvem
- Pricing section (3 cards — see Pricing below)
- CTA button: "Comece grátis — sem cartão"
- **Testimonials**: Seção pequena com 2 depoimentos de especialistas reais (ex: Advogado ganhando horas por semana, Pesquisador organizando anais facilmente).
- Footer: minimalista, mas **DEVE CONTER** links para "Termos de Uso" e "Política de Privacidade (LGPD compliance)", além de um mini-badge "Site Seguro / 100% Protegido".

**2. Auth (`/login`, `/signup`)**
- Use Supabase Auth UI component
- Magic link + email/password
- After login → redirect to `/app`

**3. App Dashboard (`/app`)**
This is the MAIN screen. Must be clean, focused, step-by-step UX.

Layout: centered card, max-width 720px

**Onboarding Tooltip:** No primeiro login do usuário, exiba um pequeno modal/foco em tela apontando para a caixa de descrição: *"Comece descrevendo com suas próprias palavras o que deseja extrair. Ex: Nome, Valor, CNPJ."*

**Step 1 — Describe extraction (always visible)**
```
Label: "O que você quer extrair?"
Textarea (4 rows, placeholder): "Ex: Quero extrair o nome das partes, CNPJ, valor do contrato e data de assinatura"
Button: "Gerar esquema de extração →"
```
On button click:
- POST to `{API_URL}/generate-schema` with `{ description: string }` and Bearer token
- Show loading spinner: "Analisando seu pedido..."
- On success: show **Schema Preview** component (see below)
- On error: show toast with error message

**Schema Preview component** (shows after /generate-schema returns):
```
Green checkmark + "Esquema gerado!"
Columns preview: pill/badge for each column name returned
  Ex: [CNPJ] [Nome das Partes] [Valor do Contrato] [Data]
Small text: "Estas serão as colunas do seu Excel"
Button to edit description and regenerate
```

**Step 2 — Upload PDF** (shows after schema is confirmed)
```
Drag & drop zone OR click to select
Accept: .pdf only
Show filename + page count after selection
Show warning if pages > plan limit
[WARNING BANNER RED/YELLOW]: "Atenção: A extração falhará se o PDF for apenas uma imagem ou documento escaneado sem texto selecionável."
```

**Step 3 — Extract button**
```
Big primary button: "Extrair dados agora →"
Disabled until both schema AND file are ready
```
On click:
- POST multipart form to `{API_URL}/extract-custom` with file + schema_prompt + columns
- Immediate response: job_id
- Transition to **Job Progress** view

**Job Progress view** (replaces extract button area):
```
Animated progress bar (indeterminate while processing)
Status text cycling: "Lendo o PDF..." → "Processando com IA..." → "Gerando Excel..."
Poll GET {API_URL}/job/{job_id} every 3 seconds
```
On status=done:
- Show success state: green checkmark + "Extração concluída!"
- Big download button: "Baixar Excel →" (calls /job/{id}/download)
- Show stats: "X páginas processadas | Y linhas extraídas"
- Button: "Nova extração" (resets the form)

On status=error:
- Show error message in red
- Button: "Tentar novamente"

**Usage bar** (top of /app page, below nav):
```
"Páginas usadas este mês: 1.240 / 3.000"
Progress bar (color: green < 70%, yellow 70-90%, red > 90%)
```
Fetch from GET `{API_URL}/usage`

**4. Extraction History (`/app/history`)**
Table columns: Arquivo | Colunas | Páginas | Status | Data | Download
- Fetch from Supabase `extraction_jobs` table directly (Supabase client)
- Filter by user_id = current user
- Order by created_at DESC
- Status badge: pending (gray) / processing (yellow spinner) / done (green) / error (red)
- Download button (only when done): calls backend download endpoint

**5. Pricing (`/pricing`)**

Three cards side by side. Middle card (Pro) is highlighted/featured.

| | Free | Starter | Pro ⭐ | Empresa |
|---|---|---|---|---|
| Preço | R$0 | R$47/mês | R$97/mês | R$297/mês |
| Páginas/mês | 300 | 3.000 | 15.000 | 80.000 |
| Arquivo máx | 50 páginas | 300 páginas | 1.000 páginas | Ilimitado |
| API Access | ❌ | ❌ | ❌ | ✅ |
| CTA | Começar grátis | Assinar | Assinar | Assinar |

Stripe integration:
- "Assinar" buttons → Stripe Checkout (use Stripe's prebuilt checkout)
- After successful payment → redirect to `/app?upgraded=true`
- Show success toast: "Plano ativado com sucesso!"

**6. Account / Billing (`/app/account`)**
- User email + avatar initials
- Current plan badge
- "Gerenciar assinatura" button → Stripe Customer Portal
- "Sair" button → Supabase signOut → redirect to `/`

---

### Navigation

**Public nav (landing):** Logo | Recursos | Preços | Entrar | Começar grátis

**App nav (authenticated):** Logo | Extrair (main) | Histórico | Uso | Conta

---

### Design System

**Brand colors:**
- Primary: `#1F4E79` (dark navy blue)
- Accent: `#2ECC71` (green — success, CTAs)
- Background: `#F8FAFC` (light gray)
- Card: `#FFFFFF`
- Text: `#1E293B`

**Typography:** Inter font

**Style:** Clean, professional, minimal. Not flashy. Target audience: researchers, lawyers, accountants, HR professionals. Think Notion + Stripe vibes.

**Spacing:** Generous padding. Cards with subtle shadows. Rounded corners (radius: 12px).

---

### Environment Variables

```
VITE_API_URL=http://localhost:8000     # backend (change to prod URL after deploy)
VITE_SUPABASE_URL=                     # your Supabase project URL
VITE_SUPABASE_ANON_KEY=               # your Supabase anon key
VITE_STRIPE_PUBLISHABLE_KEY=          # Stripe publishable key
```

---

### Supabase Setup

- Enable Email Auth + Magic Link in Supabase dashboard
- The app reads `extraction_jobs` and `user_usage` tables directly via Supabase client for the history page
- RLS is enabled (user only sees their own rows)
- After auth, store session token and send as `Authorization: Bearer {token}` to all API calls

---

### Key UX Requirements

1. **Mobile responsive** — works on phone (users may upload PDFs from mobile)
2. **Loading states** on every async action
3. **Error boundaries** — never show a blank screen on API error
4. **Toast notifications** for success/error feedback
5. **No page reload** on form submission — all async

---

### User Flow (happy path)

```
Landing → "Começar grátis" → Signup → /app
→ Type: "Quero extrair CNPJ e nome das partes"
→ Click "Gerar esquema" → See columns preview [CNPJ] [Nome das Partes]
→ Upload contrato.pdf (10 pages) → Click "Extrair"
→ Watch progress bar → "Extração concluída!"
→ Download "contrato_extrato.xlsx"
→ Usage bar updates: "10 / 300 páginas usadas"
```

---

(FIM DO PROMPT PARA LOVABLE)

---

## Guia de Integração Backend ↔ Frontend

### Endpoints do backend

| Método | URL | Auth | Descrição |
|---|---|---|---|
| `POST` | `/generate-schema` | Bearer | Body JSON: `{description: string}` → retorna `{system_prompt, columns, description}` |
| `POST` | `/extract-custom` | Bearer | Multipart form: `file` (PDF) + `schema_prompt` (string) + `columns` (JSON array string) → retorna `{job_id, status, pages}` |
| `GET` | `/job/{id}` | Bearer | Retorna `{id, status, pages_processed, columns, error_message, created_at}` |
| `GET` | `/job/{id}/download` | Bearer | Retorna Excel (octet-stream) — usar `window.open()` ou `fetch` + `createObjectURL` |
| `GET` | `/usage` | Bearer | Retorna `{plan, month, pages_used, pages_limit, pages_remaining, extractions_used}` |

### Como fazer o download no frontend

```javascript
// Nunca usar <a href={backendUrl}> para endpoints autenticados
// Usar fetch + blob:

const downloadResult = async (jobId, token) => {
  const resp = await fetch(`${API_URL}/job/${jobId}/download`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'extrato.xlsx';
  a.click();
  URL.revokeObjectURL(url);
};
```

### Polling do job (sugestão de implementação)

```javascript
const pollJob = async (jobId, token, onUpdate) => {
  const interval = setInterval(async () => {
    const resp = await fetch(`${API_URL}/job/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const job = await resp.json();
    onUpdate(job);
    if (job.status === 'done' || job.status === 'error') {
      clearInterval(interval);
    }
  }, 3000); // 3 segundos
  return () => clearInterval(interval); // cleanup
};
```

### Como pegar o token Supabase

```javascript
import { supabase } from './lib/supabase';

const { data: { session } } = await supabase.auth.getSession();
const token = session?.access_token;
```

---

## Stripe — Price IDs (criar no dashboard Stripe)

Após criar os produtos no Stripe, anote os Price IDs e configure no Lovable:

| Plano | Ciclo | Price ID |
|---|---|---|
| Starter | Mensal | `price_xxxxx` |
| Pro | Mensal | `price_xxxxx` |
| Empresa | Mensal | `price_xxxxx` |

Os Price IDs serão usados nos botões de Checkout.

---

## Checklist pós-Lovable

Antes de integrar com o backend real, verifique no Lovable:

- [ ] Login/signup funcionando (Supabase Auth)
- [ ] Token sendo enviado em todas as chamadas ao backend
- [ ] Polling do job funcionando (status atualiza a cada 3s)
- [ ] Download do Excel funcionando via fetch+blob
- [ ] Usage bar buscando dados reais do `/usage`
- [ ] Histórico lendo da tabela `extraction_jobs` no Supabase
- [ ] Responsive em mobile

---

## Nota sobre CORS

O backend em [portal/backend/main.py](portal/backend/main.py) já tem CORS configurado para aceitar `*.lovable.app` e `*.lovableproject.com`.
Quando o Lovable gerar a URL do seu projeto (ex: `https://abc123.lovable.app`), adicione ela na variável `FRONTEND_URL` do backend.
