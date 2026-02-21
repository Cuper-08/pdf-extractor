# PDF Extractor — Microserviço Python

Microserviço FastAPI para extração e chunking de PDFs acadêmicos, integrado com n8n via HTTP.

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Health check |
| POST | `/extract` | Extrai e divide PDF em chunks |

## Como usar com n8n

O n8n envia o arquivo PDF via `multipart/form-data`:

```
POST http://pdf-extractor:8000/extract
Content-Type: multipart/form-data
Field: file = <binary PDF>
```

### Resposta

```json
{
  "success": true,
  "total_paginas": 285,
  "total_chunks": 185,
  "total_caracteres": 1850000,
  "chunks": [
    {
      "texto_bruto": "...",
      "bloco_atual": 1,
      "total_blocos": 185,
      "paginas_estimadas": "1 a 7"
    }
  ]
}
```

## Deploy no Coolify

1. Faça um repositório GitHub com estes 3 arquivos: `main.py`, `requirements.txt`, `Dockerfile`
2. No Coolify > Project "Ambiente" > production > "+ New" > Application > GitHub
3. Port: `8000`, sem domínio público (rede interna Docker)
4. Deploy!

## Configurar variável de ambiente no n8n

No n8n, o nó `HTTP Request` usa a URL:
```
http://pdf-extractor:8000/extract
```
