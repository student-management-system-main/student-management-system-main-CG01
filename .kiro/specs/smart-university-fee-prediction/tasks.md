# Implementation Plan: Smart University Fee Prediction & Management System

## Overview

Implements the remaining gaps identified in the design document. Most of the backend (auth, students, invoices, transactions, reports, audit, notifications, risk service ML pipeline) is already built. This plan covers the missing API endpoints, frontend pages/enhancements, demo seed script, and property-based tests.

## Tasks

- [x] 1. Add GET /api/v1/dashboard/summary endpoint
  - Create `backend/app/dashboard/__init__.py`
  - Create `backend/app/dashboard/routes.py` with `GET /` handler querying Invoice and Student tables for `total_collected`, `total_outstanding`, `overdue_count`, `active_student_count`, and `forecast_30d` (sum of outstanding_balance for invoices due within next 30 calendar days)
  - Register `dashboard_bp` in `backend/app/__init__.py` at `/api/v1/dashboard`
  - Write unit tests in `backend/tests/test_dashboard_routes.py` covering the 5 KPI fields and the 30-day boundary
  - **Requirements**: 9.1

- [x] 2. Add GET /api/v1/risk/distribution endpoint
  - Add `GET /distribution` route to `backend/app/risk/routes.py` using a subquery to get each active student's latest RiskScore grouped by risk_category
  - Return `{"data": {"low_count": N, "medium_count": N, "high_count": N, "total": N}}`
  - Exclude students with no RiskScore from all counts
  - Write unit test verifying `low_count + medium_count + high_count == total`
  - **Requirements**: 6.11, 11.5

- [x] 3. Add POST /api/v1/risk/score and POST /api/v1/risk/retrain endpoints
  - Add `POST /score` route to `backend/app/risk/routes.py`: validate `student_id`, proxy to `RISK_SERVICE_URL/score`, write audit log, return result; return 503 if Risk Service is unreachable
  - Add `POST /retrain` route to `backend/app/risk/routes.py`: proxy to `RISK_SERVICE_URL/retrain`, write audit log, return result
  - Write unit tests for both endpoints including the 503 unreachable case
  - **Requirements**: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3

- [x] 4. Add GET /api/v1/system/health endpoint
  - Add `GET /health` route to `backend/app/system/routes.py`
  - Check database connectivity with `db.session.execute(text("SELECT 1"))`
  - Check Redis connectivity with `redis.from_url(REDIS_URL).ping()`
  - Return HTTP 200 `{"status": "ok"}` when both healthy; HTTP 503 `{"status": "degraded", "dependencies": {...}}` otherwise
  - **Requirements**: 15.1, 15.2

- [x] 5. Add risk_category filter and risk fields to GET /api/v1/students
  - Add `risk_category` query parameter to `backend/app/students/routes.py`; return 400 for invalid values
  - Join against a latest-score subquery to filter students by their most recent risk_category
  - Add `risk_category` and `score` fields (from latest RiskScore) to the `student_to_dict` serialiser, returning `null` when no score exists
  - **Requirements**: 3.6, 3.9

- [x] 6. Build RiskMonitoringPage frontend
  - Create `frontend/src/pages/RiskMonitoringPage.jsx`
  - Fetch student list from `GET /api/v1/students?per_page=200` and distribution from `GET /api/v1/risk/distribution`
  - Render a risk distribution chart (CSS/Tailwind bar chart) showing low/medium/high counts
  - Render a student risk table: Student Name, Risk Category badge, Score, Computed At, Overdue Count, Outstanding Balance; show "N/A" for unscored students
  - Add client-side filters: risk category dropdown and name search (case-insensitive on full name); both filters apply simultaneously
  - Add admin-only "Run Batch Scoring" button: calls `POST /api/v1/risk/batch`, disables + shows spinner while pending, refreshes table on completion
  - Add admin-only "Retrain Model" button: calls `POST /api/v1/risk/retrain`, shows loading state, displays result with new_roc_auc, current_roc_auc, and replaced status
  - Add `/risk` route to `frontend/src/App.jsx` and "Risk Monitoring" link to `frontend/src/components/Layout.jsx`
  - **Requirements**: 11.1, 11.2, 11.3, 11.4, 11.5, 9.3
  - **Depends on**: 2, 3

- [x] 7. Enhance DashboardPage with summary API and risk chart
  - Replace client-computed KPI values with data from `GET /api/v1/dashboard/summary`
  - Add `forecast_30d` display to the dashboard
  - Add a risk distribution chart section using `GET /api/v1/risk/distribution` data (reuse the chart from Task 6)
  - Add error handling for failed auto-refresh: retain stale data, show non-blocking error indicator, React Query retryDelay set to 10 seconds
  - **Requirements**: 9.1, 9.2, 9.3, 9.4, 9.5
  - **Depends on**: 1, 2

- [x] 8. Enhance StudentDetailPage with Rescore button and transaction history
  - Add "Rescore" button visible only to admin users (check `currentUser.role === 'admin'`): calls `POST /api/v1/risk/score` with `{student_id: id}`, shows spinner, invalidates risk query on success
  - Add transaction history section: fetch `GET /api/v1/transactions?student_id=:id&per_page=50`, render table with Transaction Ref, Amount, Payment Method, Type, Created At
  - Add "Student not found" error state: when student query returns 404, render error message with "Back to Dashboard" link
  - **Requirements**: 10.5, 10.4, 10.7
  - **Depends on**: 3

- [x] 9. Create demo dataset seed script
  - Create `backend/seed.py` with idempotent seeding logic
  - Create 4 users (2 admin, 2 staff) with password `demo1234` bcrypt-hashed at cost 4; skip if email exists
  - Create 3 fee types (Tuition 5000.00, Lab 800.00, Library 200.00); skip if name exists
  - Create 50 students with student_number format `STU-YYYY-NNNN`, enrollment dates spanning past 3 years, ~80% active; skip if student_number exists
  - Create 150+ invoices across all 4 statuses with due_dates spanning -12 to +3 months from today; skip if invoice_number exists
  - Create 100+ payment transactions and 10+ reversal transactions with realistic amounts; skip if transaction_ref exists
  - Ensure ≥10 students have varied payment histories (on-time, late, overdue) for ML training viability
  - Add CLI entry point: `python seed.py` from `backend/` directory
  - **Requirements**: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6

- [x] 10. Write property-based tests
  - Create `backend/tests/test_properties.py` with P3 (invoice balance invariant) and P8 (audit log completeness) using `hypothesis`
  - Create `risk_service/tests/test_properties.py` with P1 (classifier partition), P2 (feature vector invariants), P4 (version increment round-trip), and P9 (ensemble score clamping) using `hypothesis`
  - All property tests use `@settings(max_examples=200)` and are isolated (in-memory SQLite for DB-dependent tests)
  - **Requirements**: 6.4, 6.12, 4.9, 5.9, 7.6, 13.1

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": [1, 2, 3, 4, 5, 9, 10],
      "description": "All backend endpoints, seed script, and property tests — no dependencies"
    },
    {
      "wave": 2,
      "tasks": [6, 7, 8],
      "description": "Frontend pages — depend on wave 1 backend tasks",
      "dependencies": {
        "6": [2, 3],
        "7": [1, 2],
        "8": [3]
      }
    }
  ]
}
```

## Notes

- All new Flask routes must use `@viewer_or_admin_required` for read endpoints and `@admin_required` for write/trigger endpoints
- New blueprints must be imported lazily inside `_register_blueprints()` to avoid circular imports
- Frontend components must follow the existing Tailwind CSS class conventions (`card`, `btn-primary`, `badge`, `table-header`, `table-cell`, etc.) from `index.css`
- The seed script must use the `TestingConfig` bcrypt cost of 4 for speed, not the production cost of 12
- Property-based tests in the risk service must run against SQLite in-memory (not MySQL) using the `db_conn` fixture pattern already established in `risk_service/tests/`
