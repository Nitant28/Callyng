# E2E Test Infra: Aakashvani Frontend Refinement

## Test Philosophy
- **Opaque-box & Requirement-driven**: The E2E test suite validates the frontend from the user's perspective, ensuring that the system functions correctly and that unsupported features are cleanly hidden.
- **Methodology**: 4-tier approach covering:
  - **Tier 1**: Feature Coverage (happy path functionality)
  - **Tier 2**: Boundary and Corner Cases
  - **Tier 3**: Cross-Feature Combinations (state consistency and interaction)
  - **Tier 4**: Real-World Workload Scenarios (end-to-end integration and flow checks)

## Feature Inventory
We define $N = 4$ core system features for E2E verification:
1. **F1: Authentication Security & Session Guard**
2. **F2: Dashboard & Campaign Management**
3. **F3: Campaign Management & Lead Upload**
4. **F4: Call Logs & Analytics**

| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|---------------------|:------:|:------:|:------:|:------:|
| 1 | F1: Authentication | ORIGINAL_REQUEST R1 (branding/access) | 5 tests | 5 tests | 1 test | 1 test |
| 2 | F2: Dashboard | ORIGINAL_REQUEST R1 (aesthetic), R2 (Razorpay cleanup) | 5 tests | 5 tests | 1 test | 1 test |
| 3 | F3: Campaign & Leads | ORIGINAL_REQUEST R1 (consistency), R2 (bot config cleanup) | 5 tests | 5 tests | 1 test | 1 test |
| 4 | F4: Call Logs | ORIGINAL_REQUEST R2 (recordings/SSE cleanup) | 5 tests | 5 tests | 1 test | 2 tests |
|   | **Total (49 tests)** | | **20** | **20** | **4** | **5** |

## Test Architecture
- **Test Runner**: Python test script `/home/satyam/aakashvani/tests/test_e2e.py` executed via `pytest`.
- **Methodology of execution**:
  - **Static Analysis Checks**: Programmatic verification of the frontend component codebase (specifically in `/home/satyam/aakashvani/frontend/src/pages/client/`) to assert that the 4 unsupported features (Razorpay, Bot config, SSE live metrics, and Call Recordings) are commented out or disabled, containing `TODO` markers.
  - **Vite Build Verification**: Runs the frontend build script (`npm run build`) in `frontend/` to confirm that all UI and component changes compile successfully without error.
  - **API Compatibility Checks**: Hits simulated/actual FastAPI routes to verify authentication, campaign listing, lead uploading, and call logging.

## Test Cases Inventory

### Tier 1: Feature Coverage (20 tests)
* **F1: Authentication & Authorization**
  1. `test_f1_t1_login_success_real_api`: Verifies successful login using a mock valid API key (calling `/api/credits/balance`).
  2. `test_f1_t1_login_success_bypass`: Verifies successful login using the bypass test mode.
  3. `test_f1_t1_login_failure_invalid_key`: Verifies invalid key returns 401 and shows error.
  4. `test_f1_t1_login_failure_empty_key`: Verifies empty key does not make API requests.
  5. `test_f1_t1_logout`: Verifies logout clears localStorage and redirects.
* **F2: Dashboard & Campaign List**
  6. `test_f2_t1_list_campaigns`: Verifies campaign listing endpoint returns campaigns which render.
  7. `test_f2_t1_view_credits`: Verifies dashboard retrieves and shows credit balance.
  8. `test_f2_t1_create_campaign_success`: Verifies campaign creation endpoint.
  9. `test_f2_t1_create_campaign_invalid_budget`: Verifies campaign creation validation on negative budgets.
  10. `test_f2_t1_navigation_to_details`: Verifies navigation to campaign details page.
* **F3: Campaign Management & Lead Upload**
  11. `test_f3_t1_start_campaign`: Verifies starting a campaign sets status to `running`.
  12. `test_f3_t1_stop_campaign`: Verifies stopping a campaign sets status to `stopped`.
  13. `test_f3_t1_upload_leads_csv`: Verifies lead upload API handles valid CSV file.
  14. `test_f3_t1_view_leads_list`: Verifies leads are listed in campaign view.
  15. `test_f3_t1_edit_lead`: Verifies lead editing endpoint handles updating lead fields.
* **F4: Call Logs & Analytics**
  16. `test_f4_t1_list_call_logs`: Verifies calls list endpoint.
  17. `test_f4_t1_view_call_transcript`: Verifies retrieval of specific call log transcript.
  18. `test_f4_t1_view_call_extraction`: Verifies viewing call extraction results (outcomes/intents).
  19. `test_f4_t1_filter_by_outcome`: Verifies filtering by call outcome.
  20. `test_f4_t1_search_by_phone`: Verifies searching call logs by telephone number.

### Tier 2: Boundary & Corner Cases (20 tests)
* **F1: Authentication & Authorization**
  21. `test_f1_t2_login_boundary_key_length_exactly_12`: Exactly 12 char key is rejected if API fails.
  22. `test_f1_t2_login_boundary_key_length_13`: Greater than 12 char key goes to simulation mode if API fails.
  23. `test_f1_t2_login_boundary_key_length_25`: Greater than 24 char key automatically logs in.
  24. `test_f1_t2_login_boundary_empty_whitespace`: Key of whitespace only is rejected without request.
  25. `test_f1_t2_login_route_guards_redirect`: Accessing dashboard without key in storage redirects to login.
* **F2: Dashboard & Campaign List**
  26. `test_f2_t2_create_campaign_zero_budget`: Verifies validation when creating campaign with 0 budget.
  27. `test_f2_t2_create_campaign_huge_budget`: Verifies client credit limits prevent overdraft.
  28. `test_f2_t2_empty_campaigns_list`: Verifies empty list placeholder display.
  29. `test_f2_t2_low_credits_warning`: Verifies warning display when credits < 10.
  30. `test_f2_t2_unsupported_razorpay_disabled`: Verifies Razorpay payment UI is commented out or disabled.
* **F3: Campaign Management & Lead Upload**
  31. `test_f3_t2_upload_leads_invalid_format`: Verifies invalid formats are rejected.
  32. `test_f3_t2_upload_leads_empty_file`: Verifies empty lead file handling.
  33. `test_f3_t2_start_campaign_no_leads`: Verifies campaign behaviour when starting with 0 leads.
  34. `test_f3_t2_campaign_out_of_budget`: Verifies campaign halt when budget exhausted.
  35. `test_f3_t2_unsupported_bot_config_disabled`: Verifies bot config UI features are disabled/commented.
* **F4: Call Logs & Analytics**
  36. `test_f4_t2_empty_call_logs`: Verifies display for client with no calls.
  37. `test_f4_t2_call_log_no_transcript`: Verifies call logs handle empty transcript gracefully.
  38. `test_f4_t2_long_transcript_scroll`: Verifies scroll wrapper presence for long transcripts.
  39. `test_f4_t2_unsupported_recordings_disabled`: Verifies call recording elements are commented out in CallLogs.
  40. `test_f4_t2_unsupported_sse_metrics_disabled`: Verifies real-time active call/SSE charts are hidden.

### Tier 3: Cross-Feature Combinations (4 tests)
41. `test_f1_t3_login_state_persistence`: Verifies login token storage persistence on refresh, and clear-down on logout.
42. `test_f2_t3_campaign_creation_and_balance_update`: Verifies creating a campaign locks or deducts budget from available client balance.
43. `test_f3_t3_lead_upload_to_running_campaign`: Verifies uploading leads to a running campaign schedules them immediately.
44. `test_f4_t3_call_log_billing_match`: Verifies that actual call duration billing corresponds to client credit deduction.

### Tier 4: Real-World Application Scenarios (5 tests)
45. `test_f1_t4_full_session_cycle`: Login -> Check balance -> View campaigns -> Log out.
46. `test_f2_t4_dashboard_operator_workload`: Creating multiple campaigns, checking remaining credits, and entering detail views.
47. `test_f3_t4_campaign_lifecycle`: Upload lead list -> Start campaign -> Pause campaign -> Edit lead -> Resume.
48. `test_f4_t4_analytics_and_review`: View dashboard -> Filter calls by 'Interested' -> Inspect transcript -> Verify costs.
49. `test_f4_t4_unsupported_cleanup_audit`: Audit React pages statically to verify all 4 unsupported features (Razorpay buy, Bot configuration editor, SSE live charts, Call Recordings play/download) contain `TODO` comments indicating their de-activation.

## Coverage Thresholds
- **Tier 1**: 20/20 (100% feature coverage happy-path)
- **Tier 2**: 20/20 (100% boundary & guard coverage)
- **Tier 3**: 4/4 (100% pairwise feature interactions)
- **Tier 4**: 5/5 (100% end-to-end user flows & codebase sanitation)
