"""
Autenticação via Supabase JWT.
O token vem do frontend (Lovable.dev + Supabase Auth) no header Authorization.
"""
import os
import httpx
from fastapi import Header, HTTPException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


async def verify_token(authorization: str = Header(None)) -> str:
    """
    Valida o Bearer token com Supabase Auth e retorna o user_id.
    Levanta HTTPException 401 se inválido.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticação necessário.")

    token = authorization.removeprefix("Bearer ").strip()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_ANON_KEY,
            },
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")

    user = resp.json()
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    return user_id
