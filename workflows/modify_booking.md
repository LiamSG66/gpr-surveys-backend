# Modify Booking Workflow

**Trigger:** Booking record updated in Supabase (date or booking_time changed; status remains active — not cancelled)
**Input:** `booking_id`, `old_date`, `old_booking_time`, `skip_customer_email` (bool), `tech_email` (str|null) from webhook payload

## Steps

1. Fetch updated booking record → tools/fetch_booking.py
   - Returns booking with nested `technicians(email, google_calendar_id)` and `calendar_owner_email`
2. Update Google Calendar event → tools/update_calendar_event.py
   - **Same owner (no reassignment):** if `technicians.email == calendar_owner_email` (or no tech assigned), patches the event in place on `calendar_owner_email`'s calendar. Returns `{ calendar_event_updated: true, calendar_owner_email }`.
   - **Tech reassignment:** if `technicians.email != calendar_owner_email`, deletes event from `calendar_owner_email`'s calendar and creates a new event on `technicians.email`'s calendar. Returns `{ calendar_event_id, calendar_owner_email }` (new values — must be written back in Step 3).
3. Write any updated `calendar_event_id` and `calendar_owner_email` back to booking record → tools/update_booking_record.py
   - Only needed if reassignment occurred (new event ID + new owner email); skip if same-owner patch
4. Send customer modification confirmation email → tools/send_email.py (template: customer_modification)
   - `send_email` will auto-skip this step if `skip_customer_email=true` in the payload (admin chose silent move).
5. Send internal notification email → tools/send_email.py (template: internal_modification)
6. Send tech date-change notification → tools/send_email.py (template: tech_date_change)
   - `send_email` will auto-skip if `tech_email` is not set in the payload.
   - Always runs otherwise — tech is always notified when their job date moves.

## Error Handling

- If calendar update fails: log error, continue — customer/tech email still sent
- If email fails: retry once; log if still failing

## Notes

- If `google_calendar_event_id` is missing on the booking, skip calendar update
- `skip_customer_email` is set by the admin drag-drop move feature — allows silent reschedule without customer email
- `tech_email` is resolved by the webhook handler before calling this workflow (fetched from technicians table by assigned_to UUID)
- `calendar_owner_email` tracks which calendar currently holds the event — always use it to target the correct calendar for delete/patch operations
