# PLAN: PDF Extractor (Async Supabase Architecture)

## Contexto
O usuário escolheu a **Opção C**: Uma arquitetura assíncrona orientada a eventos usando o Supabase. O objetivo é evitar falhas de timeout e limite de memória (Erro 500) ao lidar com PDFs massivos (>1000 páginas). O foco extremo será a **coerência relacional** dos dados extraídos: O LLM fornecerá dados onde o Título A obrigatoriamente terá os Autores A e E-mails A (rejeitando miscelânea de referências não conectadas).

## 🔴 Objetivo Relacional Estrito
- **Regra de Ouro:** O Gemini será advertido via System Prompt que só pode retornar um "Projeto" se houver coesão absoluta entre `Titulo` -> `Autores` -> `E-mails do grupo`. Se na página houver autores soltos de outros projetos ou bibliografias, o LLM descartará o dado sem dó. Os dados serão formatados limpos e sem perdas.

---

## 🏗 Fase 1: Arquitetura de Banco de Dados (Supabase)
Criaremos estruturas robustas para fila de processamento. A vantagem é que se algo quebrar de madrugada, não perderemos os dados.

- `pdf_documents`:
  - `id` (UUID), `filename`, `total_pages`, `total_chunks`, `status` (processing, completed, failed), `created_at`
- `pdf_chunks`:
  - `id` (UUID)
  - `document_id` (FK para `pdf_documents`)
  - `chunk_text` (Texto do bloco de ~10k)
  - `processing_status` (pending, processed, error)
  - `retry_count` (int)
- `extracted_projects` (Tabela Final):
  - `id` (UUID)
  - `document_id` (A qual PDF pertence)
  - `chunk_id` (De qual trecho tiramos o dado)
  - `project_title`
  - `authors` (Array ou texto limpo)
  - `emails` (Array ou texto limpo)

---

## 🐍 Fase 2: Refatoração do Worker Python (`pdf-extractor`)
- **Modificar Endpoint `/extract`:**
  1. O usuário (n8n Mestre) faz upload do PDF para o Python.
  2. O Python salva o cabeçalho em `pdf_documents`.
  3. Realiza o recorte inteligente da mesma forma que resolvemos antes (sem cortar frases na metade).
  4. Agora a diferença mágica: em vez de esperar a resposta inteira, o Python **faz INSERT no Supabase** de todos os "chunks" na tabela `pdf_chunks` com status `pending`.
  5. O Python responde "202 Accepted: Recebido e dividido. Acesse o Supabase para a fila".
  *(Obs: Com isso o n8n Mestre finaliza em < 5 segundos e não trava).*

---

## ⚙️ Fase 3: Workflow N8N

### 1. Workflow Orquestrador Mestre (Recebimento)
- Pega o PDF enviado do Form ou Trigger e envia HTTP puro para a API Python.

### 2. Workflow Consumidor (O Escavador de Projetos)
- Trigger Cronológico: Roda a cada `X` minutos (ou via Hook do Supabase).
- Busca no Supabase Node: `SELECT * FROM pdf_chunks WHERE processing_status = 'pending' LIMIT 5`
- Para cada item (Split in Batches):
  - Chamada ao **Gemini Worker**.
  - **System Prompt Cego-Estrito:**
    *"Extraia Título do Trabalho, Autores e E-mails dos Autores desta página. Você NÃO DEVE INVENTAR DADOS. Se houver Título X, procure estritamente os autores do X e seus e-mails do X. Ignore e rejeite a listagem de autores Y. Ignore referências bibliográficas. Se só tiver título de cabeça e nenhum email válido colado ao autor, ignore."*
  - O JSON Processado é salvo na tabela `extracted_projects`.
  - Atualiza o chunk no Supabase para `processing_status = 'processed'`.

---

## ✅ Lista de Verificação (Pre-Flight)
- [ ] Schema do Supabase criado e permissões de API funcionando?
- [ ] Supabase Token / URL adicionados nas variáveis de ambiente do Python (Coolify)?
- [ ] Divisão na nuvem salva a fila no banco de dados com sucesso?
- [ ] Prompt Cego-Estrito do N8N não retorna "referências" falsas nem emails de outros grupos (Validação final com PDF Mestre)?

---

> 🔴 **Checkpoint do Orquestrador:** De acordo com os protocolos, finalizo a criação desta via de solução baseada na Opção C. A arquitetura protegerá contra erros de infraestrutura ao segmentar a operação, e limitará estritamente os "trabalhos inválidos" usando nosso JSON Constraint estrito no Gemini.
