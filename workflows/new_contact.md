# New Contact Submission Workflow

**Trigger:** New row inserted in `contact_submissions` table
**Input:** `submission_id` + `record` dict from webhook payload

## Steps

1. Send internal notification email with contact details → tools/send_email.py (template: contact_notification)

## Error Handling

- If email fails: retry once with 10s delay; log if still failing

## Notes

- No calendar or drive steps for contact submissions
- Internal team reviews and follows up manually
- Contact submissions are marked `processed = true` manually after follow-up
