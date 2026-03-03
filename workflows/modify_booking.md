# Modify Booking Workflow

**Trigger:** Booking record updated in Supabase (status remains active — not cancelled)
**Input:** `booking_id` from webhook payload

## Steps

1. Fetch updated booking record → tools/fetch_booking.py
   - Returns booking with nested `technicians(email, google_calendar_id)` and `calendar_owner_email`
2. Update Google Calendar event → tools/update_calendar_event.py
   - **Same owner (no reassignment):** if `technicians.email == calendar_owner_email` (or no tech assigned), patches the event in place on `calendar_owner_email`'s calendar. Returns `{ calendar_event_updated: true, calendar_owner_email }`.
   - **Tech reassignment:** if `technicians.email != calendar_owner_email`, deletes event from `calendar_owner_email`'s calendar and creates a new event on `technicians.email`'s calendar. Returns `{ calendar_event_id, calendar_owner_email }` (new values — must be written back in Step 3).
3. Write any updated `calendar_event_id` and `calendar_owner_email` back to booking record → tools/update_booking_record.py
   - Only needed if reassignment occurred (new event ID + new owner email); skip if same-owner patch
4. Send customer modification confirmation email → tools/send_email.py (template: customer_modification)
5. Send internal notification email → tools/send_email.py (template: internal_modification)

## Error Handling

- If calendar update fails: log error, continue — customer has already been notified
- If email fails: retry once; log if still failing

## Notes

- If `google_calendar_event_id` is missing on the booking, skip calendar update
- Workflow fires on any UPDATE to the bookings table where status is not 'cancelled'
- `calendar_owner_email` tracks which calendar currently holds the event — always use it to target the correct calendar for delete/patch operations
