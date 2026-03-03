"""
Write Google Calendar event ID, Drive folder ID, calendar_owner_email, and other
fields back to the booking record in Supabase.
"""

import json
from supabase import create_client
from config import settings


def run(payload: dict) -> dict:
    booking = payload.get("booking")
    if not booking:
        raise ValueError("update_booking_record: booking required")

    booking_id = booking.get("id")
    if not booking_id:
        raise ValueError("update_booking_record: booking.id required")

    updates: dict = {}
    if "calendar_event_id" in payload:
        updates["google_calendar_event_id"] = payload["calendar_event_id"]
    if "calendar_owner_email" in payload:
        updates["calendar_owner_email"] = payload["calendar_owner_email"]
    if "drive_folder_id" in payload:
        updates["google_drive_folder_id"] = payload["drive_folder_id"]
    if "drive_folder_url" in payload:
        updates["google_drive_folder_url"] = payload["drive_folder_url"]
    if "status" in payload:
        updates["status"] = payload["status"]

    if not updates:
        return {"update_booking_record_skipped": True}

    client = create_client(settings.supabase_url, settings.supabase_service_key)
    client.table("bookings").update(updates).eq("id", booking_id).execute()

    return {"booking_record_updated": True, "fields": list(updates.keys())}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
