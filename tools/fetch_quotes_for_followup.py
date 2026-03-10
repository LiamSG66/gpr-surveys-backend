"""
fetch_quotes_for_followup.py

Queries Supabase for contact_submissions that are ready for a 30-day quote
follow-up email.

Criteria:
  - quote_status = 'quoted'
  - converted_booking_id IS NULL
  - quote_sent_at between 29 and 31 days ago  (±1 day window)
  - quote_followup_sent_at IS NULL

Returns a list of contact records with email, name, quote number, and site city
so the caller can send the quote_followup email template.

Usage (standalone):
    python tools/fetch_quotes_for_followup.py

Usage (from main.py):
    from tools.fetch_quotes_for_followup import fetch_quotes_for_followup
    contacts = fetch_quotes_for_followup(supabase_client)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any


def fetch_quotes_for_followup(supabase_client: Any) -> list[dict]:
    """Return contact records eligible for a 30-day follow-up email.

    Args:
        supabase_client: An initialised supabase-py client.

    Returns:
        List of dicts, each containing at minimum:
          id, email, first_name, last_name, quote_number,
          site_city, quote_sent_at, quote_status
    """
    now       = datetime.now(timezone.utc)
    cutoff_31 = (now - timedelta(days=31)).isoformat()
    cutoff_29 = (now - timedelta(days=29)).isoformat()

    result = (
        supabase_client.table("contact_submissions")
        .select(
            "id, email, first_name, last_name, quote_number, "
            "site_city, quote_sent_at, quote_status, converted_booking_id, "
            "quote_followup_sent_at"
        )
        .eq("quote_status", "quoted")
        .gt("quote_sent_at", cutoff_31)
        .lt("quote_sent_at", cutoff_29)
        .is_("converted_booking_id", "null")
        .is_("quote_followup_sent_at", "null")
        .execute()
    )

    return result.data or []


# ── Standalone smoke-test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    client   = create_client(url, key)
    contacts = fetch_quotes_for_followup(client)

    print(f"Found {len(contacts)} quote(s) eligible for follow-up:")
    for c in contacts:
        print(
            f"  {c.get('quote_number')} | {c.get('first_name')} {c.get('last_name')} "
            f"| sent {c.get('quote_sent_at')} | city: {c.get('site_city')}"
        )
