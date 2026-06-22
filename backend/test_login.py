"""Test login via Flask test client to see actual error."""
import os, traceback
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
os.environ["FLASK_ENV"] = "local"

from app import create_app

app = create_app("local")
app.config["TESTING"] = True

with app.test_client() as client:
    print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    try:
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin1",
            "password": "demo1234"
        })
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.get_json()}")
    except Exception as e:
        traceback.print_exc()
