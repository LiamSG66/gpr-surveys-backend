"""
Upload a generated quote PDF to Supabase Storage (quote-pdfs bucket).
Input:  { pdf_bytes: str (base64), contact: dict, quote_number: str }
Output: { supabase_pdf_path: str }

Uses upsert so regenerated quotes overwrite the previous file at the same path.
"""

import base64
import httpx
from config import settings

BUCKET = "quote-pdfs"


def run(payload: dict) -> dict:
    pdf_bytes_b64 = payload.get("pdf_bytes", "")
    quote_number = payload.get("quote_number") or payload.get("contact", {}).get("quote_number", "Q00001")

    if not pdf_bytes_b64:
        return {"error": "upload_quote_to_supabase: pdf_bytes is required"}

    pdf_bytes = base64.b64decode(pdf_bytes_b64)
    path = f"{quote_number}.pdf"
    url = f"{settings.supabase_url}/storage/v1/object/{BUCKET}/{path}"

    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/pdf",
        "x-upsert": "true",
    }

    with httpx.Client(timeout=30) as client:
        res = client.put(url, content=pdf_bytes, headers=headers)

    if not res.is_success:
        return {"error": f"Supabase upload failed: {res.status_code} {res.text}"}

    return {"supabase_pdf_path": path}
