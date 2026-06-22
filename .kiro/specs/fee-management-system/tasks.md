# Implementation Plan: School/Institution Fee Management System

## Overview

This plan breaks the full system into incremental coding tasks that build on each other, starting with the database and project scaffold, then the Flask API core, AI/ML service, Celery notification engine, React dashboard, and finally integration wiring and testing. Each task references the specific requirements it satisfies.

---

## Tasks

- [x] 1. Project scaffold and environment setup
  - [x] 1.1 Initialise backend project structure
    - Create the directory layout: `backend/app/{auth,students,fees,invoices,transactions,reports,audit,risk}/`, `backend/migrations/`, `backend/tests/`, `backend/models/`
    - Add `requirements.txt` pinning Flask, Flask-JWT-Extended, SQLAlchemy, Flask-Migrate, marshmallow, celery, redis, bcrypt, joblib, scikit-learn, hypothesis, pytest, reportlab, and gunicorn
    - Add `backend/config.py` with `DevelopmentConfig`, `TestingConfig`, and `ProductionConfig` classes reading from environment variables
    - Add `backend/app/__init__.py` application factory (`create_app`)
    - _Requirements: 8.1, 8.6, 10.1_

  - [x] 1.2 Initialise frontend project structure
    - Scaffold React + Vite project under `frontend/`
    - Install dependencies: react-query, react-router-dom, axios, tailwindcss (or chosen CSS framework)
    - Create directory layout: `frontend/src/{pages,components,hooks,context,api}/`
    - Add `.env.example` with `VITE_API_BASE_URL`
    - _Requirements: 6.1, 6.5_

  - [x] 1.3 Initialise AI/ML service project structure
    - Create `risk_service/` with `app.py`, `features.py`, `train.py`, `score.py`, `models/` directory, and `requirements.txt`
    - Pin scikit-learn, joblib, numpy, pandas, Flask, hypothesis, pytest
    - _Requirements: 4.1, 4.3, 4.7, 4.8_

  - [x] 1.4 Add Docker Compose configuration
    - Write `docker-compose.yml` defining services: `api`, `worker`, `risk_service`, `db` (MySQL 8), `redis`
    - Add `Dockerfile` for `api`, `worker`, and `risk_service`
    - Configure a private Docker network for inter-service communication
    - _Requirements: 10.3_

- [x] 2. Database schema and migrations
  - [x] 2.1 Create SQLAlchemy models for all seven tables
    - Implement `User`, `Student`, `FeeType`, `Invoice`, `InvoiceLineItem`, `Transaction`, `RiskScore`, and `Log` ORM models in `backend/app/models/`
    - Enforce all constraints: UNIQUE keys, ENUM values, DEFAULT values, and FK relationships exactly as specified in the design
    - _Requirements: 1.1, 2.1, 2.2, 3.1, 4.4, 9.1_

  - [x] 2.2 Generate and apply Alembic migrations
    - Run `flask db init` and `flask db migrate` to produce the initial migration script
    - Verify migration creates all seven tables with correct indexes (`idx_status`, `idx_student`, `idx_due_date`, `idx_computed_at`, `idx_actor`, `idx_resource`, `idx_created_at`)
    - _Requirements: 1.1, 2.2, 3.1_

  - [ ]* 2.3 Write property test for financial decimal precision
    - **Property 1: Decimal precision invariant** — for any `amount` value stored and retrieved, `round(stored, 2) == original`
    - **Validates: Requirements 2.5, 3.1**

- [x] 3. Authentication and authorisation
  - [x] 3.1 Implement password hashing and user model helpers
    - Add `set_password(plain)` and `check_password(plain)` methods on `User` using bcrypt with cost factor ≥ 12
    - _Requirements: 8.7_

  - [x] 3.2 Implement JWT login, refresh, and logout endpoints
    - `POST /api/v1/auth/login` — validate credentials, issue JWT (8 h) + refresh token (7 d), return both
    - `POST /api/v1/auth/refresh` — exchange valid refresh token for new JWT
    - `POST /api/v1/auth/logout` — invalidate refresh token (blocklist in Redis)
    - Use Flask-JWT-Extended; store refresh token blocklist in Redis
    - _Requirements: 8.1, 8.4, 8.5_

  - [x] 3.3 Implement JWT middleware and role-based access decorators
    - Add `@jwt_required()` middleware applied globally (except login/refresh)
    - Add `@admin_required` decorator that returns 403 for Viewer role
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 3.4 Write unit tests for auth helpers
    - Test bcrypt hash/verify round-trip
    - Test JWT issue → decode → expiry
    - Test 401 on missing/expired token, 403 on wrong role
    - _Requirements: 8.1, 8.3, 8.4, 8.5_

- [x] 4. Student management API
  - [x] 4.1 Implement student CRUD endpoints
    - `GET /api/v1/students` — list with pagination and filters (status, assigned_admin)
    - `POST /api/v1/students` — create student, return 201 with student object within 2 s
    - `GET /api/v1/students/:id` — get detail
    - `PUT /api/v1/students/:id` — update student, write audit log entry
    - `PATCH /api/v1/students/:id/deactivate` — set `status = inactive`, write audit log entry
    - Validate all required fields with marshmallow; return descriptive errors on failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 4.2 Implement audit log writer helper
    - Create `write_audit_log(actor_id, resource_type, resource_id, action, previous_values, new_values)` utility
    - Call it from every mutating endpoint (students, invoices, transactions, reports export)
    - _Requirements: 1.4, 9.1_

  - [ ]* 4.3 Write unit tests for student endpoints
    - Test create with valid payload → 201
    - Test create with missing fields → 400 with field names
    - Test update writes audit log with previous and new values
    - Test deactivated student cannot receive new invoices (business rule guard)
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

- [x] 5. Fee type and invoice management API
  - [x] 5.1 Implement fee type endpoints
    - `GET /api/v1/fee-types` — list active fee types
    - `POST /api/v1/fee-types` — create fee type (Admin only)
    - `PUT /api/v1/fee-types/:id` — update fee type (Admin only)
    - _Requirements: 2.1_

  - [x] 5.2 Implement invoice generation endpoint
    - `POST /api/v1/invoices` — create invoice with line items, assign unique `invoice_number`, set status `unpaid`
    - Reject duplicate invoice (same student + fee type + billing period) with 409 and `DUPLICATE_INVOICE` error
    - Reject if student is inactive
    - _Requirements: 2.2, 2.3, 2.7_

  - [x] 5.3 Implement invoice status auto-update (overdue transition)
    - Add a Celery Beat periodic task `check_overdue_invoices` that runs every hour
    - For each `unpaid` invoice whose `due_date < today`, set `status = overdue` and enqueue `send_overdue_reminder`
    - _Requirements: 2.4, 5.1_

  - [x] 5.4 Implement payment application endpoint
    - `POST /api/v1/invoices/:id/payments` — apply payment, update `outstanding_balance`, set status to `paid` when balance reaches zero, record `paid_at`
    - Wrap balance update + transaction insert in a single `SERIALIZABLE` DB transaction
    - Enqueue `risk_score_task` and `notification_check_task` after commit
    - _Requirements: 2.5, 2.6, 3.1_

  - [ ]* 5.5 Write property test for invoice balance invariant
    - **Property 2: Balance non-negative invariant** — after any sequence of valid payments, `outstanding_balance >= 0`
    - **Validates: Requirements 2.5, 2.6**

  - [ ]* 5.6 Write property test for duplicate invoice rejection
    - **Property 3: Duplicate invoice idempotency** — submitting the same invoice parameters twice always results in exactly one invoice record
    - **Validates: Requirements 2.7**

  - [ ]* 5.7 Write unit tests for invoice endpoints
    - Test invoice creation → 201 with unique invoice_number
    - Test duplicate invoice → 409
    - Test payment reduces outstanding_balance correctly
    - Test full payment sets status to `paid` and records `paid_at`
    - _Requirements: 2.2, 2.3, 2.5, 2.6, 2.7_

- [x] 6. Transaction recording API
  - [x] 6.1 Implement transaction record and reversal endpoints
    - `GET /api/v1/transactions` — list with filters (student, invoice, date range)
    - `POST /api/v1/transactions` — record payment; validate amount > 0 and ≤ outstanding balance; return 201 within 2 s
    - `POST /api/v1/transactions/:id/reverse` — create reversal transaction, restore invoice balance and status
    - Enforce immutability: no UPDATE or DELETE on `transactions` table (DB-level grant + ORM guard)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 6.2 Write property test for transaction immutability
    - **Property 4: Transaction immutability** — no API call can modify or delete an existing transaction record; only new reversal records are created
    - **Validates: Requirements 3.5**

  - [ ]* 6.3 Write property test for payment amount bounds
    - **Property 5: Payment amount bounds** — for any valid payment `p`, `0 < p.amount <= invoice.outstanding_balance`
    - **Validates: Requirements 3.3, 3.4**

  - [ ]* 6.4 Write unit tests for transaction endpoints
    - Test zero/negative amount → 422 `INVALID_PAYMENT_AMOUNT`
    - Test amount exceeding balance → 422 `PAYMENT_EXCEEDS_BALANCE`
    - Test reversal restores balance and updates invoice status
    - _Requirements: 3.3, 3.4, 3.5, 3.6_

- [x] 7. Checkpoint — core API
  - Ensure all tests pass for tasks 3–6. Run `pytest backend/tests/ -x`. Ask the user if questions arise.

- [x] 8. AI/ML risk scoring service
  - [x] 8.1 Implement feature extraction module
    - Write `extract_features(student_id, db_conn)` in `risk_service/features.py`
    - Compute all seven features: `payment_history_ratio`, `overdue_invoice_count`, `total_outstanding_balance`, `enrollment_duration_days`, `historical_default_rate`, `avg_days_to_pay`, `partial_payment_count`
    - Return a numpy array in a fixed, documented column order
    - _Requirements: 4.3_

  - [ ]* 8.2 Write property test for feature extraction
    - **Property 6: Feature vector completeness** — `extract_features` always returns a vector of exactly 7 finite numeric values for any valid student_id
    - **Validates: Requirements 4.3**

  - [x] 8.3 Implement model training pipeline
    - Write `train_models(db_conn)` in `risk_service/train.py`
    - Extract feature matrix `X` and label vector `y` for all historical records
    - Split 80/20 with stratification; apply `StandardScaler`
    - Train `LogisticRegression(max_iter=1000, C=1.0)` and `DecisionTreeClassifier(max_depth=8)`
    - Evaluate with 5-fold cross-validated ROC-AUC
    - Persist models as `models/model_lr_v{version}.joblib` and `models/model_dt_v{version}.joblib`
    - Replace active model only when new ROC-AUC > current ROC-AUC (write active version to `models/registry.json`)
    - _Requirements: 4.8_

  - [x] 8.4 Implement scoring logic and risk category classification
    - Write `score_student(student_id)` in `risk_service/score.py`
    - Load active LR and DT models from `registry.json`
    - Compute `final_score = max(lr_prob * 100, dt_prob * 100)`
    - Classify: 0–39 → Low, 40–69 → Medium, 70–100 → High
    - Persist result to `risk_scores` table with model version and timestamp
    - _Requirements: 4.1, 4.4_

  - [ ]* 8.5 Write property test for risk score bounds and category consistency
    - **Property 7: Risk score range invariant** — for any student, `0.0 <= score <= 100.0`
    - **Property 8: Risk category consistency** — score in [0,39] ↔ Low; [40,69] ↔ Medium; [70,100] ↔ High
    - **Validates: Requirements 4.1, 4.4**

  - [x] 8.6 Implement risk service Flask endpoints
    - `POST /score` — score single student, return score + category + model_version + computed_at
    - `POST /score/batch` — iterate all active students, call `score_student` for each, return count
    - `POST /retrain` — trigger `train_models`, return new vs old ROC-AUC
    - `GET /health` — return `{"status": "ok"}`
    - _Requirements: 4.1, 4.2, 4.7_

  - [ ]* 8.7 Write unit tests for risk service
    - Test `score_student` returns score in [0, 100]
    - Test category thresholds at boundary values (39, 40, 69, 70)
    - Test `/health` returns 200
    - Test batch endpoint scores all active students
    - _Requirements: 4.1, 4.4, 4.7_

- [x] 9. Risk score integration in main API
  - [x] 9.1 Add risk score read endpoint and Celery task integration
    - `GET /api/v1/students/:id/risk` — proxy latest score from `risk_scores` table
    - `POST /api/v1/risk/batch` — enqueue Celery task that calls `POST /score/batch` on risk service
    - Add Celery task `risk_score_task(student_id)` that calls `POST /score` with retry (up to 5 attempts, 1-min intervals); if service unreachable, return existing score without blocking
    - Trigger `risk_score_task` after every transaction record and invoice status change
    - _Requirements: 4.2, 4.5, 4.7_

  - [ ]* 9.2 Write unit tests for risk integration
    - Test risk score endpoint returns latest score from DB
    - Test `risk_score_task` retries on service unavailability and does not block transaction response
    - Test risk category change triggers admin notification task
    - _Requirements: 4.2, 4.5_

- [x] 10. Notification engine (Celery worker)
  - [x] 10.1 Implement notification task definitions
    - Write Celery tasks in `backend/app/notifications/tasks.py`:
      - `send_overdue_reminder(invoice_id)` — email + optional SMS to student
      - `send_7day_reminder(invoice_id)` — email to student + assigned admin
      - `send_30day_escalation(invoice_id)` — email to senior admin
      - `suppress_reminders(invoice_id)` — revoke pending scheduled tasks for invoice
      - `retry_failed_notification(log_id)` — exponential backoff retry (2, 4, 8 min; max 3 retries)
    - Write `send_email(to, subject, body)` and `send_sms(to, body)` provider wrappers (SMTP/SendGrid and Twilio/Africa's Talking)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 10.2 Implement notification logging
    - After every send attempt (success or failure), write a `Log` record with recipient, channel, timestamp, and `delivery_status`
    - On final failure after 3 retries, set `delivery_status = 'failed'`
    - _Requirements: 5.5, 5.6_

  - [x] 10.3 Wire notification triggers to invoice lifecycle
    - Call `suppress_reminders` when invoice transitions to `paid`
    - Schedule `send_7day_reminder` via Celery ETA 7 days after overdue transition
    - Schedule `send_30day_escalation` via Celery ETA 30 days after overdue transition
    - Trigger admin alert notification when student risk category escalates (from 9.1)
    - _Requirements: 5.3, 5.4, 5.7, 4.5_

  - [ ]* 10.4 Write unit tests for notification tasks
    - Test `send_overdue_reminder` calls email provider and logs attempt
    - Test SMS is sent only when `sms_enabled = True`
    - Test `suppress_reminders` revokes scheduled tasks
    - Test retry logic: 3 failures → `delivery_status = 'failed'` in logs
    - _Requirements: 5.1, 5.2, 5.5, 5.6, 5.7_

- [x] 11. Reports and export API
  - [x] 11.1 Implement report generation endpoint
    - `POST /api/v1/reports` — accept filters: `date_range`, `student_group`, `fee_type`, `invoice_status`, `risk_category`
    - Execute filtered SQL query; return paginated JSON within 10 s for ≤ 10,000 records
    - Pre-built "High Risk Students" report: filter `risk_category = 'high'`, include outstanding balance and last payment date
    - Write audit log entry on report generation
    - _Requirements: 7.1, 7.2, 7.5, 7.6_

  - [x] 11.2 Implement CSV export
    - `GET /api/v1/reports/:id/export?format=csv` — stream CSV with generation timestamp, applied filters, and admin identifier in header row
    - Use Python `csv` module; stream response to avoid memory issues for large datasets
    - _Requirements: 7.3, 7.4_

  - [x] 11.3 Implement PDF export
    - `GET /api/v1/reports/:id/export?format=pdf` — generate PDF using ReportLab
    - Include institution name, generation timestamp, applied filters, admin identifier, and tabular data
    - _Requirements: 7.3, 7.4_

  - [ ]* 11.4 Write unit tests for report endpoints
    - Test report with all filters returns correct subset of data
    - Test CSV export includes timestamp and admin identifier
    - Test PDF export returns valid PDF bytes
    - Test report generation logs export event
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6_

- [x] 12. Audit log API
  - [x] 12.1 Implement audit log query endpoint
    - `GET /api/v1/audit` — Admin only; filter by `date_range`, `actor_id`, `resource_type`, `action`; return within 5 s
    - Enforce append-only: no PUT/DELETE routes on `/audit`
    - _Requirements: 9.1, 9.3, 9.4_

  - [ ]* 12.2 Write unit tests for audit log
    - Test audit entries are created for create/update/deactivate/export actions
    - Test audit log endpoint filters correctly
    - Test no DELETE or UPDATE endpoint exists for audit entries
    - _Requirements: 9.1, 9.3, 9.4_

- [x] 13. Checkpoint — backend complete
  - Run `pytest backend/tests/ -x --tb=short`. Ensure all unit and property tests pass. Ask the user if questions arise.

- [x] 14. React admin dashboard — authentication
  - [x] 14.1 Implement auth context and login page
    - Create `AuthContext` with `login(username, password)`, `logout()`, and `currentUser` state
    - Implement `LoginPage` (`/login`) with form validation; call `POST /api/v1/auth/login`; store JWT in memory and refresh token in `httpOnly` cookie
    - Redirect to `/` on success; redirect to `/login` on 401
    - _Requirements: 8.1, 8.4, 8.5_

  - [x] 14.2 Implement protected route wrapper and token refresh
    - Create `ProtectedRoute` component that checks `AuthContext`; redirects to `/login` if unauthenticated
    - Add Axios interceptor that calls `POST /api/v1/auth/refresh` on 401 and retries original request once
    - _Requirements: 8.1, 8.5_

- [x] 15. React admin dashboard — core views
  - [x] 15.1 Implement dashboard summary panel and student table
    - `DashboardPage` (`/`): fetch summary stats (total collected, outstanding, overdue count) with React Query, auto-refresh every 60 s
    - Render searchable, filterable `StudentTable` with columns: name, outstanding balance, overdue invoices, risk category (color-coded badge: green/amber/red)
    - Filter controls: Risk_Category, Invoice status, billing period
    - Show loading spinner while data loads; show user-readable error on API failure (no stack traces)
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6_

  - [x] 15.2 Implement student detail page
    - `StudentDetailPage` (`/students/:id`): display full payment history, all invoices with statuses, and current risk score with color-coded indicator
    - _Requirements: 6.3, 4.6_

  - [x] 15.3 Implement invoices and transactions pages
    - `InvoicesPage` (`/invoices`): list invoices with status filters; link to student detail
    - `TransactionsPage` (`/transactions`): transaction log with date/student filters
    - _Requirements: 6.2, 6.4_

  - [x] 15.4 Implement reports page
    - `ReportsPage` (`/reports`): filter form (date range, fee type, status, risk category); trigger report generation; display results table
    - Export buttons for CSV and PDF that call `GET /api/v1/reports/:id/export?format=csv|pdf` and trigger browser download
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 15.5 Implement audit log page
    - `AuditLogPage` (`/audit`): Admin-only view; filter by date, actor, resource type, action; paginated table
    - _Requirements: 9.3_

- [x] 16. Checkpoint — frontend complete
  - Verify all dashboard pages render without console errors. Confirm API calls succeed against a running backend. Ask the user if questions arise.

- [x] 17. Integration wiring and end-to-end tests
  - [x] 17.1 Wire all Celery Beat schedules
    - Configure `celery_beat_schedule` in `backend/celery_config.py`:
      - `check_overdue_invoices`: every hour
      - `batch_risk_scoring`: daily at midnight (configurable via `BATCH_SCORE_CRON`)
    - _Requirements: 2.4, 4.7_

  - [x] 17.2 Implement maintenance notice endpoint and banner
    - `GET /api/v1/system/maintenance` — return scheduled maintenance window if set
    - Dashboard fetches this on load and displays a banner if a window is within 24 hours
    - _Requirements: 10.4_

  - [ ]* 17.3 Write integration tests for full payment lifecycle
    - Test: create student → create fee type → generate invoice → record payment → verify invoice status = paid → verify risk score recomputed → verify notification suppressed
    - Test: overdue transition → notification sent → 7-day reminder scheduled → 30-day escalation scheduled
    - _Requirements: 2.4, 2.5, 2.6, 3.1, 4.2, 5.1, 5.3, 5.4, 5.7_

  - [ ]* 17.4 Write integration tests for auth and RBAC
    - Test: Viewer cannot POST to /students, /invoices, /transactions → 403
    - Test: expired JWT → 401 → dashboard redirects to login
    - Test: refresh token flow issues new JWT
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [ ]* 17.5 Write Playwright end-to-end tests
    - Test: Login → view dashboard → select student → view risk score
    - Test: Record payment → verify invoice status update in UI
    - Test: Generate report → export CSV → verify file download
    - _Requirements: 6.1, 6.2, 6.3, 7.3_

- [x] 18. Final checkpoint — all tests pass
  - Run `pytest backend/tests/ -x --tb=short` and `npx playwright test`. Ensure all tests pass. Ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they do not block subsequent tasks
- All financial write operations (payment application, reversal) use `SERIALIZABLE` isolation and are wrapped in a single DB transaction
- The `transactions` and `logs` tables have no UPDATE or DELETE privileges at the DB level — enforce this in the ORM layer as well
- Property tests use **Hypothesis** with `settings(max_examples=100)`; tag each test with `# Feature: fee-management-system, Property N: <text>`
- The risk service is independently deployable; the main API communicates with it over the private Docker network via HTTP
- JWT is stored in memory (not localStorage) to mitigate XSS; refresh token is in an `httpOnly` cookie
- All inter-service traffic stays on the private Docker network; only Nginx is exposed externally over HTTPS

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "8.1"] },
    { "id": 3, "tasks": ["2.3", "3.1", "8.2", "8.3"] },
    { "id": 4, "tasks": ["3.2", "8.4"] },
    { "id": 5, "tasks": ["3.3", "8.5", "8.6"] },
    { "id": 6, "tasks": ["3.4", "4.1", "8.7"] },
    { "id": 7, "tasks": ["4.2", "5.1"] },
    { "id": 8, "tasks": ["4.3", "5.2", "6.1"] },
    { "id": 9, "tasks": ["5.3", "5.4", "6.2", "6.3"] },
    { "id": 10, "tasks": ["5.5", "5.6", "5.7", "6.4", "9.1"] },
    { "id": 11, "tasks": ["9.2", "10.1"] },
    { "id": 12, "tasks": ["10.2", "11.1"] },
    { "id": 13, "tasks": ["10.3", "11.2", "12.1"] },
    { "id": 14, "tasks": ["10.4", "11.3", "12.2"] },
    { "id": 15, "tasks": ["11.4", "14.1"] },
    { "id": 16, "tasks": ["14.2"] },
    { "id": 17, "tasks": ["15.1", "15.2", "15.3"] },
    { "id": 18, "tasks": ["15.4", "15.5"] },
    { "id": 19, "tasks": ["17.1", "17.2"] },
    { "id": 20, "tasks": ["17.3", "17.4"] },
    { "id": 21, "tasks": ["17.5"] }
  ]
}
```
