# Handoff Antigravity devops-engineer — Deploy Coolify

## Missão
Fazer deploy do backend FastAPI do portal **EXTR.AI** no Coolify.
O código está pronto em `portal/backend/`. Tem Dockerfile incluso.

---

## O que fazer

### 1. Criar novo serviço no Coolify

- Tipo: **Docker** (build a partir do Dockerfile)
- Source: repositório Git (apontar para a pasta `portal/backend/`)
- Branch: `main`
- Build context: `portal/backend/`
- Dockerfile path: `portal/backend/Dockerfile`
- Porta exposta: `8000`

### 2. Configurar variáveis de ambiente

No painel do Coolify, adicionar estas env vars (pegar os valores com o dono do projeto):

```
SUPABASE_URL=https://qhjyvdywvdcbdgicwjzu.supabase.co
SUPABASE_ANON_KEY=<pegar no Supabase dashboard → Settings → API>
SUPABASE_SERVICE_KEY=<pegar no Supabase dashboard → Settings → API → service_role>
GEMINI_API_KEY=<chave da Google AI Studio>
STRIPE_SECRET_KEY=sk_live_...  (ou sk_test_ para homologação)
STRIPE_WEBHOOK_SECRET=whsec_...  (gerado ao criar o webhook no Stripe)
STRIPE_PRICE_STARTER=price_1TAyPz3VpVuJE5CXVvx850IZ
STRIPE_PRICE_PRO=price_1TAyPz3VpVuJE5CXZyg3RMNL
STRIPE_PRICE_EMPRESA=price_1TAyPz3VpVuJE5CX87UR4V88
FRONTEND_URL=https://apex-extractor-pro.lovable.app
```

> **Importante:** `FRONTEND_URL` é a URL do projeto Lovable.dev (ou o domínio customizado quando conectado).
> Ela é usada tanto para CORS quanto para redirect após pagamento Stripe.

### 3. Configurar domínio

- Subdomínio do backend: `api.extrai.online`
- No Coolify: adicionar domínio `api.extrai.online` ao serviço
- No registrador do domínio: criar registro DNS:
  ```
  Tipo: CNAME (ou A)
  Nome: api
  Valor: IP/host do servidor Coolify
  TTL: 300
  ```
- Habilitar HTTPS/SSL automático (Let's Encrypt via Coolify)

> **Nota:** Se o domínio ainda não estiver pronto, fazer deploy em URL temporária do Coolify primeiro (ex: `apex-backend.hsbmarketing.com.br`) e atualizar quando o domínio chegar.

### 4. Verificar health check

Após deploy, confirmar que está respondendo:

```bash
curl https://api.extrai.online/health
# Esperado: {"status":"ok","service":"apex-portal-backend","version":"1.0.0"}
```

### 5. Configurar webhook Stripe

No Stripe Dashboard → Developers → Webhooks → Add endpoint:
- URL: `https://api.extrai.online/webhook/stripe`
- Eventos a escutar:
  - `checkout.session.completed`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
- Copiar o **Signing secret** (`whsec_...`) e colocar em `STRIPE_WEBHOOK_SECRET` no Coolify

---

## Estrutura do backend

```
portal/backend/
├── Dockerfile          ← build com python:3.11-slim
├── requirements.txt    ← dependências (fastapi, stripe, pymupdf, etc.)
├── main.py             ← app FastAPI com 9 endpoints
└── core/
    ├── auth.py         ← verifica JWT do Supabase
    ← database.py      ← todas as operações Supabase via REST
    └── extraction.py   ← Layer 1 + Layer 2 de IA (Gemini)
```

## Endpoints disponíveis

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/generate-schema` | Layer 1: descrição → colunas |
| POST | `/extract-custom` | Layer 2: PDF → Job ID |
| GET | `/job/{id}` | Status do job |
| GET | `/job/{id}/download` | Download Excel |
| GET | `/usage` | Uso do usuário |
| POST | `/create-checkout-session` | Stripe Checkout |
| POST | `/create-portal-session` | Stripe Customer Portal |
| POST | `/webhook/stripe` | Webhook Stripe (sem JWT) |

---

## Checklist de verificação

- [ ] Container rodando sem erros nos logs
- [ ] `GET /health` retorna 200
- [ ] HTTPS ativo no subdomínio `api.extrai.online`
- [ ] Todas as env vars configuradas (sem valor vazio crítico)
- [ ] Webhook Stripe apontando para a URL correta
- [ ] `FRONTEND_URL` configurada com a URL do Lovable

---

## Observações importantes

1. **Não mexer** na pasta `dist/` na raiz do projeto — contém o `.exe` de produto separado
2. O backend roda **completamente isolado** em `portal/backend/` — não há dependência com o restante do repo
3. O serviço processa PDFs em memória (não salva em disco) — nenhum volume Docker necessário
4. O resultado Excel fica armazenado como **base64 no Supabase** (coluna `result_data` em `extraction_jobs`)
5. PDFs são **deletados da memória** após extração — conformidade LGPD automática
