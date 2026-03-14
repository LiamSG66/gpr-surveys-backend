# Schedule Interview

## Objective
Create a Google Calendar event for the interview and email the candidate confirmation.

## Steps
1. Fetch application and job posting → tools/fetch_application.py
2. Create Google Calendar interview event → tools/create_interview_calendar_event.py
3. Update interview slot with calendar event ID → tools/update_interview_slot.py
4. Send candidate interview confirmation email → tools/send_email.py (template: interview_scheduled)
