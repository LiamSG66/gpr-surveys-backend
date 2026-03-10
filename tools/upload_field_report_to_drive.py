"""
Upload a generated field report PDF to the booking's Google Drive Reports/ subfolder.

Input payload:
    {
        "booking":     { "job_number": str, "google_drive_folder_id": str },
        "pdf_bytes":   str  — base64-encoded PDF,
        "report_date": str  — "YYYY-MM-DD"
    }

Returns: { "drive_file_id": str, "drive_file_url": str }
"""

import base64
import io
from supabase import create_client
from googleapiclient.http import MediaIoBaseUpload
from tools.auth import get_google_service
from config import settings

SCOPES         = ["https://www.googleapis.com/auth/drive"]
DRIVE_SUBJECT  = "info@gprsurveys.ca"
REPORTS_SUBFOLDER = "Reports"


def _get_drive_folder_id(job_number: str) -> str | None:
    """Look up google_drive_folder_id from Supabase if not provided in payload."""
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    result = (
        client.table("bookings")
        .select("google_drive_folder_id")
        .eq("job_number", job_number)
        .single()
        .execute()
    )
    if not result.data:
        return None
    return result.data.get("google_drive_folder_id")


def _get_or_create_reports_subfolder(service, parent_folder_id: str) -> str:
    """Find (or create) the Reports/ subfolder under the booking's Drive folder."""
    query = (
        f"'{parent_folder_id}' in parents "
        f"and name='{REPORTS_SUBFOLDER}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    result = (
        service.files()
        .list(q=query, fields="files(id, name)",
              supportsAllDrives=True, includeItemsFromAllDrives=True)
        .execute()
    )
    files = result.get("files", [])
    if files:
        return files[0]["id"]

    # Create Reports/ subfolder
    folder_meta = {
        "name": REPORTS_SUBFOLDER,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id],
    }
    created = (
        service.files()
        .create(body=folder_meta, fields="id", supportsAllDrives=True)
        .execute()
    )
    return created["id"]


def run(payload: dict) -> dict:
    booking     = payload.get("booking", {})
    pdf_bytes   = payload.get("pdf_bytes", "")
    report_date = payload.get("report_date", "")

    job_number = booking.get("job_number")
    if not job_number:
        raise ValueError("upload_field_report_to_drive: booking.job_number is required")

    if not pdf_bytes:
        raise ValueError("upload_field_report_to_drive: pdf_bytes is required")

    # Get Drive folder ID
    drive_folder_id = booking.get("google_drive_folder_id") or _get_drive_folder_id(job_number)
    if not drive_folder_id:
        raise ValueError(f"upload_field_report_to_drive: No Drive folder found for {job_number}")

    service = get_google_service("drive", "v3", subject=DRIVE_SUBJECT, scopes=SCOPES)

    # Find or create Reports/ subfolder
    reports_folder_id = _get_or_create_reports_subfolder(service, drive_folder_id)

    # Build filename
    filename = f"{job_number}_Field_Report_{report_date}.pdf"

    # Upload PDF
    pdf_data = base64.b64decode(pdf_bytes)
    media = MediaIoBaseUpload(io.BytesIO(pdf_data), mimetype="application/pdf", resumable=False)
    file_metadata = {
        "name": filename,
        "parents": [reports_folder_id],
    }
    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=True)
        .execute()
    )

    file_id  = uploaded["id"]
    file_url = f"https://drive.google.com/file/d/{file_id}/view"

    return {
        "drive_file_id":  file_id,
        "drive_file_url": file_url,
    }


if __name__ == "__main__":
    import sys, json
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
