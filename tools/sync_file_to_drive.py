"""
Sync a customer-uploaded file from Supabase Storage to the booking's Google Drive folder.

Downloads the file from the 'booking-files' Supabase Storage bucket and uploads it
to the Documents/ subfolder of the booking's Drive folder.

Input payload:
    job_number  str  — e.g. "J26001"
    file_path   str  — path in Supabase Storage, e.g. "J26001/1234567890_contract.pdf"
    file_name   str  — display name to use in Drive, e.g. "1234567890_contract.pdf"

Returns: { synced_to_drive: bool, drive_file_id: str } or { synced_skipped: str } if folder not ready.
"""

import mimetypes
from supabase import create_client
from googleapiclient.http import MediaInMemoryUpload
from tools.auth import get_google_service
from config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_SUBJECT = "info@gprsurveys.ca"
STORAGE_BUCKET = "booking-files"
DOCUMENTS_SUBFOLDER = "Documents"


def _get_drive_folder_id(job_number: str) -> str | None:
    """Look up the booking's google_drive_folder_id by job_number."""
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


def _get_documents_subfolder_id(service, parent_folder_id: str) -> str | None:
    """Find the Documents/ subfolder ID under the given Drive folder."""
    query = (
        f"'{parent_folder_id}' in parents "
        f"and name='{DOCUMENTS_SUBFOLDER}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    result = (
        service.files()
        .list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = result.get("files", [])
    return files[0]["id"] if files else None


def run(payload: dict) -> dict:
    job_number = payload.get("job_number")
    file_path = payload.get("file_path")
    file_name = payload.get("file_name")

    if not job_number or not file_path or not file_name:
        raise ValueError("sync_file_to_drive: job_number, file_path, and file_name are required")

    # 1. Get Drive folder ID for this booking
    drive_folder_id = _get_drive_folder_id(job_number)
    if not drive_folder_id:
        # Booking's new_booking workflow hasn't run yet — Drive folder doesn't exist
        return {"synced_skipped": f"No Drive folder found for {job_number} — new_booking may not have run yet"}

    # 2. Find the Documents/ subfolder
    service = get_google_service("drive", "v3", subject=DRIVE_SUBJECT, scopes=SCOPES)
    documents_folder_id = _get_documents_subfolder_id(service, drive_folder_id)
    if not documents_folder_id:
        return {"synced_skipped": f"Documents subfolder not found in Drive folder for {job_number}"}

    # 3. Download file bytes from Supabase Storage
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    file_bytes = client.storage.from_(STORAGE_BUCKET).download(file_path)

    # 4. Detect MIME type from filename; fall back to octet-stream
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = "application/octet-stream"

    # 5. Upload to Documents/ subfolder
    media = MediaInMemoryUpload(file_bytes, mimetype=mime_type, resumable=False)
    file_metadata = {
        "name": file_name,
        "parents": [documents_folder_id],
    }
    uploaded = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )

    return {
        "synced_to_drive": True,
        "drive_file_id": uploaded["id"],
    }


if __name__ == "__main__":
    import sys, json
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
