"""
Create a Google Calendar interview event with a Google Meet link.

Adds the candidate as an attendee so they receive a calendar invite with the Meet link.

Returns: { calendar_event_id: str, calendar_event_link: str, meet_link: str }

payload keys: application_id, candidate_first_name, candidate_last_name, candidate_email,
              job_title, scheduled_at, duration_minutes, notes
"""

import logging
import uuid
from datetime import datetime, timedelta
from tools.auth import get_google_service
from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def run(payload: dict) -> dict:
    candidate_first  = payload.get("candidate_first_name", "") or payload.get("first_name", "")
    candidate_last   = payload.get("candidate_last_name", "") or payload.get("last_name", "")
    candidate_email  = payload.get("candidate_email", "") or payload.get("email", "")
    job_title        = payload.get("job_title", "Position")
    scheduled_at     = payload.get("scheduled_at", "")
    duration_minutes = int(payload.get("duration_minutes") or 60)
    notes            = payload.get("notes", "")
    application_id   = payload.get("application_id", "")

    if not scheduled_at:
        return {"error": "create_interview_calendar_event: scheduled_at is required"}

    try:
        scheduled_at_clean = scheduled_at.replace("Z", "+00:00")
        start_dt = datetime.fromisoformat(scheduled_at_clean)
        end_dt   = start_dt + timedelta(minutes=duration_minutes)
        start_iso = start_dt.isoformat()
        end_iso   = end_dt.isoformat()
    except Exception as e:
        return {"error": f"create_interview_calendar_event: invalid scheduled_at — {e}"}

    try:
        calendar_id = settings.google_calendar_id
        service = get_google_service("calendar", "v3", subject=calendar_id, scopes=SCOPES)

        candidate_name = f"{candidate_first} {candidate_last}".strip() or "Candidate"
        summary = f"Interview: {candidate_name} - {job_title}"

        candidate_phone = payload.get("phone", "")
        description_lines = [
            f"Candidate: {candidate_name}",
            f"Position: {job_title}",
        ]
        if candidate_email:
            description_lines.append(f"Email: {candidate_email}")
        if candidate_phone:
            description_lines.append(f"Phone: {candidate_phone}")
        if notes:
            description_lines.append(f"\nNotes: {notes}")
        if application_id:
            description_lines.append(f"\nApplication ID: {application_id}")

        event_body: dict = {
            "summary":     summary,
            "description": "\n".join(description_lines),
            "start":       {"dateTime": start_iso, "timeZone": "America/Vancouver"},
            "end":         {"dateTime": end_iso,   "timeZone": "America/Vancouver"},
            "reminders":   {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        if candidate_email:
            event_body["attendees"] = [{"email": candidate_email}]

        result = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1,
            sendUpdates="all",
        ).execute()

        # Extract the Meet video link from conferenceData
        meet_link = ""
        entry_points = result.get("conferenceData", {}).get("entryPoints", [])
        for ep in entry_points:
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri", "")
                break

        return {
            "calendar_event_id":   result["id"],
            "calendar_event_link": result.get("htmlLink", ""),
            "meet_link":           meet_link,
        }

    except Exception as e:
        logger.error(f"[create_interview_calendar_event] {e}")
        return {"error": str(e)}
