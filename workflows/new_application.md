# New Application Received

## Objective
Score the resume via Claude AI, notify the admin, and send acknowledgment to the candidate.

## Steps
1. Fetch application and job posting → tools/fetch_application.py
2. Score resume via Claude AI → tools/score_resume.py
3. Update candidate record with AI score → tools/update_candidate_record.py
4. Send admin notification email → tools/send_email.py (template: new_application)
5. Send candidate acknowledgment email → tools/send_email.py (template: application_received)
