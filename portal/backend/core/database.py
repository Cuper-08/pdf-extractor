"""
Operações Supabase via REST API (sem SDK — usa httpx diretamente).
Tabelas esperadas (criadas pelo Antigravity database-architect):
  - extraction_jobs
  - user_usage
  - subscriptions
"""
import os
from datetime import datetime
from typing import Optional
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_KEY = _SERVICE_KEY or _ANON_KEY

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Limites por plano (páginas/mês)
PLAN_LIMITS: dict[str | None, int] = {
    "free": 300,
    "starter": 3000,
    "pro": 15000,
    "empresa": 80000,
    None: 300,
}


def _current_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


async def _rest(method: str, path: str, **kwargs) -> list | dict:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=HEADERS, timeout=20, **kwargs)
    resp.raise_for_status()
    if resp.content:
        return resp.json()
    return {}


# ─────────────────────────────────────────────
# extraction_jobs
# ─────────────────────────────────────────────

async def create_job(
    user_id: str,
    filename: str,
    schema_prompt: str,
    columns: list[str],
    page_count: int,
) -> dict:
    data = {
        "user_id": user_id,
        "status": "pending",
        "schema_prompt": schema_prompt,
        "column_names": columns,
        "original_filename": filename,
        "pages_processed": page_count,
    }
    result = await _rest("POST", "extraction_jobs", json=data)
    return result[0] if isinstance(result, list) else result


async def update_job_status(
    job_id: str,
    status: str,
    result_data: Optional[str] = None,
    pages_processed: Optional[int] = None,
    error_message: Optional[str] = None,
    records_extracted: Optional[int] = None,
    preview_rows: Optional[list] = None,
) -> None:
    patch: dict = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if result_data is not None:
        patch["result_data"] = result_data
    if pages_processed is not None:
        patch["pages_processed"] = pages_processed
    if error_message is not None:
        patch["error_message"] = error_message
    if records_extracted is not None:
        patch["records_extracted"] = records_extracted
    if preview_rows is not None:
        patch["preview_rows"] = preview_rows
    if status in ("done", "completed"):
        patch["progress_pct"] = 100
    elif status == "processing":
        patch["progress_pct"] = 0

    try:
        await _rest("PATCH", f"extraction_jobs?id=eq.{job_id}", json=patch)
    except Exception:
        # Fallback: try without new columns in case migration hasn't run yet
        fallback = {k: v for k, v in patch.items()
                    if k not in ("records_extracted", "preview_rows", "progress_pct")}
        await _rest("PATCH", f"extraction_jobs?id=eq.{job_id}", json=fallback)


async def update_job_progress(job_id: str, progress_pct: int) -> None:
    """Atualiza somente o progresso percentual durante processamento."""
    try:
        await _rest(
            "PATCH",
            f"extraction_jobs?id=eq.{job_id}",
            json={"progress_pct": progress_pct, "updated_at": datetime.utcnow().isoformat()},
        )
    except Exception:
        pass  # progresso é best-effort


async def get_job(job_id: str) -> Optional[dict]:
    result = await _rest("GET", f"extraction_jobs?id=eq.{job_id}&select=*")
    if isinstance(result, list) and result:
        return result[0]
    return None


async def get_recent_schemas(user_id: str, limit: int = 5) -> list[dict]:
    """Retorna os últimos N jobs concluídos do usuário (para reuso de schemas)."""
    try:
        result = await _rest(
            "GET",
            f"extraction_jobs?user_id=eq.{user_id}&status=eq.done"
            f"&select=id,schema_prompt,column_names,original_filename,created_at"
            f"&order=created_at.desc&limit={limit}",
        )
        return result if isinstance(result, list) else []
    except Exception:
        return []


# ─────────────────────────────────────────────
# user_usage
# ─────────────────────────────────────────────

async def get_user_usage(user_id: str) -> dict:
    month = _current_month()
    result = await _rest("GET", f"user_usage?user_id=eq.{user_id}&month=eq.{month}&select=*")

    plan = await _get_user_plan(user_id)
    limit = PLAN_LIMITS.get(plan, 300)

    if isinstance(result, list) and result:
        usage = result[0]
        return {
            "plan": plan,
            "month": month,
            "pages_used": usage.get("pages_processed", 0),
            "pages_limit": limit,
            "pages_remaining": max(0, limit - usage.get("pages_processed", 0)),
            "extractions_used": usage.get("extractions_used", 0),
        }

    return {
        "plan": plan,
        "month": month,
        "pages_used": 0,
        "pages_limit": limit,
        "pages_remaining": limit,
        "extractions_used": 0,
    }


async def check_usage_limit(user_id: str, pages_requested: int) -> tuple[bool, str]:
    usage = await get_user_usage(user_id)
    if usage["pages_remaining"] < pages_requested:
        return False, (
            f"Limite de páginas atingido. "
            f"Disponível: {usage['pages_remaining']} páginas. "
            f"Solicitado: {pages_requested} páginas. "
            f"Plano atual: {usage['plan']}."
        )
    return True, ""


async def increment_usage(user_id: str, pages: int) -> None:
    month = _current_month()

    # Try to get existing row
    result = await _rest("GET", f"user_usage?user_id=eq.{user_id}&month=eq.{month}&select=*")

    if isinstance(result, list) and result:
        row = result[0]
        new_pages = row.get("pages_processed", 0) + pages
        new_extractions = row.get("extractions_used", 0) + 1
        await _rest(
            "PATCH",
            f"user_usage?user_id=eq.{user_id}&month=eq.{month}",
            json={
                "pages_processed": new_pages,
                "extractions_used": new_extractions,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
    else:
        await _rest(
            "POST",
            "user_usage",
            json={
                "user_id": user_id,
                "month": month,
                "pages_processed": pages,
                "extractions_used": 1,
            },
        )


async def _get_user_plan(user_id: str) -> Optional[str]:
    try:
        result = await _rest(
            "GET",
            f"subscriptions?user_id=eq.{user_id}&status=eq.active&select=plan&limit=1",
        )
        if isinstance(result, list) and result:
            return result[0].get("plan")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# subscriptions (Stripe)
# ─────────────────────────────────────────────

async def upsert_subscription(
    user_id: str,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    plan: str,
    status: str,
    current_period_end: Optional[str] = None,
) -> None:
    """Cria ou atualiza a assinatura do usuário no Supabase."""
    data: dict = {
        "user_id": user_id,
        "stripe_subscription_id": stripe_subscription_id,
        "stripe_customer_id": stripe_customer_id,
        "plan": plan,
        "status": status,
    }
    if current_period_end:
        data["current_period_end"] = current_period_end

    # Tenta update por stripe_subscription_id; se não existir, insere
    existing = await _rest(
        "GET",
        f"subscriptions?stripe_subscription_id=eq.{stripe_subscription_id}&select=id",
    )
    if isinstance(existing, list) and existing:
        await _rest(
            "PATCH",
            f"subscriptions?stripe_subscription_id=eq.{stripe_subscription_id}",
            json=data,
        )
    else:
        await _rest("POST", "subscriptions", json=data)


async def get_stripe_customer_id(user_id: str) -> Optional[str]:
    try:
        result = await _rest(
            "GET",
            f"subscriptions?user_id=eq.{user_id}&select=stripe_customer_id&limit=1",
        )
        if isinstance(result, list) and result:
            return result[0].get("stripe_customer_id")
    except Exception:
        pass
    return None


async def get_user_email(user_id: str) -> Optional[str]:
    """Busca email do usuário via Supabase Admin API (service role key)."""
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not service_key:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
                timeout=10,
            )
        if resp.status_code == 200:
            return resp.json().get("email")
    except Exception:
        pass
    return None
