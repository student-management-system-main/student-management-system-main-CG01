# Feature Development Checklist

Use this checklist when adding a new feature to ensure nothing is missed.

## Pre-Development

- [ ] Feature name decided (e.g., "scholarships", "dormitories")
- [ ] Requirements documented
- [ ] Database schema designed
- [ ] API endpoints listed
- [ ] Frontend pages planned

## Backend Development

### 1. Database Model

- [ ] Create `backend/app/models/feature_name.py`
- [ ] Define all SQLAlchemy models with:
  - [ ] Primary key
  - [ ] All fields with proper types
  - [ ] Relationships to other models
  - [ ] Timestamps (created_at, updated_at)
  - [ ] `to_dict()` method for serialization
- [ ] Import in `backend/app/models/__init__.py`
- [ ] Run `python backend/init_db.py` to create tables

### 2. API Blueprint

- [ ] Create directory: `backend/app/feature_name/`
- [ ] Create `__init__.py` with Blueprint:
  ```python
  from flask import Blueprint
  feature_bp = Blueprint('feature', __name__, url_prefix='/api/v1/feature')
  from . import routes
  ```
- [ ] Create `routes.py` with endpoints:
  - [ ] GET / (list with pagination)
  - [ ] POST / (create)
  - [ ] GET /{id} (read)
  - [ ] PUT /{id} (update)
  - [ ] DELETE /{id} (delete)
- [ ] Add JWT authentication: `@jwt_required()`
- [ ] Add error handling for all routes
- [ ] Create `schemas.py` with validation (optional)
- [ ] Create `tasks.py` with async jobs (if needed)

### 3. Register Blueprint

- [ ] Add import in `backend/app/__init__.py`:
  ```python
  from app.feature_name import feature_bp
  ```
- [ ] Register blueprint:
  ```python
  app.register_blueprint(feature_bp)
  ```

### 4. Testing

- [ ] Test all CRUD endpoints with curl/Postman
- [ ] Test with invalid data
- [ ] Test authentication
- [ ] Test pagination
- [ ] Test error handling

## Frontend Development

### 1. API Client

- [ ] Update `frontend/src/api/client.js` if new base URLs needed
- [ ] Test API calls with `console.log()`

### 2. Create Page Component

- [ ] Create `frontend/src/pages/Feature.jsx` with:
  - [ ] State management (useState)
  - [ ] Data fetching (useEffect)
  - [ ] Loading state
  - [ ] Error handling
  - [ ] List display
  - [ ] Forms for create/update
- [ ] Add Tailwind CSS styling
- [ ] Test with mock data first

### 3. Add Navigation

- [ ] Add route in `frontend/src/App.jsx`:
  ```jsx
  <Route path="/feature" element={<ProtectedRoute><Feature /></ProtectedRoute>} />
  ```
- [ ] Add navigation link in `frontend/src/components/Layout.jsx`
- [ ] Test navigation works

### 4. Testing

- [ ] Test list page loads
- [ ] Test create form works
- [ ] Test edit form works
- [ ] Test delete works
- [ ] Test error handling
- [ ] Test mobile responsiveness

## ML/Risk Service (If Applicable)

- [ ] Add new features to `risk_service/features.py`
- [ ] Update feature extraction function
- [ ] Retrain model: `python risk_service/train.py`
- [ ] Test with new data
- [ ] Update model version in registry.json

## Documentation

- [ ] Document API endpoints
- [ ] Document database schema
- [ ] Document how to use feature
- [ ] Add examples to README/INTEGRATION_GUIDE
- [ ] Document any configuration changes

## Deployment

- [ ] Test complete flow end-to-end
- [ ] Run `test_full_integration.ps1`
- [ ] Check database migrations for production
- [ ] Update docker-compose if needed
- [ ] Document deployment steps

## Final Checklist

- [ ] All tests passing
- [ ] No console errors
- [ ] Database initialized
- [ ] Frontend pages working
- [ ] API endpoints responding
- [ ] Authentication working
- [ ] Error handling complete
- [ ] Documentation complete
- [ ] Ready for production

---

## Quick Verification

```bash
# 1. Test backend
curl http://localhost:5000/api/v1/feature/ \
  -H "Authorization: Bearer $TOKEN"

# 2. Check database
sqlite3 backend/fee_local.db "SELECT * FROM feature_table;"

# 3. Test frontend at
http://localhost:5173/feature

# 4. Run full test
powershell -ExecutionPolicy Bypass -File test_full_integration.ps1
```
