"""
Create a Google Drive folder structure for a booking.
Folder name format: {job_number}_{YYYY-MM-DD}_{company_or_name}_{address_line1} {city}_PO_{purchase_order}
Creates subfolders: Documents/, Site Photos/, Reports/
Returns: { drive_folder_id: str, drive_folder_url: str }

Impersonates info@gprsurveys.ca so folders are owned by that account.
"""

import json
from tools.auth import get_google_service
from config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]
SUBFOLDERS = ["Documents", "Site Photos", "Reports"]
DRIVE_SUBJECT = "info@gprsurveys.ca"


def _create_folder(service, name: str, parent_id: str) -> str:
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
    return folder["id"]


def _build_folder_name(booking: dict) -> str:
    job_number = booking.get("job_number", "UNKNOWN")

    # Job date (YYYY-MM-DD) — the day the job is scheduled for
    job_date = (booking.get("date") or "").strip()[:10]

    # Company if present, else customer first + last name
    customer = booking.get("customers") or {}
    company = (customer.get("company") or "").strip()
    if company:
        name_part = company
    else:
        first = (customer.get("first_name") or "").strip()
        last = (customer.get("last_name") or "").strip()
        name_part = f"{first} {last}".strip()

    # Site address line 1 + city
    address_line1 = (booking.get("site_address_line1") or "").strip()
    city = (booking.get("site_city") or "").strip()
    address_part = f"{address_line1} {city}".strip() if city else address_line1

    # PO number — always include label, value may be blank
    po = (booking.get("purchase_order") or "").strip()
    po_part = f"PO_{po}"

    return f"{job_number}_{job_date}_{name_part}_{address_part}_{po_part}"


def run(payload: dict) -> dict:
    booking = payload.get("booking")
    if not booking:
        raise ValueError("create_drive_folder: booking required")

    folder_name = _build_folder_name(booking)
    service = get_google_service("drive", "v3", subject=DRIVE_SUBJECT, scopes=SCOPES)

    # Create main job folder under root
    job_folder_id = _create_folder(service, folder_name, settings.google_drive_root_folder_id)

    # Create subfolders
    for subfolder in SUBFOLDERS:
        _create_folder(service, subfolder, job_folder_id)

    return {
        "drive_folder_id": job_folder_id,
        "drive_folder_url": f"https://drive.google.com/drive/folders/{job_folder_id}",
    }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "booking": {"job_number": "TEST-001"}
    }
    print(json.dumps(run(payload), indent=2))
