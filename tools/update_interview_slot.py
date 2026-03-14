"""
Update an interview_slots record in Supabase with Google Calendar event details.

Saves calendar_event_id and the Google Meet link as location_or_link.

payload keys: interview_slot_id, calendar_event_id, meet_link
"""

import logging
from supabase import create_client
from config import settings

logger = logging.getLogger(__name__)


def run(payload: dict) -> dict:
    interview_slot_id = payload.get("interview_slot_id")
    calendar_event_id = payload.get("calendar_event_id")
    meet_link         = payload.get("meet_link", "")

    if not interview_slot_id:
        return {"error": "update_interview_slot: interview_slot_id is required"}

    if not calendar_event_id:
        return {"error": "update_interview_slot: calendar_event_id is required"}

    try:
        sb = create_client(settings.supabase_url, settings.supabase_service_key)

        updates: dict = {"calendar_event_id": calendar_event_id}
        if meet_link:
            updates["location_or_link"] = meet_link

        sb.table("interview_slots") \
            .update(updates) \
            .eq("id", interview_slot_id) \
            .execute()

        return {
            "interview_slot_updated": True,
            "interview_slot_id":      interview_slot_id,
            "meet_link":              meet_link,
        }

    except Exception as e:
        logger.error(f"[update_interview_slot] {e}")
        return {"error": str(e)}
