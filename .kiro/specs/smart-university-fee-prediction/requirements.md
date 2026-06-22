# Requirements Document

## Introduction

The Smart University Fee Prediction & Management System is a web application that centralises student fee records, automates payment tracking, predicts which students are likely to miss or delay payments using machine learning, triggers personalised email and SMS reminders, and provides real-time dashboards and exportable reports for finance administrators.

The backend Flask REST API, SQLAlchemy ORM models, risk scoring microservice (`risk_service/`), Celery async tasks, JWT authentication, and most report endpoints are **already implemented**. This requirements document covers the **complete intended system behaviour** end-to-end, including what is already built (to ensure it is specified and testable) and what **remains to be completed**: the React frontend pages for student management, risk monitoring, and reports; a `GET /api/v1/dashboard/summary` endpoint; a `GET /api/v1/risk/distribution` endpoint; and a demo dataset seed script.

---

## Glossary

- **System**: The complete Smart University Fee Prediction & Management System (backend API + risk microservice + frontend SPA).
- **API**: The Flask REST API served at `/api/v1`, providing all data endpoints consumed by the frontend.
- **Risk_Service**: The standalone Flask microservice (`risk_service/`) that trains ML models and scores students.
- **ML_Pipeline**: The model training pipeline in `risk_service/train.py` that trains Logistic Regression and Decision Tree classifiers.
- **Feature_Extractor**: The module `risk_service/features.py` that computes the 7-feature vector for a student from the database.
- **Scorer**: The module `risk_service/score.py` that loads the active models, runs inference, and persists `RiskScore` records.
- **Classifier**: The pure function `classify_risk(score)` in `risk_service/score.py`.
- **Dashboard**: The frontend main page (`/`) displaying KPI summary cards and the student list table.
- **Student_Ledger**: The student detail page (`/students/:id`) showing contact info, risk assessment, invoices, and transaction history.
- **Notification_Engine**: The Celery task module `app/notifications/tasks.py` that dispatches email and SMS reminders.
- **Registry**: The JSON file `risk_service/models/registry.json` recording the active model file paths, version, and ROC-AUC.
- **Admin**: A user with `role = "admin"` — full read/write access.
- **Staff**: A user with `role = "staff"` — read-only access to student and invoice data.
- **Student**: A record in the `students` table representing an enrolled student.
- **Invoice**: A billing document in the `invoices` table with status `unpaid`, `overdue`, `paid`, or `cancelled`.
- **Transaction**: An immutable payment or reversal event in the `transactions` table.
- **RiskScore**: A point-in-time ML risk assessment record in the `risk_scores` table.
- **Risk_Category**: One of `low`, `medium`, or `high` derived from the numeric score.
- **Demo_Dataset**: A seed script that populates the database with realistic synthetic student, invoice, and transaction records for demonstration.

---

## Requirements

---

### Requirement 1: User Authentication and Session Management

**User Story:** As a finance staff member or admin, I want to log in with my credentials and maintain a secure session, so that I can access the system without re-authenticating on every request.

#### Acceptance Criteria

1. WHEN a user submits a valid `email` and `password` to `POST /api/v1/auth/login`, THE API SHALL return HTTP 200 with a signed JWT access token (valid for 8 hours) and a refresh token (valid for 7 days) in the response body.
2. WHEN a user submits invalid credentials (wrong password, unknown email, or missing fields) to `POST /api/v1/auth/login`, THE API SHALL return HTTP 401 with error code `UNAUTHORIZED` and SHALL NOT reveal whether the email or password was incorrect.
3. IF token generation fails due to a system error after valid credentials are verified, THEN THE API SHALL return HTTP 500 with error code `INTERNAL_ERROR` without exposing the internal failure reason.
4. WHEN a user calls `POST /api/v1/auth/refresh` with a valid, non-revoked refresh token in the `Authorization: Bearer` header, THE API SHALL issue a new access token and return HTTP 200.
5. WHEN a user calls `POST /api/v1/auth/logout` with a valid access token, THE API SHALL add the token's JTI to the Redis blocklist with a TTL matching the token's remaining expiry and return HTTP 200.
6. WHEN a revoked or blocklisted token is presented to any protected endpoint, THE API SHALL return HTTP 401 with error code `UNAUTHORIZED`.
7. WHEN any request is made to a protected endpoint without an `Authorization: Bearer <token>` header, THE API SHALL return HTTP 401 with error code `UNAUTHORIZED`.
8. THE API SHALL store all user passwords as bcrypt hashes with a cost factor of at least 12 in production and at least 4 in testing environments.

---

### Requirement 2: Role-Based Access Control

**User Story:** As a system administrator, I want role-based access control enforced on all endpoints, so that staff members cannot perform administrative actions.

#### Acceptance Criteria

1. THE API SHALL enforce `role = "admin"` for all write operations: creating students, updating students, creating invoices, cancelling invoices, recording transactions, triggering batch scoring, and triggering model retraining.
2. IF an authenticated request carries a token with `role = "staff"` and targets an admin-only endpoint, THEN THE API SHALL return HTTP 403 with error code `FORBIDDEN`.
3. IF an authenticated request carries a token with an unrecognised or absent role claim and targets any protected endpoint, THEN THE API SHALL return HTTP 403 with error code `FORBIDDEN`.
4. THE API SHALL permit both `admin` and `staff` roles to perform read-only retrieval of students, invoices, transactions, reports, and audit logs (GET requests only).
5. WHEN a request arrives at any protected endpoint without a valid JWT (missing, malformed, or expired), THE API SHALL return HTTP 401 with error code `UNAUTHORIZED` before evaluating role.

---

### Requirement 3: Student Fee Record Management

**User Story:** As an admin, I want to create, view, update, and list student records with their full fee ledger, so that the finance team has a single centralised source of truth for each student's account.

#### Acceptance Criteria

1. WHEN an admin submits a valid student payload (required fields: `student_number`, `first_name`, `last_name`, `email`, `enrollment_date`) to `POST /api/v1/students`, THE API SHALL create a new `Student` record, return HTTP 201 with the student data, and write an audit log entry.
2. IF any required field is missing or fails validation (e.g. invalid email format, future `enrollment_date`), THEN THE API SHALL return HTTP 400 with error code `VALIDATION_ERROR` and a field-level error map.
3. WHEN a student with a duplicate `student_number` is submitted to `POST /api/v1/students`, THE API SHALL return HTTP 409 with error code `CONFLICT`.
4. WHEN an admin submits a valid partial update to `PUT /api/v1/students/:id`, THE API SHALL update only the supplied fields, return HTTP 200 with the updated student record, and write an audit log entry.
5. WHEN `GET /api/v1/students` is called, THE API SHALL return a paginated list of students where `page` defaults to 1, `per_page` defaults to 20, and `per_page` is capped at 100, along with `total` count metadata.
6. WHEN `GET /api/v1/students/:id` is called for an existing student, THE API SHALL return the student record including the student's latest `risk_category` and `score` from the most recent `RiskScore` record (by `computed_at`), or `null` if no score exists.
7. WHEN `GET /api/v1/students/:id` is called for a non-existent student ID, THE API SHALL return HTTP 404 with error code `NOT_FOUND`.
8. WHEN `GET /api/v1/students` is called with a `status` query parameter of `active` or `inactive`, THE API SHALL return only students matching that status; IF an invalid `status` value is provided, THEN THE API SHALL return HTTP 400 with error code `VALIDATION_ERROR`.
9. WHEN `GET /api/v1/students` is called with a `risk_category` query parameter of `low`, `medium`, or `high`, THE API SHALL return only students whose most recent `RiskScore` matches that category.

---

### Requirement 4: Invoice Lifecycle Management

**User Story:** As an admin, I want to create invoices for students and track them through their full lifecycle, so that outstanding balances and payment statuses are always accurate.

#### Acceptance Criteria

1. WHEN an admin submits a valid invoice payload (required: `student_id`, `total_amount` > 0, `due_date` in ISO 8601 format, at least one line item) to `POST /api/v1/invoices`, THE API SHALL create a new `Invoice` with `status = "unpaid"`, `outstanding_balance = total_amount`, auto-generate a unique `invoice_number`, and return HTTP 201.
2. IF `student_id` does not reference an existing active student, or `total_amount` ≤ 0, or `due_date` is missing or malformed, THEN THE API SHALL return HTTP 400 with error code `VALIDATION_ERROR`.
3. WHEN `GET /api/v1/invoices` is called, THE API SHALL return a paginated invoice list (default `page=1`, `per_page=20`, max `per_page=100`) filterable by `status`, `student_id`, `due_date_from` (ISO 8601), and `due_date_to` (ISO 8601).
4. WHEN `GET /api/v1/invoices/:id` is called for an existing invoice, THE API SHALL return the invoice record including all its line items.
5. WHEN an admin requests cancellation via `PATCH /api/v1/invoices/:id` with `{"status": "cancelled"}` and the invoice has no payment-type transactions, THE API SHALL update the status to `"cancelled"` and return HTTP 200.
6. IF an admin requests cancellation of an invoice that already has one or more payment-type transactions, THEN THE API SHALL return HTTP 422 with error code `UNPROCESSABLE_ENTITY` and SHALL NOT modify the invoice.
7. WHEN a Celery task runs and finds `unpaid` invoices whose `due_date` is before the current UTC date, THE System SHALL update each such invoice's status to `"overdue"` and enqueue the overdue notification task for each affected invoice.
8. WHEN a payment transaction reduces an invoice's `outstanding_balance` to exactly `0.00`, THE System SHALL update the invoice `status` to `"paid"` and record `paid_at` as the current UTC timestamp.
9. THE `outstanding_balance` for any invoice SHALL equal `total_amount − SUM(payment transaction amounts) + SUM(reversal transaction amounts)` at all times.

---

### Requirement 5: Payment Transaction Recording

**User Story:** As an admin, I want to record payments and reversals against invoices, so that the outstanding balance is kept accurate and every financial event is immutably logged.

#### Acceptance Criteria

1. WHEN an admin submits a valid payment to `POST /api/v1/transactions` (required: `invoice_id`, `amount` > 0.00, `type = "payment"`, `payment_method`), THE API SHALL create an immutable `Transaction` record, reduce the invoice's `outstanding_balance` by `amount`, assign a unique `transaction_ref`, and return HTTP 201.
2. IF `amount` is zero or negative, THEN THE API SHALL return HTTP 400 with error code `VALIDATION_ERROR`.
3. IF `amount` exceeds the invoice's current `outstanding_balance`, THEN THE API SHALL return HTTP 422 with error code `UNPROCESSABLE_ENTITY` and SHALL NOT create the transaction.
4. IF `invoice_id` references an invoice with `status = "cancelled"` or `status = "paid"`, THEN THE API SHALL return HTTP 422 with error code `UNPROCESSABLE_ENTITY` and SHALL NOT create the payment.
5. WHEN an admin submits a reversal to `POST /api/v1/transactions` with `type = "reversal"` referencing a valid existing payment `transaction_ref`, THE API SHALL create an immutable reversal `Transaction` for the full amount of the original payment, increase the invoice's `outstanding_balance` by that amount, and if the invoice was `"paid"`, set its status back to `"unpaid"`.
6. IF the referenced payment `transaction_ref` does not exist or has already been reversed, THEN THE API SHALL return HTTP 422 with error code `UNPROCESSABLE_ENTITY`.
7. WHEN a payment reduces `outstanding_balance` to exactly `0.00`, THE System SHALL set `invoice.status = "paid"` and `invoice.paid_at` to the current UTC timestamp in the same database transaction.
8. WHEN `GET /api/v1/transactions` is called, THE API SHALL return a paginated list (default `page=1`, `per_page=20`, max `per_page=100`) filterable by `student_id`, `invoice_id`, and `type`.
9. THE `outstanding_balance` of any invoice SHALL satisfy `outstanding_balance = total_amount − SUM(payment amounts) + SUM(reversal amounts)` after every transaction operation.

---

### Requirement 6: AI/ML Risk Scoring

**User Story:** As a finance admin, I want each student to be automatically assigned a High, Medium, or Low payment-risk category by the ML model, so that the team can prioritise outreach before payments become overdue.

#### Acceptance Criteria

1. WHEN `POST /score` is called on the Risk_Service with a valid integer `student_id` for an active student, THE Risk_Service SHALL extract the 7-feature vector, run inference through both the Logistic Regression and Decision Tree models, compute the ensemble score as `max(p_lr, p_dt) × 100` clamped to `[0.0, 100.0]`, persist a `RiskScore` row, and return HTTP 200 with `student_id`, `score`, `risk_category`, `model_version`, and `computed_at`.
2. IF `POST /score` is called with a `student_id` for a student whose `status = "inactive"`, THEN THE Risk_Service SHALL return HTTP 400 with error code `VALIDATION_ERROR`.
3. IF `POST /score` is called with a `student_id` that does not exist in the database, THEN THE Risk_Service SHALL return HTTP 404 with error code `NOT_FOUND`.
4. THE Classifier SHALL map scores in `[0.0, 39.9]` to `"low"`, scores in `[40.0, 69.9]` to `"medium"`, and scores in `[70.0, 100.0]` to `"high"`.
5. WHEN `POST /api/v1/risk/batch` is called by an admin, THE API SHALL return HTTP 202 and enqueue a Celery task that calls `POST /score/batch` on the Risk_Service for all active students.
6. IF the Risk_Service is unreachable when the batch Celery task runs, THEN THE Celery task SHALL retry up to 3 times with exponential backoff before marking the task as failed and logging the error.
7. WHEN a student's `risk_category` changes from `"low"` or `"medium"` to a higher category after a scoring run, AND the student has an assigned admin, THE Notification_Engine SHALL send a risk escalation email to the student's assigned admin.
8. IF a student's `risk_category` escalates but the student has no assigned admin (`assigned_admin_id IS NULL`), THEN THE System SHALL log the escalation event without sending a notification email.
9. WHEN `GET /api/v1/students/:id/risk` is called for a student with at least one `RiskScore` record, THE API SHALL return the most recent `RiskScore` (by `computed_at`) with `score`, `risk_category`, `model_version`, and `computed_at`.
10. WHEN `GET /api/v1/students/:id/risk` is called for a student with no `RiskScore` records, THE API SHALL return HTTP 404 with error code `NOT_FOUND`.
11. WHEN `GET /api/v1/risk/distribution` is called by an admin, THE API SHALL return `low_count`, `medium_count`, `high_count`, and `total` based on each active student's most recent `RiskScore`, where students with no score are excluded from the counts.
12. THE Feature_Extractor SHALL always return a numpy array of shape `(7,)` with `dtype=float64` for any existing student, where `payment_history_ratio ∈ [0.0, 1.0]`, `historical_default_rate ∈ [0.0, 1.0]`, and `enrollment_duration_days ≥ 0.0`.
13. IF any individual feature cannot be derived due to missing historical data, THE Feature_Extractor SHALL substitute `0.0` for that feature rather than raising an exception.

---

### Requirement 7: ML Model Training Pipeline

**User Story:** As a system administrator, I want the ML models to be retrained on the latest data and automatically replace the active model when performance improves, so that risk predictions stay accurate as more payment history accumulates.

#### Acceptance Criteria

1. WHEN `POST /retrain` is called on the Risk_Service and at least 10 students with successfully extracted feature vectors exist, THE ML_Pipeline SHALL apply a stratified 80/20 train/test split, train `LogisticRegression(C=1.0, max_iter=1000)` and `DecisionTreeClassifier(max_depth=8)`, evaluate both with 5-fold cross-validated ROC-AUC, and return HTTP 200 with `new_roc_auc`, `current_roc_auc`, `replaced`, `version`, and `n_samples`.
2. WHEN the cross-validated ROC-AUC of the newly trained models exceeds the `current_roc_auc` in the Registry, THE ML_Pipeline SHALL persist the LR model, DT model, and scaler as versioned joblib files and update the Registry with the new `version`, `active_lr`, `active_dt`, `active_scaler`, `current_roc_auc`, and `trained_at`; the response SHALL include `"replaced": true`.
3. IF the new cross-validated ROC-AUC does NOT exceed the `current_roc_auc`, THEN THE ML_Pipeline SHALL leave the Registry unchanged and return `"replaced": false` with both ROC-AUC values.
4. IF fewer than 10 students with successfully extracted feature vectors exist, THEN THE ML_Pipeline SHALL return HTTP 200 with `"replaced": false`, the current version, `n_samples` as the actual count, and an `"error"` field explaining the insufficient sample count; the Registry SHALL remain unchanged.
5. THE ML_Pipeline SHALL assign model versions using semantic versioning `vMAJOR.MINOR.PATCH` starting at `v1.0.0`, incrementing only the patch component on each successful replacement.
6. THE version increment function `_increment_patch(version)` SHALL produce `vX.Y.(Z+1)` for any input `vX.Y.Z` where X, Y, Z are non-negative integers, preserving the major and minor components unchanged; for a `None` or unparseable input, it SHALL return `"v1.0.0"`.
7. IF `load_active_models()` is called and the Registry references a model file that does not exist on disk, THEN THE ML_Pipeline SHALL raise `FileNotFoundError` with a message that includes the missing file path.

---

### Requirement 8: Automated Notification Workflows

**User Story:** As a finance admin, I want the system to automatically send personalised email and SMS reminders at key overdue milestones, so that students are prompted to pay before manual escalation is required.

#### Acceptance Criteria

1. WHEN an invoice transitions to `status = "overdue"`, THE Notification_Engine SHALL send an email reminder to the student's email address; IF `sms_enabled = true` AND the student has a non-null `phone` value, THE Notification_Engine SHALL also send an SMS reminder to that phone number; IF `sms_enabled = true` but `phone` is null, THE Notification_Engine SHALL skip the SMS silently and log a warning.
2. WHEN an invoice has been `overdue` for exactly 7 days (measured from the `due_date`), THE Notification_Engine SHALL send a follow-up email to the student and an email to the student's assigned admin; this follow-up SHALL be sent only once per invoice at the 7-day milestone.
3. WHEN an invoice has been `overdue` for exactly 30 days (measured from the `due_date`), THE Notification_Engine SHALL send a single escalation email to all active admin users; this escalation email SHALL be sent only once per invoice at the 30-day milestone.
4. WHEN an invoice's `status` changes to `"paid"` or `"cancelled"`, THE Notification_Engine SHALL revoke all pending Celery reminder tasks for that invoice so no further reminders are sent.
5. WHEN a notification delivery attempt fails (SMTP or Twilio error), THE Notification_Engine SHALL retry with exponential backoff: first retry after 2 minutes, second after 4 minutes, third after 8 minutes, for a maximum of 3 retry attempts.
6. IF all 3 retry attempts for a notification fail, THEN THE Notification_Engine SHALL record the final delivery status as `"failed"` in the `logs` table.
7. THE Notification_Engine SHALL log every notification attempt (both email and SMS) to the `logs` table with `channel` (`"email"` or `"sms"`), `delivery_status` (`"sent"`, `"failed"`, or `"pending"`), `recipient` (email address or phone number), `resource_id` (invoice ID), and `created_at` timestamp.

---

### Requirement 9: Admin Dashboard and KPI Summary

**User Story:** As a finance admin, I want a real-time dashboard showing key financial KPIs and a filterable student list with risk indicators, so that I can monitor the portfolio at a glance and quickly identify students needing attention.

#### Acceptance Criteria

1. WHEN `GET /api/v1/dashboard/summary` is called, THE API SHALL return: `total_collected` (sum of `total_amount` for all `paid` invoices), `total_outstanding` (sum of `outstanding_balance` for all `unpaid` and `overdue` invoices), `overdue_count` (count of invoices with `status = "overdue"`), `active_student_count` (count of students with `status = "active"`), and `forecast_30d` (sum of `outstanding_balance` for invoices with `due_date` within the next 30 calendar days from the request date, inclusive of today and the 30th day).
2. WHEN the Dashboard page loads in the browser, THE Dashboard SHALL display four KPI stat cards — Total Collected, Outstanding Balance, Overdue Invoices, and Active Students — populated from the `GET /api/v1/dashboard/summary` response.
3. WHEN the Dashboard page loads, THE Dashboard SHALL display a risk distribution chart (bar or donut) showing the count of active students in each `risk_category` based on each student's most recent `RiskScore`; students with no score SHALL be excluded from the chart.
4. WHILE the Dashboard page is open and the user is authenticated, THE Dashboard SHALL re-fetch KPI summary and student list data from the API every 60 seconds without requiring a manual page reload.
5. IF a Dashboard auto-refresh request fails, THEN THE Dashboard SHALL retain the last successfully loaded data, display a non-blocking error indicator, and retry after 10 seconds.
6. THE Dashboard student list table SHALL display at minimum: student full name, `student_number`, `status`, and current `risk_category` (showing `"N/A"` when no score exists).
7. WHEN the user types in the name filter field, THE Dashboard SHALL perform a case-insensitive partial match against `first_name + ' ' + last_name` and apply simultaneously with any active `risk_category` filter.
8. WHEN a student row in the Dashboard student table is clicked, THE Dashboard SHALL navigate the user to the Student Ledger page for that student (`/students/:id`).

---

### Requirement 10: Student Ledger Page

**User Story:** As a finance staff member, I want a dedicated student detail page showing contact information, risk score, full invoice history, and transaction history, so that I can understand a student's payment behaviour in one view.

#### Acceptance Criteria

1. WHEN the Student_Ledger page loads for a valid student ID, THE Student_Ledger SHALL display the student's full name, `student_number`, `enrollment_date`, `email`, `phone`, `status`, and `sms_enabled` preference.
2. WHEN a `RiskScore` record exists for the student, THE Student_Ledger SHALL display the latest risk category badge colour-coded (green = `"low"`, amber = `"medium"`, red = `"high"`), the numeric score out of 100, a visual progress bar using the same colour scheme, the `model_version`, and the `computed_at` timestamp.
3. IF no `RiskScore` record exists for the student, THEN THE Student_Ledger SHALL display a "Not yet scored" placeholder in the risk section.
4. WHEN the Student_Ledger page loads, THE Student_Ledger SHALL display all invoices for that student in a paginated table showing invoice number, total amount, outstanding balance, status badge, due date, and paid-at date.
5. WHEN the Student_Ledger page loads, THE Student_Ledger SHALL fetch and display the student's transaction history in a paginated table showing transaction reference, amount, payment method, type, and created-at timestamp.
6. WHEN an admin views the Student_Ledger, THE Student_Ledger SHALL display a "Rescore" button that calls `POST /api/v1/risk/score` with the student's ID, shows a loading spinner while the request is in progress, and refreshes the risk display on completion.
7. IF the Student_Ledger page is loaded with an invalid or non-existent student ID, THE Student_Ledger SHALL display a "Student not found" error message and a link to navigate back to the Dashboard.

---

### Requirement 11: Risk Monitoring Page

**User Story:** As a finance admin, I want a dedicated risk monitoring page that lists all students segmented by risk category with their key risk metrics, so that I can run batch scoring and take targeted action on high-risk accounts.

#### Acceptance Criteria

1. WHEN the Risk Monitoring page loads, THE Risk_Monitoring_Page SHALL display a table of all students with their latest `risk_category`, numeric `score`, `computed_at` timestamp, overdue invoice count, and total outstanding balance; students with no score SHALL show `"N/A"` for score fields.
2. WHEN the user selects a `risk_category` filter (`all`, `low`, `medium`, `high`), THE Risk_Monitoring_Page SHALL filter the table client-side to show only matching students; the filter SHALL apply simultaneously with any active name search.
3. WHEN an admin clicks the "Run Batch Scoring" button, THE Risk_Monitoring_Page SHALL call `POST /api/v1/risk/batch`, disable the button and display a loading indicator for the duration, and refresh the risk table on receiving the completion signal.
4. WHEN an admin clicks the "Retrain Model" button, THE Risk_Monitoring_Page SHALL call `POST /api/v1/risk/retrain`, display a loading indicator, and on completion show the returned `new_roc_auc`, `current_roc_auc`, and a message indicating whether the model was replaced.
5. WHEN `GET /api/v1/risk/distribution` is called, THE API SHALL return `low_count`, `medium_count`, `high_count`, and `total` for all active students based on their most recent `RiskScore`, where `low_count + medium_count + high_count = total` and students with no score are excluded.

---

### Requirement 12: Reports and Data Export

**User Story:** As a finance admin, I want to generate filtered reports and export them as CSV or PDF, so that I can share financial data with university management.

#### Acceptance Criteria

1. WHEN an admin calls `POST /api/v1/reports` with `report_type = "fee_collection"` and optional filters (`date_from`, `date_to`, `invoice_status`, `risk_category`), THE API SHALL generate the report, persist it with a `report_id` and `generated_at` timestamp, and return HTTP 201 with the `report_id`, record count, and applied filters.
2. WHEN an admin calls `POST /api/v1/reports` with `report_type = "high_risk_students"`, THE API SHALL generate a report showing all students whose most recent `RiskScore.risk_category = "high"`, including each student's outstanding balance and most recent payment date.
3. WHEN `GET /api/v1/reports/:id/export?format=csv` is called for an existing report within 1 hour of generation, THE API SHALL return the data as a UTF-8 encoded CSV file with `Content-Disposition: attachment` headers and metadata comment rows (report type, generated-at, generated-by, applied filters) before the data columns.
4. WHEN `GET /api/v1/reports/:id/export?format=pdf` is called for an existing report within 1 hour of generation, THE API SHALL return a ReportLab-generated PDF with a title section, metadata table, and a formatted data table.
5. WHEN a report is generated with filters applied, the record count SHALL be less than or equal to the record count of the same report type with no filters applied.
6. IF `GET /api/v1/reports/:id/export` is called more than 1 hour after `generated_at`, THEN THE API SHALL return HTTP 404 with error code `NOT_FOUND`.
7. IF `GET /api/v1/reports/:id` is called for a non-existent `report_id`, THEN THE API SHALL return HTTP 404 with error code `NOT_FOUND`.
8. THE Reports_Page in the frontend SHALL allow the user to select a report type, apply date and status filters, submit the generation request, and download the result as CSV or PDF.

---

### Requirement 13: Audit Logging

**User Story:** As a system administrator, I want every mutating action to be recorded in an immutable audit log, so that all financial operations can be traced back to the responsible user.

#### Acceptance Criteria

1. WHEN any of the following operations completes successfully, THE System SHALL write exactly one audit log entry to the `logs` table: student created, student updated, invoice created, invoice status changed, transaction recorded, report generated, report exported, batch scoring triggered, model retrained.
2. WHEN `GET /api/v1/audit` is called with `page` and `per_page` parameters (defaults: `page=1`, `per_page=20`, max `per_page=100`), THE API SHALL return a paginated audit log spanning the complete historical trail, with each entry containing `actor_id`, `resource_type`, `resource_id`, `action`, `previous_values` (JSON), `new_values` (JSON), and `created_at`.
3. WHEN `GET /api/v1/audit` is called with filter parameters `resource_type`, `action`, or `actor_id`, THE API SHALL return only entries matching all supplied filters simultaneously.
4. THE `logs` table SHALL be append-only: no DELETE or UPDATE operations SHALL be permitted on existing audit log rows from within the application layer.
5. GET (read-only) operations SHALL NOT generate audit log entries.

---

### Requirement 14: Demo Dataset

**User Story:** As a developer or evaluator, I want a seed script that populates the database with realistic synthetic data, so that the system can be demonstrated without requiring real student records.

#### Acceptance Criteria

1. WHEN the demo seed script is executed, THE System SHALL create at least 50 `Student` records with realistic names, unique `student_number` values, valid email addresses, and `enrollment_date` values distributed across the past 3 years.
2. WHEN the demo seed script is executed, THE System SHALL create at least 150 `Invoice` records distributed across all four statuses (`paid`, `overdue`, `unpaid`, `cancelled`) with `due_date` values spread across the past 12 months and next 3 months.
3. WHEN the demo seed script is executed, THE System SHALL create at least 100 `Transaction` records of type `"payment"` and at least 10 of type `"reversal"`, each referencing valid existing invoices and students.
4. WHEN the demo seed script is executed, THE System SHALL create at least 2 users with `role = "admin"` and at least 2 users with `role = "staff"`, each with a bcrypt-hashed password known to the developer for immediate login.
5. WHEN the demo seed script is executed a second time on a database that already contains seeded data, THE System SHALL NOT create duplicate records — it SHALL skip or upsert records that match on their unique key (`student_number`, `invoice_number`, `transaction_ref`, user `email`).
6. AFTER the demo seed script completes, WHEN `POST /retrain` is called on the Risk_Service, THE ML_Pipeline SHALL have at least 10 students with extractable feature vectors and SHALL successfully train and register an active model in the Registry.

---

### Requirement 15: System Health and Availability

**User Story:** As a system operator, I want health check endpoints and a maintenance window notification, so that I can monitor service availability and inform users of planned downtime.

#### Acceptance Criteria

1. WHEN `GET /api/v1/system/health` is called and the database and Redis connections are healthy, THE API SHALL return HTTP 200 with `{"status": "ok"}`.
2. IF `GET /api/v1/system/health` is called and the database or Redis connection is unavailable, THEN THE API SHALL return HTTP 503 with `{"status": "degraded"}` and a message identifying which dependency is unhealthy.
3. WHEN `GET /health` is called on the Risk_Service and the service is running, THE Risk_Service SHALL return HTTP 200 with `{"status": "ok"}`.
4. WHEN the `MAINTENANCE_START` and `MAINTENANCE_END` environment variables are set to valid ISO 8601 datetime strings and the current UTC time falls within that window, THE API SHALL return HTTP 503 with error code `SERVICE_UNAVAILABLE` for all non-health-check endpoints.
5. WHEN a scheduled maintenance window's `MAINTENANCE_START` is within the next 24 hours, THE Dashboard SHALL display a maintenance banner to all authenticated users showing the start and end times.
6. WHEN any unhandled exception occurs in the API, THE API SHALL return HTTP 500 with a generic message and SHALL NOT expose stack traces, SQL queries, or internal configuration details to the client.

---

## Correctness Properties

The following properties are suitable for property-based testing using `hypothesis` (Python) and `fast-check` (JavaScript/TypeScript).

### P1 — Risk Classifier Partition Coverage
For all `score` values `s ∈ [0.0, 100.0]`, `classify_risk(s)` SHALL return exactly one of `"low"`, `"medium"`, or `"high"`, deterministically:
- `s ∈ [0.0, 39.9]` → `"low"`
- `s ∈ [40.0, 69.9]` → `"medium"`
- `s ∈ [70.0, 100.0]` → `"high"`
- For any `s < 0.0` or `s > 100.0`, `classify_risk(s)` SHALL raise `ValueError`.

### P2 — Feature Vector Invariants
For any valid `student_id`, `extract_features(student_id, db_conn)` SHALL return a `numpy.ndarray` of shape `(7,)` with `dtype=float64` where:
- `features[0]` (payment_history_ratio) ∈ `[0.0, 1.0]`
- `features[1]` (overdue_invoice_count) ≥ `0.0`
- `features[2]` (total_outstanding_balance) ≥ `0.0`
- `features[3]` (enrollment_duration_days) ≥ `0.0`
- `features[4]` (historical_default_rate) ∈ `[0.0, 1.0]`
- `features[6]` (partial_payment_count) ≥ `0.0`

### P3 — Invoice Balance Invariant
For any invoice with any combination of payment and reversal transactions, the `outstanding_balance` SHALL always satisfy:
`outstanding_balance = total_amount − SUM(payment amounts) + SUM(reversal amounts)`
This must hold after every transaction event, including partial payments, full payments, and chained reversals.

### P4 — Version Increment Round-Trip
For any valid semantic version string `"vX.Y.Z"` where X, Y, Z are non-negative integers:
- `_increment_patch("vX.Y.Z")` SHALL return `"vX.Y.(Z+1)"`
- Major and minor components SHALL remain unchanged
- Applying `_increment_patch` N times starting from `"vX.Y.Z"` SHALL yield `"vX.Y.(Z+N)"`
- `_increment_patch(None)` and `_increment_patch("")` SHALL return `"v1.0.0"`

### P5 — Report Filter Monotonicity (Metamorphic Property)
For any report type `T` and any non-empty filter set `F`:
`record_count(T, F) ≤ record_count(T, no_filters)`
This must hold for all valid combinations of `date_from`, `date_to`, `invoice_status`, and `risk_category` filters.

### P6 — Risk Distribution Count Invariant
`GET /api/v1/risk/distribution` SHALL always return counts satisfying:
`low_count + medium_count + high_count = total`
where `total` equals the number of active students who have at least one `RiskScore` record.

### P7 — Token Revocation Irreversibility
For any valid JWT access token `T` that has been successfully revoked via `POST /api/v1/auth/logout`:
Every subsequent request to any protected endpoint using `T` SHALL return HTTP 401, for the entire remaining duration of `T`'s original expiry window.

### P8 — Audit Log Completeness
For any sequence of N successful mutating API operations (create/update student, create/cancel invoice, record transaction, trigger batch score, retrain), the count of audit log entries SHALL increase by exactly N. GET operations SHALL contribute 0 new entries.

### P9 — Ensemble Score Clamping
For any student where LR produces probability `p_lr ∈ [0.0, 1.0]` and DT produces `p_dt ∈ [0.0, 1.0]`:
- `final_score = max(p_lr, p_dt) × 100`
- `0.0 ≤ final_score ≤ 100.0` always holds

### P10 — Demo Seed Idempotence
Running the demo seed script twice on the same database SHALL produce an identical final count of `Student`, `Invoice`, `Transaction`, and `User` records as running it once. No duplicate records with the same unique key SHALL exist after the second execution.
