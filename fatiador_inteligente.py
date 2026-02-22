import sys
import os
import requests
import fitz  # PyMuPDF
import time
import pandas as pd # Para processar os dados finais

def split_and_upload(pdf_path, webhook_url, chunk_size=50):
    if not os.path.exists(pdf_path):
        print(f"Erro: Arquivo '{pdf_path}' não encontrado.")
        return

    print(f"Abrindo o arquivo: {pdf_path}")
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"Total de páginas no PDF: {total_pages}")

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_dir = "chunks_temporarios"
    os.makedirs(output_dir, exist_ok=True)

    chunks_enviados = 0
    todos_projetos = [] # Lista para acumular os resultados do n8n

    for start_page in range(0, total_pages, chunk_size):
        end_page = min(start_page + chunk_size, total_pages) - 1
        chunk_doc = fitz.open()  # Novo PDF vazio
        
        # Insere as páginas correspondentes ao chunk
        chunk_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
        
        chunk_filename = os.path.join(output_dir, f"{base_name}_paginas_{start_page+1}_a_{end_page+1}.pdf")
        chunk_doc.save(chunk_filename)
        chunk_doc.close()
        
        print(f"\n[{start_page+1} a {end_page+1}] Mini-PDF gerado: {chunk_filename}")
        
        # Faz o envio (Upload) para o Webhook do N8N
        print(f"  -> Processando páginas no N8N (Gemini)... Aguarde (isso leva uns 10~15s)")
        try:
            with open(chunk_filename, 'rb') as f:
                # O nó 'Extract from File' no N8N está esperando o binary property name "input"
                files = {'input': (os.path.basename(chunk_filename), f, 'application/pdf')}
                response = requests.post(webhook_url, files=files)
                
                if response.status_code in (200, 201):
                    # O n8n foi configurado para devolver a resposta do Nó Code (os objetos da planilha)
                    try:
                        dados_retornados = response.json()
                        todos_projetos.extend(dados_retornados)
                        print(f"  -> Sucesso! +{len(dados_retornados)} projetos extraídos desta fatia.")
                    except ValueError:
                         print(f"  -> Erro: O N8N não retornou JSON. Resposta: {response.text}")
                         
                    chunks_enviados += 1
                else:
                    print(f"  -> Erro na Extração: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            print(f"  -> Falha na conexão com o Webhook: {str(e)}")
            
        # Pequena pausa tática
        time.sleep(2)

    doc.close()
    
    # === FASE FINAL: CONSOLIDAÇÃO NO EXCEL ===
    print(f"\n--- Processamento Finalizado ---")
    print(f"Total de fatias processadas: {chunks_enviados}")
    print(f"Total absoluto de Trabalhos extraídos: {len(todos_projetos)}")
    
    if len(todos_projetos) > 0:
        print("Gerando Planilha Consolidada...")
        df = pd.DataFrame(todos_projetos)
        # Salva a planilha na mesma pasta de onde o fatiador rola
        excel_filename = f"{base_name}_Resultados_Completos.xlsx"
        df.to_excel(excel_filename, index=False)
        print(f"✅ EXCEL SALVO COM SUCESSO: {excel_filename}")
        print("Pode abrir a planilha no seu computador!")
    else:
        print("⚠️ Nenhum dado foi encontrado pelas IAs ou houve erro no processamento.")

if __name__ == "__main__":
    # Caminho corrigido com 'r' (Raw String) para evitar erros com colchetes/barras no Windows
    PDF_FILE = r"pdf-extractor/tests/XII_CEC_Trabalho-39.pdf" 
    
    # O Nginx padrão bloqueia arquivos acima de 1MB. A fatia de 50 páginas desse PDF deu 1.08MB, causando ConnectionResetError.
    # Reduzimos para 40 páginas (aprox. 850kb) para fluir perfeitamente!
    N8N_WEBHOOK_URL = "https://n8n.hsbmarketing.com.br/webhook/fatiador-api"
    split_and_upload(PDF_FILE, N8N_WEBHOOK_URL, chunk_size=40)
