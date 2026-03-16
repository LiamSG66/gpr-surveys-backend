"""
Create a Google Calendar event for a booking.

Returns: { calendar_event_id: str, calendar_owner_email: str }

The `calendar_subject` payload field controls which calendar receives the event.
Defaults to 'info@gprsurveys.ca' (used for all new bookings before a tech is assigned).
"""

import json
from tools.auth import get_google_service
from config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def run(payload: dict) -> dict:
    booking = payload.get("booking")
    if not booking:
        raise ValueError("create_calendar_event: booking is required in payload")

    calendar_subject = payload.get("calendar_subject", "info@gprsurveys.ca")
    service = get_google_service("calendar", "v3", subject=calendar_subject, scopes=SCOPES)

    job_number = booking.get("job_number", "")
    service_name = booking.get("service", "Survey")
    city = booking.get("site_city", "")
    date = booking.get("date", "")
    time = booking.get("booking_time", "08:00:00")
    is_blocked = booking.get("is_blocked", False)

    customer = booking.get("customers") or {}
    notes = booking.get("notes", "")
    description = "\n".join([
        f"Job: {job_number}",
        f"Service: {service_name}",
        f"Site: {booking.get('site_address_line1', '')} {city}",
        f"Site Contact: {booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')}",
        f"Site Phone: {booking.get('site_contact_phone', '')}",
        f"Customer: {customer.get('first_name', '')} {customer.get('last_name', '')}",
        f"Notes: {notes}",
    ])

    if is_blocked:
        # All-day event for blocked dates — avoids timezone rollback issues
        # Google Calendar all-day events use date-only strings; end is exclusive
        from datetime import date as date_type, timedelta
        end_date_obj = date_type.fromisoformat(date) + timedelta(days=1)
        event = {
            "summary": f"GPR - BLOCKED - {notes or 'Date blocked by admin'}",
            "description": f"Blocked: {notes or 'Date blocked by admin'}",
            "start": {"date": date},
            "end": {"date": end_date_obj.isoformat()},
            "reminders": {"useDefault": False, "overrides": []},
        }
    else:
        # Build ISO datetime strings — use additional_dates for multi-day jobs
        additional_dates = booking.get("additional_dates") or []
        time_parts = time.split(":")
        end_time_h = int(time_parts[0]) + 4
        end_time_str = f"{str(end_time_h).zfill(2)}:{time_parts[1]}:00"

        if len(additional_dates) > 1:
            # Create one event per date, collect all IDs
            event_ids = []
            for day in sorted(additional_dates):
                event = {
                    "summary": f"GPR - {job_number} - {service_name} - {city}",
                    "description": description,
                    "start": {"dateTime": f"{day}T{time}", "timeZone": "America/Vancouver"},
                    "end": {"dateTime": f"{day}T{end_time_str}", "timeZone": "America/Vancouver"},
                    "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60}]},
                }
                result = service.events().insert(calendarId=calendar_subject, body=event).execute()
                event_ids.append(result["id"])
            return {
                "calendar_event_id": ",".join(event_ids),
                "calendar_owner_email": calendar_subject,
            }
        else:
            # Single-day booking
            day = date
            event = {
                "summary": f"GPR - {job_number} - {service_name} - {city}",
                "description": description,
                "start": {"dateTime": f"{day}T{time}", "timeZone": "America/Vancouver"},
                "end": {"dateTime": f"{day}T{end_time_str}", "timeZone": "America/Vancouver"},
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60}]},
            }
            result = service.events().insert(calendarId=calendar_subject, body=event).execute()
            return {
                "calendar_event_id": result["id"],
                "calendar_owner_email": calendar_subject,
            }

    # Insert on the impersonated user's primary calendar (calendarId = their email)
    result = service.events().insert(calendarId=calendar_subject, body=event).execute()

    return {
        "calendar_event_id": result["id"],
        "calendar_owner_email": calendar_subject,
    }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "booking": {
            "job_number": "TEST-001",
            "service": "Concrete Scanning",
            "site_city": "Edmonton",
            "date": "2026-04-01",
            "booking_time": "09:00:00",
            "site_address_line1": "123 Test St",
            "site_contact_first_name": "Test",
            "site_contact_last_name": "User",
            "site_contact_phone": "780-555-0100",
            "notes": "Standalone test — delete this event",
            "customers": {"first_name": "Test", "last_name": "Customer"},
        }
    }
    print(json.dumps(run(payload), indent=2))
