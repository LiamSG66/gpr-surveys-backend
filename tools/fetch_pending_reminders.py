"""
Fetch all bookings scheduled 48 hours from now that haven't been reminded yet.
Returns: { bookings: [...] }
"""

import json
from datetime import datetime, timedelta
from supabase import create_client
from config import settings


def run(payload: dict = {}) -> dict:
    client = create_client(settings.supabase_url, settings.supabase_service_key)

    target_date = (datetime.utcnow() + timedelta(hours=48)).date().isoformat()

    result = (
        client.table("bookings")
        .select("*, customers(*)")
        .eq("date", target_date)
        .eq("status", "confirmed")
        .eq("is_blocked", False)
        .execute()
    )

    return {"bookings": result.data or []}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
