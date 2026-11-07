from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from markupsafe import escape
from datetime import datetime, timezone, timedelta
from models import db, User, AuditLog
from app import limiter
import re

def log_audit(user_id, action, target_table=None, target_id=None, details=None):
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip_address and ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()
    log = AuditLog(
        user_id=user_id, 
        action=action, 
        target_table=target_table, 
        target_id=target_id, 
        ip_address=ip_address, 
        details=details
    )
    db.session.add(log)
    db.session.commit()

def is_valid_password(password):
    if len(password) < 8: return False
    if not re.search(r"[A-Za-z]", password): return False
    if not re.search(r"\d", password): return False
    return True

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", error_message="Terlalu banyak percobaan login. Silakan coba lagi nanti.")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        nrp = request.form.get('nrp')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(nrp=nrp).first()
        if user and user.check_password(password):
            if not user.is_approved:
                log_audit(user.id, 'LOGIN_FAILED', details=f'Failed login attempt for NRP: {nrp} (Account Pending)')
                flash('Your account is pending admin approval.', 'error')
                return render_template('auth/login.html')

            user.last_login = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7)
            user.login_count = (user.login_count or 0) + 1
            
            import secrets
            token = secrets.token_hex(16)
            user.session_token = token
            
            db.session.commit()
            
            login_user(user, remember=remember)
            session['session_token'] = token
            session.permanent = True
            log_audit(user.id, 'LOGIN_SUCCESS', details='User logged in successfully')
            next_page = request.args.get('next')
            if user.role == 'User':
                return redirect(next_page or url_for('helpdesk.index'))
            return redirect(next_page or url_for('dashboard'))
        else:
            log_audit(user.id if user else None, 'LOGIN_FAILED', details=f'Failed login attempt for NRP: {nrp}')
            flash('Invalid NRP or password.', 'error')
            
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        nrp = request.form.get('nrp')
        password = request.form.get('password')
        role = 'Technician' # Forced to Technician
        
        if not name or not nrp or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('auth.register'))
            
        if not is_valid_password(password):
            flash('Password must be at least 8 characters long and contain both letters and numbers.', 'error')
            return redirect(url_for('auth.register'))
            
        # Sanitize input to prevent Reflected XSS
        safe_name = str(escape(name))
        safe_nrp = str(escape(nrp))
        
        try:
            if User.query.filter_by(nrp=safe_nrp).first():
                flash('NRP already registered.', 'error')
                return redirect(url_for('auth.register'))
                
            new_user = User(nrp=safe_nrp, name=safe_name, role=role)
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            log_audit(new_user.id, 'USER_REGISTERED', 'User', new_user.id, 'User registered successfully')
            
            flash('Registration successful. Please wait for an administrator to approve your account before logging in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            return redirect(url_for('auth.register'))
        
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    log_audit(current_user.id, 'LOGOUT_SUCCESS', details='User logged out')
    logout_user()
    # flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        name = request.form.get('name')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if name and name.strip() != '' and current_user.name != name.strip():
            current_user.name = name.strip()
            log_audit(current_user.id, 'PROFILE_UPDATED', 'User', current_user.id, 'User updated profile name')
            
        if new_password:
            if not is_valid_password(new_password):
                flash('Password must be at least 8 characters long and contain both letters and numbers.', 'error')
                return redirect(url_for('auth.profile'))
            if new_password != confirm_password:
                flash('Passwords do not match. Please try again.', 'error')
                return redirect(url_for('auth.profile'))
            current_user.set_password(new_password)
            log_audit(current_user.id, 'PASSWORD_CHANGED', 'User', current_user.id, 'User changed password')
            
        db.session.commit()
        flash('Your profile has been updated successfully.', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('auth/profile.html')
