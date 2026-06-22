# 🚀 Adding New Features to Student Management System

This guide shows how to extend the system with new features following the existing patterns and architecture.

## Quick Navigation

- [Adding Backend Endpoints](#adding-backend-endpoints)
- [Adding Database Models](#adding-database-models)
- [Adding Frontend Pages](#adding-frontend-pages)
- [Extending ML Features](#extending-ml-features)
- [Common Patterns](#common-patterns)
- [Example: Complete Feature](#example-complete-feature)

---

## Adding Backend Endpoints

### Step 1: Create a Blueprint Module

Backend uses Flask blueprints for modular endpoints. Create a new module in `app/`:

**File**: `backend/app/scholarships/__init__.py`
```python
from flask import Blueprint

scholarships_bp = Blueprint(
    'scholarships',
    __name__,
    url_prefix='/api/v1/scholarships'
)

from . import routes  # Import routes to register them
```

### Step 2: Add Routes

**File**: `backend/app/scholarships/routes.py`
```python
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Student, Scholarship
from . import scholarships_bp

@scholarships_bp.route('/', methods=['GET'])
@jwt_required()
def list_scholarships():
    """Get all scholarships with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    scholarships = Scholarship.query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return jsonify({
        'status': 'success',
        'data': {
            'scholarships': [s.to_dict() for s in scholarships.items],
            'total': scholarships.total,
            'pages': scholarships.pages,
            'current_page': page
        }
    }), 200

@scholarships_bp.route('/<int:scholarship_id>', methods=['GET'])
@jwt_required()
def get_scholarship(scholarship_id):
    """Get scholarship by ID"""
    scholarship = Scholarship.query.get(scholarship_id)
    
    if not scholarship:
        return jsonify({'status': 'error', 'message': 'Scholarship not found'}), 404
    
    return jsonify({
        'status': 'success',
        'data': scholarship.to_dict()
    }), 200

@scholarships_bp.route('/', methods=['POST'])
@jwt_required()
def create_scholarship():
    """Create new scholarship"""
    data = request.get_json()
    
    # Validate required fields
    required = ['name', 'amount', 'eligibility_criteria']
    if not all(field in data for field in required):
        return jsonify({
            'status': 'error',
            'message': 'Missing required fields'
        }), 400
    
    scholarship = Scholarship(
        name=data['name'],
        amount=data['amount'],
        eligibility_criteria=data['eligibility_criteria'],
        available_slots=data.get('available_slots', 0)
    )
    
    db.session.add(scholarship)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'data': scholarship.to_dict()
    }), 201

@scholarships_bp.route('/<int:scholarship_id>', methods=['PUT'])
@jwt_required()
def update_scholarship(scholarship_id):
    """Update scholarship"""
    scholarship = Scholarship.query.get(scholarship_id)
    
    if not scholarship:
        return jsonify({'status': 'error', 'message': 'Scholarship not found'}), 404
    
    data = request.get_json()
    
    # Update fields if provided
    if 'name' in data:
        scholarship.name = data['name']
    if 'amount' in data:
        scholarship.amount = data['amount']
    if 'eligibility_criteria' in data:
        scholarship.eligibility_criteria = data['eligibility_criteria']
    
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'data': scholarship.to_dict()
    }), 200
```

### Step 3: Register Blueprint in App Factory

**File**: `backend/app/__init__.py` (add to create_app function)
```python
def create_app(config_name="LocalConfig"):
    app = Flask(__name__)
    # ... existing code ...
    
    # Register blueprints
    from app.students import students_bp
    from app.invoices import invoices_bp
    from app.scholarships import scholarships_bp  # NEW
    
    app.register_blueprint(students_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(scholarships_bp)  # NEW
    
    # ... rest of code ...
    return app
```

### Step 4: Create Schema for Validation (Optional)

**File**: `backend/app/scholarships/schemas.py`
```python
from marshmallow import Schema, fields, validate

class ScholarshipSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    amount = fields.Float(required=True, validate=validate.Range(min=0))
    eligibility_criteria = fields.Str(required=True)
    available_slots = fields.Int(validate=validate.Range(min=0))
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
```

---

## Adding Database Models

### Step 1: Create Model File

**File**: `backend/app/models/scholarship.py`
```python
from app import db
from datetime import datetime

class Scholarship(db.Model):
    __tablename__ = 'scholarships'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    eligibility_criteria = db.Column(db.Text, nullable=False)
    available_slots = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    awards = db.relationship('ScholarshipAward', backref='scholarship', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'amount': self.amount,
            'eligibility_criteria': self.eligibility_criteria,
            'available_slots': self.available_slots,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class ScholarshipAward(db.Model):
    __tablename__ = 'scholarship_awards'
    
    id = db.Column(db.Integer, primary_key=True)
    scholarship_id = db.Column(db.Integer, db.ForeignKey('scholarships.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    awarded_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, withdrawn, expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='scholarship_awards')
    
    def to_dict(self):
        return {
            'id': self.id,
            'scholarship_id': self.scholarship_id,
            'student_id': self.student_id,
            'awarded_date': self.awarded_date.isoformat(),
            'status': self.status
        }
```

### Step 2: Import in Models __init__.py

**File**: `backend/app/models/__init__.py`
```python
from app.models.scholarship import Scholarship, ScholarshipAward

__all__ = ['Scholarship', 'ScholarshipAward']
```

### Step 3: Initialize Database

```bash
# Add tables to database
python backend/init_db.py
```

---

## Adding Frontend Pages

### Step 1: Create Page Component

**File**: `frontend/src/pages/Scholarships.jsx`
```jsx
import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Spinner, ErrorAlert } from '../components';

export function Scholarships() {
  const [scholarships, setScholarships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    fetchScholarships();
  }, [currentPage]);

  const fetchScholarships = async () => {
    try {
      setLoading(true);
      const response = await api.get('/scholarships/', {
        params: { page: currentPage, per_page: 20 }
      });
      setScholarships(response.data.data.scholarships);
    } catch (err) {
      setError(err.message || 'Failed to load scholarships');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorAlert message={error} />;

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6">Scholarships</h1>
      
      <div className="grid gap-4">
        {scholarships.map(scholarship => (
          <div key={scholarship.id} className="bg-white p-4 rounded shadow">
            <h3 className="text-xl font-semibold">{scholarship.name}</h3>
            <p className="text-gray-600">Amount: ${scholarship.amount}</p>
            <p className="text-gray-600">Slots: {scholarship.available_slots}</p>
            <p className="text-gray-700 mt-2">{scholarship.eligibility_criteria}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Step 2: Add Route in Router

**File**: `frontend/src/App.jsx`
```jsx
import { Scholarships } from './pages/Scholarships';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Existing routes */}
        <Route path="/students" element={<ProtectedRoute><Students /></ProtectedRoute>} />
        
        {/* New route */}
        <Route path="/scholarships" element={<ProtectedRoute><Scholarships /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
```

### Step 3: Add Navigation Link

**File**: `frontend/src/components/Layout.jsx`
```jsx
export function Layout({ children }) {
  return (
    <div className="min-h-screen bg-gray-100">
      <nav className="bg-blue-600 text-white p-4">
        <div className="container mx-auto flex gap-4">
          <a href="/dashboard">Dashboard</a>
          <a href="/students">Students</a>
          <a href="/invoices">Invoices</a>
          <a href="/scholarships">Scholarships</a>  {/* NEW */}
        </div>
      </nav>
      <main>{children}</main>
    </div>
  );
}
```

---

## Extending ML Features

### Step 1: Add New Feature

**File**: `risk_service/features.py` (add to feature extraction)
```python
def extract_scholarship_features(student):
    """Extract scholarship-related features"""
    # Count scholarships student has
    num_scholarships = len(student.scholarship_awards)
    
    # Calculate total scholarship amount
    total_scholarship = sum(
        award.scholarship.amount 
        for award in student.scholarship_awards
    )
    
    # Check if high-achieving (GPA > 3.5, etc.)
    is_high_achiever = student.gpa > 3.5 if hasattr(student, 'gpa') else 0
    
    return {
        'num_scholarships': num_scholarships,
        'scholarship_amount': total_scholarship,
        'is_high_achiever': int(is_high_achiever)
    }

def get_all_features(student):
    """Get complete feature set including new features"""
    existing_features = extract_student_features(student)
    scholarship_features = extract_scholarship_features(student)
    
    return {**existing_features, **scholarship_features}
```

### Step 2: Retrain Model with New Features

```bash
cd risk_service
python train.py
```

---

## Common Patterns

### Pattern 1: Pagination

```python
@blueprint.route('/list', methods=['GET'])
@jwt_required()
def list_items():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    items = Item.query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return jsonify({
        'data': {
            'items': [i.to_dict() for i in items.items],
            'total': items.total,
            'pages': items.pages,
            'current_page': page
        }
    }), 200
```

### Pattern 2: Error Handling

```python
def safe_endpoint(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': 'Server error'}), 500
    return wrapper
```

### Pattern 3: CRUD Operations

```python
# CREATE
@bp.route('/', methods=['POST'])
def create():
    item = Item(**request.get_json())
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201

# READ
@bp.route('/<int:id>', methods=['GET'])
def read(id):
    item = Item.query.get_or_404(id)
    return jsonify(item.to_dict()), 200

# UPDATE
@bp.route('/<int:id>', methods=['PUT'])
def update(id):
    item = Item.query.get_or_404(id)
    item.update(request.get_json())
    db.session.commit()
    return jsonify(item.to_dict()), 200

# DELETE
@bp.route('/<int:id>', methods=['DELETE'])
def delete(id):
    item = Item.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return '', 204
```

### Pattern 4: Async Tasks (Celery)

**File**: `backend/app/scholarships/tasks.py`
```python
from app import celery

@celery.task
def notify_scholarship_award(student_id, scholarship_id):
    """Send notification about scholarship award"""
    student = Student.query.get(student_id)
    scholarship = Scholarship.query.get(scholarship_id)
    
    # Send email
    send_email(
        to=student.email,
        subject=f"Congratulations! {scholarship.name}",
        body=f"You've been awarded ${scholarship.amount}"
    )
    
    # Log activity
    log_activity(f"Scholarship awarded to {student.full_name}")
    
    return {'status': 'success'}

# Trigger from route
@scholarships_bp.route('/<int:scholarship_id>/award/<int:student_id>', methods=['POST'])
@jwt_required()
def award_scholarship(scholarship_id, student_id):
    # ... validation ...
    
    # Queue async task
    task = notify_scholarship_award.delay(student_id, scholarship_id)
    
    return jsonify({'status': 'queued', 'task_id': task.id}), 202
```

---

## Example: Complete Feature

### Adding "Scholarships" Feature (Full Example)

#### 1. Backend Model

**File**: `backend/app/models/scholarship.py`
```python
from app import db
from datetime import datetime

class Scholarship(db.Model):
    __tablename__ = 'scholarships'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    eligibility_criteria = db.Column(db.Text)
    available_slots = db.Column(db.Integer, default=1)
    applications = db.relationship('ScholarshipApplication', backref='scholarship', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'amount': self.amount,
            'description': self.description,
            'eligibility_criteria': self.eligibility_criteria,
            'available_slots': self.available_slots
        }

class ScholarshipApplication(db.Model):
    __tablename__ = 'scholarship_applications'
    
    id = db.Column(db.Integer, primary_key=True)
    scholarship_id = db.Column(db.Integer, db.ForeignKey('scholarships.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    applied_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref='scholarship_applications')
    
    def to_dict(self):
        return {
            'id': self.id,
            'scholarship_id': self.scholarship_id,
            'student_id': self.student_id,
            'status': self.status,
            'applied_date': self.applied_date.isoformat()
        }
```

#### 2. Backend Routes

**File**: `backend/app/scholarships/routes.py`
```python
from flask import request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models import Scholarship, ScholarshipApplication, Student
from . import scholarships_bp

@scholarships_bp.route('/', methods=['GET'])
@jwt_required()
def list_scholarships():
    scholarships = Scholarship.query.all()
    return jsonify({
        'status': 'success',
        'data': [s.to_dict() for s in scholarships]
    }), 200

@scholarships_bp.route('/', methods=['POST'])
@jwt_required()
def create_scholarship():
    data = request.get_json()
    scholarship = Scholarship(
        name=data['name'],
        amount=data['amount'],
        description=data.get('description'),
        eligibility_criteria=data.get('eligibility_criteria'),
        available_slots=data.get('available_slots', 1)
    )
    db.session.add(scholarship)
    db.session.commit()
    return jsonify({'status': 'success', 'data': scholarship.to_dict()}), 201

@scholarships_bp.route('/<int:scholarship_id>/apply', methods=['POST'])
@jwt_required()
def apply_scholarship(scholarship_id):
    data = request.get_json()
    student_id = data.get('student_id')
    
    # Check if already applied
    existing = ScholarshipApplication.query.filter_by(
        scholarship_id=scholarship_id,
        student_id=student_id
    ).first()
    
    if existing:
        return jsonify({'status': 'error', 'message': 'Already applied'}), 400
    
    app = ScholarshipApplication(
        scholarship_id=scholarship_id,
        student_id=student_id
    )
    db.session.add(app)
    db.session.commit()
    
    return jsonify({'status': 'success', 'data': app.to_dict()}), 201

@scholarships_bp.route('/applications/<int:app_id>/approve', methods=['PATCH'])
@jwt_required()
def approve_application(app_id):
    app = ScholarshipApplication.query.get_or_404(app_id)
    app.status = 'approved'
    db.session.commit()
    return jsonify({'status': 'success', 'data': app.to_dict()}), 200
```

#### 3. Frontend Component

**File**: `frontend/src/pages/Scholarships.jsx`
```jsx
import { useState, useEffect } from 'react';
import { api } from '../api/client';

export function Scholarships() {
  const [scholarships, setScholarships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    amount: '',
    description: '',
    eligibility_criteria: '',
    available_slots: 1
  });

  useEffect(() => {
    loadScholarships();
  }, []);

  const loadScholarships = async () => {
    try {
      const response = await api.get('/scholarships/');
      setScholarships(response.data.data);
    } catch (err) {
      console.error('Failed to load scholarships:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await api.post('/scholarships/', formData);
      setFormData({ name: '', amount: '', description: '', eligibility_criteria: '', available_slots: 1 });
      setShowForm(false);
      loadScholarships();
    } catch (err) {
      console.error('Failed to create scholarship:', err);
    }
  };

  const handleApply = async (scholarshipId) => {
    try {
      await api.post(`/scholarships/${scholarshipId}/apply`, {
        student_id: 1  // Get from context
      });
      alert('Application submitted!');
      loadScholarships();
    } catch (err) {
      console.error('Failed to apply:', err);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-4">Scholarships</h1>
      
      <button
        onClick={() => setShowForm(!showForm)}
        className="bg-blue-600 text-white px-4 py-2 rounded mb-4"
      >
        {showForm ? 'Cancel' : 'Add Scholarship'}
      </button>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white p-4 rounded shadow mb-6">
          <input
            type="text"
            placeholder="Scholarship Name"
            value={formData.name}
            onChange={(e) => setFormData({...formData, name: e.target.value})}
            required
            className="w-full p-2 border rounded mb-2"
          />
          <input
            type="number"
            placeholder="Amount"
            value={formData.amount}
            onChange={(e) => setFormData({...formData, amount: e.target.value})}
            required
            className="w-full p-2 border rounded mb-2"
          />
          <textarea
            placeholder="Description"
            value={formData.description}
            onChange={(e) => setFormData({...formData, description: e.target.value})}
            className="w-full p-2 border rounded mb-2"
          />
          <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded">
            Create
          </button>
        </form>
      )}

      <div className="grid gap-4">
        {scholarships.map(scholarship => (
          <div key={scholarship.id} className="bg-white p-4 rounded shadow">
            <h3 className="text-xl font-semibold">{scholarship.name}</h3>
            <p className="text-gray-600">Amount: ${scholarship.amount}</p>
            <p className="text-gray-700 mt-2">{scholarship.description}</p>
            <button
              onClick={() => handleApply(scholarship.id)}
              className="mt-4 bg-blue-600 text-white px-4 py-2 rounded"
            >
              Apply Now
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

#### 4. Initialize & Test

```bash
# Initialize database with new table
python backend/init_db.py

# Restart backend
python backend/wsgi.py

# Test endpoint
curl -X GET http://localhost:5000/api/v1/scholarships/ \
  -H "Authorization: Bearer $TOKEN"
```

---

## Development Workflow

### For Each New Feature:

1. **Design Database Schema**
   - Define models in `app/models/`
   - Add relationships

2. **Create Backend API**
   - Create blueprint in `app/feature_name/`
   - Add routes.py with CRUD operations
   - Add schemas.py for validation
   - Add tasks.py for async operations

3. **Register in App Factory**
   - Import and register blueprint in `app/__init__.py`

4. **Update Database**
   - Run `python init_db.py` to create tables

5. **Create Frontend Components**
   - Add page in `frontend/src/pages/`
   - Add route in `App.jsx`
   - Add navigation link

6. **Test**
   - Test API with curl or Postman
   - Test frontend in browser
   - Run test_full_integration.ps1

---

## Best Practices

### Backend
- ✅ Always validate input data
- ✅ Use JWT tokens for authentication
- ✅ Return consistent JSON responses
- ✅ Use database relationships, not foreign keys
- ✅ Create async tasks for long operations
- ✅ Log important operations

### Frontend
- ✅ Use API client wrapper for all requests
- ✅ Handle loading and error states
- ✅ Store JWT tokens in localStorage
- ✅ Use environment variables for API URL
- ✅ Implement pagination for lists
- ✅ Add error alerts and validation

### Database
- ✅ Use meaningful table names
- ✅ Define all relationships
- ✅ Add indexes for frequently queried fields
- ✅ Use appropriate data types
- ✅ Always set timestamps (created_at, updated_at)
- ✅ Use cascade delete for related records

### ML/Risk Service
- ✅ Document all features used
- ✅ Version your models
- ✅ Track model performance metrics
- ✅ Retrain periodically with new data
- ✅ Validate model improvements before deployment

---

## Common Tasks

### Add a New Field to Existing Model

1. **Update Model**
```python
class Student(db.Model):
    # ... existing fields ...
    gpa = db.Column(db.Float, default=0.0)  # NEW
```

2. **Reinitialize Database**
```bash
python backend/init_db.py
```

3. **Update to_dict()**
```python
def to_dict(self):
    return {
        # ... existing fields ...
        'gpa': self.gpa  # NEW
    }
```

### Add Endpoint Filter

```python
@bp.route('/', methods=['GET'])
def list_items():
    # Filter by status
    status = request.args.get('status')
    query = Item.query
    
    if status:
        query = query.filter_by(status=status)
    
    items = query.all()
    return jsonify([i.to_dict() for i in items]), 200
```

### Add Email Notification

```python
from flask_mail import Mail, Message

mail = Mail(app)

@celery.task
def send_notification_email(student_email, subject, body):
    msg = Message(subject=subject, recipients=[student_email], body=body)
    mail.send(msg)
    return {'status': 'sent'}

# Use in route
send_notification_email.delay(student.email, 'Invoice Reminder', 'Your invoice is due...')
```

---

## Troubleshooting

**Blueprint not registering?**
- Check it's imported in `app/__init__.py`
- Verify `url_prefix` is correct
- Check no duplicate routes

**Frontend can't call new endpoint?**
- Verify backend is running
- Check exact URL path
- Add JWT token to Authorization header
- Check CORS configuration

**Database table not created?**
- Run `python backend/init_db.py`
- Check model is imported in `app/models/__init__.py`
- Verify no syntax errors in model definition

---

## Next Steps

- Explore existing features in `backend/app/`
- Follow the same patterns for new features
- Test thoroughly before deployment
- Refer back to this guide for common patterns

Happy coding! 🚀
