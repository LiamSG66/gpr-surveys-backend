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

    # Build ISO datetime strings
    start_dt = f"{date}T{time}"
    end_time_h = int(time.split(":")[0]) + 4
    end_dt = f"{date}T{str(end_time_h).zfill(2)}:{time.split(':')[1]}:00"

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

    event = {
        "summary": f"GPR - {job_number} - {service_name} - {city}",
        "description": description,
        "start": {"dateTime": start_dt, "timeZone": "America/Edmonton"},
        "end": {"dateTime": end_dt, "timeZone": "America/Edmonton"},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60}]},
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
