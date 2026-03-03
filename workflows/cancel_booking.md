# Cancel Booking Workflow

**Trigger:** Booking status changes to 'cancelled' in Supabase
**Input:** `booking_id` from webhook payload

## Steps

1. Fetch cancelled booking record → tools/fetch_booking.py
2. Delete Google Calendar event → tools/delete_calendar_event.py
   - Uses `calendar_owner_email` from the fetched booking to target the correct calendar
   - Event may be on `info@gprsurveys.ca` (unassigned) or on a technician's calendar (assigned)
   - Always read `calendar_owner_email` from the booking — never assume `info@gprsurveys.ca`
3. Send customer cancellation confirmation email → tools/send_email.py (template: customer_cancellation)
4. Send internal cancellation notification → tools/send_email.py (template: internal_cancellation)
   - Sends to admin (`gmail_internal_recipient`) always
   - Also sends to assigned technician's email if one is assigned (handled inside send_email.py)

## Error Handling

- If calendar deletion fails: log error, continue — event can be deleted manually
- If email fails: retry once; log if still failing

## Notes

- Drive folder is retained (do not delete) — may contain files already uploaded
- If `google_calendar_event_id` is missing, skip calendar step silently
