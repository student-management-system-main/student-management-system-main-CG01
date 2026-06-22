# 🎓 Student Management System - Quick Start

## System Status: ✅ FULLY OPERATIONAL

All services are running and tested. The system is ready to use!

## 🚀 Quick Start (30 seconds)

### 1️⃣ Backend & Risk Service (Already Running)

```bash
# Backend API
http://localhost:5000/api/v1

# Risk Service (ML Scoring)
http://localhost:5001
```

### 2️⃣ Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser

### 3️⃣ Login

Use any of these credentials:
- **Username**: `admin1` **Password**: `demo1234`
- **Username**: `staff1` **Password**: `demo1234`

## 📊 What's Included

✅ **Backend API** - 50+ endpoints  
✅ **SQLite Database** - Local development ready  
✅ **ML Risk Scoring** - Student risk assessment  
✅ **Authentication** - JWT tokens  
✅ **Demo Data** - 50 students, 150 invoices  
✅ **Celery Tasks** - Async notifications  

## 📚 Documentation

- **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** - Complete system guide (API, models, architecture)
- **[test_full_integration.ps1](./test_full_integration.ps1)** - End-to-end test script

## 🔍 Test All Systems

```bash
# PowerShell (Windows)
powershell -ExecutionPolicy Bypass -File test_full_integration.ps1

# Or manually test key endpoints
curl http://localhost:5000/api/v1/system/health
curl http://localhost:5001/health
```

## 💻 Key Endpoints

### Authentication
```
POST   /api/v1/auth/login         - Login
POST   /api/v1/auth/refresh       - Refresh token
POST   /api/v1/auth/logout        - Logout
```

### Students
```
GET    /api/v1/students/          - List students
POST   /api/v1/students/          - Create student
GET    /api/v1/students/{id}      - Get student
```

### Financial
```
GET    /api/v1/invoices/          - List invoices
POST   /api/v1/transactions/      - Record payment
GET    /api/v1/fee-types/         - Fee types
```

### Risk & Analytics
```
GET    /api/v1/risk/distribution  - Risk stats
POST   /api/v1/risk/score         - Score student
GET    /api/v1/system/health      - Health check
```

## 🛠️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Frontend (React + Vite)                     │
│                   http://localhost:5173                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│               Backend (Flask REST API)                       │
│                  http://localhost:5000                       │
├─────────────────────┬─────────────────────┬─────────────────┤
│  Database           │  Risk Service       │  Celery Tasks   │
│  (SQLite)           │  (ML Models)        │  (Async)        │
│  fee_local.db       │  Port 5001          │  In-Memory      │
└─────────────────────┴─────────────────────┴─────────────────┘
```

## 📱 Test Data Available

**Students**: 50 active students with enrollment dates  
**Invoices**: 150 invoices (paid, unpaid, overdue)  
**Transactions**: 82 payment records  
**Users**: 4 demo users (2 admin, 2 staff)

## ⚙️ Configuration

### Local Development (Already Set)
- Database: SQLite (no setup needed)
- Broker: In-memory (no Redis needed)
- Models: Loaded from ./risk_service/models/

### For Production
See [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md#production-kubernetes-deployment) for:
- MySQL database setup
- Redis broker configuration
- Docker & Kubernetes deployment

## 🐛 Troubleshooting

### Services won't start?
```bash
# Check Python dependencies
pip list | grep Flask

# Reinitialize database
python backend/init_db.py

# Check ports are available
netstat -ano | findstr :5000
```

### Frontend can't connect?
```
# Verify backend running: http://localhost:5000/api/v1/system/health
# Check frontend .env for API base URL
# Should be: VITE_API_BASE_URL=http://localhost:5000/api/v1
```

### Risk service not scoring?
```
# Check it's running: http://localhost:5001/health
# Verify models exist: risk_service/models/
# Check logs for errors
```

## 📖 Complete Documentation

For detailed information on:
- Complete API reference
- ML model details  
- Data flow architecture
- Configuration options
- Production deployment
- Error troubleshooting

→ See **[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)**

## 🎯 What to Try First

1. ✅ Open frontend at http://localhost:5173
2. ✅ Login with admin1 / demo1234
3. ✅ View the dashboard with 50 students
4. ✅ Check invoices and transactions
5. ✅ View risk distribution statistics
6. ✅ Score a student using ML model

## 📞 System Status

**Overall Status**: ✅ **OPERATIONAL**

- Backend API: ✅ Running
- Risk Service: ✅ Running  
- Database: ✅ Initialized
- Demo Data: ✅ Loaded
- Authentication: ✅ Working
- ML Scoring: ✅ Active

---

**Happy coding! 🚀**

For questions, see [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)
