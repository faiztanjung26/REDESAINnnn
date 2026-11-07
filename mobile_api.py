import os
import json
import uuid
import time
import hashlib
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app, g
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from markupsafe import escape

from models import (
    db, User, WorkOrder, WorkOrderStatus, WorkOrderProcedure,
    WorkOrderChecklistParameter, WorkOrderPart, WorkOrderLog,
    WorkOrderAttachment, Part, Asset, Site, Team, DigitalSignature, AuditLog
)

mobile_api_bp = Blueprint('mobile_api', __name__, url_prefix='/api/mobile')

# Token Serializer Helper
def get_serializer():
    secret_key = current_app.config.get('SECRET_KEY') or 'cmms2-mobile-secret-key-2026'
    return URLSafeTimedSerializer(secret_key, salt='cmms-mobile-auth')

def generate_token(user_id):
    s = get_serializer()
    return s.dumps({'user_id': user_id, 'created_at': datetime.utcnow().isoformat()})

def verify_token(token, max_age_seconds=30 * 24 * 3600):  # 30 days token validity
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age_seconds)
        return data.get('user_id')
    except (SignatureExpired, BadTimeSignature, Exception):
        return None

# Authentication Decorator
def mobile_auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        token = None

        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1].strip()
        elif 'X-Auth-Token' in request.headers:
            token = request.headers.get('X-Auth-Token').strip()

        if not token:
            return jsonify({
                'status': 'error',
                'message': 'Autentikasi diperlukan. Header Authorization: Bearer <token> tidak ditemukan.'
            }), 401

        user_id = verify_token(token)
        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Token sesi tidak valid atau telah kedaluwarsa. Silakan login kembali.'
            }), 401

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({
                'status': 'error',
                'message': 'Pengguna tidak ditemukan di sistem.'
            }), 401

        if not user.is_approved:
            return jsonify({
                'status': 'error',
                'message': 'Akun Anda belum disetujui oleh administrator.'
            }), 403

        # Update last_active
        now_jkt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7)
        user.last_active = now_jkt
        try:
            db.session.commit()
        except:
            db.session.rollback()

        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def log_mobile_audit(user_id, action, target_table=None, target_id=None, details=None):
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        audit = AuditLog(
            user_id=user_id,
            action=action,
            target_table=target_table,
            target_id=target_id,
            ip_address=ip,
            details=f"[Mobile App] {details or ''}"
        )
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        db.session.rollback()

def get_status_color(status_name):
    color_map = {
        'Draft': '#94a3b8',        # Slate
        'Assigned': '#0ea5e9',     # Sky blue
        'Confirmed': '#0284c7',    # Deep sky
        'In Progress': '#2563eb',  # Royal blue
        'Hold': '#f59e0b',         # Amber
        'Solved': '#8b5cf6',       # Violet
        'Completed': '#10b981',    # Emerald green
        'Closed': '#64748b',       # Gray
        'Incompleted': '#ef4444'   # Red
    }
    return color_map.get(status_name, '#64748b')

def check_technician_wo_access(wo, user):
    if user.role in ['Admin', 'Supervisor']:
        return True
    if wo.assigned_to == user.id:
        return True
    if user in getattr(wo, 'assignees', []):
        return True
    return False


# ==========================================================
# AUTHENTICATION ENDPOINTS
# ==========================================================

@mobile_api_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint for mobile technician app
    Request body (JSON or Form):
    - nrp: string
    - password: string
    """
    data = request.get_json(silent=True) or request.form
    nrp = (data.get('nrp') or '').strip()
    password = data.get('password') or ''

    if not nrp or not password:
        return jsonify({
            'status': 'error',
            'message': 'NRP dan kata sandi wajib diisi.'
        }), 400

    user = User.query.filter_by(nrp=nrp).first()
    if not user or not user.check_password(password):
        log_mobile_audit(user.id if user else None, 'LOGIN_FAILED', details=f"Gagal login mobile NRP: {nrp}")
        return jsonify({
            'status': 'error',
            'message': 'NRP atau kata sandi yang Anda masukkan salah.'
        }), 401

    if not user.is_approved:
        log_mobile_audit(user.id, 'LOGIN_FAILED', details=f"Akun belum disetujui: {nrp}")
        return jsonify({
            'status': 'error',
            'message': 'Akun Anda sedang menunggu persetujuan administrator.'
        }), 403

    # Generate token
    token = generate_token(user.id)

    # Update login timestamp
    now_jkt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7)
    user.last_login = now_jkt
    user.login_count = (user.login_count or 0) + 1
    user.session_token = secrets_token = hashlib.sha256(f"{user.id}-{time.time()}".encode()).hexdigest()[:32]
    db.session.commit()

    log_mobile_audit(user.id, 'LOGIN_SUCCESS', details='Teknisi berhasil login melalui aplikasi Android')

    site_name = user.site.name if user.site else 'Semua Site'
    team_name = user.team.name if user.team else '-'

    return jsonify({
        'status': 'success',
        'message': 'Login berhasil',
        'token': token,
        'user': {
            'id': user.id,
            'nrp': user.nrp,
            'name': user.name,
            'role': user.role,
            'phone_number': user.phone_number or '',
            'site_id': user.site_id,
            'site_name': site_name,
            'team_id': user.team_id,
            'team_name': team_name
        }
    })


@mobile_api_bp.route('/profile', methods=['GET'])
@mobile_auth_required
def get_profile():
    """Get technician profile details and work order stats"""
    user = g.current_user

    # Compute assigned work order statistics
    wos_query = WorkOrder.query
    if user.role == 'Technician':
        wos_query = wos_query.filter(
            (WorkOrder.assigned_to == user.id) | 
            (WorkOrder.assignees.any(id=user.id))
        )

    all_wos = wos_query.all()
    total_assigned = len(all_wos)
    in_progress_count = sum(1 for w in all_wos if w.current_status and w.current_status.name == 'In Progress')
    completed_count = sum(1 for w in all_wos if w.current_status and w.current_status.name in ['Solved', 'Completed', 'Closed'])
    hold_count = sum(1 for w in all_wos if w.current_status and w.current_status.name == 'Hold')

    now = datetime.utcnow()
    overdue_count = sum(
        1 for w in all_wos 
        if w.suggested_completion_date and w.suggested_completion_date < now 
        and (not w.current_status or w.current_status.control_type != 'Closed' and w.current_status.name not in ['Solved', 'Completed'])
    )

    return jsonify({
        'status': 'success',
        'user': {
            'id': user.id,
            'nrp': user.nrp,
            'name': user.name,
            'role': user.role,
            'phone_number': user.phone_number or '',
            'site_id': user.site_id,
            'site_name': user.site.name if user.site else 'Semua Site',
            'team_id': user.team_id,
            'team_name': user.team.name if user.team else '-',
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None,
            'stats': {
                'total_assigned': total_assigned,
                'in_progress': in_progress_count,
                'hold': hold_count,
                'completed': completed_count,
                'overdue': overdue_count
            }
        }
    })


@mobile_api_bp.route('/profile/update', methods=['POST'])
@mobile_auth_required
def update_profile():
    """Update profile information (display name, phone number)"""
    user = g.current_user
    data = request.get_json(silent=True) or request.form

    name = data.get('name')
    phone = data.get('phone_number')

    if name and name.strip():
        user.name = str(escape(name.strip()))
    if phone is not None:
        user.phone_number = phone.strip()

    db.session.commit()
    log_mobile_audit(user.id, 'PROFILE_UPDATED', 'User', user.id, 'Pembaruan profil teknisi via Android')

    return jsonify({
        'status': 'success',
        'message': 'Profil berhasil diperbarui.',
        'user': {
            'id': user.id,
            'nrp': user.nrp,
            'name': user.name,
            'role': user.role,
            'phone_number': user.phone_number or '',
            'site_id': user.site_id,
            'site_name': user.site.name if user.site else 'Semua Site'
        }
    })


@mobile_api_bp.route('/profile/change-password', methods=['POST'])
@mobile_auth_required
def change_password():
    """Change user password"""
    user = g.current_user
    data = request.get_json(silent=True) or request.form

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not user.check_password(current_password):
        return jsonify({
            'status': 'error',
            'message': 'Kata sandi saat ini tidak cocok.'
        }), 400

    if len(new_password) < 8:
        return jsonify({
            'status': 'error',
            'message': 'Kata sandi baru minimal harus 8 karakter.'
        }), 400

    if new_password != confirm_password:
        return jsonify({
            'status': 'error',
            'message': 'Konfirmasi kata sandi baru tidak cocok.'
        }), 400

    user.set_password(new_password)
    db.session.commit()
    log_mobile_audit(user.id, 'PASSWORD_CHANGED', 'User', user.id, 'Ganti password teknisi via Android')

    return jsonify({
        'status': 'success',
        'message': 'Kata sandi berhasil diubah.'
    })


# ==========================================================
# DASHBOARD ENDPOINTS
# ==========================================================

@mobile_api_bp.route('/dashboard', methods=['GET'])
@mobile_auth_required
def get_dashboard():
    """
    Get dashboard metrics and priority work orders for technician
    """
    user = g.current_user
    now = datetime.utcnow()
    start_of_today = datetime(now.year, now.month, now.day, 0, 0, 0)
    end_of_today = datetime(now.year, now.month, now.day, 23, 59, 59)

    query = WorkOrder.query
    if user.role == 'Technician':
        query = query.filter(
            (WorkOrder.assigned_to == user.id) | 
            (WorkOrder.assignees.any(id=user.id))
        )
    elif user.site_id:
        query = query.join(Asset).filter(Asset.site_id == user.site_id)

    all_wos = query.order_by(WorkOrder.date_created.desc()).all()

    assigned_count = 0
    in_progress_count = 0
    hold_count = 0
    solved_count = 0
    completed_count = 0
    overdue_count = 0
    today_count = 0

    today_wos = []
    urgent_wos = []
    recent_wos = []

    for wo in all_wos:
        status_name = wo.current_status.name if wo.current_status else 'Draft'
        is_closed = wo.current_status and wo.current_status.control_type == 'Closed'

        if status_name in ['Assigned', 'Confirmed']:
            assigned_count += 1
        elif status_name == 'In Progress':
            in_progress_count += 1
        elif status_name == 'Hold':
            hold_count += 1
        elif status_name == 'Solved':
            solved_count += 1
        elif status_name in ['Completed', 'Closed']:
            completed_count += 1

        is_overdue = False
        if wo.suggested_completion_date and not is_closed and status_name not in ['Solved', 'Completed']:
            if wo.suggested_completion_date < now:
                overdue_count += 1
                is_overdue = True

        # Due today or active today
        is_today = False
        target_date = wo.suggested_completion_date or wo.date_created
        if target_date and start_of_today <= target_date <= end_of_today:
            today_count += 1
            is_today = True

        wo_summary = {
            'id': wo.id,
            'code': wo.code or f"WO-{wo.id}",
            'description': wo.description or '',
            'priority': wo.priority or 'Medium',
            'status': status_name,
            'status_color': get_status_color(status_name),
            'maintenance_type': wo.maintenance_type or 'Corrective',
            'asset_name': wo.asset.name if wo.asset else '-',
            'asset_code': wo.asset.code if wo.asset else '-',
            'location': (wo.asset.location.name if wo.asset and wo.asset.location else (wo.asset.site.name if wo.asset and wo.asset.site else '-')),
            'suggested_completion_date': wo.suggested_completion_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_completion_date else None,
            'is_overdue': is_overdue,
            'procedures_total': wo.procedures.count(),
            'procedures_completed': wo.procedures.filter_by(is_completed=True).count()
        }

        if is_today and len(today_wos) < 5:
            today_wos.append(wo_summary)

        if (wo.priority in ['Highest', 'High'] or is_overdue) and not is_closed and status_name not in ['Solved', 'Completed'] and len(urgent_wos) < 5:
            urgent_wos.append(wo_summary)

        if len(recent_wos) < 5:
            recent_wos.append(wo_summary)

    return jsonify({
        'status': 'success',
        'metrics': {
            'total_assigned': len(all_wos),
            'assigned': assigned_count,
            'in_progress': in_progress_count,
            'hold': hold_count,
            'solved': solved_count,
            'completed': completed_count,
            'overdue': overdue_count,
            'due_today': today_count
        },
        'today_work_orders': today_wos,
        'urgent_work_orders': urgent_wos,
        'recent_work_orders': recent_wos
    })


# ==========================================================
# WORK ORDERS ENDPOINTS
# ==========================================================

@mobile_api_bp.route('/work-orders', methods=['GET'])
@mobile_auth_required
def list_work_orders():
    """
    List work orders assigned to current technician with filters
    Query params:
    - status: 'all', 'assigned', 'in_progress', 'hold', 'solved', 'completed'
    - priority: 'Highest', 'High', 'Medium', 'Low'
    - search: keyword search in code, description, asset name
    - page: int (default 1)
    - limit: int (default 20)
    """
    user = g.current_user
    status_filter = request.args.get('status', 'all').lower()
    priority_filter = request.args.get('priority', '')
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)

    query = WorkOrder.query
    if user.role == 'Technician':
        query = query.filter(
            (WorkOrder.assigned_to == user.id) | 
            (WorkOrder.assignees.any(id=user.id))
        )
    elif user.site_id:
        query = query.join(Asset).filter(Asset.site_id == user.site_id)

    # Filter by Status
    if status_filter != 'all':
        status_map = {
            'assigned': ['Assigned', 'Confirmed'],
            'in_progress': ['In Progress'],
            'hold': ['Hold'],
            'solved': ['Solved'],
            'completed': ['Completed', 'Closed'],
            'draft': ['Draft']
        }
        target_names = status_map.get(status_filter, [])
        if target_names:
            query = query.join(WorkOrderStatus).filter(WorkOrderStatus.name.in_(target_names))

    # Filter by Priority
    if priority_filter:
        query = query.filter(WorkOrder.priority == priority_filter)

    # Search keyword
    if search_query:
        search_like = f"%{search_query}%"
        query = query.filter(
            (WorkOrder.code.ilike(search_like)) |
            (WorkOrder.description.ilike(search_like)) |
            (WorkOrder.asset.has(Asset.name.ilike(search_like)))
        )

    # Order by target date / date created descending
    query = query.order_by(
        db.case(
            (WorkOrder.priority == 'Highest', 1),
            (WorkOrder.priority == 'High', 2),
            (WorkOrder.priority == 'Medium', 3),
            else_=4
        ),
        WorkOrder.suggested_completion_date.asc().nullslast(),
        WorkOrder.date_created.desc()
    )

    total_count = query.count()
    wos = query.offset((page - 1) * limit).limit(limit).all()

    now = datetime.utcnow()
    results = []
    for wo in wos:
        status_name = wo.current_status.name if wo.current_status else 'Draft'
        is_closed = wo.current_status and wo.current_status.control_type == 'Closed'
        is_overdue = bool(wo.suggested_completion_date and not is_closed and status_name not in ['Solved', 'Completed'] and wo.suggested_completion_date < now)

        proc_total = wo.procedures.count()
        proc_done = wo.procedures.filter_by(is_completed=True).count()
        progress_pct = round((proc_done / proc_total * 100)) if proc_total > 0 else 0

        location_name = '-'
        if wo.asset:
            if getattr(wo.asset, 'location', None):
                location_name = wo.asset.location.name or '-'
            elif getattr(wo.asset, 'site', None):
                location_name = wo.asset.site.name or '-'

        results.append({
            'id': wo.id,
            'code': wo.code or f"WO-{wo.id}",
            'description': wo.description or '',
            'priority': wo.priority or 'Medium',
            'status': status_name,
            'status_color': get_status_color(status_name),
            'maintenance_type': wo.maintenance_type or 'Corrective',
            'asset_id': wo.asset_id,
            'asset_name': wo.asset.name if wo.asset else '-',
            'asset_code': wo.asset.code if wo.asset else '-',
            'location': location_name,
            'suggested_start_date': wo.suggested_start_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_start_date else None,
            'suggested_completion_date': wo.suggested_completion_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_completion_date else None,
            'start_date': wo.start_date.strftime('%Y-%m-%d %H:%M') if wo.start_date else None,
            'end_date': wo.end_date.strftime('%Y-%m-%d %H:%M') if wo.end_date else None,
            'is_overdue': is_overdue,
            'procedures_total': proc_total,
            'procedures_completed': proc_done,
            'progress_percent': progress_pct,
            'checklists_total': wo.checklist_parameters.count()
        })

    return jsonify({
        'status': 'success',
        'total': total_count,
        'page': page,
        'limit': limit,
        'data': results
    })


@mobile_api_bp.route('/work-orders/<int:id>', methods=['GET'])
@mobile_auth_required
def get_work_order_detail(id):
    """
    Get full work order details including procedures, checklists, parts, logs, and signatures
    """
    user = g.current_user
    wo = WorkOrder.query.get(id)
    if not wo:
        return jsonify({'status': 'error', 'message': 'Work Order tidak ditemukan.'}), 404

    if not check_technician_wo_access(wo, user):
        return jsonify({'status': 'error', 'message': 'Akses ditolak. WO ini tidak ditugaskan kepada Anda.'}), 403

    status_name = wo.current_status.name if wo.current_status else 'Draft'

    # Build Procedures
    procedures_list = []
    for proc in wo.procedures.order_by(WorkOrderProcedure.id.asc()).all():
        raw_photos = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]
        photo_urls = []
        for p in raw_photos:
            if p.startswith('http') or p.startswith('data:'):
                photo_urls.append(p)
            else:
                photo_urls.append(f"/static/{p.lstrip('/')}")

        procedures_list.append({
            'id': proc.id,
            'name': proc.name,
            'requires_attachment': bool(proc.requires_attachment),
            'min_photos': int(getattr(proc, 'min_photos', 0) or 0),
            'estimated_minutes': int(getattr(proc, 'estimated_minutes', 0) or 0),
            'is_completed': bool(proc.is_completed),
            'status': proc.status or ('Done' if proc.is_completed else 'Pending'),
            'notes': proc.notes or '',
            'photos': photo_urls,
            'attachment_path': proc.attachment_path or ''
        })

    # Build Checklists
    checklists_list = []
    for chk in wo.checklist_parameters.order_by(WorkOrderChecklistParameter.id.asc()).all():
        checklists_list.append({
            'id': chk.id,
            'parameter': chk.parameter,
            'standard': chk.standard or '',
            'value': chk.value or ''
        })

    # Build Spare Parts
    parts_list = []
    for wp in wo.used_parts.all():
        parts_list.append({
            'id': wp.id,
            'part_id': wp.part_id,
            'part_name': wp.part.name if wp.part else '-',
            'part_code': wp.part.code if wp.part else '-',
            'unit': wp.part.unit if wp.part else 'Pcs',
            'quantity_used': wp.quantity_used or 1.0,
            'date_added': wp.date_added.strftime('%Y-%m-%d %H:%M') if wp.date_added else None
        })

    # Build Logs
    logs_list = []
    for log in wo.logs.order_by(WorkOrderLog.created_at.desc()).all():
        logs_list.append({
            'id': log.id,
            'user_name': log.user.name if log.user else 'System',
            'log_text': log.log_text,
            'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else None
        })

    # Allowed technician actions
    allowed_actions = []
    if status_name in ['Draft', 'Assigned', 'Confirmed']:
        allowed_actions = ['start']
    elif status_name == 'In Progress':
        allowed_actions = ['hold', 'solve']
    elif status_name == 'Hold':
        allowed_actions = ['resume']

    location_name = '-'
    site_name = '-'
    if wo.asset:
        if getattr(wo.asset, 'location', None):
            location_name = wo.asset.location.name or '-'
        if getattr(wo.asset, 'site', None):
            site_name = wo.asset.site.name or '-'

    assignee_names = [a.name for a in wo.assignees]
    if wo.assignee and wo.assignee.name not in assignee_names:
        assignee_names.insert(0, wo.assignee.name)

    now = datetime.utcnow()
    is_closed = wo.current_status and wo.current_status.control_type == 'Closed'
    is_overdue = bool(wo.suggested_completion_date and not is_closed and status_name not in ['Solved', 'Completed'] and wo.suggested_completion_date < now)

    return jsonify({
        'status': 'success',
        'data': {
            'id': wo.id,
            'code': wo.code or f"WO-{wo.id}",
            'description': wo.description or '',
            'priority': wo.priority or 'Medium',
            'status': status_name,
            'status_color': get_status_color(status_name),
            'maintenance_type': wo.maintenance_type or 'Corrective',
            'project_code': wo.project_code or '',
            'work_instructions': wo.work_instructions or '',
            'delay_reason': wo.delay_reason or '',
            'tasklist_note': getattr(wo, 'tasklist_note', '') or '',
            'estimated_hours': wo.estimated_hours,
            'suggested_start_date': wo.suggested_start_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_start_date else None,
            'suggested_completion_date': wo.suggested_completion_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_completion_date else None,
            'start_date': wo.start_date.strftime('%Y-%m-%d %H:%M') if wo.start_date else None,
            'end_date': wo.end_date.strftime('%Y-%m-%d %H:%M') if wo.end_date else None,
            'is_overdue': is_overdue,
            'asset': {
                'id': wo.asset_id,
                'name': wo.asset.name if wo.asset else '-',
                'code': wo.asset.code if wo.asset else '-',
                'model_number': getattr(wo.asset, 'model_number', '-') if wo.asset else '-',
                'serial_number': getattr(wo.asset, 'serial_number', '-') if wo.asset else '-',
                'location': location_name,
                'site': site_name
            },
            'team': wo.team.name if wo.team else '-',
            'assignees': assignee_names,
            'procedures': procedures_list,
            'checklists': checklists_list,
            'parts_used': parts_list,
            'logs': logs_list,
            'signatures': {
                'customer_name': wo.customer_name or '',
                'customer_title': wo.customer_title or '',
                'customer_signature': wo.customer_signature or '',
                'technician_signature': wo.technician_signature or ''
            },
            'allowed_actions': allowed_actions
        }
    })


@mobile_api_bp.route('/work-orders/<int:id>/status', methods=['POST'])
@mobile_auth_required
def update_work_order_status(id):
    """
    Change status of work order
    Body:
    - action: 'start' | 'hold' | 'resume' | 'solve'
    - reason: string (required if hold)
    """
    user = g.current_user
    wo = WorkOrder.query.get(id)
    if not wo:
        return jsonify({'status': 'error', 'message': 'Work Order tidak ditemukan.'}), 404

    if not check_technician_wo_access(wo, user):
        return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403

    data = request.get_json(silent=True) or request.form
    action = (data.get('action') or '').strip().lower()
    reason = (data.get('reason') or '').strip()

    action_map = {
        'start': 'In Progress',
        'hold': 'Hold',
        'resume': 'In Progress',
        'solve': 'Solved'
    }

    target_status_name = action_map.get(action)
    if not target_status_name:
        return jsonify({'status': 'error', 'message': f'Aksi tidak valid: {action}'}), 400

    target_status = WorkOrderStatus.query.filter_by(name=target_status_name).first()
    if not target_status:
        # Auto-create status if missing
        target_status = WorkOrderStatus(name=target_status_name, control_type='Active' if target_status_name != 'Solved' else 'Closed')
        db.session.add(target_status)
        db.session.flush()

    # START / RESUME Action
    if action in ['start', 'resume']:
        if action == 'start' and not wo.start_date:
            wo.start_date = datetime.utcnow()
        wo.status_id = target_status.id
        wo.end_date = None

        log_msg = f"Teknisi {user.name} memulai pengerjaan Work Order." if action == 'start' else f"Teknisi {user.name} melanjutkan pengerjaan Work Order."
        db.session.add(WorkOrderLog(work_order_id=wo.id, user_id=user.id, log_text=log_msg))

    # HOLD Action
    elif action == 'hold':
        if not reason:
            return jsonify({'status': 'error', 'message': 'Alasan penundaan (delay reason) wajib diisi saat menunda WO.'}), 400
        wo.status_id = target_status.id
        wo.delay_reason = reason
        log_msg = f"Work Order ditunda oleh {user.name}. Alasan: {reason}"
        db.session.add(WorkOrderLog(work_order_id=wo.id, user_id=user.id, log_text=log_msg))

    # SOLVE Action (Teknisi Selesai)
    elif action == 'solve':
        # 1. Validasi Prosedur & Foto
        incomplete_procs = []
        for proc in wo.procedures:
            num_photos = len([p for p in (proc.attachment_path or '').split('|') if p.strip()])
            if not proc.is_completed:
                incomplete_procs.append(f"{proc.name} (Belum dicentang)")
            elif proc.requires_attachment and not proc.attachment_path:
                incomplete_procs.append(f"{proc.name} (Foto bukti wajib dilampirkan)")
            elif proc.min_photos > 0 and num_photos < proc.min_photos:
                incomplete_procs.append(f"{proc.name} (Minimal {proc.min_photos} foto, baru {num_photos})")

        if incomplete_procs:
            return jsonify({
                'status': 'error',
                'message': f"Tidak dapat menyelesaikan WO. Prosedur belum lengkap: {', '.join(incomplete_procs)}"
            }), 400

        # 2. Validasi Parameter Checklist
        missing_chks = [c.parameter for c in wo.checklist_parameters if not (c.value and str(c.value).strip())]
        if missing_chks:
            return jsonify({
                'status': 'error',
                'message': f"Nilai parameter checklist belum diisi: {', '.join(missing_chks)}"
            }), 400

        wo.status_id = target_status.id
        wo.end_date = datetime.utcnow()
        if wo.start_date:
            wo.estimated_hours = round((wo.end_date - wo.start_date).total_seconds() / 3600, 2)

        # Log completion
        log_msg = f"Work order diselesaikan oleh teknisi {user.name}."
        db.session.add(WorkOrderLog(work_order_id=wo.id, user_id=user.id, log_text=log_msg))

        # Generate DigitalSignature record if signatures present
        if wo.customer_signature or wo.technician_signature:
            existing_sig = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
            if not existing_sig:
                signer = wo.customer_name or user.name
                title = wo.customer_title or 'Teknisi'
                sig_id = str(uuid.uuid4())
                ts = str(time.time())
                data_to_hash = f"{wo.code}|{signer}|{ts}"
                doc_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
                new_sig = DigitalSignature(
                    id=sig_id,
                    work_order_id=wo.id,
                    signer_name=signer,
                    signer_title=title,
                    signed_at=datetime.utcnow(),
                    document_hash=doc_hash,
                    status='Valid'
                )
                db.session.add(new_sig)

    db.session.commit()
    log_mobile_audit(user.id, 'WO_STATUS_CHANGED', 'WorkOrder', wo.id, f"Aksi status: {action} -> {target_status_name}")

    return jsonify({
        'status': 'success',
        'message': f"Status Work Order berhasil diperbarui menjadi {target_status_name}.",
        'new_status': target_status_name,
        'status_color': get_status_color(target_status_name),
        'start_date': wo.start_date.strftime('%Y-%m-%d %H:%M') if wo.start_date else None,
        'end_date': wo.end_date.strftime('%Y-%m-%d %H:%M') if wo.end_date else None
    })


@mobile_api_bp.route('/work-orders/<int:id>/procedures/<int:proc_id>', methods=['POST'])
@mobile_auth_required
def update_procedure(id, proc_id):
    """
    Update procedure status, notes, completion and upload photos
    Accepts JSON or multipart/form-data with 'photos' files
    """
    user = g.current_user
    proc = WorkOrderProcedure.query.filter_by(id=proc_id, work_order_id=id).first()
    if not proc:
        return jsonify({'status': 'error', 'message': 'Prosedur tidak ditemukan.'}), 404

    data = request.form if request.form else (request.get_json(silent=True) or {})

    # Check delete photo action
    if data.get('action') == 'delete_photo' or data.get('delete_photo'):
        return delete_procedure_photo_mobile(id, proc_id)

    # Toggle / update completion
    if 'is_completed' in data:
        val = data['is_completed']
        proc.is_completed = (val is True or val == 'true' or val == '1' or val == 1)
        proc.status = 'Done' if proc.is_completed else 'Pending'
        if proc.is_completed:
            proc.completed_at = datetime.utcnow()
            proc.completed_by_id = user.id

    if 'notes' in data:
        proc.notes = str(escape(data['notes']))

    # Handle photo uploads
    uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    current_photos = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]

    # Process files from request.files
    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            fname = secure_filename(f"wo{id}_proc{proc_id}_{int(time.time())}_{file.filename}")
            filepath = os.path.join(uploads_dir, fname)
            file.save(filepath)
            rel_path = f"uploads/{fname}"
            if rel_path not in current_photos:
                current_photos.append(rel_path)

    proc.attachment_path = '|'.join(current_photos)
    db.session.commit()

    total_procs = proc.work_order.procedures.count()
    completed_procs = proc.work_order.procedures.filter_by(is_completed=True).count()
    progress_pct = round((completed_procs / total_procs * 100)) if total_procs > 0 else 0

    return jsonify({
        'status': 'success',
        'message': 'Prosedur berhasil diperbarui.',
        'procedure': {
            'id': proc.id,
            'is_completed': proc.is_completed,
            'status': proc.status,
            'notes': proc.notes or '',
            'photos': [f"/static/{p}" for p in current_photos],
            'attachment_path': proc.attachment_path
        },
        'progress_percent': progress_pct
    })


@mobile_api_bp.route('/work-orders/<int:id>/procedures/<int:proc_id>/photos/delete', methods=['POST'])
@mobile_auth_required
def delete_procedure_photo_mobile(id, proc_id):
    """
    Delete a photo evidence from a work order procedure
    Body:
    - photo_path: "uploads/..." or "/static/uploads/..."
    - photo_index: int (optional)
    """
    user = g.current_user
    proc = WorkOrderProcedure.query.filter_by(id=proc_id, work_order_id=id).first()
    if not proc:
        return jsonify({'status': 'error', 'message': 'Prosedur tidak ditemukan.'}), 404

    wo = proc.work_order
    if wo.current_status and wo.current_status.control_type == 'Closed':
        return jsonify({'status': 'error', 'message': 'Work Order sudah ditutup, tidak dapat mengubah foto.'}), 400

    data = request.get_json(silent=True) or request.form or {}
    photo_path = data.get('photo_path')
    photo_index = data.get('photo_index')

    current_photos = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]
    deleted = None

    if photo_path:
        norm = photo_path.replace('/static/', '').strip()
        for p in list(current_photos):
            if p == norm or p.endswith(norm) or norm.endswith(p):
                deleted = p
                current_photos.remove(p)
                break
    elif photo_index is not None:
        try:
            idx = int(photo_index)
            if 0 <= idx < len(current_photos):
                deleted = current_photos.pop(idx)
        except (ValueError, TypeError):
            pass

    if not deleted:
        return jsonify({'status': 'error', 'message': 'Foto tidak ditemukan atau sudah dihapus.'}), 404

    # Remove physical file if in static/uploads
    try:
        fpath = os.path.join(current_app.root_path, 'static', deleted.replace('/', os.sep))
        if os.path.isfile(fpath):
            os.remove(fpath)
    except Exception as e:
        current_app.logger.error(f"[Mobile API Photo Delete] Gagal hapus file {deleted}: {e}")

    proc.attachment_path = '|'.join(current_photos) if current_photos else None

    # Check minimum photo requirement
    req_min = proc.min_photos if proc.min_photos > 0 else (1 if proc.requires_attachment else 0)
    total_photos = len(current_photos)
    if req_min > 0 and total_photos < req_min:
        proc.is_completed = False
        proc.status = 'Pending'

    db.session.commit()

    total_procs = wo.procedures.count()
    completed_procs = wo.procedures.filter_by(is_completed=True).count()
    progress_pct = round((completed_procs / total_procs * 100)) if total_procs > 0 else 0

    return jsonify({
        'status': 'success',
        'message': 'Foto bukti berhasil dihapus.',
        'procedure': {
            'id': proc.id,
            'is_completed': proc.is_completed,
            'status': proc.status,
            'notes': proc.notes or '',
            'photos': [f"/static/{p}" for p in current_photos],
            'attachment_path': proc.attachment_path or ''
        },
        'progress_percent': progress_pct
    })


@mobile_api_bp.route('/work-orders/<int:id>/checklists', methods=['POST'])
@mobile_auth_required
def update_checklists(id):
    """
    Bulk or single update of checklist parameters
    Body:
    - items: [{"id": 12, "value": "220V"}, ...]
    or
    - id: 12
    - value: "220V"
    """
    data = request.get_json(silent=True) or request.form
    items = data.get('items')

    if items is None and 'id' in data:
        items = [{'id': data.get('id'), 'value': data.get('value')}]

    if not items or not isinstance(items, list):
        return jsonify({'status': 'error', 'message': 'Data checklist tidak valid.'}), 400

    updated_count = 0
    for item in items:
        chk_id = item.get('id')
        val = item.get('value')
        if chk_id:
            chk = WorkOrderChecklistParameter.query.filter_by(id=chk_id, work_order_id=id).first()
            if chk:
                chk.value = str(val).strip() if val is not None else ''
                updated_count += 1

    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': f'{updated_count} parameter checklist berhasil disimpan.'
    })


@mobile_api_bp.route('/parts', methods=['GET'])
@mobile_auth_required
def search_parts():
    """Search available spare parts for technician to add"""
    query = request.args.get('q', '').strip()
    parts_q = Part.query
    if query:
        search_like = f"%{query}%"
        parts_q = parts_q.filter(
            (Part.name.ilike(search_like)) |
            (Part.code.ilike(search_like))
        )

    parts = parts_q.limit(30).all()
    results = []
    for p in parts:
        results.append({
            'id': p.id,
            'code': p.code,
            'name': p.name,
            'unit': p.unit or 'Pcs',
            'price': p.price or 0.0
        })

    return jsonify({'status': 'success', 'data': results})


@mobile_api_bp.route('/work-orders/<int:id>/parts', methods=['POST'])
@mobile_auth_required
def add_work_order_part(id):
    """Add spare part used for work order"""
    user = g.current_user
    wo = WorkOrder.query.get(id)
    if not wo:
        return jsonify({'status': 'error', 'message': 'Work Order tidak ditemukan.'}), 404

    data = request.get_json(silent=True) or request.form
    part_id = data.get('part_id')
    quantity = float(data.get('quantity', 1.0) or 1.0)

    if not part_id:
        return jsonify({'status': 'error', 'message': 'Suku cadang wajib dipilih.'}), 400

    part = db.session.get(Part, int(part_id))
    if not part:
        return jsonify({'status': 'error', 'message': 'Suku cadang tidak ditemukan.'}), 404

    # Create WorkOrderPart
    w_part = WorkOrderPart(
        work_order_id=wo.id,
        part_id=part.id,
        quantity_used=quantity,
        date_added=datetime.utcnow()
    )
    db.session.add(w_part)

    # Log entry
    log_text = f"Penggunaan suku cadang: {part.name} ({quantity} {part.unit or 'Pcs'}) ditambahkan oleh {user.name}."
    db.session.add(WorkOrderLog(work_order_id=wo.id, user_id=user.id, log_text=log_text))

    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'Suku cadang berhasil ditambahkan.',
        'part': {
            'id': w_part.id,
            'part_id': part.id,
            'part_name': part.name,
            'part_code': part.code,
            'unit': part.unit or 'Pcs',
            'quantity_used': quantity
        }
    })


@mobile_api_bp.route('/work-orders/<int:id>/parts/<int:part_usage_id>', methods=['DELETE'])
@mobile_auth_required
def remove_work_order_part(id, part_usage_id):
    """Remove a used spare part from work order"""
    user = g.current_user
    w_part = WorkOrderPart.query.filter_by(id=part_usage_id, work_order_id=id).first()
    if not w_part:
        return jsonify({'status': 'error', 'message': 'Penggunaan suku cadang tidak ditemukan.'}), 404

    part_name = w_part.part.name if w_part.part else 'Suku Cadang'
    db.session.delete(w_part)

    log_text = f"Penggunaan suku cadang: {part_name} dihapus oleh {user.name}."
    db.session.add(WorkOrderLog(work_order_id=id, user_id=user.id, log_text=log_text))

    db.session.commit()
    return jsonify({
        'status': 'success',
        'message': 'Suku cadang berhasil dihapus.'
    })


@mobile_api_bp.route('/work-orders/<int:id>/tasklist_note', methods=['POST'])
@mobile_auth_required
def update_tasklist_note_mobile(id):
    user = g.current_user
    wo = WorkOrder.query.get(id)
    if not wo:
        return jsonify({'status': 'error', 'message': 'Work Order tidak ditemukan.'}), 404
        
    if not check_technician_wo_access(wo, user):
        return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403
        
    if wo.current_status and wo.current_status.control_type == 'Closed':
        return jsonify({'status': 'error', 'message': 'Work order sudah ditutup.'}), 400
        
    data = request.get_json(silent=True) or request.form
    note = (data.get('tasklist_note') or '').strip()
    wo.tasklist_note = note if note else None
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Catatan tasklist berhasil disimpan.',
        'tasklist_note': wo.tasklist_note or ''
    })


@mobile_api_bp.route('/work-orders/<int:id>/logs', methods=['POST'])
@mobile_auth_required
def add_work_order_log(id):
    """Add a work progress log/note to work order"""
    user = g.current_user
    wo = WorkOrder.query.get(id)
    if not wo:
        return jsonify({'status': 'error', 'message': 'Work Order tidak ditemukan.'}), 404

    data = request.get_json(silent=True) or request.form
    log_text = (data.get('log_text') or '').strip()

    if not log_text:
        return jsonify({'status': 'error', 'message': 'Catatan log tidak boleh kosong.'}), 400

    new_log = WorkOrderLog(
        work_order_id=wo.id,
        user_id=user.id,
        log_text=str(escape(log_text)),
        created_at=datetime.utcnow()
    )
    db.session.add(new_log)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'Catatan pekerjaan berhasil ditambahkan.',
        'log': {
            'id': new_log.id,
            'user_name': user.name,
            'log_text': new_log.log_text,
            'created_at': new_log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    })


@mobile_api_bp.route('/work-orders/<int:id>/signature', methods=['POST'])
@mobile_auth_required
def save_signatures(id):
    """
    Save customer and technician digital signatures
    Body:
    - technician_signature: base64 data URL
    - customer_signature: base64 data URL
    - customer_name: string
    - customer_title: string
    """
    user = g.current_user
    wo = WorkOrder.query.get(id)
    if not wo:
        return jsonify({'status': 'error', 'message': 'Work Order tidak ditemukan.'}), 404

    data = request.get_json(silent=True) or request.form

    if 'customer_name' in data:
        wo.customer_name = str(escape(data.get('customer_name') or ''))
    if 'customer_title' in data:
        wo.customer_title = str(escape(data.get('customer_title') or ''))

    if 'customer_signature' in data and data['customer_signature']:
        wo.customer_signature = data['customer_signature']

    if 'technician_signature' in data and data['technician_signature']:
        wo.technician_signature = data['technician_signature']

    # Create DigitalSignature hash entry
    if wo.customer_signature or wo.technician_signature:
        existing_sig = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
        if not existing_sig:
            signer = wo.customer_name or user.name
            title = wo.customer_title or 'Teknisi'
            sig_id = str(uuid.uuid4())
            ts = str(time.time())
            data_to_hash = f"{wo.code}|{signer}|{ts}"
            doc_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
            new_sig = DigitalSignature(
                id=sig_id,
                work_order_id=wo.id,
                signer_name=signer,
                signer_title=title,
                signed_at=datetime.utcnow(),
                document_hash=doc_hash,
                status='Valid'
            )
            db.session.add(new_sig)

    db.session.commit()
    log_mobile_audit(user.id, 'SIGNATURE_SAVED', 'WorkOrder', wo.id, 'Tanda tangan digital berhasil disimpan via Android')

    return jsonify({
        'status': 'success',
        'message': 'Tanda tangan digital berhasil disimpan.'
    })


# ==========================================================
# OFFLINE SYNC ENDPOINTS
# ==========================================================

@mobile_api_bp.route('/sync/download', methods=['GET'])
@mobile_auth_required
def sync_download():
    """
    Complete bundle download of all active work orders, procedures, checklists,
    parts catalog, and assets for offline execution.
    """
    user = g.current_user
    query = WorkOrder.query
    if user.role == 'Technician':
        query = query.filter(
            (WorkOrder.assigned_to == user.id) | 
            (WorkOrder.assignees.any(id=user.id))
        )
    elif user.site_id:
        query = query.join(Asset).filter(Asset.site_id == user.site_id)

    all_wos = query.all()
    active_wos = [w for w in all_wos if not (w.current_status and w.current_status.control_type == 'Closed')]

    wo_list = []
    proc_list = []
    chk_list = []
    parts_used_list = []
    logs_list = []

    for wo in active_wos:
        status_name = wo.current_status.name if wo.current_status else 'Draft'
        location_name = '-'
        site_name = '-'
        if wo.asset:
            if getattr(wo.asset, 'location', None):
                location_name = wo.asset.location.name or '-'
            if getattr(wo.asset, 'site', None):
                site_name = wo.asset.site.name or '-'

        wo_list.append({
            'id': wo.id,
            'code': wo.code or f"WO-{wo.id}",
            'description': wo.description or '',
            'priority': wo.priority or 'Medium',
            'status': status_name,
            'status_color': get_status_color(status_name),
            'maintenance_type': wo.maintenance_type or 'Corrective',
            'work_instructions': wo.work_instructions or '',
            'delay_reason': wo.delay_reason or '',
            'asset_id': wo.asset_id,
            'asset_name': wo.asset.name if wo.asset else '-',
            'asset_code': wo.asset.code if wo.asset else '-',
            'location': location_name,
            'site': site_name,
            'team': wo.team.name if wo.team else '-',
            'suggested_start_date': wo.suggested_start_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_start_date else None,
            'suggested_completion_date': wo.suggested_completion_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_completion_date else None,
            'start_date': wo.start_date.strftime('%Y-%m-%d %H:%M') if wo.start_date else None,
            'end_date': wo.end_date.strftime('%Y-%m-%d %H:%M') if wo.end_date else None,
            'customer_name': wo.customer_name or '',
            'customer_title': wo.customer_title or '',
            'customer_signature': wo.customer_signature or '',
            'technician_signature': wo.technician_signature or ''
        })

        # Procedures
        for proc in wo.procedures:
            proc_list.append({
                'id': proc.id,
                'work_order_id': proc.work_order_id,
                'name': proc.name,
                'requires_attachment': bool(proc.requires_attachment),
                'min_photos': int(getattr(proc, 'min_photos', 0) or 0),
                'estimated_minutes': int(getattr(proc, 'estimated_minutes', 0) or 0),
                'is_completed': bool(proc.is_completed),
                'status': proc.status or 'Pending',
                'notes': proc.notes or '',
                'attachment_path': proc.attachment_path or '',
                'synced': 1
            })

        # Checklists
        for chk in wo.checklist_parameters:
            chk_list.append({
                'id': chk.id,
                'work_order_id': chk.work_order_id,
                'parameter': chk.parameter,
                'standard': chk.standard or '',
                'value': chk.value or '',
                'synced': 1
            })

        # Used parts
        for wp in wo.used_parts:
            parts_used_list.append({
                'id': wp.id,
                'work_order_id': wp.work_order_id,
                'part_id': wp.part_id,
                'part_name': wp.part.name if wp.part else '-',
                'part_code': wp.part.code if wp.part else '-',
                'unit': wp.part.unit if wp.part else 'Pcs',
                'quantity_used': wp.quantity_used or 1.0,
                'synced': 1
            })

        # Logs
        for lg in wo.logs:
            logs_list.append({
                'id': lg.id,
                'work_order_id': lg.work_order_id,
                'user_name': lg.user.name if lg.user else 'System',
                'log_text': lg.log_text,
                'created_at': lg.created_at.strftime('%Y-%m-%d %H:%M:%S') if lg.created_at else None,
                'synced': 1
            })

    # Parts catalog for offline addition
    parts_catalog = [
        {'id': p.id, 'code': p.code, 'name': p.name, 'unit': p.unit or 'Pcs'}
        for p in Part.query.limit(100).all()
    ]

    return jsonify({
        'status': 'success',
        'server_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'counts': {
            'work_orders': len(wo_list),
            'procedures': len(proc_list),
            'checklists': len(chk_list),
            'parts_used': len(parts_used_list),
            'logs': len(logs_list)
        },
        'work_orders': wo_list,
        'procedures': proc_list,
        'checklists': chk_list,
        'parts_used': parts_used_list,
        'logs': logs_list,
        'parts_catalog': parts_catalog
    })


@mobile_api_bp.route('/sync/upload', methods=['POST'])
@mobile_auth_required
def sync_upload():
    """
    Batch upload from mobile outbox queue when re-connected.
    Accepts JSON or multipart/form-data with photos and JSON payload strings.
    """
    user = g.current_user
    payload_str = request.form.get('payload')
    data = json.loads(payload_str) if payload_str else (request.get_json(silent=True) or {})

    procedures_data = data.get('procedures', [])
    checklists_data = data.get('checklists', [])
    status_changes = data.get('status_changes', [])
    logs_data = data.get('logs', [])
    signatures_data = data.get('signatures', [])
    parts_data = data.get('parts', [])

    updated_procs = 0
    updated_chks = 0
    updated_statuses = 0
    added_logs = 0
    saved_signatures = 0
    added_parts = 0

    try:
        # 1. Process Status Changes
        action_map = {'start': 'In Progress', 'hold': 'Hold', 'resume': 'In Progress', 'solve': 'Solved'}
        for sc in status_changes:
            wo_id = sc.get('work_order_id')
            action = (sc.get('action') or '').lower()
            reason = sc.get('reason')
            wo = WorkOrder.query.get(wo_id)
            if wo and action in action_map:
                t_name = action_map[action]
                t_stat = WorkOrderStatus.query.filter_by(name=t_name).first()
                if t_stat:
                    wo.status_id = t_stat.id
                if action == 'start' and not wo.start_date:
                    wo.start_date = datetime.utcnow()
                elif action == 'hold':
                    wo.delay_reason = reason or wo.delay_reason
                elif action == 'solve':
                    wo.end_date = datetime.utcnow()
                    if wo.start_date:
                        wo.estimated_hours = round((wo.end_date - wo.start_date).total_seconds() / 3600, 2)
                updated_statuses += 1

        # 2. Process Procedures
        for p_item in procedures_data:
            p_id = p_item.get('id')
            proc = WorkOrderProcedure.query.get(p_id)
            if proc:
                proc.is_completed = bool(p_item.get('is_completed', True))
                proc.status = p_item.get('status', 'Done' if proc.is_completed else 'Pending')
                if 'notes' in p_item:
                    proc.notes = p_item['notes']
                proc.completed_at = datetime.utcnow()
                proc.completed_by_id = user.id
                updated_procs += 1

        # 2.1 Process Deleted Photos
        for d_item in data.get('deleted_photos', []):
            dp_id = d_item.get('procedure_id')
            dp_path = d_item.get('photo_path')
            if dp_id and dp_path:
                d_proc = WorkOrderProcedure.query.get(dp_id)
                if d_proc and d_proc.attachment_path:
                    norm = dp_path.replace('/static/', '').strip()
                    cur_p = [p.strip() for p in d_proc.attachment_path.split('|') if p.strip()]
                    cur_p = [p for p in cur_p if p != norm and not p.endswith(norm)]
                    d_proc.attachment_path = '|'.join(cur_p) if cur_p else None
                    req_min = d_proc.min_photos if d_proc.min_photos > 0 else (1 if d_proc.requires_attachment else 0)
                    if req_min > 0 and len(cur_p) < req_min:
                        d_proc.is_completed = False
                        d_proc.status = 'Pending'

        # 3. Process Checklists
        for c_item in checklists_data:
            c_id = c_item.get('id')
            chk = WorkOrderChecklistParameter.query.get(c_id)
            if chk:
                chk.value = str(c_item.get('value', ''))
                updated_chks += 1

        # 4. Process Logs
        for l_item in logs_data:
            wo_id = l_item.get('work_order_id')
            text_val = l_item.get('log_text')
            if wo_id and text_val:
                db.session.add(WorkOrderLog(
                    work_order_id=wo_id,
                    user_id=user.id,
                    log_text=text_val,
                    created_at=datetime.utcnow()
                ))
                added_logs += 1

        # 5. Process Signatures
        for s_item in signatures_data:
            wo_id = s_item.get('work_order_id')
            wo = WorkOrder.query.get(wo_id)
            if wo:
                if s_item.get('customer_name'):
                    wo.customer_name = s_item['customer_name']
                if s_item.get('customer_title'):
                    wo.customer_title = s_item['customer_title']
                if s_item.get('customer_signature'):
                    wo.customer_signature = s_item['customer_signature']
                if s_item.get('technician_signature'):
                    wo.technician_signature = s_item['technician_signature']
                saved_signatures += 1

        # 6. Process Parts
        for pt_item in parts_data:
            wo_id = pt_item.get('work_order_id')
            part_id = pt_item.get('part_id')
            qty = float(pt_item.get('quantity', 1.0) or 1.0)
            if wo_id and part_id:
                w_pt = WorkOrderPart(
                    work_order_id=wo_id,
                    part_id=part_id,
                    quantity_used=qty,
                    date_added=datetime.utcnow()
                )
                db.session.add(w_pt)
                added_parts += 1

        # 7. Process Photo Attachments
        uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        for key, file in request.files.items():
            if key.startswith('file_') and file and file.filename:
                # Key format: file_<proc_id>_<timestamp>
                parts = key.split('_')
                if len(parts) >= 2:
                    try:
                        proc_id = int(parts[1])
                        proc = WorkOrderProcedure.query.get(proc_id)
                        if proc:
                            fname = secure_filename(f"wo{proc.work_order_id}_proc{proc_id}_sync_{file.filename}")
                            fpath = os.path.join(uploads_dir, fname)
                            file.save(fpath)
                            rel_p = f"uploads/{fname}"
                            cur = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]
                            if rel_p not in cur:
                                cur.append(rel_p)
                            proc.attachment_path = '|'.join(cur)
                    except Exception as fe:
                        current_app.logger.error(f"[Sync Upload] Gagal upload foto {key}: {fe}")

        db.session.commit()
        log_mobile_audit(user.id, 'SYNC_UPLOAD_SUCCESS', details=f"Sync batch sukses: {updated_procs} prosedur, {updated_chks} checklist, {updated_statuses} status")

        return jsonify({
            'status': 'success',
            'message': 'Sinkronisasi data offline berhasil diterapkan ke server.',
            'results': {
                'updated_procedures': updated_procs,
                'updated_checklists': updated_chks,
                'updated_statuses': updated_statuses,
                'added_logs': added_logs,
                'saved_signatures': saved_signatures,
                'added_parts': added_parts
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[Sync Upload Error] {e}")
        return jsonify({
            'status': 'error',
            'message': f"Terjadi kesalahan saat sinkronisasi batch: {str(e)}"
        }), 500
