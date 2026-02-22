# Processo Atual de Extração de Dados (N8N + Python Local)

Este documento documenta como o sistema de extração de PDFs acadêmicos (Títulos, Autores e E-mails) funciona na versão atual (Fevereiro de 2026), antes da conversão para um aplicativo Standalone (.exe).

## O Problema que este Processo Resolve
Arquivos PDF de Anais de Congressos costumam ter centenas ou milhares de páginas. Tentar processar tudo de uma vez no N8N causava erros de falta de memória (OOM - Out of Memory) e limite de tokens nas APIs de IA. Além disso, a IA se "perdia" no meio de tanto texto, misturando e-mails ou esquecendo autores.

## A Arquitetura Híbrida (Python + N8N)
Para contornar o limite de hardware e de Tokens, a solução atual divide as responsabilidades:

### 1. O Computador Local (Motor de Fatiamento)
- **O que é:** Um script Python (`fatiador_inteligente.py`) rodando na máquina do usuário.
- **Ferramenta Chave:** `PyMuPDF` (fitz).
- **Como funciona:** 
  1. Ele lê o PDF original (ex: 5.000 páginas) sem carregar tudo na memória gráfica.
  2. Ele "fatia" silenciosamente o PDF em pequenos pedaços de **40 páginas** cada (aproximadamente 850kb, tamanho seguro para passar limpo pelo Nginx/N8N).
  3. Ele faz o Upload (POST HTTP) dessas 40 páginas, **uma por uma**, para um Webhook no seu N8N.
  4. Após enviar, ele tira uma pausa e fica aguardando o N8N devolver um JSON com a "planilha" preenchida daquela respectiva fatia.
  5. No final do processo de todas as fatias, o próprio script junta os resultados de todas as respostas que recebeu do N8N e cospe o arquivo `*_Resultados_Completos.xlsx` na mesma pasta do PDF no seu computador local.

### 2. O Servidor na Nuvem (O Cérebro N8N)
- **O que é:** O seu workflow "Final copy-Atualizada" hospedado na nuvem.
- **Como funciona:**
  1. **Webhook:** Recebe aquele mini-PDF de 40 páginas enviado pelo script Python.
  2. **Extração N8N:** O nó `n8n-nodes-base.extractFromFile` converte as páginas do PDF para Texto limpo.
  3. **AI Agent (Gemini):** O N8N manda esse texto para a nuvem da Inteligência Artificial (Gemini Pro/Flash ou OpenAI). No Prompt, damos instruções muito rígidas.
    - *A Regra de Ouro do Prompt:* Extraia no formato de Tabela Markdown. Cada linha deve ter: Título | Autor | E-mail.
    - *Se houver vários autores no mesmo projeto:* Deve repetir o 'Título' em linhas novas para que nenhum autor/e-mail fique fora de tabela.
  4. **Code Node (Javascript):** A IA vai responder algo como: 
     ```markdown
     | Título | Autor | E-mail |
     | A COVID... | João | joao@.com |
     ```
     O Nó "Code" recebe esse Markdown e usa JavaScript (`.split('\n')`) para explodir as réguas do markdown, limpar os espaços e converter tudo para um Array JSON de dados puros validos: `[{"Títulos...": "...", "Nomes...": "...", "E-mails...": "..."}]`.
  5. **Resposta do Webhook (Respond to Webhook):** O N8N pega esse JSON gerado e responde a requisição HTTP aberta pelo fatiador em Python. Devido à nossa configuração `responseData: 'allEntries'`, o N8N devolve todos os JSONs empacotados em lista.

## Resumo dos Custos da Versão Atual
- **Quem faz força computacional (CPU/RAM)?** O seu computador, ao cortar o PDF, e o seu servidor VPS (ao rodar o NodeJS do N8N).
- **Quem paga pela Inteligência?** Você. A conta da API (Google ou OpenAI) informada lá nas *Credentials* do N8N é a sua. Cada fatia de 40 páginas enviada gera um débito na sua conta em uso de Tokens.

---
*Documento gerado como registro ("As Is") antes de evoluirmos o sistema para um executável autônomo (Standalone).*
