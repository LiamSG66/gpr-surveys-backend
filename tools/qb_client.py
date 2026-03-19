"""
Shared QuickBooks OAuth 2.0 client.

Reads the refresh token from Supabase app_config (falls back to QB_REFRESH_TOKEN env var).
After each refresh, updates os.environ immediately (fixes same-invocation token reuse)
and writes the new token to Supabase (fixes cross-invocation persistence).

This replaces the broken `modal secret update` subprocess approach.
"""

import os
import logging

from intuitlib.client import AuthClient
from quickbooks import QuickBooks
from supabase import create_client
from config import settings

logger = logging.getLogger(__name__)

_CONFIG_KEY = "QB_REFRESH_TOKEN"
_REDIRECT_URI = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"


def _read_token_from_supabase() -> str | None:
    try:
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        result = (
            client.table("app_config")
            .select("value")
            .eq("key", _CONFIG_KEY)
            .single()
            .execute()
        )
        if result.data:
            return result.data["value"]
    except Exception as e:
        logger.warning(f"[qb_client] Could not read token from Supabase: {e}")
    return None


def _write_token_to_supabase(token: str) -> None:
    try:
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        client.table("app_config").upsert({"key": _CONFIG_KEY, "value": token}).execute()
        logger.info("[qb_client] Rotated refresh token persisted to Supabase.")
    except Exception as e:
        logger.warning(f"[qb_client] Could not persist rotated refresh token: {e}")


def get_qb_client() -> QuickBooks:
    """
    Build an authenticated QuickBooks client, refreshing the OAuth token.

    Token resolution order:
      1. Supabase app_config (most up-to-date across invocations)
      2. QB_REFRESH_TOKEN env var (Modal secret — fallback for first run)

    After refreshing, the new token is written to both os.environ and Supabase
    so the next tool in the same invocation and the next Modal invocation both
    have the correct token.
    """
    client_id     = os.environ["QB_CLIENT_ID"]
    client_secret = os.environ["QB_CLIENT_SECRET"]
    realm_id      = os.environ["QB_REALM_ID"]
    environment   = os.environ.get("QB_ENVIRONMENT", "production")

    # Prefer Supabase — it holds the latest rotated token.
    # Fall back to env var on first run before Supabase is seeded.
    refresh_token = _read_token_from_supabase() or os.environ["QB_REFRESH_TOKEN"]

    auth_client = AuthClient(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=_REDIRECT_URI,
        environment=environment,
    )
    auth_client.refresh(refresh_token=refresh_token)

    new_token = auth_client.refresh_token
    if new_token and new_token != refresh_token:
        # Update env var immediately so subsequent tools in the same invocation
        # pick up the new token without hitting Supabase again.
        os.environ["QB_REFRESH_TOKEN"] = new_token
        # Persist to Supabase for future invocations.
        _write_token_to_supabase(new_token)

    return QuickBooks(
        auth_client=auth_client,
        company_id=realm_id,
        minorversion=65,
    )
