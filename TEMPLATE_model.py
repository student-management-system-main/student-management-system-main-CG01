# Template: Backend Model

Copy this to `backend/app/models/FEATURE_NAME.py` and customize

```python
from app import db
from datetime import datetime

class FeatureName(db.Model):
    """Main entity for the feature"""
    __tablename__ = 'feature_names'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # Core Fields
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')
    
    # Foreign Keys
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='feature_names')
    related_items = db.relationship('RelatedItem', backref='feature_name', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'student_id': self.student_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
    
    def __repr__(self):
        return f'<FeatureName {self.name}>'


class RelatedItem(db.Model):
    """Related entity (if needed)"""
    __tablename__ = 'related_items'
    
    id = db.Column(db.Integer, primary_key=True)
    feature_name_id = db.Column(db.Integer, db.ForeignKey('feature_names.id'), nullable=False)
    value = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'feature_name_id': self.feature_name_id,
            'value': self.value,
            'created_at': self.created_at.isoformat()
        }
```

## Steps to Use:

1. Copy this file to `backend/app/models/feature_name.py`
2. Replace `FeatureName` with your feature name (CamelCase)
3. Replace `feature_names` with table name (snake_case)
4. Add your fields
5. Add relationships
6. Import in `backend/app/models/__init__.py`
7. Run `python backend/init_db.py`

## Common Field Types:

```python
db.Column(db.String(255))          # Text (max 255 chars)
db.Column(db.Text)                 # Long text
db.Column(db.Integer)              # Whole numbers
db.Column(db.Float)                # Decimals
db.Column(db.Boolean, default=True) # True/False
db.Column(db.DateTime)              # Date and time
db.Column(db.Date)                 # Date only
db.Column(db.Enum('active', 'inactive'))  # Choices
```
