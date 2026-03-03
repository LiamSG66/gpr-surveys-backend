"""
Fetch a full booking record from Supabase by booking_id.
Joins technicians to return tech_email and google_calendar_id alongside calendar_owner_email.
Returns: dict with booking (+ nested customers, booking_files, technicians data).
"""

from supabase import create_client
from config import settings


def run(payload: dict) -> dict:
    booking_id = payload.get("booking_id") or payload.get("record", {}).get("id")
    if not booking_id:
        raise ValueError("fetch_booking: booking_id is required in payload")

    client = create_client(settings.supabase_url, settings.supabase_service_key)

    result = (
        client.table("bookings")
        .select("*, customers(*), booking_files(*), technicians(email, google_calendar_id)")
        .eq("id", booking_id)
        .single()
        .execute()
    )

    if not result.data:
        raise RuntimeError(f"fetch_booking: booking {booking_id} not found")

    return {"booking": result.data}


if __name__ == "__main__":
    import sys, json
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2, default=str))
