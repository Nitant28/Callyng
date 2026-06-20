import re

with open("guides/bugs2.md", "r") as f:
    content = f.read()

bug39_40 = """
- **BUG-39 [P2] / Feature — `api/routes/leads.py`: Manual lead status transitions too restrictive**
  - **Issue:** The `_MANUAL_TRANSITIONS` map restricts admins from transitioning a lead from `callback_scheduled` or `pending` into `completed` when a campaign is paused.
  - **Impact:** Clients lack the freedom to manually close or complete leads if they handled them offline.
  - **Fix:** Update `_MANUAL_TRANSITIONS` to allow transitions to `completed` from `pending` and `callback_scheduled`.
- **BUG-40 [P2] / Feature — `AdminCampaigns.jsx`: `max_attempts` is not editable**
  - **Issue:** The backend API supports updating `max_attempts`, but the frontend UI has no input field for it. It is hardcoded to `3`.
  - **Impact:** Admins cannot dynamically change the retry limit for a campaign from the dashboard.
  - **Fix:** Add a number input field for "Max Attempts" to the campaign creation and edit modals.
"""

bug41 = """
- **BUG-41 [P3] / Enhancement — `api/routes/campaigns.py`: CSV Upload lacks compliance `next_attempt_at` initialization**
  - **Issue:** During CSV upload, if the time is outside the 9 AM - 9 PM IST window, it fails to set `next_attempt_at = next_compliant_time()`.
  - **Impact:** The dialer will immediately claim newly uploaded leads at night, only to individually defer them in the dialer loop. This causes unnecessary DB load and locking edge cases.
  - **Fix:** During CSV upload, calculate and assign `next_compliant_time()` to leads if uploaded outside business hours.
"""

bug38 = """
- **BUG-38 [P1] / Feature — `post_call_processor.py`: Smart Callback Time & IST Mismatch**
  - **Issue:** `_parse_callback_time` strictly uses `datetime.fromisoformat` and fails gracefully to +4 hours if the LLM hallucinates natural language. Further, it defines `_IST = timezone.utc` which is mathematically wrong for IST.
  - **Impact:** Callbacks are scheduled at incorrect times due to UTC offset mismatches, and natural language callback requests are silently dropped.
  - **Fix:** Integrate a smart NLP date parser (e.g. `dateparser`) to gracefully handle extraction data mismatches. Correctly define `_IST = ZoneInfo("Asia/Kolkata")` and localize callbacks.
"""

# Insert Phase 1
content = content.replace("## Phase 2:", bug39_40 + "\n## Phase 2:")

# Insert Phase 3
content = content.replace("## Phase 4:", bug41 + "\n## Phase 4:")

# Insert Phase 4
content = content.replace("## Phase 5:", bug38 + "\n## Phase 5:")

with open("guides/bugs2.md", "w") as f:
    f.write(content)
