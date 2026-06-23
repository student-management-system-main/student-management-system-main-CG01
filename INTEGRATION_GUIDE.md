# Student Management System - Complete Integration Guide

## System overview

This is a fully integrated student fee management system with machine learning-based risk scoring, built with:
- **Backend**: Flask REST API (Python)
- **Risk Service**: ML-based scoring microservice (Flask + scikit-learn)
- **Frontend**: React + Vite (separate repo)
- **Database**: SQLite (local) / MySQL (production)
- **Task Queue**: Celery with in-memory broker (local) / Redis (production)

## Project Structure

```
student-management-system-main/
├── backend/                          # Flask REST API
│   ├── app/                          # Application code
│   │   ├── __init__.py              # App factory, JWT blocklist
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── auth/                    # Login, JWT tokens
│   │   ├── students/                # Student CRUD
│   │   ├── invoices/                # Invoice management
│   │   ├── transactions/            # Payment tracking
│   │   ├── risk/                    # Risk scoring endpoints
│   │   ├── fees/                    # Fee type management
│   │   ├── notifications/           # Email/SMS tasks
│   │   └── audit/                   # Audit logging
│   ├── migrations/                  # Alembic migrations
│   ├── tests/                       # Unit & integration tests
│   ├── wsgi.py                      # WSGI entry point
│   ├── config.py                    # Configuration (local/prod/test)
│   ├── init_db.py                   # Database initialization
│   ├── seed.py                      # Demo data seeding
│   ├── celery_config.py            # Celery Beat schedule
│   └── requirements.txt             # Python dependencies
│
├── risk_service/                    # ML Scoring Microservice
│   ├── app.py                       # Flask app
│   ├── config.py                    # Configuration
│   ├── score.py                     # Scoring logic
│   ├── train.py                     # Model training
│   ├── features.py                  # Feature extraction
│   ├── models/                      # Trained models & registry
│   │   ├── model_lr_v1.0.0.joblib  # Logistic Regression
│   │   ├── model_dt_v1.0.0.joblib  # Decision Tree
│   │   ├── scaler_v1.0.0.joblib    # Feature scaler
│   │   └── registry.json           # Model metadata
│   └── requirements.txt
│
└── frontend/                        # React Web UI
    ├── src/
    ├── package.json
    ├── vite.config.js
    └── tailwind.config.js
```

## Quick Start

### 1. Backend Setup (Already Done)

```bash
# Navigate to backend
cd backend

# Install dependencies
pip install -r requirements.txt

# Initialize database
python init_db.py

# Seed demo data
python seed.py

# Start server
FLASK_ENV=local python -m flask --app wsgi:app run --port 5000
```

**Backend runs on**: http://localhost:5000

### 2. Risk Service Setup (Already Done)

```bash
# Navigate to risk service
cd risk_service

# Install dependencies
pip install -r requirements.txt

# Start service
python app.py
```

**Risk Service runs on**: http://localhost:5001

### 3. Frontend Setup (Next Step)

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

**Frontend runs on**: http://localhost:5173

## API Endpoints Summary

### Authentication (http://localhost:5000/api/v1)

```
POST   /auth/login              - Login with username/password
POST   /auth/refresh            - Refresh access token
POST   /auth/logout             - Revoke token
```

**Login credentials** (from seed.py):
- admin1 / demo1234 (admin)
- admin2 / demo1234 (admin)
- staff1 / demo1234 (viewer)
- staff2 / demo1234 (viewer)

### Students

```
GET    /students/               - List students (paginated)
POST   /students/               - Create new student
GET    /students/{id}           - Get student details
PUT    /students/{id}           - Update student
PATCH  /students/{id}/deactivate - Deactivate student
```

**Example**: Get 50 students with pagination
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/v1/students/
```

### Financial Management

```
GET    /invoices/               - List invoices
POST   /invoices/               - Create invoice
GET    /invoices/{id}           - Get invoice details
PATCH  /invoices/{id}/pay       - Mark invoice as paid

GET    /fee-types/              - List fee types
POST   /fee-types/              - Create fee type

POST   /transactions/           - Record payment
GET    /transactions/           - List transactions
```

### Risk Management

```
GET    /risk/distribution       - Risk distribution stats
POST   /risk/score              - Score single student
POST   /risk/batch              - Score all students (async)
POST   /risk/retrain            - Retrain models

GET    /students/{id}/risk      - Get student's risk score
```

**Example**: Score a student
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"student_id": 1}' \
  http://localhost:5000/api/v1/risk/score
```

### System

```
GET    /system/health           - Health check
GET    /system/maintenance      - Maintenance window
```

## Data Flow

### Complete Student Lifecycle

```
1. STUDENT REGISTRATION
   POST /students → Create new student record

2. INVOICE GENERATION  
   POST /invoices → Create invoice for student
   - Links to fee types
   - Generates line items
   - Sets due date

3. PAYMENT COLLECTION
   POST /transactions → Record payment
   - Updates invoice status
   - Updates outstanding balance
   - Triggers audit log

4. RISK ASSESSMENT
   POST /risk/score → ML model scores student
   - Extracts features from student data
   - Runs Logistic Regression model
   - Runs Decision Tree model  
   - Returns ensemble score (max of both)
   - Categories: low (0-39), medium (40-69), high (70-100)
   - Stores in risk_scores table

5. NOTIFICATIONS
   Automatic triggers:
   - Invoice overdue: send_overdue_reminder
   - 7 days after overdue: send_7day_reminder
   - 30 days after overdue: send_30day_escalation
   - Risk escalation: admin_notification_task

6. REPORTING & ANALYTICS
   GET /reports/risk-summary → Risk distribution dashboard
   GET /reports/financial-summary → Financial overview
   GET /audit → Activity audit trail
```

## ML Model Details

### Risk Scoring Ensemble

**Active Models**: v1.0.0 (ROC-AUC: 0.8796)

**Model Files** (./risk_service/models/):
- `model_lr_v1.0.0.joblib` - Logistic Regression classifier
- `model_dt_v1.0.0.joblib` - Decision Tree classifier
- `scaler_v1.0.0.joblib` - Feature StandardScaler

**Features Extracted**:
- Student status
- Enrollment date
- Invoice count
- Outstanding balance
- Payment history
- Transaction patterns

**Scoring Algorithm**:
```python
lr_probability = model_lr.predict_proba(features)[1] * 100
dt_probability = model_dt.predict_proba(features)[1] * 100
final_score = max(lr_probability, dt_probability)

if final_score < 40: category = "low"
elif final_score < 70: category = "medium"  
else: category = "high"
```

**Retraining**:
```bash
# Trigger retraining via API
POST /retrain → Risk service retrains models

# Requirements for retraining
- Need at least 100 labeled samples
- Models compared on ROC-AUC
- Only deploy if improvement > baseline
```

## Database Schema

### Users Table
- id, username, email, password_hash
- role (admin | viewer)
- is_active, created_at, updated_at

### Students Table
- id, student_number, first_name, last_name, email, phone
- enrollment_date, status (active | inactive)
- assigned_admin_id, sms_enabled
- created_at, updated_at

### Invoices Table
- id, invoice_number, student_id
- total_amount, outstanding_balance
- status (unpaid | overdue | paid | cancelled)
- due_date, paid_at
- created_at, updated_at

### Transactions Table
- id, invoice_id, amount
- type (payment | reversal)
- reference, created_at

### RiskScores Table
- id, student_id, score (0-100)
- risk_category (low | medium | high)
- model_version, computed_at

### Additional Tables
- fee_types, invoice_line_items, logs, audit_logs

## Configuration

### Local Development (.env)

```env
# Backend
DATABASE_URL=sqlite:///fee_local.db
FLASK_ENV=local
SECRET_KEY=local-dev-secret-key-2025
JWT_SECRET_KEY=local-dev-jwt-secret-key-2025
JWT_ACCESS_TOKEN_EXPIRES=28800          # 8 hours
JWT_REFRESH_TOKEN_EXPIRES=604800        # 7 days
CELERY_BROKER_URL=memory://              # No Redis needed!
CELERY_RESULT_BACKEND=cache+memory://
CELERY_TASK_ALWAYS_EAGER=true            # Execute immediately
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
RISK_SERVICE_URL=http://localhost:5001

# Risk Service
DB_URL=sqlite:///../backend/fee_local.db
MODEL_DIR=./models
RISK_SERVICE_PORT=5001
```

### Production (Kubernetes/Docker)

```env
# Use Redis for broker
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Use MySQL for database
DATABASE_URL=mysql+pymysql://user:pass@mysql:3306/fee_management

# Secure keys
SECRET_KEY=<strong-random-key>
JWT_SECRET_KEY=<strong-random-key>

# HTTPS and security
CORS_ORIGINS=https://yourdomain.com
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
```

## Key Improvements Over Original

### 1. Removed Redis Dependency ✓
- JWT blocklist: In-memory set (local) or DB (production)
- Task reminders: In-memory dict (local) or Redis (production)
- Health check: Database-only

### 2. Simplified Celery Setup ✓
- Local dev: Uses in-memory broker (`memory://`)
- No Redis needed for local development
- Eager task execution (synchronous)

### 3. SQLite for Local Development ✓
- Easy setup: just `init_db.py`
- No external database server needed
- Same ORM (SQLAlchemy) works for both SQLite and MySQL

### 4. Relative Model Paths ✓
- Updated registry.json to use relative paths
- Works across different installations
- Portable model directory

## Testing & Validation

### Health Checks
```bash
# Backend health
curl http://localhost:5000/api/v1/system/health
# Response: {"status":"ok","dependencies":{"database":true}}

# Risk service health
curl http://localhost:5001/health
# Response: {"status":"ok"}
```

### Integration Test
```bash
#!/bin/bash

# 1. Login
TOKEN=$(curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin1","password":"demo1234"}' | jq -r '.data.access_token')

# 2. List students
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/v1/students/

# 3. Get invoices
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/v1/invoices/

# 4. Check risk distribution
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/v1/risk/distribution

# 5. Score a student
curl -X POST http://localhost:5000/api/v1/risk/score \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"student_id":1}'
```

## Troubleshooting

### Backend won't start
```
Error: "cannot import name '_jwt_blocklist'"
Fix: Restart Python interpreter - clear __pycache__
```

### Risk service can't find models
```
Error: "FileNotFoundError: model_lr_v1.0.0.joblib"
Fix: Update MODEL_DIR in .env to absolute path, or ensure relative path from risk_service/
```

### Token invalid
```
Error: "Bad Authorization header. Expected 'Authorization: Bearer '"
Fix: Include "Bearer " prefix in Authorization header
```

### Database locked
```
Error: "database is locked"
Fix: Only one process should access SQLite at a time. Close other connections.
```

## Next Steps

1. **Frontend Integration**
   - Set API base URL to http://localhost:5000/api/v1
   - Configure auth token storage (localStorage/sessionStorage)
   - Build dashboard, student list, invoice management UI

2. **Production Deployment**
   - Switch to MySQL database
   - Switch to Redis broker
   - Use Gunicorn + Nginx for backend
   - Deploy with Docker Compose or Kubernetes

3. **Advanced Features**
   - Batch risk scoring on schedule
   - Automated notifications (email/SMS)
   - Financial reports and analytics
   - Audit trail and compliance logging

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        React Frontend (5173)                 │
│                   ├─ Dashboard                               │
│                   ├─ Student Management                      │
│                   ├─ Invoice Management                      │
│                   └─ Risk Analytics                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS/JSON
┌──────────────────────▼──────────────────────────────────────┐
│             Flask REST API (Backend - 5000)                  │
│  ├─ /auth         - JWT Authentication                      │
│  ├─ /students     - Student CRUD                            │
│  ├─ /invoices     - Invoice Management                      │
│  ├─ /risk         - Risk Scoring                            │
│  ├─ /transactions - Payment Processing                      │
│  └─ /reports      - Analytics & Reporting                  │
└──────────────────────┬──────────────────────────────────────┘
         │             │              │
         │             │              │
    ┌────▼──┐    ┌────▼──┐     ┌────▼──┐
    │ Risk  │    │ Celery │    │SQLite │
    │Service│    │ Tasks  │    │   DB  │
    │(5001) │    │        │    │       │
    │       │    │ Timers │    │       │
    └────────┘    │Queues │    └───────┘
                  └────────┘

     ML Scoring   Async Jobs   Persistent
     Microservice  & Scheduling  Storage
```

## Files Modified for Redis Removal

### Backend
1. **app/__init__.py**
   - Replaced Redis JWT blocklist with `_jwt_blocklist` set()
   - Added `_task_reminders` dict for local dev
   - Updated Celery config for memory:// broker

2. **app/auth/routes.py**
   - Removed Redis import
   - Updated logout to use in-memory blocklist

3. **app/invoices/tasks.py**
   - Removed Redis import
   - Uses in-memory task registry

4. **app/notifications/tasks.py**
   - Removed Redis import
   - Updated suppress_reminders() for in-memory dict

5. **app/system/routes.py**
   - Made Redis health check optional
   - Database-only health check for local dev

6. **config.py**
   - LocalConfig uses in-memory Celery
   - ProductionConfig can still use Redis

## Performance Notes

- **Local Dev**: Fast response times, in-memory operations
- **Risk Scoring**: ~50-100ms per student (depends on features)
- **Batch Scoring**: All 50 students in ~5 seconds
- **Database**: SQLite suitable for dev/test, not production scale

---

**System Status**: ✓ FULLY OPERATIONAL
**Last Updated**: 2025-06-04
