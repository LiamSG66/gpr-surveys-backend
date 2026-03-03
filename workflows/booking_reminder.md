# Booking Reminder Workflow

**Trigger:** Daily cron job (runs at 8 AM local time)
**Input:** None — fetches 48h-window bookings internally

## Steps

1. Fetch all confirmed bookings scheduled 48 hours from now → tools/fetch_pending_reminders.py
2. For each booking: send reminder email to customer → tools/send_email.py (template: booking_reminder)

## Error Handling

- If reminder email fails for a booking: log error, continue to next booking (don't halt the full run)
- Rate limiting: add 1s delay between emails if sending more than 10 in one run

## Notes

- The cron job in main.py handles the loop; this workflow describes the per-booking logic
- Only send reminders to bookings with status = 'confirmed' and is_blocked = false
