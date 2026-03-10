# Assign Booking Workflow

**Trigger:** Booking's `assigned_to` field changed (tech assignment, reassignment, or unassignment) and NO other significant fields (date, time, service) changed simultaneously.
**Input:** `booking_id` from webhook payload

## Steps

1. Fetch updated booking record → tools/fetch_booking.py
   - Returns booking with nested `technicians(email, google_calendar_id)` and `calendar_owner_email`
2. Update Google Calendar event → tools/update_calendar_event.py
   - **Tech assigned/reassigned:** moves event from current `calendar_owner_email` calendar to tech's calendar
   - **Tech unassigned:** moves event back to `info@gprsurveys.ca` calendar
3. Write updated `calendar_event_id` and `calendar_owner_email` back to booking record → tools/update_booking_record.py
   - Only needed if reassignment occurred (new event ID + new owner email); skip if same-owner patch

## Notes

- Does NOT send customer notification — assignment changes are internal only
- The tech's assignment/unassignment email is handled by the Next.js API route calling `send_tech_notification_endpoint` directly
- Handles both assignment and unassignment (un-assign moves event back to `info@gprsurveys.ca`)
