#!/usr/bin/env python
"""
Initialize the database by creating all tables from SQLAlchemy models.

This script bypasses Alembic migrations and directly creates the schema
using SQLAlchemy's create_all() method, which automatically handles
database-specific syntax (SQLite, MySQL, PostgreSQL, etc.).

Usage:
    python init_db.py
"""

import os
import sys
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db

def init_database():
    """Create all tables in the database."""
    # Create app with default (local) config
    app = create_app()
    
    with app.app_context():
        print("Creating all database tables...")
        db.create_all()
        print("✓ Database initialized successfully!")
        
        # Verify tables were created
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\nTables created ({len(tables)}):")
        for table in sorted(tables):
            print(f"  - {table}")

if __name__ == "__main__":
    init_database()
