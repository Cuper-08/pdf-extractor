from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz  # PyMuPDF
import math

app = FastAPI(title="PDF Extractor", version="1.0.0")

CHUNK_SIZE = 10000  # caracteres por bloco (menor = mais chunks, mais precisão)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/extract")
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Apenas arquivos PDF são aceitos")
    
    pdf_bytes = await file.read()
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(500, f"Erro ao abrir PDF: {str(e)}")
    
    # Extrai todo o texto página por página
    full_text = ""
    for page_num in range(len(doc)):
        page = doc[page_num]
        full_text += page.get_text()
    
    doc.close()
    
    # Divide em chunks
    chunks = []
    total_chars = len(full_text)
    total_chunks = math.ceil(total_chars / CHUNK_SIZE)
    
    for i in range(total_chunks):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, total_chars)
        chunk_text = full_text[start:end]
        
        # Estima páginas (aproximação)
        chars_per_page = total_chars / max(len(doc), 1) if total_chars > 0 else 1
        page_start = math.floor(start / chars_per_page) + 1
        page_end = math.floor(end / chars_per_page) + 1
        
        chunks.append({
            "texto_bruto": chunk_text,
            "bloco_atual": i + 1,
            "total_blocos": total_chunks,
            "paginas_estimadas": f"{page_start} a {page_end}"
        })
    
    return {
        "success": True,
        "total_paginas": len(doc),
        "total_chunks": total_chunks,
        "total_caracteres": total_chars,
        "chunks": chunks
    }
