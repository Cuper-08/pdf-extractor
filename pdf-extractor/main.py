from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz  # PyMuPDF
import math

app = FastAPI(title="PDF Extractor", version="1.0.0")

CHUNK_SIZE = 10000  # characters per chunk

@app.get("/health")
def health():
    return {"status": "ok", "service": "pdf-extractor"}

@app.post("/extract")
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open PDF: {str(e)}")

    # Extract full text page by page
    full_text = ""
    total_pages = len(doc)
    for page_num in range(total_pages):
        page = doc[page_num]
        full_text += page.get_text()

    doc.close()

    total_chars = len(full_text)
    if total_chars == 0:
        raise HTTPException(status_code=422, detail="PDF has no extractable text (may be scanned/image-based)")

    total_chunks = math.ceil(total_chars / CHUNK_SIZE)
    chars_per_page = total_chars / max(total_pages, 1)

    chunks = []
    start = 0
    chunk_index = 1
    
    while start < total_chars:
        # Pegamos o corte inicial de 10 mil caracteres
        end = min(start + CHUNK_SIZE, total_chars)
        
        # Se não chegamos ao fim do arquivo, buscamos uma quebra "suave" (parágrafo ou frase)
        if end < total_chars:
            # Procura a quebra de parágrafo dupla mais próxima do final deste bloco
            break_pos = full_text.rfind('\n\n', start, end)
            
            # Se não achou parágrafo na metade final do bloco, tenta ponto final com quebra de linha
            if break_pos == -1 or break_pos < start + (CHUNK_SIZE // 2):
                break_pos = full_text.rfind('.\n', start, end)
                
            # Se ainda não achou, tenta ponto final comum
            if break_pos == -1 or break_pos < start + (CHUNK_SIZE // 2):
                break_pos = full_text.rfind('. ', start, end)
                
            # Se encontrou alguma quebra válida e ela não encurta barbaramente o bloco (ex: retém > 50%), faz o corte nela
            if break_pos != -1 and break_pos > start + (CHUNK_SIZE // 2):
                end = break_pos + 1  # Inclui a pontuação/quebra

        chunk_text = full_text[start:end]

        page_start = math.floor(start / chars_per_page) + 1
        page_end = min(math.floor(end / chars_per_page) + 1, total_pages)

        chunks.append({
            "texto_bruto": chunk_text,
            "bloco_atual": chunk_index,
            "paginas_estimadas": f"{page_start} a {page_end}"
        })
        
        start = end
        chunk_index += 1

    # Atualiza o total de blocos gerados para todos os chunks
    total_blocos_reais = len(chunks)
    for c in chunks:
        c["total_blocos"] = total_blocos_reais

    return {
        "success": True,
        "total_paginas": total_pages,
        "total_chunks": total_chunks,
        "total_caracteres": total_chars,
        "chunks": chunks
    }
