# Technical Design Document

## Overview

The Smart University Fee Prediction & Management System is a three-layer application:

- **Frontend** — React 18 SPA (Vite + TailwindCSS + React Query + React Router)
- **Backend API** — Flask REST API with SQLAlchemy, Celery, Redis, JWT auth
- **Risk Service** — Standalone Flask microservice running scikit-learn ML models

Most of the backend is already implemented. This document captures the complete architecture, documents what exists, and specifies what remains to be built: the `GET /api/v1/dashboard/summary` endpoint, the `GET /api/v1/risk/distribution` endpoint, the Risk Monitoring frontend page (`/risk`), enhancements to the Dashboard and Student Ledger pages, the demo dataset seed script, and property-based tests.

---

## Architecture

```
Browser
  │  React 18 SPA (Vite, TailwindCSS, React Query)
  │
  ▼ HTTPS / REST JSON
Flask API  (backend/  port 5000)
  │  JWT auth  │  Blueprints  │  SQLAlchemy ORM
  │  Celery tasks ──► Redis broker (port 6379)
  │
  ├── MySQL (port 3306)  ← single source of truth
  │
  └──► Risk Service  (risk_service/  port 5001)
         Flask app  │  scikit-learn models
         models/registry.json  │  joblib files
```

All services are containerised via `docker-compose.yml`. The API and Risk Service share the same MySQL instance. Redis is used for both the Celery broker/result-backend and the JWT blocklist.

---

## Database Schema

### Existing tables (already migrated)

| Table | Key columns |
|---|---|
| `users` | id, username, email, password_hash (bcrypt), role (admin/staff), is_active |
| `students` | id, student_number (unique), first_name, last_name, email, phone, enrollment_date, status (active/inactive), assigned_admin_id FK→users, sms_enabled |
| `fee_types` | id, name, amount, due_date |
| `invoices` | id, invoice_number (unique), student_id FK, total_amount, outstanding_balance, status (unpaid/overdue/paid/cancelled), due_date, paid_at |
| `invoice_line_items` | id, invoice_id FK, fee_type_id FK, amount |
| `transactions` | id, transaction_ref (unique), student_id FK, invoice_id FK, amount, payment_method, type (payment/reversal), reversal_of FK→transactions |
| `risk_scores` | id, student_id FK, score (Numeric 5,2), risk_category (low/medium/high), model_version, computed_at |
| `logs` | id, actor_id FK→users, resource_type, resource_id, action, channel, delivery_status, previous_values (JSON), new_values (JSON), created_at |

All financial amounts are `DECIMAL(12,2)`. Timestamps are `DATETIME` stored as UTC. No soft-deletes — the `logs` table is append-only by application convention.

---

## Backend API

### Base URL: `/api/v1`

All responses follow the envelope pattern:
- **Success**: `{"data": <payload>}`
- **Error**: `{"error": {"code": "ERROR_CODE", "message": "...", "details": {}}}`

### Authentication (`app/auth/routes.py`) — *already implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | None | Returns `access_token` + `refresh_token` |
| POST | `/auth/refresh` | refresh JWT | Returns new `access_token` |
| POST | `/auth/logout` | access JWT | Adds JTI to Redis blocklist |

JWT access token: 8 hours. Refresh token: 7 days. Stored in `Authorization: Bearer` header. Blocklist key: `blocklist:{jti}` in Redis with TTL = remaining token expiry.

### Students (`app/students/routes.py`) — *already implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/students` | viewer+ | Paginated list; filters: `status`, `assigned_admin_id` |
| POST | `/students` | admin | Create student; writes audit log |
| GET | `/students/:id` | viewer+ | Returns student + latest risk_category/score |
| PUT | `/students/:id` | admin | Partial update; writes audit log |
| PATCH | `/students/:id/deactivate` | admin | Set status=inactive; audit log |
| GET | `/students/:id/risk` | viewer+ | Latest RiskScore for student |

**Note**: The existing `GET /students` does not yet filter by `risk_category`. This filter needs to be added (join against latest `risk_scores` subquery).

### Invoices (`app/invoices/routes.py`) — *already implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/invoices` | viewer+ | Paginated; filters: `student_id`, `status`, `due_date_from`, `due_date_to` |
| POST | `/invoices` | admin | Create with line items; auto-generates `invoice_number` |
| GET | `/invoices/:id` | viewer+ | Invoice + line items |
| PATCH | `/invoices/:id` | admin | Cancel invoice (if no payments) |
| POST | `/invoices/:id/payments` | admin | Record payment against invoice |

### Transactions (`app/transactions/routes.py`) — *already implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/transactions` | viewer+ | Paginated; filters: `student_id`, `invoice_id`, `date_from`, `date_to` |
| POST | `/transactions` | admin | Record payment transaction |
| POST | `/transactions/:id/reverse` | admin | Reverse a prior payment |

### Risk (`app/risk/routes.py`) — *partial — needs new endpoints*

| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| POST | `/risk/batch` | admin | ✅ exists | Enqueue batch scoring Celery task |
| POST | `/risk/score` | admin | **⬜ missing** | Score single student via Risk Service |
| POST | `/risk/retrain` | admin | **⬜ missing** | Trigger model retraining via Risk Service |
| GET | `/risk/distribution` | viewer+ | **⬜ missing** | Risk category counts for active students |

#### `POST /api/v1/risk/score`
Proxies to `POST http://risk_service:5001/score`. Returns the Risk Service response. Writes an audit log entry.

#### `POST /api/v1/risk/retrain`
Proxies to `POST http://risk_service:5001/retrain`. Returns the retrain result. Writes an audit log entry.

#### `GET /api/v1/risk/distribution`
Query pattern:
```sql
SELECT rs.risk_category, COUNT(*) as count
FROM risk_scores rs
INNER JOIN (
  SELECT student_id, MAX(computed_at) as latest
  FROM risk_scores GROUP BY student_id
) latest ON rs.student_id = latest.student_id
       AND rs.computed_at = latest.latest
INNER JOIN students s ON s.id = rs.student_id
WHERE s.status = 'active'
GROUP BY rs.risk_category
```
Response: `{"data": {"low_count": N, "medium_count": N, "high_count": N, "total": N}}`

### Dashboard (`app/dashboard/routes.py`) — **⬜ missing — new blueprint**

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/dashboard/summary` | viewer+ | KPI summary for the dashboard |

#### `GET /api/v1/dashboard/summary`

```python
# total_collected = SUM(total_amount) WHERE status='paid'
# total_outstanding = SUM(outstanding_balance) WHERE status IN ('unpaid','overdue')
# overdue_count = COUNT(*) WHERE status='overdue'
# active_student_count = COUNT(*) FROM students WHERE status='active'
# forecast_30d = SUM(outstanding_balance) WHERE due_date BETWEEN today AND today+30d
```

Response shape:
```json
{
  "data": {
    "total_collected": "125000.00",
    "total_outstanding": "43500.00",
    "overdue_count": 12,
    "active_student_count": 87,
    "forecast_30d": "18200.00"
  }
}
```

New file: `backend/app/dashboard/routes.py`, registered at `/api/v1/dashboard`.

### Reports (`app/reports/routes.py`) — *already implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/reports` | viewer+ | Generate report (fee_collection / high_risk_students) |
| GET | `/reports/:id/export` | viewer+ | Export CSV or PDF; expires after 1 hour |

### Audit (`app/audit/routes.py`) — *already implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/audit` | viewer+ | Paginated audit log; filters: `resource_type`, `action`, `actor_id` |

### System (`app/system/routes.py`) — *partially implemented*

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/system/maintenance` | None | Returns maintenance window if configured |
| GET | `/system/health` | None | **⬜ missing** — DB + Redis liveness check |

#### `GET /api/v1/system/health`
Checks `db.session.execute(text("SELECT 1"))` and `redis.ping()`. Returns `{"status": "ok"}` on success, `{"status": "degraded", "dependencies": {...}}` with 503 on failure.

---

## Risk Service API

### Base URL: `http://risk_service:5001`

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/score` | Score a single student |
| POST | `/score/batch` | Score all active students |
| POST | `/retrain` | Trigger model retraining |

### Scoring logic (`risk_service/score.py`) — *already implemented*

1. Load `lr_model`, `dt_model`, `scaler` from `models/registry.json`
2. Call `extract_features(student_id, db_conn)` → `ndarray(7,)`
3. Scale: `X_scaled = scaler.transform(features.reshape(1, -1))`
4. Get probabilities: `p_lr = lr_model.predict_proba(X_scaled)[0][1]`, `p_dt = ...`
5. Ensemble: `final_score = max(p_lr * 100, p_dt * 100)` clamped to `[0, 100]`
6. Classify: `[0,39]→low`, `[40,69]→medium`, `[70,100]→high`
7. Insert into `risk_scores` table

### Feature extraction (`risk_service/features.py`) — *already implemented*

7 features extracted per student via SQL queries:

| Index | Feature | SQL source |
|---|---|---|
| 0 | `payment_history_ratio` | COUNT(*) with on-time flag / total invoices |
| 1 | `overdue_invoice_count` | COUNT WHERE status='overdue' |
| 2 | `total_outstanding_balance` | SUM(outstanding_balance) WHERE status≠'cancelled' |
| 3 | `enrollment_duration_days` | TODAY - enrollment_date |
| 4 | `historical_default_rate` | defaulted invoices / total |
| 5 | `avg_days_to_pay` | AVG(DATEDIFF(paid_at, due_date)) |
| 6 | `partial_payment_count` | invoices with payment txn but balance > 0 |

All features default to `0.0` when no historical data exists.

### Model training (`risk_service/train.py`) — *already implemented*

Pipeline:
1. Extract (X, y) for all students — label=1 if any overdue/late-paid invoice
2. Stratified 80/20 split (`random_state=42`)
3. `StandardScaler` fit on train, applied to both splits
4. Train `LogisticRegression(C=1.0, max_iter=1000)` + `DecisionTreeClassifier(max_depth=8)`
5. 5-fold cross-validated ROC-AUC (average of both models)
6. Replace active model only if new ROC-AUC > current
7. Save models as `models/model_lr_{version}.joblib`, `models/model_dt_{version}.joblib`, `models/scaler_{version}.joblib`
8. Update `models/registry.json`

Version scheme: `vMAJOR.MINOR.PATCH` starting at `v1.0.0`, patch incremented on each replacement.

---

## Celery Tasks

All tasks run in a Flask application context via `ContextTask`. Broker and result backend: Redis.

| Task | Module | Trigger | Retries |
|---|---|---|---|
| `risk_score_task(student_id)` | `app/risk/tasks.py` | After payment; after batch score | 5× 60s backoff |
| `batch_risk_scoring_task()` | `app/risk/tasks.py` | `POST /risk/batch`; nightly cron | none |
| `send_overdue_reminder(invoice_id)` | `app/notifications/tasks.py` | Invoice goes overdue | 3× exponential |
| `send_7day_reminder(invoice_id)` | `app/notifications/tasks.py` | Celery Beat schedule | 3× exponential |
| `send_30day_escalation(invoice_id)` | `app/notifications/tasks.py` | Celery Beat schedule | 3× exponential |
| `suppress_reminders(invoice_id)` | `app/notifications/tasks.py` | Invoice paid/cancelled | none |
| `admin_notification_task(student_id, category)` | `app/notifications/tasks.py` | Risk escalation detected | none |
| `retry_failed_notification(log_id)` | `app/notifications/tasks.py` | Manual / scheduled | 3× 2/4/8 min |

Notification retry backoff: 2 min, 4 min, 8 min (exponential). After 3 failures the `logs` entry is updated to `delivery_status="failed"`.

---

## Frontend

### Technology stack
- React 18 with JSX
- Vite 5 (dev server + build)
- TailwindCSS 3 (utility classes, custom `card`, `btn-primary`, `badge`, `table-*` classes in `index.css`)
- React Query 5 (`@tanstack/react-query`) for server state, caching, and auto-refetch
- React Router 6 for client-side routing
- Axios for HTTP (interceptors add `Authorization: Bearer` header automatically)

### Routing (App.jsx) — *already implemented*

| Route | Component | Status |
|---|---|---|
| `/login` | `LoginPage` | ✅ exists |
| `/` | `DashboardPage` | ✅ exists (needs enhancements) |
| `/students/:id` | `StudentDetailPage` | ✅ exists (needs enhancements) |
| `/invoices` | `InvoicesPage` | ✅ exists |
| `/transactions` | `TransactionsPage` | ✅ exists |
| `/reports` | `ReportsPage` | ✅ exists |
| `/audit-log` | `AuditLogPage` | ✅ exists |
| `/risk` | `RiskMonitoringPage` | **⬜ missing** |

### Auth flow
JWT is stored in React state only (not localStorage). On page refresh the user must log in again. The `AuthContext` registers a `logout` callback with the Axios client module. A 401 response from any protected endpoint triggers automatic logout.

### DashboardPage (`/`) — *exists, needs enhancements*

**Currently implemented:**
- 4 KPI stat cards (computed client-side from raw invoices/students queries)
- Student table with name, student number, outstanding balance, overdue count, risk badge, status
- Name search + risk category filter (client-side)
- 60-second auto-refetch via React Query `refetchInterval`
- Click row → navigate to `/students/:id`

**Enhancements needed:**
1. Switch KPI data source from client-computed to `GET /api/v1/dashboard/summary` (includes server-computed `forecast_30d`)
2. Add a risk distribution chart (bar or donut) using `GET /api/v1/risk/distribution`
3. Add error indicator when auto-refresh fails (retain stale data, show non-blocking toast)
4. Add `RiskMonitoringPage` link in the `Layout` navigation

### StudentDetailPage (`/students/:id`) — *exists, needs enhancements*

**Currently implemented:**
- Student contact info, status badge, enrollment date, SMS preference
- Risk badge + numeric score + progress bar + model version + computed_at
- Invoice table (invoice number, total, outstanding, status, due date, paid at)
- "Not yet scored" placeholder when no RiskScore exists

**Enhancements needed:**
1. Add "Rescore" button (admin only, calls `POST /api/v1/risk/score`, shows spinner, refreshes risk panel)
2. Add transaction history table (transaction ref, amount, payment method, type, created at) via `GET /api/v1/transactions?student_id=:id`
3. Add "Student not found" error state when API returns 404

### RiskMonitoringPage (`/risk`) — **⬜ new page**

New file: `frontend/src/pages/RiskMonitoringPage.jsx`

**Components and behaviour:**

```
┌─────────────────────────────────────────────────────────────┐
│  Risk Monitoring                                             │
│  ┌──────────────┐  ┌───────────────────────────────────┐   │
│  │ Distribution │  │  Search + Risk Filter              │   │
│  │ chart (donut)│  │  [Run Batch Scoring] [Retrain Model]│   │
│  └──────────────┘  └───────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Student | Risk | Score | Computed At | Overdue | Bal │  │
│  │ ...                                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

Data sources:
- Student risk data: `GET /api/v1/students?per_page=200` joined with risk data
- Distribution chart: `GET /api/v1/risk/distribution`
- Run Batch Scoring: `POST /api/v1/risk/batch` → button disabled + spinner while pending
- Retrain Model: `POST /api/v1/risk/retrain` → shows modal/inline result with `new_roc_auc`, `current_roc_auc`, `replaced`

Filtering: client-side by `risk_category` and student name (case-insensitive partial match on full name).

Students with no score show `"N/A"` for score fields.

### ReportsPage (`/reports`) — *already implemented*

Filter form (report_type, date_from, date_to, invoice_status, risk_category) + Generate button + CSV/PDF download buttons. Table preview of generated records. No changes needed.

---

## Demo Dataset Seed Script

**New file**: `backend/seed.py`

Creates deterministic synthetic data for demonstration purposes. Designed to be idempotent — uses `INSERT OR IGNORE` / `get_or_create` patterns keyed on unique constraints.

**Minimum data volumes:**
- 4 users: 2 admin (`admin1@demo.com`, `admin2@demo.com`), 2 staff (`staff1@demo.com`, `staff2@demo.com`). Password: `demo1234` (bcrypt-hashed at cost 4).
- 50 students with realistic Sri Lankan names, unique `student_number` in format `STU-YYYY-NNNN`, enrollment dates spread over 3 years, ~80% active / 20% inactive.
- 3 fee types: Tuition Fee (5000.00), Lab Fee (800.00), Library Fee (200.00)
- 150+ invoices: ~40% paid, ~25% overdue, ~25% unpaid, ~10% cancelled. Due dates spread across -12 to +3 months from today.
- 100+ payment transactions covering the paid and partially-paid invoices
- 10+ reversal transactions on a subset of paid invoices

**Idempotency**: Before inserting each entity, check by its unique key (student_number, email, invoice_number, transaction_ref). Skip if already exists.

**ML readiness**: The seed data produces ≥10 students with varied payment histories (mix of on-time, overdue, late payments) so that `POST /retrain` can train and register a model.

Run command: `cd backend && python seed.py`

---

## Property-Based Tests

Tests use `hypothesis` (Python) for backend and are located in:
- `backend/tests/test_properties.py` — invoice balance invariant, token revocation, audit log completeness
- `risk_service/tests/test_properties.py` — classifier partition, feature vector invariants, version increment, ensemble score clamping

### Key strategies

**P1 — Classifier partition** (`test_properties.py` in risk_service):
```python
@given(st.floats(min_value=0.0, max_value=100.0))
def test_classify_risk_partition(score):
    result = classify_risk(score)
    assert result in ("low", "medium", "high")
    if score <= 39: assert result == "low"
    elif score <= 69: assert result == "medium"
    else: assert result == "high"
```

**P3 — Invoice balance invariant** (`test_properties.py` in backend):
```python
@given(
    total=st.decimals(min_value="0.01", max_value="99999.99"),
    payments=st.lists(st.decimals(min_value="0.01", max_value="1000"), max_size=10),
)
def test_balance_invariant(total, payments, app):
    # Create invoice, apply payments sequentially, assert balance = total - sum(payments)
```

**P4 — Version increment**:
```python
@given(major=st.integers(0,99), minor=st.integers(0,99), patch=st.integers(0,999))
def test_increment_patch_round_trip(major, minor, patch):
    v = f"v{major}.{minor}.{patch}"
    result = _increment_patch(v)
    assert result == f"v{major}.{minor}.{patch+1}"
```

**P9 — Ensemble score clamping**:
```python
@given(p_lr=st.floats(0.0, 1.0), p_dt=st.floats(0.0, 1.0))
def test_ensemble_score_clamped(p_lr, p_dt):
    score = max(p_lr * 100, p_dt * 100)
    score = max(0.0, min(100.0, score))
    assert 0.0 <= score <= 100.0
```

---

## Security Design

| Concern | Mechanism |
|---|---|
| Password storage | bcrypt, cost ≥12 prod, ≥4 test |
| Token transport | `Authorization: Bearer` header only (no cookies for access tokens) |
| Token revocation | Redis blocklist keyed by JTI; TTL = remaining expiry |
| CORS | Restricted to `CORS_ORIGINS` env var in production; `*` in dev |
| SQL injection | SQLAlchemy ORM + parameterised `text()` queries only |
| Financial race conditions | `SELECT ... FOR UPDATE` on invoice row before balance update |
| Error leakage | Global 500 handler returns generic message; no stack traces |
| Role enforcement | `@admin_required` / `@viewer_or_admin_required` decorators on every route |

---

## Configuration

All configuration is read from environment variables. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:password@localhost/fee_management` | MySQL connection |
| `JWT_SECRET_KEY` | `change-jwt-secret` | JWT signing key |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `RISK_SERVICE_URL` | `http://risk_service:5001` | Risk service base URL |
| `CELERY_BROKER_URL` | same as REDIS_URL | Celery message broker |
| `BATCH_SCORE_CRON` | `0 0 * * *` | Nightly batch scoring schedule |
| `MAINTENANCE_START` | None | ISO 8601 maintenance window start |
| `MAINTENANCE_END` | None | ISO 8601 maintenance window end |
| `BCRYPT_LOG_ROUNDS` | 12 (prod) / 4 (test/dev) | Password hashing cost |

Testing config uses `sqlite:///:memory:`, `CELERY_TASK_ALWAYS_EAGER=True`, and `BCRYPT_LOG_ROUNDS=4`.

---

## Components and Interfaces

### Backend Components

#### `app/__init__.py` — Application Factory
- `create_app(config_name)` → `Flask` — initialises all extensions, registers blueprints
- Extensions: `db` (SQLAlchemy), `migrate` (Flask-Migrate), `jwt` (Flask-JWT-Extended), `cors` (Flask-CORS), `celery` (Celery)
- Blueprints registered at `/api/v1`: `auth_bp`, `students_bp`, `fees_bp`, `invoices_bp`, `transactions_bp`, `reports_bp`, `audit_bp`, `risk_bp`, `system_bp`, **`dashboard_bp`** (new)

#### `app/dashboard/routes.py` — **New**
- `dashboard_bp = Blueprint("dashboard", __name__)`
- `GET /` → `get_summary()` — queries Invoice and Student tables, returns KPI dict
- Registered at `/api/v1/dashboard`

#### `app/risk/routes.py` — Extended
- `POST /score` → `score_student_endpoint()` — proxies to Risk Service `POST /score`; audit log entry
- `POST /retrain` → `retrain_model()` — proxies to Risk Service `POST /retrain`; audit log entry
- `GET /distribution` → `get_risk_distribution()` — SQL aggregation query

#### `app/system/routes.py` — Extended
- `GET /health` → `health_check()` — pings DB and Redis; returns `{"status": "ok"}` or 503

#### `app/auth/decorators.py` — *already implemented*
- `@admin_required` — verifies JWT + `role == "admin"`
- `@viewer_or_admin_required` — verifies JWT + `role in ("admin", "staff")`
- `get_current_user_id()` → `int | None` — extracts user id from JWT identity

#### `app/audit/helpers.py` — *already implemented*
- `write_audit_log(actor_id, resource_type, resource_id, action, previous_values, new_values)` — inserts a `Log` row

#### Risk Service Components

| Module | Interface |
|---|---|
| `risk_service/app.py` | `create_app() → Flask`; routes: `/health`, `/score`, `/score/batch`, `/retrain` |
| `risk_service/features.py` | `extract_features(student_id, db_conn) → np.ndarray(7,)` |
| `risk_service/score.py` | `score_student(student_id, db_conn) → dict`; `classify_risk(score) → str` |
| `risk_service/train.py` | `train_models(db_conn) → dict`; `load_active_models() → (lr, dt, scaler, version)` |

#### Frontend Components

| Component | File | Purpose |
|---|---|---|
| `AuthProvider` | `context/AuthContext.jsx` | JWT state, login/logout, token memory storage |
| `ProtectedRoute` | `components/ProtectedRoute.jsx` | Redirect to /login if unauthenticated |
| `Layout` | `components/Layout.jsx` | Sidebar nav + page wrapper |
| `Spinner` | `components/Spinner.jsx` | Loading indicator |
| `ErrorAlert` | `components/ErrorAlert.jsx` | Error message display |
| `StatusBadge` | `components/StatusBadge.jsx` | Invoice status badge; `RiskBadge` for risk category |
| `apiClient` | `api/client.js` | Axios instance; attaches `Authorization` header; 401 → logout |

**New components needed:**
- `RiskMonitoringPage` — `pages/RiskMonitoringPage.jsx`
- `RiskDistributionChart` — inline in `DashboardPage` or `RiskMonitoringPage` (SVG bar or CSS donut using Tailwind)

---

## Data Models

### ORM Models (SQLAlchemy)

#### `Student` (`app/models/student.py`)
```
id              Integer PK
student_number  String(50) UNIQUE NOT NULL
first_name      String(100) NOT NULL
last_name       String(100) NOT NULL
email           String(255) NOT NULL
phone           String(30) nullable
enrollment_date Date NOT NULL
status          Enum('active','inactive') DEFAULT 'active'
assigned_admin_id Integer FK→users nullable
sms_enabled     Boolean DEFAULT False
created_at      DateTime server_default=NOW()
updated_at      DateTime onupdate=NOW()
```

#### `Invoice` (`app/models/invoice.py`)
```
id                  Integer PK
invoice_number      String(50) UNIQUE NOT NULL
student_id          Integer FK→students RESTRICT
total_amount        Numeric(12,2) NOT NULL
outstanding_balance Numeric(12,2) NOT NULL
status              Enum('unpaid','overdue','paid','cancelled') DEFAULT 'unpaid'
due_date            Date NOT NULL
paid_at             DateTime nullable
created_at / updated_at  DateTime
```

Invariant: `outstanding_balance = total_amount - SUM(payments) + SUM(reversals)` enforced at the application layer on every transaction.

#### `Transaction` (`app/models/transaction.py`)
```
id              Integer PK
transaction_ref String(50) UNIQUE NOT NULL  (format: TXN-YYYYMMDD-NNNNNN)
student_id      Integer FK→students
invoice_id      Integer FK→invoices
amount          Numeric(12,2) NOT NULL
payment_method  String(50) NOT NULL
type            Enum('payment','reversal')
reversal_of     Integer FK→transactions nullable
created_at      DateTime server_default=NOW()
```

Immutable — no UPDATE/DELETE routes exist on the transactions blueprint.

#### `RiskScore` (`app/models/risk_score.py`)
```
id             Integer PK
student_id     Integer FK→students CASCADE
score          Numeric(5,2) NOT NULL   [0.00 – 100.00]
risk_category  Enum('low','medium','high')
model_version  String(50) NOT NULL
computed_at    DateTime server_default=NOW()
```

New row on every scoring run. Latest = `ORDER BY computed_at DESC LIMIT 1`.

#### `Log` (`app/models/log.py`)
```
id              Integer PK
actor_id        Integer FK→users nullable
resource_type   String(50)
resource_id     Integer nullable
action          String(50)
channel         String(10) nullable  ('email','sms')
delivery_status String(10) nullable  ('sent','failed','pending')
previous_values JSON nullable
new_values      JSON nullable
created_at      DateTime server_default=NOW()
```

Append-only — no UPDATE/DELETE permitted from application layer.

### Registry (`risk_service/models/registry.json`)
```json
{
  "active_lr":      "…/models/model_lr_v1.0.0.joblib",
  "active_dt":      "…/models/model_dt_v1.0.0.joblib",
  "active_scaler":  "…/models/scaler_v1.0.0.joblib",
  "version":        "v1.0.0",
  "current_roc_auc": 0.82,
  "trained_at":     "2025-01-15T00:00:00Z"
}
```

---

## Correctness Properties

### Property 1: Risk Classifier Partition
`classify_risk(s)` is total and deterministic on `[0, 100]`:
- `s ∈ [0.0, 39.0]` → `"low"`; `s ∈ [40.0, 69.0]` → `"medium"`; `s ∈ [70.0, 100.0]` → `"high"`
- Scores outside `[0, 100]` raise `ValueError`
- Implemented as a pure function with no side effects

**Validates: Requirements 6.4**

### Property 2: Feature Vector Shape Invariant
`extract_features(student_id, conn)` → shape `(7,)`, `dtype=float64`, all non-negative; ratios ∈ `[0, 1]`

**Validates: Requirements 6.12, 6.13**

### Property 3: Invoice Balance Invariant
After any sequence of payment and reversal transactions:
`invoice.outstanding_balance == invoice.total_amount - SUM(t.amount for t in payments) + SUM(t.amount for t in reversals)`

**Validates: Requirements 4.9, 5.9**

### Property 4: Version Increment Homomorphism
`_increment_patch("vX.Y.Z") == f"vX.Y.{Z+1}"` for all non-negative X, Y, Z.
Composability: applying N times yields patch = Z + N.

**Validates: Requirements 7.5, 7.6**

### Property 5: Report Filter Monotonicity
`len(records(type, filters)) ≤ len(records(type, {}))` for all valid filter combinations.

**Validates: Requirements 12.5**

### Property 6: Risk Distribution Additivity
`low_count + medium_count + high_count == total` where total = active students with ≥1 risk score.

**Validates: Requirements 6.11, 11.5**

### Property 7: Token Revocation Irreversibility
A revoked JTI always returns 401 until token natural expiry.

**Validates: Requirements 1.6**

### Property 8: Audit Log Completeness
Every successful mutating operation appends exactly 1 audit log row.

**Validates: Requirements 13.1, 13.5**

### Property 9: Ensemble Score Clamping
`0.0 ≤ max(p_lr, p_dt) * 100 ≤ 100.0` for all `p_lr, p_dt ∈ [0, 1]`.

**Validates: Requirements 6.1**

### Property 10: Seed Idempotence
Running seed script twice produces identical record counts (no duplicates on unique keys).

**Validates: Requirements 14.5**

---

## Error Handling

### HTTP Error Envelope
All error responses use the standard envelope:
```json
{"error": {"code": "ERROR_CODE", "message": "Human-readable message", "details": {}}}
```

### Error code mapping

| HTTP | Code | Trigger |
|---|---|---|
| 400 | `BAD_REQUEST` | Malformed request, invalid params |
| 400 | `VALIDATION_ERROR` | Schema validation failure (includes field-level `details`) |
| 401 | `UNAUTHORIZED` | Missing, expired, revoked, or invalid JWT |
| 403 | `FORBIDDEN` | Valid JWT but insufficient role |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Duplicate unique key (student_number, invoice_number) |
| 422 | `UNPROCESSABLE_ENTITY` | Semantically invalid operation (overpayment, cancel paid invoice) |
| 500 | `INTERNAL_ERROR` | Unhandled exception — no internal detail exposed |
| 503 | `SERVICE_UNAVAILABLE` | Maintenance window or health check failure |

### Frontend error handling
- React Query `onError` callbacks surface errors via `<ErrorAlert>` component
- Auto-refresh failures (Req 9): retain stale data, show non-blocking toast, retry after 10 s
- 401 response: Axios interceptor clears token, redirects to `/login`
- 404 on student page: renders "Student not found" with back-to-dashboard link

### Risk Service error handling
- Student not found: 404 `NOT_FOUND`
- Inactive student: 400 `VALIDATION_ERROR`
- Model not trained (`FileNotFoundError`/`ValueError`): returns stub score `{score: 0.0, risk_category: "low", model_version: "none"}`

---

## Testing Strategy

### Backend (pytest + hypothesis)

**Location**: `backend/tests/`

| Test file | Coverage |
|---|---|
| `test_auth_routes.py` | Login success/failure, refresh, logout, blocklist |
| `test_audit_routes.py` | Pagination, filters, append-only enforcement |
| `test_properties.py` | P3 (balance invariant), P7 (token revocation), P8 (audit log completeness) |

**Test config**: `TestingConfig` — SQLite in-memory, `CELERY_TASK_ALWAYS_EAGER=True`, `BCRYPT_LOG_ROUNDS=4`

### Risk Service (pytest + hypothesis)

**Location**: `risk_service/tests/`

| Test file | Coverage |
|---|---|
| `test_features.py` | Feature extraction SQL logic, edge cases (no invoices, no transactions) |
| `test_score.py` | Scoring pipeline, stub fallback when no model, score clamping |
| `test_train.py` | Training pipeline, version increment, registry update guard |
| `test_properties.py` | P1 (classifier), P2 (feature vector), P4 (version increment), P9 (ensemble clamping) |

### Property-based test approach
All property tests use `hypothesis` with `@given` + `@settings(max_examples=200)`. Database-dependent tests use an in-memory SQLite fixture. Pure function tests (classifier, version increment) require no database.

### Integration smoke tests
Run against `docker-compose up` in CI:
1. Seed database (`python seed.py`)
2. `POST /retrain` → assert `replaced=true`
3. `POST /score` for student_id=1 → assert `risk_category ∈ {low, medium, high}`
4. `GET /api/v1/dashboard/summary` → assert all 5 KPI fields present
5. `GET /api/v1/risk/distribution` → assert `low+medium+high == total`
