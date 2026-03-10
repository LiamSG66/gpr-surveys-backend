"""
Download a quote PDF from Google Drive by file ID.
Input:  { drive_file_id: str }
Output: { pdf_bytes: str (base64), pdf_filename: str }
"""

import base64
import json
import io
from googleapiclient.http import MediaIoBaseDownload
from tools.auth import get_google_service

SCOPES        = ["https://www.googleapis.com/auth/drive"]
DRIVE_SUBJECT = "info@gprsurveys.ca"


def run(payload: dict) -> dict:
    drive_file_id = payload.get("drive_file_id")
    pdf_filename  = payload.get("pdf_filename", "quote.pdf")

    if not drive_file_id:
        raise ValueError("fetch_quote_pdf_from_drive: drive_file_id is required")

    service = get_google_service("drive", "v3", subject=DRIVE_SUBJECT, scopes=SCOPES)

    # Fetch file name from Drive metadata
    try:
        meta = service.files().get(
            fileId=drive_file_id,
            fields="name",
            supportsAllDrives=True,
        ).execute()
        pdf_filename = meta.get("name", pdf_filename)
    except Exception:
        pass

    # Download file bytes
    request  = service.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
    buf      = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    pdf_bytes = buf.getvalue()
    return {
        "pdf_bytes":    base64.b64encode(pdf_bytes).decode("utf-8"),
        "pdf_filename": pdf_filename,
    }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    result = run(payload)
    print(f"pdf_filename: {result['pdf_filename']}")
    print(f"pdf_bytes length: {len(result['pdf_bytes'])}")
