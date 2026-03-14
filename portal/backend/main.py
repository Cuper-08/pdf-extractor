"""
Apex Extractor Portal — Backend FastAPI
Endpoints:
  GET  /health
  POST /generate-schema    → Layer 1: descrição → system_prompt + colunas
  POST /extract-custom     → Layer 2: PDF + schema_prompt → Job ID (async)
  GET  /job/{id}           → Status do job (polling)
  GET  /job/{id}/download  → Download Excel quando done
  GET  /usage              → Uso do usuário no mês atual
"""
import os
import base64
import json
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import fitz  # PyMuPDF

from core.auth import verify_token
from core.database import (
    create_job,
    update_job_status,
    get_job,
    get_user_usage,
    check_usage_limit,
    increment_usage,
)
from core.extraction import generate_schema, process_pdf_extraction, create_excel

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="Apex Extractor Portal API",
    version="1.0.0",
    description="API para extração inteligente de dados de PDFs via IA",
)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.lovable.app",
        "https://*.lovableproject.com",
        FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class GenerateSchemaRequest(BaseModel):
    description: str


class GenerateSchemaResponse(BaseModel):
    system_prompt: str
    columns: list[str]
    description: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    original_filename: str
    pages_processed: int
    columns: Optional[list[str]]
    error_message: Optional[str]
    created_at: str


# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "apex-portal-backend", "version": "1.0.0"}


# ─────────────────────────────────────────────
# POST /generate-schema  (Layer 1)
# ─────────────────────────────────────────────

@app.post("/generate-schema", response_model=GenerateSchemaResponse)
async def generate_schema_endpoint(
    req: GenerateSchemaRequest,
    user_id: str = Depends(verify_token),
):
    """
    Recebe descrição em linguagem natural do usuário.
    Retorna system_prompt gerado pela IA + lista de colunas para preview.
    """
    if not req.description or len(req.description.strip()) < 5:
        raise HTTPException(400, "Descrição muito curta. Explique o que quer extrair.")

    try:
        result = await generate_schema(req.description)
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar esquema: {e}")

    return result


# ─────────────────────────────────────────────
# POST /extract-custom  (Layer 2 — async)
# ─────────────────────────────────────────────

@app.post("/extract-custom", status_code=202)
async def extract_custom(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    schema_prompt: str = Form(...),
    columns: str = Form("[]"),
    user_id: str = Depends(verify_token),
):
    """
    Recebe PDF + schema_prompt (obtido via /generate-schema).
    Processa em background. Retorna job_id para polling via /job/{id}.
    """
    try:
        column_list: list[str] = json.loads(columns)
    except Exception:
        column_list = []

    pdf_bytes = await file.read()
    if len(pdf_bytes) < 100:
        raise HTTPException(400, "Arquivo PDF inválido ou vazio.")

    # Conta páginas antes de criar o job
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        doc.close()
    except Exception as e:
        raise HTTPException(400, f"Não foi possível abrir o PDF: {e}")

    # Verifica limite de uso do plano
    allowed, reason = await check_usage_limit(user_id, page_count)
    if not allowed:
        raise HTTPException(402, reason)

    # Cria job no Supabase
    try:
        job = await create_job(
            user_id=user_id,
            filename=file.filename or "arquivo.pdf",
            schema_prompt=schema_prompt,
            columns=column_list,
            page_count=page_count,
        )
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar job: {e}")

    job_id = job["id"]

    # Dispara extração em background
    background_tasks.add_task(
        _run_extraction,
        job_id=job_id,
        user_id=user_id,
        pdf_bytes=pdf_bytes,
        schema_prompt=schema_prompt,
        column_list=column_list,
        page_count=page_count,
    )

    return {"job_id": job_id, "status": "pending", "pages": page_count}


async def _run_extraction(
    job_id: str,
    user_id: str,
    pdf_bytes: bytes,
    schema_prompt: str,
    column_list: list[str],
    page_count: int,
) -> None:
    """Background task: processa extração e persiste resultado no Supabase."""
    try:
        await update_job_status(job_id, "processing")

        records = await process_pdf_extraction(pdf_bytes, schema_prompt)
        excel_bytes = create_excel(records, column_list)

        result_b64 = base64.b64encode(excel_bytes).decode()
        await update_job_status(
            job_id,
            "done",
            result_data=result_b64,
            pages_processed=page_count,
        )
        await increment_usage(user_id, page_count)

    except Exception as e:
        await update_job_status(job_id, "error", error_message=str(e)[:500])


# ─────────────────────────────────────────────
# GET /job/{id}  (polling de status)
# ─────────────────────────────────────────────

@app.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user_id: str = Depends(verify_token),
):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado.")
    if job.get("user_id") != user_id:
        raise HTTPException(403, "Acesso negado.")

    return {
        "id": job["id"],
        "status": job["status"],
        "original_filename": job.get("original_filename", ""),
        "pages_processed": job.get("pages_processed", 0),
        "columns": job.get("column_names"),
        "error_message": job.get("error_message"),
        "created_at": job.get("created_at", ""),
    }


# ─────────────────────────────────────────────
# GET /job/{id}/download
# ─────────────────────────────────────────────

@app.get("/job/{job_id}/download")
async def download_job_result(
    job_id: str,
    user_id: str = Depends(verify_token),
):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado.")
    if job.get("user_id") != user_id:
        raise HTTPException(403, "Acesso negado.")
    if job.get("status") != "done":
        raise HTTPException(400, f"Job ainda não concluído. Status: {job.get('status')}")

    result_b64 = job.get("result_data")
    if not result_b64:
        raise HTTPException(500, "Resultado não disponível.")

    excel_bytes = base64.b64decode(result_b64)
    base_name = (job.get("original_filename") or "resultado").removesuffix(".pdf")

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{base_name}_extrato.xlsx"'
        },
    )


# ─────────────────────────────────────────────
# GET /usage
# ─────────────────────────────────────────────

@app.get("/usage")
async def get_usage(user_id: str = Depends(verify_token)):
    """Retorna uso do usuário no mês corrente + limite do plano."""
    return await get_user_usage(user_id)
