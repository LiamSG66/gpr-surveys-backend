"""
Delete a Google Calendar event when a booking is cancelled.

Uses `calendar_owner_email` from the booking to target the correct calendar
(event may be on info@gprsurveys.ca or on an assigned technician's calendar).
"""

import json
from tools.auth import get_google_service

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def run(payload: dict) -> dict:
    booking = payload.get("booking")
    event_id = booking.get("google_calendar_event_id") if booking else None

    if not event_id:
        return {"calendar_delete_skipped": True}

    calendar_owner = booking.get("calendar_owner_email", "info@gprsurveys.ca")
    service = get_google_service("calendar", "v3", subject=calendar_owner, scopes=SCOPES)

    service.events().delete(calendarId=calendar_owner, eventId=event_id).execute()

    return {"calendar_event_deleted": True, "calendar_owner_email": calendar_owner}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
