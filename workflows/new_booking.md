# New Booking Workflow

**Trigger:** New booking inserted in Supabase (status: pending)
**Input:** `booking_id` from webhook payload

## Steps

1. Fetch full booking record → tools/fetch_booking.py
   - Query joins `technicians(email, google_calendar_id)` and returns `calendar_owner_email`
2. Create Google Calendar event → tools/create_calendar_event.py
   - `calendar_subject` = `info@gprsurveys.ca` (all new bookings go here; no tech assigned yet)
   - Returns `{ calendar_event_id, calendar_owner_email }` (both stored in Step 6)
3. Create Google Drive folder at /Jobs/{job_number}/ with subfolders: Documents/, Site Photos/, Reports/ → tools/create_drive_folder.py
   - Returns `{ drive_folder_id, drive_folder_url }`
4. Send booking received email to customer → tools/send_email.py (template: booking_received)
5. Send internal notification email → tools/send_email.py (template: internal_notification)
6. Write `calendar_event_id`, `calendar_owner_email`, `drive_folder_id`, and `drive_folder_url` back to booking record → tools/update_booking_record.py

## Error Handling

- If calendar creation fails: log error, retry once; if still fails, flag booking for manual review (do not block remaining steps)
- If Drive creation fails: log error, continue — non-blocking
- If customer email fails: retry once with 30s delay; if still fails, log and continue
- If internal notification fails: log and continue — non-blocking

## Expected Output

- Booking record updated with `google_calendar_event_id`, `calendar_owner_email`, `google_drive_folder_id`, `google_drive_folder_url`
- Customer receives booking received email (pending review)
- Internal team receives notification email
- Google Calendar event created on `info@gprsurveys.ca` for the job date
