"""
Motor de extração do portal — 2 camadas de IA.

Layer 1 — generate_schema():
  Recebe descrição em linguagem natural → Gemini gera system_prompt customizado
  + lista de colunas (JSON). Roda UMA VEZ por job.

Layer 2 — process_pdf_extraction():
  PDF → PyMuPDF → chunks (smart_split) → Gemini processa em paralelo
  → parse tabela Markdown → dedup → retorna list[dict]

Funções utilitárias (portadas de extrator_standalone.py):
  smart_split, parse_generic_table, consolidar_generico, create_excel
"""
import os
import re
import json
import asyncio
import unicodedata
from io import BytesIO
from typing import Optional

import fitz  # PyMuPDF
import httpx
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CHUNK_SIZE = 40_000        # chars por chunk (~10 páginas densas)
MAX_CONCURRENT = 3         # máximo de chunks em paralelo (evita rate limit)

# ─────────────────────────────────────────────
# GEMINI — model discovery (async, cached)
# ─────────────────────────────────────────────

_model_cache: dict[str, str] = {}
_model_lock = asyncio.Lock()

PREFERRED_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash-001",
    "models/gemini-flash-latest",
    "models/gemini-1.5-flash",
]


async def _get_gemini_model(api_key: str) -> str:
    if api_key in _model_cache:
        return _model_cache[api_key]

    async with _model_lock:
        if api_key in _model_cache:
            return _model_cache[api_key]

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                timeout=15,
            )
        if resp.status_code != 200:
            raise Exception(f"Chave Gemini inválida (HTTP {resp.status_code})")

        available = [m["name"] for m in resp.json().get("models", [])]
        model = None
        for pref in PREFERRED_MODELS:
            if pref in available:
                model = pref
                break
        if not model:
            flash = [m for m in available if "flash" in m.lower()]
            model = flash[0] if flash else available[0]

        _model_cache[api_key] = model
        return model


async def _call_gemini(system_prompt: str, user_text: str, api_key: str) -> str:
    model = await _get_gemini_model(api_key)
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": 0.1},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=120)

    if resp.status_code == 429:
        await asyncio.sleep(30)
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=120)

    if resp.status_code != 200:
        raise Exception(f"Gemini error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise Exception(f"Resposta inesperada do Gemini: {json.dumps(data)[:300]}")


# ─────────────────────────────────────────────
# LAYER 1 — generate_schema
# ─────────────────────────────────────────────

META_SYSTEM = """Você é um especialista em extração de dados estruturados de documentos PDF.
Sua resposta deve ser SOMENTE um JSON válido (sem markdown, sem código, sem explicação).
"""

META_USER_TEMPLATE = """O usuário quer extrair as seguintes informações de seus documentos PDF:

{user_request}

Crie um system prompt preciso para que uma IA extraia esses dados.

Retorne EXATAMENTE este JSON (sem markdown, sem texto adicional):
{{
  "system_prompt": "...",
  "columns": ["coluna1", "coluna2", ...]
}}

O system_prompt deve:
1. Definir exatamente quais campos extrair — serão as colunas da tabela Markdown
2. Exigir que a saída seja EXCLUSIVAMENTE uma tabela Markdown com essas colunas
3. Instruir a deixar células VAZIAS quando o dado não existir (NUNCA inventar)
4. Definir UMA LINHA por registro/item encontrado
5. Instruir a repetir campos-chave em cada linha (ex: número do processo com múltiplas partes)
6. Instruir a ignorar cabeçalhos, rodapés e numeração de página
7. Ser escrito em português

O campo "columns" deve listar as colunas exatas que aparecerão na tabela."""


async def generate_schema(user_description: str) -> dict:
    """
    Layer 1: gera system_prompt + colunas a partir da descrição do usuário.
    Retorna: {system_prompt: str, columns: list[str], description: str}
    """
    api_key = GEMINI_API_KEY
    if not api_key:
        raise Exception("GEMINI_API_KEY não configurada no servidor.")

    user_text = META_USER_TEMPLATE.format(user_request=user_description.strip())
    raw = await _call_gemini(META_SYSTEM, user_text, api_key)

    # Parse JSON — com fallback por regex se a IA adicionar markdown
    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise Exception(f"Resposta da IA não é JSON válido: {raw[:300]}")
        parsed = json.loads(match.group())

    system_prompt = parsed.get("system_prompt", "")
    columns = parsed.get("columns", [])

    if not system_prompt or not columns:
        raise Exception("Resposta incompleta do gerador de esquema. Tente reformular a descrição.")

    return {
        "system_prompt": system_prompt,
        "columns": columns,
        "description": user_description,
    }


# ─────────────────────────────────────────────
# LAYER 2 — process_pdf_extraction
# ─────────────────────────────────────────────

def smart_split(full_text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """
    Divide texto em chunks nas fronteiras naturais (parágrafo → frase → espaço).
    Portado de pdf-extractor/main.py:30-52.
    """
    chunks = []
    total = len(full_text)
    start = 0

    while start < total:
        end = min(start + chunk_size, total)

        if end < total:
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


async def _extract_chunk(chunk: str, schema_prompt: str, sem: asyncio.Semaphore) -> str:
    async with sem:
        return await _call_gemini(
            schema_prompt,
            f"Extraia os dados deste texto:\n\n{chunk}",
            GEMINI_API_KEY,
        )


async def process_pdf_extraction(pdf_bytes: bytes, schema_prompt: str) -> list[dict]:
    """
    Layer 2: extrai texto do PDF → divide em chunks → processa com Gemini
    em paralelo → faz parse → dedup → retorna list[dict].
    """
    # 1. Extrai texto do PDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    if not full_text.strip():
        raise Exception("PDF sem texto extraível. O arquivo pode ser baseado em imagens (scan).")

    # 2. Divide em chunks
    chunks = smart_split(full_text)

    # 3. Processa em paralelo com semáforo de rate limit
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [_extract_chunk(chunk, schema_prompt, sem) for chunk in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 4. Coleta registros (ignora chunks com erro)
    all_records: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            continue  # chunk falhou — best effort
        records = parse_generic_table(r)
        all_records.extend(records)

    # 5. Dedup e retorna
    return consolidar_generico(all_records)


# ─────────────────────────────────────────────
# PARSER — tabela Markdown genérica
# ─────────────────────────────────────────────

def parse_generic_table(markdown_text: str) -> list[dict]:
    """
    Converte tabela Markdown de qualquer estrutura em list[dict].
    Detecta cabeçalho automaticamente.
    Portado e generalizado de extrator_standalone.py:240-278.
    """
    lines = [l for l in markdown_text.split("\n") if l.strip() and "|" in l]
    # Remove linhas separadoras (|---|---|)
    lines = [l for l in lines if not re.match(r"^\s*\|[\s|:-]+\|\s*$", l)]

    if not lines:
        return []

    def split_row(line: str) -> list[str]:
        parts = line.split("|")
        # Remove primeira e última parte vazias (|col1|col2| → ['', 'col1', 'col2', ''])
        if parts and not parts[0].strip():
            parts = parts[1:]
        if parts and not parts[-1].strip():
            parts = parts[:-1]
        return [p.strip() for p in parts]

    header_candidates = split_row(lines[0])

    # Detecta se primeira linha é cabeçalho
    HEADER_KEYWORDS = {
        "título", "titulo", "trabalho", "autor", "email", "e-mail", "nome",
        "cnpj", "valor", "data", "número", "numero", "tipo", "parte",
        "endereço", "endereco", "telefone", "cpf", "processo", "contrato",
    }
    is_header = any(
        any(kw in col.lower() for kw in HEADER_KEYWORDS)
        for col in header_candidates
    )

    if is_header:
        headers = header_candidates
        data_lines = lines[1:]
    else:
        headers = [f"Coluna {i+1}" for i in range(len(header_candidates))]
        data_lines = lines

    records = []
    for line in data_lines:
        cols = split_row(line)
        if len(cols) >= len(headers):
            record = {headers[i]: cols[i] for i in range(len(headers))}
            records.append(record)
        elif cols:
            # Linha incompleta — preenche com vazio
            record = {headers[i]: (cols[i] if i < len(cols) else "") for i in range(len(headers))}
            records.append(record)

    return records


def consolidar_generico(records: list[dict]) -> list[dict]:
    """
    Dedup por igualdade exata de todos os campos (NFC normalizado).
    Apenas linhas 100% idênticas são removidas — registros distintos com
    os mesmos valores em algumas colunas (ex: mesmo autor em obras diferentes)
    são preservados normalmente.
    """
    if not records:
        return []

    keys = list(records[0].keys())
    seen: set[str] = set()
    result: list[dict] = []

    for rec in records:
        chave = "|||".join(
            unicodedata.normalize("NFC", str(rec.get(k) or "").strip().lower())
            for k in keys
        )
        if chave not in seen:
            seen.add(chave)
            result.append(rec)

    return result


# ─────────────────────────────────────────────
# EXCEL — geração via BytesIO
# ─────────────────────────────────────────────

def create_excel(records: list[dict], columns: Optional[list[str]] = None) -> bytes:
    """
    Gera Excel formatado a partir de list[dict].
    Retorna bytes (para armazenar no Supabase ou streaming download).
    """
    if records:
        df = pd.DataFrame(records)
        if columns:
            # Reordena pelas colunas esperadas; adiciona as extras no final
            ordered = [c for c in columns if c in df.columns]
            extras = [c for c in df.columns if c not in columns]
            df = df[ordered + extras]
        df = df.fillna("")
    else:
        df = pd.DataFrame(columns=columns or [])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados Extraídos")
        ws = writer.sheets["Dados Extraídos"]

        # Auto-largura das colunas
        for col_cells in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col_cells), default=10)
            col_letter = col_cells[0].column_letter
            ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

        # Estilo do cabeçalho (azul escuro)
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

    output.seek(0)
    return output.read()
