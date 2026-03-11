# Confirm Booking Workflow

**Trigger:** bookings UPDATE where status changes to "confirmed"
**Input:** `booking_id` from webhook payload

## Steps

1. Fetch full booking record → tools/fetch_booking.py
   - Query joins `technicians(email, google_calendar_id)` and returns customer details
2. Send customer confirmation email → tools/send_email.py (template: customer_confirmation)

## Error Handling

- If booking fetch fails: log error and abort — cannot send email without customer details
- If customer email fails: retry once with 30s delay; if still fails, log and continue

## Expected Output

- Customer receives confirmation email stating their job is confirmed, with full booking details and a modify link
