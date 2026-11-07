from models import User, db

def test_new_user():
    """
    Test creating a new User object.
    """
    user = User(nrp='12345', name='Test User', role='Technician')
    assert user.nrp == '12345'
    assert user.name == 'Test User'
    assert user.role == 'Technician'
    # Sebelum di-commit ke database, nilai default dari SQLAlchemy mungkin bernilai None.
    assert user.is_approved in (False, None)

def test_password_hashing():
    """
    Test that passwords are hashed correctly and can be verified.
    """
    user = User(nrp='admin', name='Admin')
    user.set_password('mysecretpassword')
    
    assert user.password_hash is not None
    assert user.check_password('mysecretpassword') is True
    assert user.check_password('wrongpassword') is False

def test_user_db_operations(app):
    """
    Test saving user to database and querying it.
    """
    with app.app_context():
        user = User(nrp='u001', name='DB User', role='User')
        user.set_password('password123')
        
        db.session.add(user)
        db.session.commit()
        
        # Query back
        queried_user = User.query.filter_by(nrp='u001').first()
        assert queried_user is not None
        assert queried_user.name == 'DB User'
        assert queried_user.check_password('password123') is True
