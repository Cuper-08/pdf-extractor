import os
import math
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz  # PyMuPDF

app = FastAPI(title="PDF Extractor Async", version="2.0.0")

# Supabase config via environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zcoixlvbkssvuxamzwvs.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

CHUNK_SIZE = 10000  # Target characters per chunk

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def smart_split(full_text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text at natural boundaries (paragraphs, sentences) near chunk_size."""
    chunks = []
    total_chars = len(full_text)
    start = 0

    while start < total_chars:
        end = min(start + chunk_size, total_chars)

        if end < total_chars:
            # Try paragraph break first
            bp = full_text.rfind("\n\n", start, end)
            if bp == -1 or bp < start + chunk_size // 2:
                bp = full_text.rfind(".\n", start, end)
            if bp == -1 or bp < start + chunk_size // 2:
                bp = full_text.rfind(". ", start, end)
            if bp != -1 and bp > start + chunk_size // 2:
                end = bp + 1

        chunks.append(full_text[start:end])
        start = end

    return chunks


async def supabase_insert(table: str, data: dict) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=data, headers=SUPABASE_HEADERS, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) else result


@app.get("/health")
def health():
    return {"status": "ok", "service": "pdf-extractor", "version": "2.0.0 async"}


@app.post("/extract", status_code=202)
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    if not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_KEY not configured")

    try:
        pdf_bytes = await file.read()

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to open PDF: {e}")

        total_pages = len(doc)
        full_text = "".join(doc[i].get_text() for i in range(total_pages))
        # Close document right after extraction — before any processing
        doc.close()

        total_chars = len(full_text)
        if total_chars == 0:
            raise HTTPException(
                status_code=422,
                detail="PDF has no extractable text (may be scanned/image-based)",
            )

        # Calculate BEFORE doc is needed again (doc is already closed — use saved total_pages)
        raw_chunks = smart_split(full_text)
        total_chunks = len(raw_chunks)
        chars_per_page = total_chars / max(total_pages, 1)

        # 1. Register document in Supabase
        doc_record = await supabase_insert(
            "pdf_documents",
            {
                "filename": file.filename,
                "total_pages": total_pages,
                "total_chunks": total_chunks,
                "status": "processing",
            },
        )
        document_id = doc_record["id"]

        # 2. Insert all chunks into the queue table
        for idx, chunk_text in enumerate(raw_chunks):
            start_char = sum(len(c) for c in raw_chunks[:idx])
            end_char = start_char + len(chunk_text)
            page_start = math.floor(start_char / chars_per_page) + 1
            page_end = min(math.floor(end_char / chars_per_page) + 1, total_pages)

            await supabase_insert(
                "pdf_chunks",
                {
                    "document_id": document_id,
                    "chunk_index": idx + 1,
                    "chunk_text": chunk_text,
                    "estimated_pages": f"{page_start} a {page_end}",
                    "processing_status": "pending",
                    "retry_count": 0,
                },
            )

        return {
            "accepted": True,
            "message": "PDF received and split into chunks. Processing queue created.",
            "document_id": document_id,
            "filename": file.filename,
            "total_pages": total_pages,
            "total_chunks": total_chunks,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "traceback": traceback.format_exc()},
        )
