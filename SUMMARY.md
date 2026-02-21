# Projeto: Extrator de dados N8N

## Status Atual
O projeto está em uma fase avançada de depuração e estabilização da arquitetura de extração de PDFs.

### Componentes Principais
- **Microserviço Python (`pdf-extractor`):** Implementado em FastAPI com PyMuPDF. Responsável pela extração bruta de texto e divisão em chunks. Deploy realizado no Coolify.
- **n8n Workflow MASTER (`MhhPOCMHhekhCKHF`):** Orquestrador principal. Recebe o PDF, chama o serviço Python e gerencia o loop de processamento de chunks.
- **n8n Workflow WORKER (`EEJXd3ftWC9TW8QZ`):** Executado para cada chunk. Utiliza LLM (Google Gemini) para extração estruturada e salva no Supabase.

### Marcos Alcançados
- ✅ Criação e deploy do microserviço Python no Coolify.
- ✅ Refatoração dos workflows n8n para eliminação de gargalos de memória.
- ✅ Correção de bugs críticos de loop (nó `Despacha_Lotes` e placeholder de chunks vazios).
- ✅ Validação estrutural completa dos workflows (0 erros no MCP n8n).

### Próximos Passos
- [ ] Executar teste fim-a-fim com PDF real de grande porte.
- [ ] Monitorar inserções no Supabase e geração do Excel final.

## Estrutura do Repositório
- `pdf-extractor/`: Código fonte do microserviço Python (FastAPI).
- `n8n-skills/`: Módulos de conhecimento e suporte para n8n.
- `.agent/`: Configurações, agentes, skills e workflows do sistema Antigravity.
