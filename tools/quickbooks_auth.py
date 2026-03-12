"""
QuickBooks Online OAuth 2.0 — one-time authorization helper.

Run this script once to get your refresh token and realm ID.
It starts a local HTTP server on port 8080, opens your browser to the QBO OAuth URL,
captures the auth code from the callback, and saves QB_REFRESH_TOKEN + QB_REALM_ID to .env.

Usage:
    cd gpr-surveys-backend
    export $(grep -v '^#' .env | xargs)
    python3 tools/quickbooks_auth.py
"""

import os
import sys
import webbrowser
from urllib.parse import urlparse, parse_qs

from intuitlib.client import AuthClient
from intuitlib.enums import Scopes


# ─── Config ───────────────────────────────────────────────────────────────────

CLIENT_ID     = os.environ.get("QB_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("QB_CLIENT_SECRET", "")
REDIRECT_URI  = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
ENV_FILE      = os.path.join(os.path.dirname(__file__), "..", ".env")

# Toggle to True for sandbox, False for production
USE_SANDBOX = False
ENVIRONMENT = "sandbox" if USE_SANDBOX else "production"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: QB_CLIENT_ID and QB_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    auth_client = AuthClient(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        environment=ENVIRONMENT,
    )

    auth_url = auth_client.get_authorization_url([Scopes.ACCOUNTING])
    print(f"\nOpening browser to authorize QuickBooks Online ({ENVIRONMENT})...")
    print(f"URL: {auth_url}\n")
    webbrowser.open(auth_url)

    print("After authorizing in the browser, you will be redirected to the Intuit OAuth Playground.")
    print("Copy the FULL URL from your browser's address bar and paste it here.\n")
    redirect_url = input("Paste the full redirect URL: ").strip()

    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    _auth_code = params.get("code", [None])[0]
    _realm_id  = params.get("realmId", [None])[0]

    if not _auth_code or not _realm_id:
        print("ERROR: Could not parse code or realmId from URL.")
        sys.exit(1)

    print(f"\nReceived auth code. Exchanging for tokens...")
    auth_client.get_bearer_token(_auth_code, realm_id=_realm_id)

    refresh_token = auth_client.refresh_token
    realm_id      = _realm_id

    print(f"\nSuccess!")
    print(f"  QB_REFRESH_TOKEN = {refresh_token}")
    print(f"  QB_REALM_ID      = {realm_id}")

    # Update .env file
    _update_env(refresh_token, realm_id)
    print(f"\nSaved to {os.path.abspath(ENV_FILE)}")
    print("Add these to Modal secrets + Vercel env vars when deploying.")


def _update_env(refresh_token: str, realm_id: str):
    """Append or update QB_REFRESH_TOKEN and QB_REALM_ID in .env file."""
    env_path = os.path.abspath(ENV_FILE)
    lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    # Remove existing QB_REFRESH_TOKEN / QB_REALM_ID lines
    lines = [l for l in lines if not l.startswith("QB_REFRESH_TOKEN=") and not l.startswith("QB_REALM_ID=")]

    # Append new values
    lines.append(f"QB_REFRESH_TOKEN={refresh_token}\n")
    lines.append(f"QB_REALM_ID={realm_id}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    main()
