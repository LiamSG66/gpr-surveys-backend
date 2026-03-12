"""
Upload a generated quote PDF to Google Drive.
Input:  { contact: dict, pdf_bytes: str (base64), quote_number: str (optional) }
Output: { drive_file_id: str, drive_url: str, drive_folder_id: str, drive_folder_url: str }

Creates a per-quote subfolder inside GOOGLE_DRIVE_QUOTES_FOLDER_ID with the naming
convention: {quote_number}_{YYYY-MM-DD}_{company_or_name}_{site_address_line1} {site_city}_PO_{po}
Then drops the PDF directly in that folder.
"""

import base64
import io
import json
from googleapiclient.http import MediaIoBaseUpload
from tools.auth import get_google_service
from config import settings

SCOPES        = ["https://www.googleapis.com/auth/drive"]
DRIVE_SUBJECT = "info@gprsurveys.ca"

QUOTES_FOLDER_ID = "1zOwNLwjfjQX438vNE7SZNzU4lLcrwExr"


def _build_folder_name(contact: dict, quote_number: str) -> str:
    # Quote creation date (YYYY-MM-DD) from created_at ISO timestamp
    created_at = (contact.get("created_at") or "").strip()
    quote_date = created_at[:10] if created_at else ""

    # Company or first+last name
    company = (contact.get("company") or "").strip()
    if company:
        name_part = company
    else:
        first = (contact.get("first_name") or "").strip()
        last  = (contact.get("last_name") or "").strip()
        name_part = f"{first} {last}".strip()

    # Site address
    address_line1 = (contact.get("site_address_line1") or "").strip()
    city          = (contact.get("site_city") or "").strip()
    address_part  = f"{address_line1} {city}".strip() if city else address_line1

    # PO (quotes don't have a PO at this stage — kept for naming consistency)
    po = (contact.get("purchase_order") or "").strip()

    return f"{quote_number}_{quote_date}_{name_part}_{address_part}_PO_{po}"


def _build_pdf_filename(contact: dict, quote_number: str) -> str:
    company = (contact.get("company") or "").strip()
    if company:
        name_part = company.replace(" ", "_")
    else:
        first = (contact.get("first_name") or "").strip()
        last  = (contact.get("last_name") or "").strip()
        name_part = f"{first}_{last}".strip("_")
    return f"{quote_number}_{name_part}.pdf"


def _create_folder(service, name: str, parent_id: str) -> str:
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(
        body=metadata, fields="id", supportsAllDrives=True
    ).execute()
    return folder["id"]


def run(payload: dict) -> dict:
    contact       = payload.get("contact", {})
    pdf_bytes_b64 = payload.get("pdf_bytes", "")
    quote_number  = payload.get("quote_number") or contact.get("quote_number", "Q00001")

    if not pdf_bytes_b64:
        raise ValueError("upload_quote_to_drive: pdf_bytes is required")

    pdf_bytes   = base64.b64decode(pdf_bytes_b64)
    folder_name = _build_folder_name(contact, quote_number)
    filename    = _build_pdf_filename(contact, quote_number)

    service = get_google_service("drive", "v3", subject=DRIVE_SUBJECT, scopes=SCOPES)

    # Create per-quote subfolder inside the year folder
    quote_folder_id = _create_folder(service, folder_name, QUOTES_FOLDER_ID)

    # Upload PDF directly into the quote folder
    media = MediaIoBaseUpload(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        resumable=False,
    )
    uploaded = service.files().create(
        body={"name": filename, "parents": [quote_folder_id]},
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()

    drive_file_id = uploaded["id"]
    return {
        "drive_file_id":    drive_file_id,
        "drive_url":        f"https://drive.google.com/file/d/{drive_file_id}/view",
        "drive_folder_id":  quote_folder_id,
        "drive_folder_url": f"https://drive.google.com/drive/folders/{quote_folder_id}",
    }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
