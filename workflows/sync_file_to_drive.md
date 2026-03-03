# Sync File to Drive Workflow

**Trigger:** New row inserted in `booking_files` Supabase table (customer uploads a file during the booking wizard)
**Input:** `job_number`, `file_path`, `file_name` from the webhook record

## Steps

1. Download file from Supabase Storage and upload to the booking's Drive Documents/ subfolder → tools/sync_file_to_drive.py
   - Looks up `google_drive_folder_id` on the booking by `job_number`
   - Finds the Documents/ subfolder under that Drive folder
   - Downloads the file bytes from the `booking-files` Supabase Storage bucket
   - Uploads to Drive Documents/ subfolder, preserving the original filename

## Error Handling

- If `google_drive_folder_id` is NULL on the booking (new_booking workflow hasn't run yet): return `synced_skipped` — log and do not retry. The Drive folder will be created shortly; any delay is acceptable since this is a support document, not a blocking requirement.
- If the Documents/ subfolder is not found: log error, return `synced_skipped` — non-blocking.
- If Supabase Storage download fails: log error, raise — allows Modal to surface the failure in logs.
- If Drive upload fails: log error, raise — allows Modal to surface the failure in logs.

## Expected Output

- File appears in `/Jobs/{job_number}/Documents/` in Google Drive
- Owned by `info@gprsurveys.ca` via DWD impersonation
