"""
Attach a PDF to a QuickBooks Online invoice using the Attachable API.

Input payload:
    {
        "invoice_id": str,
        "pdf_bytes":  str,   # base64-encoded
        "filename":   str    # e.g. "GPR-2601_Field_Report_2026-03-05.pdf"
    }

Returns: { "attachable_id": str }
"""

import os
import base64
import subprocess

from intuitlib.client import AuthClient
from quickbooks import QuickBooks
from quickbooks.objects.attachable import Attachable, AttachableRef


def _persist_new_refresh_token(new_token: str) -> None:
    """Write the rotated QB refresh token back to Modal secrets so it survives across invocations."""
    try:
        subprocess.run(
            ["modal", "secret", "update", "gpr-surveys-secrets", f"QB_REFRESH_TOKEN={new_token}"],
            check=True,
            capture_output=True,
        )
        print("[qb_auth] Rotated refresh token saved to Modal secrets.")
    except Exception as exc:
        print(f"[qb_auth] WARNING: could not persist rotated refresh token: {exc}")


def _get_qb_client() -> QuickBooks:
    client_id     = os.environ["QB_CLIENT_ID"]
    client_secret = os.environ["QB_CLIENT_SECRET"]
    refresh_token = os.environ["QB_REFRESH_TOKEN"]
    realm_id      = os.environ["QB_REALM_ID"]
    environment   = os.environ.get("QB_ENVIRONMENT", "sandbox")

    auth_client = AuthClient(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8080/callback",
        environment=environment,
    )
    auth_client.refresh(refresh_token=refresh_token)

    # Persist the new rotated token so the next invocation doesn't get invalid_grant.
    if auth_client.refresh_token and auth_client.refresh_token != refresh_token:
        _persist_new_refresh_token(auth_client.refresh_token)

    return QuickBooks(
        auth_client=auth_client,
        company_id=realm_id,
        minorversion=65,
    )


def run(payload: dict) -> dict:
    invoice_id = payload.get("invoice_id")
    pdf_bytes  = payload.get("pdf_bytes", "")
    filename   = payload.get("filename", "field_report.pdf")

    if not invoice_id:
        raise ValueError("attach_to_quickbooks_invoice: invoice_id is required")
    if not pdf_bytes:
        raise ValueError("attach_to_quickbooks_invoice: pdf_bytes is required")

    qb = _get_qb_client()

    decoded = base64.b64decode(pdf_bytes)

    attachable = Attachable()
    attachable.FileName    = filename
    attachable.ContentType = "application/pdf"
    attachable._FileBytes  = decoded  # python-quickbooks uses this for binary upload

    ref = AttachableRef()
    ref.EntityRef = {"type": "Invoice", "value": invoice_id}
    attachable.AttachableRef = [ref]

    attachable.save(qb=qb)

    return {"attachable_id": attachable.Id}


if __name__ == "__main__":
    import sys, json
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
