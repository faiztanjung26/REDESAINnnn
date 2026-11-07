import os
import sys
# Masukkan root direktori ke sys.path agar pytest mengenali modul 'app' dan 'models'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app import create_app
from models import db

@pytest.fixture
def app():
    # Override DATABASE_URL to use in-memory SQLite for testing
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    
    # We also need a SECRET_KEY for sessions
    os.environ['SECRET_KEY'] = 'test-secret-key'
    
    app = create_app()
    app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # Disable CSRF for testing
    })

    # Set up application context and database
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
