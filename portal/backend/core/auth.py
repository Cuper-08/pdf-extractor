"""
Autenticação via Supabase JWT.
O token vem do frontend (Lovable.dev + Supabase Auth) no header Authorization.

Otimizações:
  - Connection pooling: httpx.AsyncClient compartilhado (evita TCP handshake por request)
  - TTL cache: tokens validados são cacheados por 60s (evita round-trip ao Supabase)
"""
import logging
import os

import httpx
from cachetools import TTLCache
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# ── Connection pool compartilhado ────────────────
_auth_client: httpx.AsyncClient | None = None


def _get_auth_client() -> httpx.AsyncClient:
    global _auth_client
    if _auth_client is None or _auth_client.is_closed:
        _auth_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            timeout=httpx.Timeout(10.0),
        )
    return _auth_client


# ── TTL cache: token → user_id (60s) ────────────
_token_cache: TTLCache[str, str] = TTLCache(maxsize=512, ttl=60)


async def verify_token(authorization: str = Header(None)) -> str:
    """
    Valida o Bearer token com Supabase Auth e retorna o user_id.
    Levanta HTTPException 401 se inválido.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticação necessário.")

    token = authorization.removeprefix("Bearer ").strip()

    # Cache hit → retorna user_id sem round-trip
    cached = _token_cache.get(token)
    if cached:
        return cached

    try:
        resp = await _get_auth_client().get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_ANON_KEY,
            },
        )
    except Exception as e:
        logger.error("Supabase auth indisponível: %s", e)
        raise HTTPException(status_code=503, detail=f"Serviço de autenticação indisponível: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")

    user = resp.json()
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    # Cacheia para evitar round-trips repetidos
    _token_cache[token] = user_id
    return user_id
