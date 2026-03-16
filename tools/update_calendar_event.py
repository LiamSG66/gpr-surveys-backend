"""
Update or move a Google Calendar event when a booking is modified.

Three scenarios:
  1. Same owner (no change): patch event in place on calendar_owner_email.
  2. Tech reassignment (tech_email != calendar_owner_email): delete from current calendar,
     create fresh event on tech's calendar, return new event ID + updated owner.
  3. Un-assign (tech_email is None, event is on a tech's calendar): delete from tech's calendar,
     create fresh event on info@gprsurveys.ca, return new event ID + reset owner.

Returns one of:
  { calendar_update_skipped: True }
  { calendar_event_updated: True, calendar_owner_email: str }
  { calendar_event_id: str, calendar_owner_email: str }   ← on reassignment or un-assign
"""

import json
from config import settings
from tools.auth import get_google_service

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _build_event_body(booking: dict) -> dict:
    job_number = booking.get("job_number", "")
    service_name = booking.get("service", "Survey")
    city = booking.get("site_city", "")
    date = booking.get("date", "")
    time = booking.get("booking_time", "08:00:00")

    # Use end_date for multi-day jobs
    end_date = booking.get("end_date") or date
    start_dt = f"{date}T{time}"
    end_time_h = int(time.split(":")[0]) + 4
    end_dt = f"{end_date}T{str(end_time_h).zfill(2)}:{time.split(':')[1]}:00"

    customer = booking.get("customers") or {}
    description = "\n".join([
        f"Job: {job_number}",
        f"Service: {service_name}",
        f"Site: {booking.get('site_address_line1', '')} {city}",
        f"Site Contact: {booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')}",
        f"Site Phone: {booking.get('site_contact_phone', '')}",
        f"Customer: {customer.get('first_name', '')} {customer.get('last_name', '')}",
        f"Notes: {booking.get('notes', '')}",
    ])

    return {
        "summary": f"GPR - {job_number} - {service_name} - {city}",
        "description": description,
        "start": {"dateTime": start_dt, "timeZone": "America/Edmonton"},
        "end": {"dateTime": end_dt, "timeZone": "America/Edmonton"},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60}]},
    }


def run(payload: dict) -> dict:
    booking = payload.get("booking")
    if not booking:
        raise ValueError("update_calendar_event: booking required")

    event_id = booking.get("google_calendar_event_id")
    if not event_id:
        return {"calendar_update_skipped": True}

    calendar_owner = booking.get("calendar_owner_email", "info@gprsurveys.ca")

    # Determine the target calendar: use assigned tech's email if set, else current owner
    technician = booking.get("technicians") or {}
    tech_email = technician.get("email")

    default_calendar = settings.gmail_internal_recipient

    if tech_email and tech_email != calendar_owner:
        # --- Reassignment: delete from old calendar, create on tech's calendar ---
        old_service = get_google_service("calendar", "v3", subject=calendar_owner, scopes=SCOPES)
        old_service.events().delete(calendarId=calendar_owner, eventId=event_id).execute()

        new_service = get_google_service("calendar", "v3", subject=tech_email, scopes=SCOPES)
        result = new_service.events().insert(calendarId=tech_email, body=_build_event_body(booking)).execute()

        return {
            "calendar_event_id": result["id"],
            "calendar_owner_email": tech_email,
        }

    elif not tech_email and calendar_owner != default_calendar:
        # --- Un-assign: tech removed, event still on their calendar — move back to info@ ---
        old_service = get_google_service("calendar", "v3", subject=calendar_owner, scopes=SCOPES)
        old_service.events().delete(calendarId=calendar_owner, eventId=event_id).execute()

        new_service = get_google_service("calendar", "v3", subject=default_calendar, scopes=SCOPES)
        result = new_service.events().insert(calendarId=default_calendar, body=_build_event_body(booking)).execute()

        return {
            "calendar_event_id": result["id"],
            "calendar_owner_email": default_calendar,
        }

    else:
        # --- Same owner: patch event in place ---
        service = get_google_service("calendar", "v3", subject=calendar_owner, scopes=SCOPES)
        patch = _build_event_body(booking)
        service.events().patch(calendarId=calendar_owner, eventId=event_id, body=patch).execute()

        return {
            "calendar_event_updated": True,
            "calendar_owner_email": calendar_owner,
        }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
