from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from models import db, WorkOrder, User, WorkOrderStatus
from datetime import datetime, timezone, timedelta, date
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import extract

def get_wib_now():
    """Mengembalikan waktu saat ini dalam zona waktu WIB (UTC+7 / Asia/Jakarta)"""
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)

schedule_bp = Blueprint('schedule', __name__, template_folder='templates/schedule')

def get_or_create_kantor_pusat():
    from models import Site
    kp = Site.query.filter(Site.name.ilike('%Kantor Pusat%')).first()
    if not kp:
        kp = Site(
            name='Kantor Pusat',
            address='Kantor Pusat',
            timezone='Asia/Jakarta',
            project_code='HQ'
        )
        db.session.add(kp)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            kp = Site.query.filter(Site.name.ilike('%Kantor Pusat%')).first()
    return kp

def ensure_kantor_pusat_shifts(kp_site_id):
    from models import Shift
    reg_shift = Shift.query.filter_by(site_id=kp_site_id, is_off_day=False).first()
    if not reg_shift:
        reg_shift = Shift(
            site_id=kp_site_id,
            name='Reguler (09:00 - 17:00)',
            start_time=datetime.strptime('09:00', '%H:%M').time(),
            end_time=datetime.strptime('17:00', '%H:%M').time(),
            is_off_day=False
        )
        db.session.add(reg_shift)
    else:
        if not reg_shift.start_time or reg_shift.start_time.strftime('%H:%M') != '09:00' or reg_shift.end_time.strftime('%H:%M') != '17:00':
            reg_shift.name = 'Reguler (09:00 - 17:00)'
            reg_shift.start_time = datetime.strptime('09:00', '%H:%M').time()
            reg_shift.end_time = datetime.strptime('17:00', '%H:%M').time()
            reg_shift.is_off_day = False

    off_shift = Shift.query.filter_by(site_id=kp_site_id, is_off_day=True).filter(~Shift.name.ilike('%cuti%')).first()
    if not off_shift:
        off_shift = Shift(
            site_id=kp_site_id,
            name='Libur / Off Day',
            start_time=datetime.strptime('00:00', '%H:%M').time(),
            end_time=datetime.strptime('00:00', '%H:%M').time(),
            is_off_day=True
        )
        db.session.add(off_shift)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return reg_shift, off_shift

def get_kantor_pusat_users(kp_site_id):
    from models import User
    # Karyawan kantor pusat: user dengan site_id == kp_site_id atau site_id is None
    users = User.query.filter(
        (User.site_id == kp_site_id) | (User.site_id.is_(None))
    ).filter(User.role != 'Admin').all()
    if not users:
        users = User.query.filter(
            (User.site_id == kp_site_id) | (User.site_id.is_(None))
        ).all()
    return users

def ensure_kantor_pusat_schedule(kp_site_id, start_date=None, end_date=None, force_update=False):
    from models import Shift, UserShift, User
    from sqlalchemy import text
    try:
        db.session.execute(text('ALTER TABLE user_shift ADD COLUMN notes TEXT;'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    reg_shift, off_shift = ensure_kantor_pusat_shifts(kp_site_id)
    users = get_kantor_pusat_users(kp_site_id)
    if not users:
        return 0

    user_ids = [u.id for u in users]
    today = datetime.now().date()

    if not start_date:
        start_date = today - timedelta(days=60)
    if not end_date:
        end_date = today + timedelta(days=90)

    existing_shifts = UserShift.query.filter(
        UserShift.user_id.in_(user_ids),
        UserShift.date >= start_date,
        UserShift.date <= end_date
    ).all()
    existing_map = {(s.user_id, s.date): s for s in existing_shifts}

    new_shifts = []
    updated_count = 0
    curr = start_date
    while curr <= end_date:
        is_weekend = curr.weekday() >= 5  # 5=Sabtu, 6=Minggu
        target_shift_id = off_shift.id if is_weekend else reg_shift.id

        for uid in user_ids:
            key = (uid, curr)
            if key not in existing_map:
                new_shifts.append(UserShift(
                    user_id=uid,
                    shift_id=target_shift_id,
                    date=curr
                ))
                updated_count += 1
            elif force_update:
                existing_shift = existing_map[key]
                # Do not overwrite external site deployment shifts or cuti
                if existing_shift.shift and existing_shift.shift.site_id == kp_site_id and not existing_shift.shift.name.lower().startswith('cuti'):
                    if existing_shift.shift_id != target_shift_id:
                        existing_shift.shift_id = target_shift_id
                        updated_count += 1
        curr += timedelta(days=1)

    if new_shifts:
        try:
            db.session.bulk_save_objects(new_shifts)
            db.session.commit()
        except Exception:
            db.session.rollback()
            try:
                for i in range(0, len(new_shifts), 100):
                    db.session.add_all(new_shifts[i:i+100])
                    db.session.commit()
            except Exception:
                db.session.rollback()
    elif force_update and updated_count > 0:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return updated_count

def get_or_create_kantor_pusat_user_shift(user_id, date_val, kp_site_id=None):
    from models import UserShift, Site
    user_shift = UserShift.query.filter_by(user_id=user_id, date=date_val).first()
    if user_shift:
        return user_shift
    if not kp_site_id:
        kp = get_or_create_kantor_pusat()
        kp_site_id = kp.id
    reg_shift, off_shift = ensure_kantor_pusat_shifts(kp_site_id)
    is_weekend = date_val.weekday() >= 5
    target_shift_id = off_shift.id if is_weekend else reg_shift.id
    user_shift = UserShift(
        user_id=user_id,
        shift_id=target_shift_id,
        date=date_val
    )
    db.session.add(user_shift)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        user_shift = UserShift.query.filter_by(user_id=user_id, date=date_val).first()
    return user_shift

@schedule_bp.route('/')
@schedule_bp.route('/schedule')
@schedule_bp.route('/schedule/')
@login_required
def index():
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Langsung masuk ke schedule Kantor Pusat (pemetaan teknisi)
    kp = get_or_create_kantor_pusat()
    return redirect(url_for('schedule.site_schedule', site_id=kp.id))

@schedule_bp.route('/site/<int:site_id>')
@login_required
def site_schedule(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    from models import Site, Shift, UserShift, Team
    site = Site.query.get_or_404(site_id)
    is_kp = 'kantor pusat' in site.name.lower()
    
    # Ensure supervisor can only see their site
    if current_user.role != 'Admin' and current_user.site_id and current_user.site_id != site.id and not (is_kp and current_user.site_id is None):
        flash('Access denied.', 'danger')
        return redirect(url_for('schedule.index'))

    if is_kp:
        ensure_kantor_pusat_shifts(site.id)
        base_technicians = get_kantor_pusat_users(site.id)
    else:
        base_technicians = User.query.filter(User.role != 'Admin', User.site_id == site.id).all()

    # Also include any technician/user who has shifts assigned at this site
    site_shifts = Shift.query.filter_by(site_id=site.id).all()
    site_shift_ids = [s.id for s in site_shifts]
    extra_technicians = []
    if site_shift_ids:
        extra_uids = [r[0] for r in db.session.query(UserShift.user_id).filter(UserShift.shift_id.in_(site_shift_ids)).distinct().all() if r[0]]
        if extra_uids:
            extra_technicians = User.query.filter(User.id.in_(extra_uids)).all()

    tech_map = {t.id: t for t in base_technicians}
    for t in extra_technicians:
        tech_map[t.id] = t
    technicians = sorted(list(tech_map.values()), key=lambda x: (x.name or '').lower())
    teams = Team.query.filter_by(site_id=site.id).all()

    # Get all sites for deployment dropdown (exclude Kantor Pusat)
    all_sites = Site.query.filter(~Site.name.ilike('%kantor pusat%')).order_by(Site.name).all()

    return render_template('schedule/site_schedule.html', site=site, technicians=technicians, teams=teams, is_kantor_pusat=is_kp, all_sites=all_sites)

@schedule_bp.route('/api/shifts/<int:site_id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def api_shifts(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    from models import Shift
    
    if request.method == 'GET':
        from models import Site
        site = Site.query.get(site_id)
        if site and 'kantor pusat' in site.name.lower():
            ensure_kantor_pusat_shifts(site_id)
        shifts = Shift.query.filter_by(site_id=site_id).all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'start_time': s.start_time.strftime('%H:%M') if s.start_time else '-',
            'end_time': s.end_time.strftime('%H:%M') if s.end_time else '-',
            'is_off_day': s.is_off_day
        } for s in shifts])
        
    elif request.method == 'PUT':
        data = request.json
        shift_id = data.get('id')
        shift = Shift.query.get(shift_id)
        if not shift or shift.site_id != site_id:
            return jsonify({'success': False, 'error': 'Shift not found'}), 404
            
        shift.name = data.get('name')
        shift.is_off_day = bool(data.get('is_off_day', False))
        if not shift.is_off_day:
            shift.start_time = datetime.strptime(data.get('start_time', '00:00'), '%H:%M').time()
            shift.end_time = datetime.strptime(data.get('end_time', '00:00'), '%H:%M').time()
        else:
            shift.start_time = datetime.strptime('00:00', '%H:%M').time()
            shift.end_time = datetime.strptime('00:00', '%H:%M').time()
            
        try:
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
            
    elif request.method == 'POST':
        data = request.json
        is_off_day = bool(data.get('is_off_day', False))
        if not is_off_day:
            start_t = datetime.strptime(data.get('start_time', '00:00'), '%H:%M').time()
            end_t = datetime.strptime(data.get('end_time', '00:00'), '%H:%M').time()
        else:
            start_t = datetime.strptime('00:00', '%H:%M').time()
            end_t = datetime.strptime('00:00', '%H:%M').time()
            
        shift = Shift(
            site_id=site_id,
            name=data.get('name'),
            start_time=start_t,
            end_time=end_t,
            is_off_day=is_off_day
        )
        db.session.add(shift)
        try:
            db.session.commit()
            return jsonify({'success': True, 'id': shift.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
            
    elif request.method == 'DELETE':
        shift_id = request.args.get('id')
        shift = Shift.query.get_or_404(shift_id)
        db.session.delete(shift)
        try:
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/shift_assignments/<int:site_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_shift_assignments(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    from models import Shift, UserShift
    
    if request.method == 'GET':
        from models import Site
        from sqlalchemy.orm import joinedload, selectinload
        from datetime import timedelta
        site = Site.query.get(site_id)
        is_kp = bool(site and 'kantor pusat' in site.name.lower())
        
        start_str = request.args.get('start')
        end_str = request.args.get('end')
        
        start_date = None
        end_date = None
        if start_str:
            try:
                start_date = datetime.strptime(start_str.split('T')[0], '%Y-%m-%d').date()
            except Exception:
                start_date = None
        if end_str:
            try:
                end_date = datetime.strptime(end_str.split('T')[0], '%Y-%m-%d').date()
            except Exception:
                end_date = None

        if is_kp:
            ensure_kantor_pusat_shifts(site_id)
            if start_date and end_date:
                ensure_kantor_pusat_schedule(site_id, start_date=start_date, end_date=end_date)
            else:
                ensure_kantor_pusat_schedule(site_id)

        mode = request.args.get('mode', 'plan')

        if is_kp and mode == 'plan':
            # Sinkronisasi work order aktif agar selalu update dengan schedule
            try:
                sync_active_work_orders_to_schedule()
            except Exception:
                db.session.rollback()

            # Kantor Pusat Schedule Plan: HANYA untuk nama-nama teknisi dan site yang di-deploy!
            kp_users = get_kantor_pusat_users(site_id)
            kp_user_ids = [u.id for u in kp_users]

            deploy_query = UserShift.query.options(
                joinedload(UserShift.user),
                joinedload(UserShift.shift).joinedload(Shift.site)
            ).join(Shift).filter(
                Shift.site_id != site_id,
                db.or_(
                    UserShift.user_id.in_(kp_user_ids),
                    UserShift.notes.ilike('WO%')
                )
            )

            if start_date:
                deploy_query = deploy_query.filter(UserShift.date >= start_date)
            if end_date:
                deploy_query = deploy_query.filter(UserShift.date <= end_date)

            deployed_assignments = deploy_query.order_by(UserShift.date.asc(), UserShift.id.asc()).all()

            # Kelompokkan hari-hari penugasan berturut-turut menjadi 1 bar panjang (multi-day span) di kalender
            groups = {}
            for a in deployed_assignments:
                site_id_val = a.shift.site_id if a.shift else None
                key = (a.user_id, site_id_val, (getattr(a, 'notes', '') or '').strip())
                if key not in groups:
                    groups[key] = []
                groups[key].append(a)

            events = []
            for (u_id, s_id, note_val), items in groups.items():
                items.sort(key=lambda x: x.date)
                
                spans = []
                current_span = [items[0]]
                for item in items[1:]:
                    prev_item = current_span[-1]
                    if item.date == prev_item.date + timedelta(days=1):
                        current_span.append(item)
                    elif item.date == prev_item.date:
                        current_span.append(item)
                    else:
                        spans.append(current_span)
                        current_span = [item]
                if current_span:
                    spans.append(current_span)

                for span in spans:
                    first_item = span[0]
                    last_item = span[-1]
                    dest_site_name = first_item.shift.site.name if (first_item.shift and first_item.shift.site) else 'Site Lain'
                    user_name = first_item.user.name if first_item.user else 'Teknisi'
                    user_nrp = first_item.user.nrp if (first_item.user and first_item.user.nrp) else ''

                    start_iso = first_item.date.isoformat()
                    # FullCalendar exclusive end date: last_date + 1 day
                    end_exclusive = last_item.date + timedelta(days=1)
                    end_iso = end_exclusive.isoformat()

                    is_multiday = (last_item.date > first_item.date)
                    day_count = (last_item.date - first_item.date).days + 1

                    if is_multiday:
                        title_text = f"{user_name} - {dest_site_name} ({day_count} Hari)"
                    else:
                        title_text = f"{user_name} - {dest_site_name}"

                    color = '#0284c7'  # Sky Blue

                    expected_time = f"{first_item.shift.start_time.strftime('%H:%M')} - {first_item.shift.end_time.strftime('%H:%M')}" if (first_item.shift and first_item.shift.start_time and first_item.shift.end_time) else (first_item.shift.name if first_item.shift else '-')

                    all_ids = [item.id for item in span]
                    primary_id = first_item.id

                    events.append({
                        'id': primary_id,
                        'title': title_text,
                        'start': start_iso,
                        'end': end_iso,
                        'backgroundColor': color,
                        'borderColor': color,
                        'allDay': True,
                        'order': 1,
                        'extendedProps': {
                            'user_id': first_item.user_id,
                            'user_name': user_name,
                            'user_nrp': user_nrp,
                            'shift_id': first_item.shift_id,
                            'shift_name': first_item.shift.name if first_item.shift else 'Penugasan',
                            'is_off_day': False,
                            'site_id': first_item.shift.site_id if first_item.shift else None,
                            'site_name': dest_site_name,
                            'is_deployed': True,
                            'notes': note_val,
                            'is_multiday': is_multiday,
                            'day_count': day_count,
                            'start_date': start_iso,
                            'end_date': last_item.date.isoformat(),
                            'assignment_ids': all_ids,
                            'expected_time': expected_time,
                            'actual_in': '-',
                            'actual_out': '-',
                            'status': f'Deploy ke {dest_site_name}'
                        }
                    })
            return jsonify(events)

        # Get all shifts for this site to filter user_shifts
        shifts = Shift.query.filter_by(site_id=site_id).all()
        shift_ids = [s.id for s in shifts]
        
        assign_query = UserShift.query.options(
            joinedload(UserShift.user),
            joinedload(UserShift.shift).joinedload(Shift.site),
            selectinload(UserShift.attendance_records)
        )
        if is_kp and mode == 'realisasi':
            kp_users = get_kantor_pusat_users(site_id)
            kp_user_ids = [u.id for u in kp_users]
            assign_query = assign_query.filter(
                (UserShift.shift_id.in_(shift_ids)) | (UserShift.user_id.in_(kp_user_ids))
            )
        else:
            assign_query = assign_query.filter(UserShift.shift_id.in_(shift_ids))
        
        if start_date:
            assign_query = assign_query.filter(UserShift.date >= start_date)
        if end_date:
            assign_query = assign_query.filter(UserShift.date <= end_date)
            
        assignments = assign_query.all()
        
        # Load leaves for this site
        from models import EmployeeLeave, EmployeeOvertime
        leave_query = EmployeeLeave.query.options(
            joinedload(EmployeeLeave.user),
            joinedload(EmployeeLeave.replacement_user),
            joinedload(EmployeeLeave.original_shift)
        ).filter_by(status='Approved')
        
        if is_kp:
            leave_query = leave_query.filter(
                (EmployeeLeave.site_id == site_id) | (EmployeeLeave.site_id.is_(None))
            )
        else:
            leave_query = leave_query.filter_by(site_id=site_id)
            
        if start_date:
            leave_query = leave_query.filter(EmployeeLeave.end_date >= start_date)
        if end_date:
            leave_query = leave_query.filter(EmployeeLeave.start_date <= end_date)
            
        site_leaves = leave_query.all()
        
        # Load overtimes for this site
        ot_query = EmployeeOvertime.query.options(
            joinedload(EmployeeOvertime.user)
        ).filter_by(status='Approved')
        
        if is_kp:
            ot_query = ot_query.filter(
                (EmployeeOvertime.site_id == site_id) | (EmployeeOvertime.site_id.is_(None))
            )
        else:
            ot_query = ot_query.filter_by(site_id=site_id)
            
        if start_date:
            ot_query = ot_query.filter(EmployeeOvertime.end_date >= start_date)
        if end_date:
            ot_query = ot_query.filter(EmployeeOvertime.start_date <= end_date)
            
        site_overtimes = ot_query.all()
        
        leave_map = {}
        replacing_map = {}
        for l in site_leaves:
            curr_d = max(l.start_date, start_date) if start_date else l.start_date
            last_d = min(l.end_date, end_date) if end_date else l.end_date
            while curr_d <= last_d:
                leave_map[(l.user_id, curr_d)] = l
                if l.replacement_user_id and l.replacement_user:
                    replacing_map[(l.replacement_user_id, curr_d)] = {
                        'for_name': l.user.name if l.user else 'Karyawan',
                        'leave_type': l.leave_type,
                        'is_shift_swap': bool(l.is_shift_swap)
                    }
                curr_d += timedelta(days=1)
        
        # Load overtimes for this site
        overtime_map = {}
        for ot in site_overtimes:
            curr_d = max(ot.start_date, start_date) if start_date else ot.start_date
            last_d = min(ot.end_date, end_date) if end_date else ot.end_date
            while curr_d <= last_d:
                overtime_map[(ot.user_id, curr_d)] = ot
                curr_d += timedelta(days=1)

        # Load attendance records map by (user_id, date) and (nrp, date)
        from models import AttendanceRecord
        att_filter = []
        if start_date:
            att_filter.append(AttendanceRecord.date >= start_date)
        if end_date:
            att_filter.append(AttendanceRecord.date <= end_date)
        
        all_att_records = AttendanceRecord.query.filter(*att_filter).all() if att_filter else AttendanceRecord.query.all()
        attendance_map = {}
        for rec_item in all_att_records:
            if rec_item.user_id:
                attendance_map[(rec_item.user_id, rec_item.date)] = rec_item
            if rec_item.nrp:
                attendance_map[(str(rec_item.nrp).strip(), rec_item.date)] = rec_item
        
        # mode already extracted above
        
        if mode == 'cuti':
            cuti_events = []
            for l in site_leaves:
                curr_d = l.start_date
                while curr_d <= l.end_date:
                    u_name = l.user.name if l.user else 'Karyawan'
                    rep_name = l.replacement_user.name if (l.replacement_user_id and l.replacement_user) else None
                    
                    rep_txt = ""
                    bg_color = "#eab308" # Yellow
                    if l.replacement_status == 'assigned' and rep_name:
                        rep_txt = f" (Pengganti: {rep_name})"
                        bg_color = "#f59e0b"
                    elif l.replacement_status == 'pending':
                        rep_txt = " [Butuh Pengganti]"
                        bg_color = "#ef4444"
                    elif l.replacement_status == 'not_needed':
                        bg_color = "#94a3b8"
                    
                    # Cuti person event (Off Day karena cuti)
                    cuti_events.append({
                        'id': f"leave-{l.id}-{curr_d.isoformat()}",
                        'title': f"{u_name} - {l.leave_type}{rep_txt}",
                        'start': curr_d.isoformat(),
                        'backgroundColor': bg_color,
                        'borderColor': bg_color,
                        'allDay': True,
                        'order': 100,
                        'extendedProps': {
                            'user_id': l.user_id,
                            'user_name': u_name,
                            'shift_id': l.original_shift_id,
                            'shift_name': l.original_shift.name if l.original_shift else 'Cuti',
                            'is_off_day': True,
                            'expected_time': 'Off Day (Cuti)',
                            'actual_in': '-',
                            'actual_out': '-',
                            'status': f'Cuti ({l.leave_type})',
                            'is_cuti': True,
                            'leave_id': l.id,
                            'leave_type': l.leave_type,
                            'leave_reason': l.reason or '-',
                            'replacement_status': l.replacement_status,
                            'replacement_name': rep_name,
                            'is_replacement': False,
                            'is_shift_swap': bool(l.is_shift_swap),
                            'is_overtime': False
                        }
                    })
                    
                    # Replacement event
                    if l.replacement_status == 'assigned' and l.replacement_user:
                        swap_text = "Pindah Shift" if l.is_shift_swap else "Masuk Ganti"
                        cuti_events.append({
                            'id': f"leave-rep-{l.id}-{curr_d.isoformat()}",
                            'title': f"{rep_name} - {swap_text} {u_name}",
                            'start': curr_d.isoformat(),
                            'backgroundColor': '#0ea5e9',
                            'borderColor': '#0284c7',
                            'allDay': True,
                            'order': 101,
                            'extendedProps': {
                                'user_id': l.replacement_user_id,
                                'user_name': rep_name,
                                'shift_id': l.original_shift_id,
                                'shift_name': l.original_shift.name if l.original_shift else 'Pengganti',
                                'is_off_day': False,
                                'expected_time': f"Menggantikan shift {l.original_shift.name if l.original_shift else 'Cuti'}",
                                'actual_in': '-',
                                'actual_out': '-',
                                'status': 'Pengganti Cuti',
                                'is_cuti': False,
                                'leave_id': l.id,
                                'leave_type': l.leave_type,
                                'leave_reason': l.reason or '-',
                                'replacement_status': 'assigned',
                                'replacement_name': rep_name,
                                'is_replacement': True,
                                'replacing_user_name': u_name,
                                'is_shift_swap': bool(l.is_shift_swap),
                                'is_overtime': False
                            }
                        })
                    curr_d += timedelta(days=1)
            return jsonify(cuti_events)
            
        if mode == 'lembur':
            lembur_events = []
            for ot in site_overtimes:
                curr_d = ot.start_date
                while curr_d <= ot.end_date:
                    u_name = ot.user.name if ot.user else 'Teknisi'
                    lembur_events.append({
                        'id': f"ot-{ot.id}-{curr_d.isoformat()}",
                        'title': f"{u_name} - Lembur ({ot.start_time.strftime('%H:%M')} - {ot.end_time.strftime('%H:%M')}) [{ot.duration_hours} Jam]",
                        'start': curr_d.isoformat(),
                        'backgroundColor': '#8b5cf6',
                        'borderColor': '#7c3aed',
                        'allDay': True,
                        'order': 100,
                        'extendedProps': {
                            'user_id': ot.user_id,
                            'user_name': u_name,
                            'shift_id': None,
                            'shift_name': 'Lembur',
                            'is_off_day': False,
                            'expected_time': f"{ot.start_time.strftime('%H:%M')} - {ot.end_time.strftime('%H:%M')}",
                            'actual_in': "-",
                            'actual_out': "-",
                            'status': 'Lembur',
                            'is_cuti': False,
                            'is_overtime': True,
                            'overtime_id': ot.id,
                            'overtime_start': f"{ot.start_date.strftime('%d/%m/%Y')} {ot.start_time.strftime('%H:%M')}",
                            'overtime_end': f"{ot.end_date.strftime('%d/%m/%Y')} {ot.end_time.strftime('%H:%M')}",
                            'overtime_hours': ot.duration_hours,
                            'overtime_reason': ot.reason or '-'
                        }
                    })
                    curr_d += timedelta(days=1)
            return jsonify(lembur_events)

        events = []
        assigned_user_dates = set()
        for a in assignments:
            assigned_user_dates.add((a.user_id, a.date))
            shift_name = a.shift.name.lower()
            
            # Default Plan colors
            color = '#94a3b8' # Default slate
            if 'siang' in shift_name:
                color = '#22c55e' # Green
            elif 'pagi' in shift_name:
                color = '#0ea5e9' # Blue
            elif 'reguler' in shift_name:
                color = '#6b7280' # Gray
            elif 'cuti' in shift_name:
                color = '#eab308' # Yellow
            elif 'libur' in shift_name:
                color = '#ef4444' # Red

            if a.shift.is_off_day:
                order = 9999
            elif a.shift.start_time:
                order = a.shift.start_time.hour * 60 + a.shift.start_time.minute
            else:
                order = 0
                
            status_badge = ""
            actual_color = None
            
            ot_info = overtime_map.get((a.user_id, a.date))
            has_ot = bool(ot_info)
            
            rec = None
            if a.attendance_records:
                rec = a.attendance_records[0]
            if not rec and a.user_id:
                rec = attendance_map.get((a.user_id, a.date))
            if not rec and a.user and a.user.nrp:
                rec = attendance_map.get((str(a.user.nrp).strip(), a.date))

            if rec:
                rec_status = rec.status
                if a.shift.is_off_day:
                    if rec.jam_masuk:
                        rec_status = 'Lembur Hari Libur' if has_ot else 'Hadir dalam Waktu Libur'
                    else:
                        rec_status = 'Libur'
                elif not rec_status or rec_status in ['Hadir', 'Tanpa Jadwal', 'Tidak Ada Jadwal']:
                    status_list = []
                    if rec.jam_masuk and a.shift.start_time and rec.jam_masuk.time() > a.shift.start_time:
                        status_list.append('Terlambat')
                    if rec.jam_pulang and a.shift.end_time and a.shift.start_time:
                        s_end = datetime.combine(rec.date, a.shift.end_time)
                        if a.shift.end_time <= a.shift.start_time:
                            s_end += timedelta(days=1)
                        if rec.jam_pulang < s_end:
                            status_list.append('Pulang Cepat')
                    if not rec.jam_masuk: status_list.append('Tidak Absen Masuk')
                    if not rec.jam_pulang: status_list.append('Tidak Absen Pulang')
                    rec_status = ' & '.join(status_list) if status_list else 'Sesuai Jadwal'
                elif 'Lembur' in rec_status and not has_ot:
                    rec_status = rec_status.replace('Lembur', '').strip(' &').strip() or 'Sesuai Jadwal'
                
                if rec_status == 'Sesuai Jadwal':
                    status_badge = " [Ontime]"
                    actual_color = '#22c55e' # Green
                elif 'Terlambat' in rec_status or 'Pulang Cepat' in rec_status:
                    status_badge = f" [{rec_status}]"
                    actual_color = '#eab308' # Yellow
                elif rec_status == 'Hadir dalam Waktu Libur':
                    status_badge = " [Hadir dalam Waktu Libur]"
                    actual_color = '#0284c7' # Sky blue
                elif 'Lembur' in rec_status:
                    if has_ot:
                        status_badge = " [Lembur]"
                        actual_color = '#8b5cf6' # Purple
                    else:
                        status_badge = " [Hadir dalam Waktu Libur]" if a.shift.is_off_day else ""
                        actual_color = '#0284c7' if a.shift.is_off_day else '#94a3b8'
                elif rec_status == 'Libur':
                    status_badge = ""
                    actual_color = '#94a3b8' # Gray
                else:
                    status_badge = f" [{rec_status}]"
                    actual_color = '#94a3b8' # Gray
            elif a.date < datetime.today().date() and not a.shift.is_off_day:
                status_badge = " [Alpha]"
                actual_color = '#ef4444' # Red
            else:
                actual_color = '#cbd5e1' # Light gray for future/off days without records
                
            leave_info = leave_map.get((a.user_id, a.date))
            rep_info = replacing_map.get((a.user_id, a.date))
            
            leave_badge = ""
            if leave_info:
                if leave_info.replacement_status == 'assigned' and leave_info.replacement_user:
                    swap_txt = "Pindah Shift: " if leave_info.is_shift_swap else ""
                    leave_badge = f" ({swap_txt}Pengganti: {leave_info.replacement_user.name})"
                elif leave_info.replacement_status == 'pending':
                    leave_badge = " [Butuh Pengganti]"
            elif rep_info:
                if rep_info.get('is_shift_swap'):
                    leave_badge = f" [Pindah Shift - Ganti {rep_info['for_name']}]"
                else:
                    if has_ot:
                        leave_badge = f" [Lembur - Ganti {rep_info['for_name']}]"
                    else:
                        leave_badge = f" [Ganti {rep_info['for_name']}]"
            
            ot_badge = " [Lembur]" if (has_ot and '[Lembur]' not in leave_badge and '[Lembur]' not in status_badge) else ""
            if mode == 'realisasi':
                color = actual_color or color
                if a.shift and a.shift.site_id != site_id:
                    dest_site = a.shift.site.name if a.shift.site else a.shift.name
                    title_text = f"{a.user.name}{status_badge}{ot_badge} [Deploy: {dest_site}]"
                else:
                    title_text = f"{a.user.name}{leave_badge}{status_badge}{ot_badge}"
            else:
                title_text = f"{a.user.name} - {a.shift.name}{leave_badge}{ot_badge}"
                
            events.append({
                'id': a.id,
                'title': title_text,
                'start': a.date.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'allDay': True,
                'order': order,
                'extendedProps': {
                    'user_id': a.user_id,
                    'user_name': a.user.name,
                    'shift_id': a.shift_id,
                    'shift_name': a.shift.name,
                    'is_off_day': a.shift.is_off_day,
                    'expected_time': "Off Day / Libur" if a.shift.is_off_day else f"{a.shift.start_time.strftime('%H:%M')} - {a.shift.end_time.strftime('%H:%M')}",
                    'user_nrp': a.user.nrp if (a.user and a.user.nrp) else '',
                    'actual_in': rec.jam_masuk.strftime('%H:%M') if (rec and rec.jam_masuk) else "-",
                    'actual_out': rec.jam_pulang.strftime('%H:%M') if (rec and rec.jam_pulang) else "-",
                    'status': rec_status if rec else ("Alpha" if a.date < datetime.today().date() and not a.shift.is_off_day else "Belum Hadir"),
                    'is_cuti': bool(leave_info or 'cuti' in shift_name),
                    'leave_id': leave_info.id if leave_info else None,
                    'leave_type': leave_info.leave_type if leave_info else None,
                    'leave_reason': leave_info.reason if leave_info else None,
                    'replacement_status': leave_info.replacement_status if leave_info else None,
                    'replacement_name': leave_info.replacement_user.name if (leave_info and leave_info.replacement_user) else None,
                    'is_replacement': bool(rep_info),
                    'replacing_user_name': rep_info['for_name'] if rep_info else None,
                    'is_shift_swap': bool(leave_info.is_shift_swap) if leave_info else (bool(rep_info.get('is_shift_swap')) if rep_info else False),
                    'is_overtime': has_ot,
                    'overtime_id': ot_info.id if ot_info else None,
                    'overtime_start': f"{ot_info.start_date.strftime('%d/%m/%Y')} {ot_info.start_time.strftime('%H:%M')}" if ot_info else None,
                    'overtime_end': f"{ot_info.end_date.strftime('%d/%m/%Y')} {ot_info.end_time.strftime('%H:%M')}" if ot_info else None,
                    'overtime_hours': ot_info.duration_hours if ot_info else 0,
                    'overtime_reason': ot_info.reason if (ot_info and ot_info.reason) else None
                }
            })

        # Standalone Overtime and Attendance events (only displayed in Realisasi mode, not in Schedule Plan)
        if mode == 'realisasi':
            # Standalone Overtime events (technicians with overtime but no regular UserShift on that day)
            for (uid, d), ot in overtime_map.items():
                if (uid, d) not in assigned_user_dates:
                    u_name = ot.user.name if ot.user else 'Teknisi'
                    events.append({
                        'id': f"ot-{ot.id}-{d.isoformat()}",
                        'title': f"{u_name} - Lembur ({ot.start_time.strftime('%H:%M')} - {ot.end_time.strftime('%H:%M')}) [Lembur]",
                        'start': d.isoformat(),
                        'backgroundColor': '#8b5cf6',
                        'borderColor': '#7c3aed',
                        'allDay': True,
                        'order': 9998,
                        'extendedProps': {
                            'user_id': ot.user_id,
                            'user_name': u_name,
                            'shift_id': None,
                            'shift_name': 'Lembur',
                            'is_off_day': False,
                            'expected_time': f"{ot.start_time.strftime('%H:%M')} - {ot.end_time.strftime('%H:%M')}",
                            'actual_in': "-",
                            'actual_out': "-",
                            'status': 'Lembur',
                            'is_cuti': False,
                            'is_overtime': True,
                            'overtime_id': ot.id,
                            'overtime_start': f"{ot.start_date.strftime('%d/%m/%Y')} {ot.start_time.strftime('%H:%M')}",
                            'overtime_end': f"{ot.end_date.strftime('%d/%m/%Y')} {ot.end_time.strftime('%H:%M')}",
                            'overtime_hours': ot.duration_hours,
                            'overtime_reason': ot.reason or '-'
                        }
                    })
                    
            # Standalone Attendance events (users with attendance but no shift/overtime)
            from models import AttendanceRecord, User
            att_query = AttendanceRecord.query.options(joinedload(AttendanceRecord.user))
            if is_kp:
                att_query = att_query.join(User).filter(
                    (User.site_id == site_id) | (User.site_id.is_(None))
                )
            else:
                att_query = att_query.join(User).filter(
                    User.site_id == site_id
                )
            if start_date:
                att_query = att_query.filter(AttendanceRecord.date >= start_date)
            if end_date:
                att_query = att_query.filter(AttendanceRecord.date <= end_date)
            standalone_attendances = att_query.all()
            
            for att in standalone_attendances:
                if not att.user_id: continue
                if (att.user_id, att.date) not in assigned_user_dates and (att.user_id, att.date) not in overtime_map:
                    u_name = att.user.name if att.user else (att.nama or 'Unknown')
                    actual_in = att.jam_masuk.strftime('%H:%M') if att.jam_masuk else "-"
                    actual_out = att.jam_pulang.strftime('%H:%M') if att.jam_pulang else "-"
                    status = att.status or 'Tanpa Jadwal'
                    
                    title_text = f"{u_name} - Hadir ({actual_in} - {actual_out})"
                    color = '#0284c7' # Light blue for attendance without shift
                        
                    events.append({
                        'id': f"att-only-{att.id}",
                        'title': title_text,
                        'start': att.date.isoformat(),
                        'backgroundColor': color,
                        'borderColor': color,
                        'allDay': True,
                        'order': 10000,
                        'extendedProps': {
                            'user_id': att.user_id,
                            'user_name': u_name,
                            'shift_id': None,
                            'shift_name': 'Tanpa Jadwal',
                            'is_off_day': False,
                            'expected_time': "-",
                            'actual_in': actual_in,
                            'actual_out': actual_out,
                            'status': status,
                            'is_cuti': False,
                            'is_overtime': False
                        }
                    })
                
        return jsonify(events)
        
    elif request.method == 'POST':
        data = request.json
        shift_id = data.get('shift_id')
        date_str = data.get('date')
        user_ids = data.get('user_ids', [])
        team_id = data.get('team_id')
        
        try:
            date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
            from models import User
            
            if team_id:
                team_users = User.query.filter_by(team_id=team_id).all()
                user_ids.extend([u.id for u in team_users])
                
            # Remove duplicates
            user_ids = list(set(user_ids))
            
            if not user_ids:
                return jsonify({'success': False, 'error': 'No users selected'}), 400
                
            new_assignments = []
            for uid in user_ids:
                assignment = UserShift(
                    user_id=uid,
                    shift_id=shift_id,
                    date=date_val
                )
                db.session.add(assignment)
                new_assignments.append(assignment)
                
            db.session.commit()
            return jsonify({'success': True, 'ids': [a.id for a in new_assignments]})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
            
    elif request.method == 'DELETE':
        ids_str = request.args.get('ids') or request.args.get('id')
        id_list = []
        if ids_str:
            for piece in str(ids_str).split(','):
                piece = piece.strip()
                if piece.isdigit():
                    id_list.append(int(piece))
                    
        if not id_list:
            return jsonify({'success': False, 'error': 'No assignment id provided'}), 400

        assignments = UserShift.query.filter(UserShift.id.in_(id_list)).all()
        if not assignments:
            return jsonify({'success': False, 'error': 'Assignment not found'}), 404
        
        kp = get_or_create_kantor_pusat()
        reg_shift, off_shift = ensure_kantor_pusat_shifts(kp.id)

        for assignment in assignments:
            if assignment.user and (assignment.user.site_id == kp.id or assignment.user.site_id is None):
                is_weekend = assignment.date.weekday() >= 5
                assignment.shift_id = off_shift.id if is_weekend else reg_shift.id
                assignment.notes = None
            else:
                db.session.delete(assignment)
                
        try:
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/shifts/<int:site_id>/apply_fixed_schedule', methods=['POST'])
@login_required
def api_apply_fixed_schedule(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
    from models import Site
    site = Site.query.get_or_404(site_id)
    if 'kantor pusat' not in site.name.lower():
        return jsonify({'error': 'Fitur ini hanya untuk Kantor Pusat'}), 400
    
    data = request.json or {}
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    count = ensure_kantor_pusat_schedule(site_id, start_date=start_date, end_date=end_date, force_update=data.get('overwrite', False))
    return jsonify({
        'success': True,
        'message': f'Jadwal tetap Kantor Pusat (Senin-Jumat 9-5) berhasil diterapkan ({count} shift diperbarui/dibuat).'
    })

@schedule_bp.route('/api/technician_deployment/<int:site_id>', methods=['POST'])
@login_required
def api_technician_deployment(site_id):
    """Bulk assign teknisi Kantor Pusat ke site tertentu untuk rentang tanggal"""
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    from models import Site, Shift, UserShift
    site = Site.query.get_or_404(site_id)

    data = request.get_json(silent=True) or {}
    user_ids = data.get('user_ids', [])
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    notes = (data.get('notes') or '').strip()

    if not user_ids:
        return jsonify({'success': False, 'error': 'Pilih minimal satu teknisi'}), 400
    if not start_date_str or not end_date_str:
        return jsonify({'success': False, 'error': 'Tanggal mulai dan selesai harus diisi'}), 400

    def parse_date(d_str):
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(str(d_str).strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError(f"Invalid date: {d_str}")

    try:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
    except ValueError:
        return jsonify({'success': False, 'error': 'Format tanggal tidak valid (gunakan YYYY-MM-DD)'}), 400

    if start_date > end_date:
        return jsonify({'success': False, 'error': 'Tanggal mulai tidak boleh lebih besar dari tanggal selesai'}), 400

    try:
        # Pastikan kolom notes ada pada tabel user_shift
        from sqlalchemy import text
        try:
            db.session.execute(text('ALTER TABLE user_shift ADD COLUMN notes TEXT;'))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # Auto get or create shift pemetaan untuk site tujuan (tidak wajib setting shift manual di site)
        default_shift = Shift.query.filter_by(site_id=site_id, is_off_day=False).first()
        if not default_shift:
            default_shift = Shift.query.filter_by(site_id=site_id).first()
        if not default_shift:
            default_shift = Shift(
                site_id=site_id,
                name='Penugasan',
                start_time=datetime.strptime('08:00', '%H:%M').time(),
                end_time=datetime.strptime('17:00', '%H:%M').time(),
                is_off_day=False
            )
            db.session.add(default_shift)
            db.session.flush()

        replace_site_deployment = data.get('replace_site_deployment', False)
        created = 0
        skipped = 0
        current_date = start_date

        while current_date <= end_date:
            if replace_site_deployment:
                site_shifts = Shift.query.filter_by(site_id=site_id).all()
                site_shift_ids = [s.id for s in site_shifts]
                if site_shift_ids:
                    # Cari teknisi yang sebelumnya di-deploy ke site ini tapi sekarang di-uncheck saat edit
                    removals = UserShift.query.filter(
                        UserShift.shift_id.in_(site_shift_ids),
                        UserShift.date == current_date,
                        ~UserShift.user_id.in_(user_ids)
                    ).all()
                    
                    kp = get_or_create_kantor_pusat()
                    reg_shift, off_shift = ensure_kantor_pusat_shifts(kp.id)
                    is_weekend = current_date.weekday() >= 5
                    target_kp_shift_id = off_shift.id if is_weekend else reg_shift.id

                    for rem in removals:
                        rem.shift_id = target_kp_shift_id
                        rem.notes = None

            for user_id in user_ids:
                # Cek apakah sudah ada UserShift untuk user+date ini
                existing_shifts = UserShift.query.filter_by(
                    user_id=user_id,
                    date=current_date
                ).all()

                if existing_shifts:
                    primary = existing_shifts[0]
                    primary.shift_id = default_shift.id
                    primary.notes = notes
                    created += 1
                    # Bersihkan duplikat jika ada
                    for dup in existing_shifts[1:]:
                        db.session.delete(dup)
                    continue

                # Buat UserShift baru dengan shift site tujuan
                user_shift = UserShift(
                    user_id=user_id,
                    shift_id=default_shift.id,
                    date=current_date,
                    notes=notes
                )
                db.session.add(user_shift)
                created += 1

            current_date += timedelta(days=1)

        db.session.commit()
        msg = f'Perubahan penugasan ke site {site.name} berhasil disimpan.' if replace_site_deployment else f'{created} penugasan teknisi ke site {site.name} berhasil disimpan.'
        return jsonify({
            'success': True,
            'created': created,
            'skipped': skipped,
            'message': msg
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Gagal menyimpan: {str(e)}'}), 500

def sync_work_order_to_schedule(wo):
    """
    Menyelaraskan penugasan teknisi pada Work Order secara otomatis ke Team Schedule (Pemetaan Site).
    Setiap teknisi yang di-assign ke WO akan otomatis dijadwalkan ke Site tempat asset berada
    pada tanggal pengerjaan WO dengan catatan (notes) berupa nomor WO dan deskripsinya.
    """
    from models import db, Shift, UserShift, Site, Asset, User
    from datetime import datetime, date, timedelta

    if not wo:
        return False

    # 1. Tentukan Site tujuan dari Asset atau Project Code
    site_id = None
    if wo.asset and wo.asset.site_id:
        site_id = wo.asset.site_id
    elif getattr(wo, 'asset_id', None):
        ast = db.session.get(Asset, wo.asset_id)
        if ast and ast.site_id:
            site_id = ast.site_id
    
    if not site_id and getattr(wo, 'project_code', None):
        st = Site.query.filter_by(project_code=wo.project_code).first()
        if st:
            site_id = st.id

    if not site_id:
        return False

    kp = get_or_create_kantor_pusat()
    reg_shift, off_shift = ensure_kantor_pusat_shifts(kp.id)

    # 2. Tentukan teknisi yang di-assign
    user_ids = set()
    if getattr(wo, 'assignees', None):
        user_ids.update([u.id for u in wo.assignees if u])
    if getattr(wo, 'assigned_to', None):
        user_ids.add(wo.assigned_to)
    if getattr(wo, 'team', None) and wo.team and wo.team.users:
        user_ids.update([u.id for u in wo.team.users if u])

    # 3. Tentukan rentang tanggal penugasan (dalam WIB / Local Date)
    def to_local_date(dt_val):
        if not dt_val:
            return None
        if isinstance(dt_val, datetime):
            return (dt_val + timedelta(hours=7)).date()
        if isinstance(dt_val, date):
            return dt_val
        return None

    start_d = to_local_date(wo.suggested_start_date) or to_local_date(wo.start_date) or to_local_date(wo.date_created) or datetime.now().date()
    end_d = to_local_date(wo.suggested_completion_date) or to_local_date(wo.end_date) or start_d

    if end_d < start_d:
        end_d = start_d

    # Batasi rentang maksimum 30 hari untuk mencegah loop jika tanggal WO diisi terlalu jauh
    if (end_d - start_d).days > 30:
        end_d = start_d + timedelta(days=30)

    # 4. Format Catatan / Note
    wo_desc = (wo.description or '').strip().replace('\r', ' ').replace('\n', ' ')
    if len(wo_desc) > 50:
        wo_desc = wo_desc[:47] + '...'
    wo_note_tag = f"WO {wo.code}"
    wo_full_note = f"{wo_note_tag}: {wo_desc}" if wo_desc else wo_note_tag

    # 5. Cari shift tujuan di site_id (jika bukan KP)
    if site_id == kp.id:
        default_shift = reg_shift
    else:
        default_shift = Shift.query.filter_by(site_id=site_id, is_off_day=False).first()
        if not default_shift:
            default_shift = Shift.query.filter_by(site_id=site_id).first()
        if not default_shift:
            default_shift = Shift(
                site_id=site_id,
                name='Penugasan',
                start_time=datetime.strptime('08:00', '%H:%M').time(),
                end_time=datetime.strptime('17:00', '%H:%M').time(),
                is_off_day=False
            )
            db.session.add(default_shift)
            db.session.flush()

    # 6. Bersihkan penugasan sebelumnya untuk WO ini yang sudah tidak berlaku
    old_shifts = UserShift.query.filter(UserShift.notes.ilike(f"%{wo.code}%")).all()
    for os in old_shifts:
        is_still_valid = (
            os.user_id in user_ids and
            start_d <= os.date <= end_d and
            os.shift and os.shift.site_id == site_id
        )
        if not is_still_valid:
            is_weekend = os.date.weekday() >= 5
            os.shift_id = off_shift.id if is_weekend else reg_shift.id
            parts = [p.strip() for p in (os.notes or '').split(',') if wo.code not in p]
            os.notes = ', '.join(parts) if parts else None

    # Jika tidak ada teknisi di WO ini, selesai (semua penugasan lama sudah dikembalikan ke KP)
    if not user_ids:
        db.session.commit()
        return True

    # 7. Petakan setiap teknisi ke site untuk setiap hari di rentang tanggal
    curr_d = start_d
    while curr_d <= end_d:
        for uid in user_ids:
            existing_shifts = UserShift.query.filter_by(user_id=uid, date=curr_d).all()
            if existing_shifts:
                primary = existing_shifts[0]
                primary.shift_id = default_shift.id
                if not primary.notes:
                    primary.notes = wo_full_note
                elif wo.code in primary.notes:
                    parts = [p.strip() for p in primary.notes.split(',') if wo.code not in p]
                    parts.append(wo_full_note)
                    primary.notes = ', '.join(parts)
                else:
                    primary.notes = f"{primary.notes}, {wo_full_note}"
                
                for dup in existing_shifts[1:]:
                    db.session.delete(dup)
            else:
                new_us = UserShift(
                    user_id=uid,
                    shift_id=default_shift.id,
                    date=curr_d,
                    notes=wo_full_note
                )
                db.session.add(new_us)

        curr_d += timedelta(days=1)

    db.session.commit()
    return True

def remove_work_order_from_schedule(wo_code):
    """
    Mengembalikan teknisi yang dijadwalkan untuk WO ini ke shift Kantor Pusat.
    """
    from models import db, UserShift
    if not wo_code:
        return False
    kp = get_or_create_kantor_pusat()
    reg_shift, off_shift = ensure_kantor_pusat_shifts(kp.id)
    
    shifts = UserShift.query.filter(UserShift.notes.ilike(f"%{wo_code}%")).all()
    for s in shifts:
        is_weekend = s.date.weekday() >= 5
        s.shift_id = off_shift.id if is_weekend else reg_shift.id
        parts = [p.strip() for p in (s.notes or '').split(',') if wo_code not in p]
        s.notes = ', '.join(parts) if parts else None
        
    db.session.commit()
    return True

def sync_active_work_orders_to_schedule():
    """
    Sinkronisasi semua work order aktif/terbuka yang memiliki teknisi ke team schedule.
    """
    from models import WorkOrder, WorkOrderStatus, db
    open_statuses = WorkOrderStatus.query.filter(WorkOrderStatus.control_type != 'Closed').all()
    open_status_ids = [s.id for s in open_statuses]
    if not open_status_ids:
        return 0
    wos = WorkOrder.query.filter(WorkOrder.status_id.in_(open_status_ids)).all()
    count = 0
    for wo in wos:
        if getattr(wo, 'assignees', None) or getattr(wo, 'assigned_to', None) or getattr(wo, 'team_id', None):
            try:
                if sync_work_order_to_schedule(wo):
                    count += 1
            except Exception:
                db.session.rollback()
    return count

@schedule_bp.route('/api/technicians/kantor_pusat')
@login_required
def api_technicians_kantor_pusat():
    """Get list teknisi Kantor Pusat untuk dropdown"""
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403

    from models import User
    kp = get_or_create_kantor_pusat()
    users = get_kantor_pusat_users(kp.id)

    result = []
    for u in users:
        result.append({
            'id': u.id,
            'name': u.name,
            'nrp': u.nrp or '-',
            'role': u.role
        })

    return jsonify(result)

def get_or_create_cuti_shift(site_id):
    from models import Shift
    cuti_shift = Shift.query.filter_by(site_id=site_id).filter(Shift.name.ilike('%cuti%')).first()
    if not cuti_shift:
        cuti_shift = Shift(
            site_id=site_id,
            name='Cuti',
            is_off_day=True,
            start_time=datetime.strptime('00:00', '%H:%M').time(),
            end_time=datetime.strptime('00:00', '%H:%M').time()
        )
        db.session.add(cuti_shift)
        db.session.commit()
    return cuti_shift

@schedule_bp.route('/api/leaves/available_replacements/<int:site_id>')
@login_required
def api_available_replacements(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    date_str = request.args.get('date')
    exclude_user_id = request.args.get('exclude_user_id', type=int)
    
    if not date_str:
        return jsonify({'error': 'Date is required'}), 400
        
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
        
    from models import User, Shift, UserShift, EmployeeLeave, Site
    site = Site.query.get(site_id)
    is_kp = bool(site and 'kantor pusat' in site.name.lower())
    
    # All technicians in site except leave applicant
    if is_kp:
        base_techs = User.query.filter((User.site_id == site_id) | (User.site_id.is_(None))).filter(User.role != 'Admin').all()
    else:
        base_techs = User.query.filter(User.role != 'Admin', User.site_id == site_id).all()
        
    site_shifts = Shift.query.filter_by(site_id=site_id).all()
    site_shift_ids = [s.id for s in site_shifts]
    extra_techs = []
    if site_shift_ids:
        extra_uids = [r[0] for r in db.session.query(UserShift.user_id).filter(UserShift.shift_id.in_(site_shift_ids)).distinct().all() if r[0]]
        if extra_uids:
            extra_techs = User.query.filter(User.id.in_(extra_uids)).all()
        
    tech_map = {t.id: t for t in base_techs}
    for t in extra_techs:
        tech_map[t.id] = t
    if exclude_user_id:
        tech_map.pop(exclude_user_id, None)
    technicians = sorted(list(tech_map.values()), key=lambda x: (x.name or '').lower())
    
    # Active leaves on target date
    if is_kp:
        active_leaves = EmployeeLeave.query.filter(
            (EmployeeLeave.site_id == site_id) | (EmployeeLeave.site_id.is_(None)),
            EmployeeLeave.status == 'Approved',
            EmployeeLeave.start_date <= target_date,
            EmployeeLeave.end_date >= target_date
        ).all()
    else:
        active_leaves = EmployeeLeave.query.filter(
            EmployeeLeave.site_id == site_id,
            EmployeeLeave.status == 'Approved',
            EmployeeLeave.start_date <= target_date,
            EmployeeLeave.end_date >= target_date
        ).all()
    
    users_on_leave = set(l.user_id for l in active_leaves)
    users_already_replacing = set(l.replacement_user_id for l in active_leaves if l.replacement_user_id)
    
    # User shifts on target date
    shifts_on_date = UserShift.query.join(Shift).filter(
        Shift.site_id == site_id,
        UserShift.date == target_date
    ).all()
    
    user_shift_map = {us.user_id: us.shift for us in shifts_on_date}
    
    available = []
    for tech in technicians:
        if tech.id in users_on_leave or tech.id in users_already_replacing:
            continue
            
        tech_shift = user_shift_map.get(tech.id)
        if tech_shift:
            if tech_shift.is_off_day:
                available.append({
                    'id': tech.id,
                    'name': tech.name,
                    'nrp': tech.nrp or '-',
                    'status': f"Jadwal: {tech_shift.name} (Off Day)",
                    'category': 'off_day',
                    'is_free': True
                })
            else:
                time_str = f" ({tech_shift.start_time.strftime('%H:%M')} - {tech_shift.end_time.strftime('%H:%M')})" if tech_shift.start_time and tech_shift.end_time else ""
                available.append({
                    'id': tech.id,
                    'name': tech.name,
                    'nrp': tech.nrp or '-',
                    'status': f"Jadwal Saat Ini: {tech_shift.name}{time_str}",
                    'category': 'other_shift',
                    'is_free': False
                })
        else:
            available.append({
                'id': tech.id,
                'name': tech.name,
                'nrp': tech.nrp or '-',
                'status': "Jadwal: Kosong (Belum ada shift)",
                'category': 'off_day',
                'is_free': True
            })
            
    # Sort: Off Day / Kosong first, then other shifts, then name
    available.sort(key=lambda x: (0 if x['category'] == 'off_day' else 1, x['name']))
    return jsonify(available)

@schedule_bp.route('/api/leaves/<int:site_id>', methods=['GET'])
@login_required
def api_get_leaves(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    from models import EmployeeLeave, Site
    site = Site.query.get(site_id)
    is_kp = bool(site and 'kantor pusat' in site.name.lower())
    
    status_filter = request.args.get('status')
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    if is_kp:
        query = EmployeeLeave.query.filter((EmployeeLeave.site_id == site_id) | (EmployeeLeave.site_id.is_(None)))
    else:
        query = EmployeeLeave.query.filter_by(site_id=site_id)
    
    if status_filter and status_filter != 'all':
        query = query.filter_by(replacement_status=status_filter)
        
    if year:
        from sqlalchemy import extract
        query = query.filter(extract('year', EmployeeLeave.start_date) == year)
    if month:
        from sqlalchemy import extract
        query = query.filter(extract('month', EmployeeLeave.start_date) == month)
        
    leaves = query.order_by(EmployeeLeave.start_date.desc()).all()
    
    results = []
    for l in leaves:
        results.append({
            'id': l.id,
            'user_id': l.user_id,
            'user_name': l.user.name if l.user else 'Unknown',
            'user_nrp': l.user.nrp if l.user else '-',
            'start_date': l.start_date.isoformat(),
            'end_date': l.end_date.isoformat(),
            'date_display': l.start_date.strftime('%d/%m/%Y') if l.start_date == l.end_date else f"{l.start_date.strftime('%d/%m/%Y')} - {l.end_date.strftime('%d/%m/%Y')}",
            'leave_type': l.leave_type,
            'reason': l.reason or '-',
            'needs_replacement': l.needs_replacement,
            'replacement_user_id': l.replacement_user_id,
            'replacement_name': l.replacement_user.name if l.replacement_user else None,
            'replacement_status': l.replacement_status,
            'is_shift_swap': bool(l.is_shift_swap),
            'original_shift_id': l.original_shift_id,
            'original_shift_name': l.original_shift.name if l.original_shift else 'Tidak Ada',
            'replacement_original_shift_name': l.replacement_original_shift.name if l.replacement_original_shift else None,
            'status': l.status,
            'created_at': l.created_at.strftime('%d/%m/%Y %H:%M') if l.created_at else '-'
        })
        
    if is_kp:
        all_site_leaves = EmployeeLeave.query.filter((EmployeeLeave.site_id == site_id) | (EmployeeLeave.site_id.is_(None))).all()
    else:
        all_site_leaves = EmployeeLeave.query.filter_by(site_id=site_id).all()
    summary = {
        'total': len(all_site_leaves),
        'pending_replacement': sum(1 for l in all_site_leaves if l.replacement_status == 'pending'),
        'assigned_replacement': sum(1 for l in all_site_leaves if l.replacement_status == 'assigned'),
        'not_needed': sum(1 for l in all_site_leaves if l.replacement_status == 'not_needed')
    }
    
    return jsonify({
        'leaves': results,
        'summary': summary
    })

@schedule_bp.route('/api/leaves/<int:site_id>', methods=['POST'])
@login_required
def api_create_leave(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json or {}
    user_id = data.get('user_id')
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date') or start_date_str
    leave_type = data.get('leave_type', 'Cuti')
    reason = data.get('reason', '')
    needs_replacement = bool(data.get('needs_replacement', False))
    replacement_user_id = data.get('replacement_user_id')
    if replacement_user_id:
        try:
            replacement_user_id = int(replacement_user_id)
        except (ValueError, TypeError):
            replacement_user_id = None
        
    if not user_id or not start_date_str:
        return jsonify({'success': False, 'error': 'Karyawan dan Tanggal Mulai wajib diisi'}), 400
        
    try:
        from datetime import timedelta
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        if end_date < start_date:
            return jsonify({'success': False, 'error': 'Tanggal selesai tidak boleh sebelum tanggal mulai'}), 400
            
        from models import User, Shift, UserShift, EmployeeLeave, Site
        site = Site.query.get(site_id)
        is_kp = bool(site and 'kantor pusat' in site.name.lower())
        user = User.query.get(user_id)
        site_shifts = Shift.query.filter_by(site_id=site_id).all()
        site_shift_ids = [s.id for s in site_shifts]
        has_site_shift = UserShift.query.filter(UserShift.user_id == user_id, UserShift.shift_id.in_(site_shift_ids)).first() if site_shift_ids else False
        if not user or (user.site_id != site_id and not (is_kp and user.site_id is None) and not has_site_shift):
            return jsonify({'success': False, 'error': 'Karyawan tidak ditemukan di site ini'}), 404
            
        cuti_shift = get_or_create_cuti_shift(site_id)
        
        if needs_replacement:
            replacement_status = 'assigned' if replacement_user_id else 'pending'
        else:
            replacement_status = 'not_needed'
            replacement_user_id = None
            
        is_shift_swap = bool(data.get('is_shift_swap', False))
        replacement_original_shift_id = None
        if replacement_user_id:
            rep_orig = UserShift.query.filter_by(user_id=replacement_user_id, date=start_date).first()
            if rep_orig:
                replacement_original_shift_id = rep_orig.shift_id

        # Detect original shift (from start_date)
        existing_shift_assignment = UserShift.query.filter_by(
            user_id=user_id,
            date=start_date
        ).first()
        original_shift_id = None
        if existing_shift_assignment and not existing_shift_assignment.shift.is_off_day:
            original_shift_id = existing_shift_assignment.shift_id
        else:
            # Check if there is a default working shift at this site
            first_work_shift = Shift.query.filter_by(site_id=site_id, is_off_day=False).first()
            if first_work_shift:
                original_shift_id = first_work_shift.id
            
        leave_record = EmployeeLeave(
            site_id=site_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            leave_type=leave_type,
            reason=reason,
            needs_replacement=needs_replacement,
            replacement_user_id=replacement_user_id,
            replacement_status=replacement_status,
            original_shift_id=original_shift_id,
            is_shift_swap=is_shift_swap,
            replacement_original_shift_id=replacement_original_shift_id,
            status='Approved',
            created_by_id=current_user.id
        )
        db.session.add(leave_record)
        
        # Update/assign UserShifts for each day in range
        curr_d = start_date
        while curr_d <= end_date:
            # 1. Update/set user's shift to Cuti
            user_shift = UserShift.query.filter_by(user_id=user_id, date=curr_d).first()
            if user_shift:
                user_shift.shift_id = cuti_shift.id
            else:
                user_shift = UserShift(
                    user_id=user_id,
                    shift_id=cuti_shift.id,
                    date=curr_d
                )
                db.session.add(user_shift)
                
            # 2. If replacement selected, assign replacement to original shift
            if replacement_user_id and original_shift_id:
                rep_shift = UserShift.query.filter_by(user_id=replacement_user_id, date=curr_d).first()
                if is_shift_swap:
                    # Pindah Shift: directly move their shift to original_shift_id
                    if rep_shift:
                        rep_shift.shift_id = original_shift_id
                    else:
                        db.session.add(UserShift(
                            user_id=replacement_user_id,
                            shift_id=original_shift_id,
                            date=curr_d
                        ))
                else:
                    # Lembur / Rangkap:
                    if rep_shift:
                        if rep_shift.shift.is_off_day:
                            rep_shift.shift_id = original_shift_id
                        else:
                            # If replacement has another shift, add coverage assignment if not exists
                            already_has = UserShift.query.filter_by(user_id=replacement_user_id, shift_id=original_shift_id, date=curr_d).first()
                            if not already_has:
                                db.session.add(UserShift(
                                    user_id=replacement_user_id,
                                    shift_id=original_shift_id,
                                    date=curr_d
                                ))
                    else:
                        rep_shift = UserShift(
                            user_id=replacement_user_id,
                            shift_id=original_shift_id,
                            date=curr_d
                        )
                        db.session.add(rep_shift)
                    
            curr_d += timedelta(days=1)
            
        db.session.commit()
        return jsonify({
            'success': True,
            'id': leave_record.id,
            'message': 'Jadwal cuti berhasil disimpan'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/leaves/<int:site_id>/assign_replacement', methods=['POST'])
@login_required
def api_assign_leave_replacement(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json or {}
    leave_id = data.get('leave_id')
    replacement_user_id = data.get('replacement_user_id')
    is_shift_swap = bool(data.get('is_shift_swap', False))
    
    if not leave_id or not replacement_user_id:
        return jsonify({'success': False, 'error': 'Leave ID dan Teknisi Pengganti wajib diisi'}), 400
        
    try:
        from models import EmployeeLeave, User, UserShift, Shift
        from datetime import timedelta
        
        leave = EmployeeLeave.query.get_or_404(leave_id)
        if leave.site_id != site_id:
            return jsonify({'success': False, 'error': 'Cuti tidak ditemukan di site ini'}), 404
            
        from models import Site
        site = Site.query.get(site_id)
        is_kp = bool(site and 'kantor pusat' in site.name.lower())
        rep_user = User.query.get(replacement_user_id)
        site_shifts = Shift.query.filter_by(site_id=site_id).all()
        site_shift_ids = [s.id for s in site_shifts]
        has_rep_shift = UserShift.query.filter(UserShift.user_id == replacement_user_id, UserShift.shift_id.in_(site_shift_ids)).first() if site_shift_ids else False
        if not rep_user or (rep_user.site_id != site_id and not (is_kp and rep_user.site_id is None) and not has_rep_shift):
            return jsonify({'success': False, 'error': 'Teknisi pengganti tidak valid'}), 400
            
        rep_orig = UserShift.query.filter_by(user_id=rep_user.id, date=leave.start_date).first()
        leave.replacement_original_shift_id = rep_orig.shift_id if rep_orig else None
        leave.is_shift_swap = is_shift_swap
        leave.replacement_user_id = rep_user.id
        leave.replacement_status = 'assigned'
        
        target_shift_id = leave.original_shift_id
        if not target_shift_id:
            work_shift = Shift.query.filter_by(site_id=site_id, is_off_day=False).first()
            if work_shift:
                target_shift_id = work_shift.id
                
        if target_shift_id:
            curr_d = leave.start_date
            while curr_d <= leave.end_date:
                rep_shift = UserShift.query.filter_by(user_id=rep_user.id, date=curr_d).first()
                if is_shift_swap:
                    # Pindah Shift: directly move their shift to target_shift_id
                    if rep_shift:
                        rep_shift.shift_id = target_shift_id
                    else:
                        db.session.add(UserShift(
                            user_id=rep_user.id,
                            shift_id=target_shift_id,
                            date=curr_d
                        ))
                else:
                    # Lembur / Rangkap:
                    if rep_shift:
                        if rep_shift.shift.is_off_day:
                            rep_shift.shift_id = target_shift_id
                        else:
                            already_has = UserShift.query.filter_by(user_id=rep_user.id, shift_id=target_shift_id, date=curr_d).first()
                            if not already_has:
                                db.session.add(UserShift(
                                    user_id=rep_user.id,
                                    shift_id=target_shift_id,
                                    date=curr_d
                                ))
                    else:
                        db.session.add(UserShift(
                            user_id=rep_user.id,
                            shift_id=target_shift_id,
                            date=curr_d
                        ))
                curr_d += timedelta(days=1)
                
        db.session.commit()
        return jsonify({'success': True, 'message': f'Teknisi {rep_user.name} berhasil ditugaskan sebagai pengganti'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/leaves/<int:site_id>/<int:leave_id>', methods=['DELETE'])
@login_required
def api_delete_leave(site_id, leave_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        from models import EmployeeLeave, UserShift, Shift
        from datetime import timedelta
        
        leave = EmployeeLeave.query.get_or_404(leave_id)
        if leave.site_id != site_id:
            return jsonify({'success': False, 'error': 'Cuti tidak ditemukan di site ini'}), 404
            
        cuti_shift = Shift.query.filter_by(site_id=site_id).filter(Shift.name.ilike('%cuti%')).first()
        cuti_shift_id = cuti_shift.id if cuti_shift else None
        
        curr_d = leave.start_date
        while curr_d <= leave.end_date:
            u_shift = UserShift.query.filter_by(user_id=leave.user_id, date=curr_d).first()
            if u_shift and u_shift.shift_id == cuti_shift_id:
                if leave.original_shift_id:
                    u_shift.shift_id = leave.original_shift_id
                else:
                    db.session.delete(u_shift)
                    
            if leave.replacement_user_id and leave.original_shift_id:
                if leave.is_shift_swap and leave.replacement_original_shift_id:
                    # Revert shift back to original shift before swap
                    rep_shift = UserShift.query.filter_by(user_id=leave.replacement_user_id, date=curr_d).first()
                    if rep_shift:
                        rep_shift.shift_id = leave.replacement_original_shift_id
                else:
                    rep_shifts = UserShift.query.filter_by(user_id=leave.replacement_user_id, date=curr_d).all()
                    for rs in rep_shifts:
                        if rs.shift_id == leave.original_shift_id:
                            if len(rep_shifts) > 1:
                                db.session.delete(rs)
                            else:
                                off_shift = Shift.query.filter_by(site_id=site_id, is_off_day=True).first()
                                if off_shift:
                                    rs.shift_id = off_shift.id
                                else:
                                    db.session.delete(rs)
                    
            curr_d += timedelta(days=1)
            
        db.session.delete(leave)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Data cuti berhasil dihapus'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/overtime/<int:site_id>', methods=['GET', 'POST'])
@login_required
def api_overtime(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    from models import EmployeeOvertime, User, Site
    from datetime import datetime
    site = Site.query.get(site_id)
    is_kp = bool(site and 'kantor pusat' in site.name.lower())
    
    if request.method == 'GET':
        if is_kp:
            overtimes = EmployeeOvertime.query.filter(
                (EmployeeOvertime.site_id == site_id) | (EmployeeOvertime.site_id.is_(None))
            ).order_by(EmployeeOvertime.start_date.desc(), EmployeeOvertime.id.desc()).all()
        else:
            overtimes = EmployeeOvertime.query.filter_by(site_id=site_id).order_by(EmployeeOvertime.start_date.desc(), EmployeeOvertime.id.desc()).all()
        result = []
        for ot in overtimes:
            result.append({
                'id': ot.id,
                'user_id': ot.user_id,
                'user_name': ot.user.name if ot.user else 'Unknown',
                'user_nrp': ot.user.nrp if ot.user else '-',
                'start_date': ot.start_date.strftime('%Y-%m-%d'),
                'start_date_display': ot.start_date.strftime('%d/%m/%Y'),
                'start_time': ot.start_time.strftime('%H:%M'),
                'end_date': ot.end_date.strftime('%Y-%m-%d'),
                'end_date_display': ot.end_date.strftime('%d/%m/%Y'),
                'end_time': ot.end_time.strftime('%H:%M'),
                'duration_hours': ot.duration_hours,
                'reason': ot.reason or '-',
                'status': ot.status,
                'created_at': ot.created_at.strftime('%d/%m/%Y %H:%M') if ot.created_at else '-'
            })
        return jsonify(result)
        
    elif request.method == 'POST':
        data = request.json or {}
        user_id = data.get('user_id')
        start_date_str = data.get('start_date')
        start_time_str = data.get('start_time')
        end_date_str = data.get('end_date')
        end_time_str = data.get('end_time')
        reason = (data.get('reason') or '').strip()
        
        if not user_id or not start_date_str or not start_time_str or not end_date_str or not end_time_str:
            return jsonify({'success': False, 'error': 'Semua field wajib diisi (Teknisi, Tanggal Mulai, Jam Mulai, Tanggal Selesai, Jam Selesai)'}), 400
            
        try:
            from models import Site
            site = Site.query.get(site_id)
            is_kp = bool(site and 'kantor pusat' in site.name.lower())
            user = User.query.get(user_id)
            site_shifts = Shift.query.filter_by(site_id=site_id).all()
            site_shift_ids = [s.id for s in site_shifts]
            has_site_shift = UserShift.query.filter(UserShift.user_id == user_id, UserShift.shift_id.in_(site_shift_ids)).first() if site_shift_ids else False
            if not user or (user.site_id != site_id and not (is_kp and user.site_id is None) and not has_site_shift):
                return jsonify({'success': False, 'error': 'Teknisi tidak valid untuk site ini'}), 400
                
            start_d = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            start_t = datetime.strptime(start_time_str, '%H:%M').time()
            end_d = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_t = datetime.strptime(end_time_str, '%H:%M').time()
            
            start_dt = datetime.combine(start_d, start_t)
            end_dt = datetime.combine(end_d, end_t)
            
            if end_dt <= start_dt:
                return jsonify({'success': False, 'error': 'Waktu selesai lembur harus lebih besar dari waktu mulai lembur'}), 400
                
            ot = EmployeeOvertime(
                site_id=site_id,
                user_id=user.id,
                start_date=start_d,
                start_time=start_t,
                end_date=end_d,
                end_time=end_t,
                reason=reason,
                status='Approved',
                created_by_id=current_user.id
            )
            db.session.add(ot)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'id': ot.id,
                'message': f'Jadwal lembur untuk {user.name} berhasil disimpan'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/overtime/<int:site_id>/<int:overtime_id>', methods=['DELETE'])
@login_required
def api_delete_overtime(site_id, overtime_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        from models import EmployeeOvertime
        ot = EmployeeOvertime.query.get_or_404(overtime_id)
        if ot.site_id != site_id:
            return jsonify({'success': False, 'error': 'Data lembur tidak ditemukan di site ini'}), 404
            
        db.session.delete(ot)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Data lembur berhasil dihapus'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/events')
@login_required
def api_events():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    tech_id = request.args.get('technician_id')
    
    from models import Asset
    query = WorkOrder.query
    
    # Site filtering: non-admin only sees WOs from their site
    if current_user.role != 'Admin' and current_user.site_id:
        query = query.join(Asset).filter(Asset.site_id == current_user.site_id)
    
    if tech_id:
        query = query.filter(WorkOrder.assignees.any(id=int(tech_id)))
        
    work_orders = query.all()
    
    events = []
    
    # Generate some simple determinist colors for technicians
    tech_colors = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#14b8a6']
    
    for wo in work_orders:
        if not wo.suggested_start_date:
            continue # Skip WOs clearly not scheduled yet
            
        start_date = wo.suggested_start_date.isoformat() + 'Z'
        end_date = (wo.suggested_completion_date.isoformat() + 'Z') if wo.suggested_completion_date else start_date
        
        # Color specific to the primary assignee for visual grouping
        primary_color = '#64748b' # default slate
        titles = []
        if wo.assignees:
            primary_id = wo.assignees[0].id
            primary_color = tech_colors[primary_id % len(tech_colors)]
            titles.append(f"[{wo.assignees[0].name}]")
            
        site_name = wo.asset.site.name if (wo.asset and getattr(wo.asset, 'site', None)) else 'Unknown Site'
        titles.append(f"{wo.code} - {site_name}")
        
        title = " ".join(titles)
        
        events.append({
            'id': wo.id,
            'title': title,
            'start': start_date,
            'end': end_date,
            'backgroundColor': primary_color,
            'borderColor': primary_color,
            'url': url_for('work_orders.edit', id=wo.id), # Clicking goes to WO details
            'extendedProps': {
                'wo_code': wo.code,
                'status': wo.current_status.name if wo.current_status else 'Draft',
                'description': wo.description if hasattr(wo, 'description') else '',
                'asset': wo.asset.name if wo.asset else 'No Asset'
            }
        })
        
    return jsonify(events)

@schedule_bp.route('/api/update_event', methods=['POST'])
@login_required
def api_update_event():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json
    wo_id = data.get('id')
    new_start_str = data.get('start')
    new_end_str = data.get('end')
    
    wo = WorkOrder.query.get_or_404(wo_id)
    is_all_day = bool(data.get('allDay'))
    
    if new_start_str:
        try:
            # FullCalendar sends ISO strings like 2026-04-03T10:00:00Z
            start_dt = datetime.fromisoformat(new_start_str.replace('Z', '+00:00')).replace(tzinfo=None)
            wo.suggested_start_date = start_dt
            if not new_end_str:
                wo.suggested_completion_date = start_dt
        except Exception as e:
            pass
            
    if new_end_str:
        try:
            end_dt = datetime.fromisoformat(new_end_str.replace('Z', '+00:00')).replace(tzinfo=None)
            if is_all_day and end_dt.date() > (wo.suggested_start_date.date() if wo.suggested_start_date else end_dt.date()):
                # FullCalendar allDay end date is exclusive, so subtract 1 day to get inclusive completion date
                end_dt = end_dt - timedelta(days=1)
            wo.suggested_completion_date = end_dt
        except Exception:
            pass
            
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/quick_assign', methods=['POST'])
@login_required
def api_quick_assign():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    from models import Asset, WorkOrderStatus
    data = request.json
    
    try:
        # Create a simplified Work Order to act as a Schedule Assignment
        code = f"SCH-{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d%H%M%S')}"
        status = WorkOrderStatus.query.filter_by(control_type='Active').first() or WorkOrderStatus.query.first()
        
        new_wo = WorkOrder(
            code=code,
            description=data.get('description', 'Scheduled Task'),
            asset_id=data.get('asset_id'),
            maintenance_type='Other', # General schedule
            status_id=status.id if status else None,
            priority='Medium'
        )
        
        start_dt = data.get('start_date')
        end_dt = data.get('end_date')
        if start_dt:
            from datetime import timedelta
            new_wo.suggested_start_date = datetime.strptime(start_dt, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
        if end_dt:
            from datetime import timedelta
            new_wo.suggested_completion_date = datetime.strptime(end_dt, '%Y-%m-%dT%H:%M') - timedelta(hours=7)
            
        db.session.add(new_wo)
        db.session.flush() # to get id
        
        # Add assignees
        tech_id = data.get('technician_id')
        if tech_id:
            tech = db.session.get(User, tech_id)
            if tech:
                new_wo.assignees.append(tech)
                
        # Log Creation
        l = WorkOrderLog(work_order_id=new_wo.id, user_id=current_user.id, log_text="Work Order created (Scheduled).")
        db.session.add(l)
                
        db.session.commit()
        return jsonify({'success': True, 'wo_id': new_wo.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/api/kanban_events')
@login_required
def api_kanban_events():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    tech_id = request.args.get('technician_id')
    
    from models import Asset, WorkOrderStatus
    query = WorkOrder.query
    
    if current_user.role != 'Admin' and current_user.site_id:
        query = query.join(Asset).filter(Asset.site_id == current_user.site_id)
        
    if tech_id:
        query = query.filter(WorkOrder.assignees.any(id=int(tech_id)))
        
    # Only fetch non-closed to avoid huge payloads, or at least order by id desc
    # For now, let's fetch everything that is not 'Closed' control type if possible, or limit to 200
    work_orders = query.join(WorkOrderStatus, WorkOrder.status_id == WorkOrderStatus.id, isouter=True) \
                       .filter(db.or_(WorkOrderStatus.control_type != 'Closed', WorkOrderStatus.id == None)) \
                       .order_by(WorkOrder.id.desc()).limit(200).all()
    
    events = []
    for wo in work_orders:
        site_name = wo.asset.site.name if (wo.asset and getattr(wo.asset, 'site', None)) else 'Unknown Site'
        
        events.append({
            'id': wo.id,
            'code': wo.code,
            'description': wo.description,
            'status_id': wo.status_id,
            'priority': wo.priority,
            'site': site_name,
            'assignees': [a.name for a in wo.assignees]
        })
        
    return jsonify(events)

@schedule_bp.route('/api/update_wo_status', methods=['POST'])
@login_required
def api_update_wo_status():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    wo_id = data.get('wo_id')
    new_status_id = data.get('status_id')
    
    wo = WorkOrder.query.get_or_404(wo_id)
    if new_status_id:
        wo.status_id = new_status_id
        try:
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'Invalid status'}), 400

@schedule_bp.route('/export/<int:site_id>')
@login_required
def export_schedule(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    import pandas as pd
    import io
    from flask import send_file
    from models import Shift, UserShift, Site
    
    site = Site.query.get_or_404(site_id)
    shifts = Shift.query.filter_by(site_id=site_id).all()
    shift_ids = [s.id for s in shifts]
    
    assignments = UserShift.query.filter(UserShift.shift_id.in_(shift_ids)).all()
    
    data = []
    for a in assignments:
        data.append({
            'NRP': a.user.nrp,
            'Technician Name': a.user.name,
            'Shift Name': a.shift.name,
            'Date (YYYY-MM-DD)': a.date.strftime('%Y-%m-%d')
        })
        
    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame(columns=['NRP', 'Technician Name', 'Shift Name', 'Date (YYYY-MM-DD)'])
        
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Schedule')
    output.seek(0)
    
    return send_file(output, as_attachment=True, download_name=f'schedule_{site.name.replace(" ", "_")}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@schedule_bp.route('/template')
@login_required
def template_schedule():
    import pandas as pd
    import io
    from flask import send_file
    
    df = pd.DataFrame(columns=['NRP', 'Shift Name', 'Date (YYYY-MM-DD)'])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template')
    output.seek(0)
    
    return send_file(output, as_attachment=True, download_name='schedule_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@schedule_bp.route('/import/<int:site_id>', methods=['POST'])
@login_required
def import_schedule(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    import pandas as pd
    from models import Shift, UserShift, User
    
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('schedule.site_schedule', site_id=site_id))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('schedule.site_schedule', site_id=site_id))
        
    if not file.filename.endswith(('.xls', '.xlsx')):
        flash('Invalid file format', 'danger')
        return redirect(url_for('schedule.site_schedule', site_id=site_id))
        
    try:
        df = pd.read_excel(file)
        required_cols = ['NRP', 'Shift Name', 'Date (YYYY-MM-DD)']
        for col in required_cols:
            if col not in df.columns:
                flash(f'Missing column: {col}', 'danger')
                return redirect(url_for('schedule.site_schedule', site_id=site_id))
                
        shifts = Shift.query.filter_by(site_id=site_id).all()
        shift_map = {s.name.lower(): s.id for s in shifts}
        
        users = User.query.filter_by(site_id=site_id).all()
        user_map = {str(u.nrp).strip(): u.id for u in users}
        
        success_count = 0
        for index, row in df.iterrows():
            nrp_val = str(row['NRP']).strip()
            if nrp_val.endswith('.0'):
                nrp_val = nrp_val[:-2]
            shift_name_val = str(row['Shift Name']).strip().lower()
            date_val = row['Date (YYYY-MM-DD)']
            
            tech_id = user_map.get(nrp_val)
            shift_id = shift_map.get(shift_name_val)
            
            try:
                if isinstance(date_val, str):
                    date_val = datetime.strptime(date_val, '%Y-%m-%d').date()
                elif isinstance(date_val, datetime):
                    date_val = date_val.date()
                else:
                    date_val = pd.to_datetime(date_val).date()
            except Exception as e:
                continue
                
            if not tech_id or not shift_id:
                continue
                
            existing = UserShift.query.filter_by(user_id=tech_id, shift_id=shift_id, date=date_val).first()
            if not existing:
                new_assignment = UserShift(user_id=tech_id, shift_id=shift_id, date=date_val)
                db.session.add(new_assignment)
                success_count += 1
                
        db.session.commit()
        flash(f'Successfully imported {success_count} schedule assignments.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing file: {str(e)}', 'danger')
        
    return redirect(url_for('schedule.site_schedule', site_id=site_id))

@schedule_bp.route('/template_absensi')
@login_required
def template_absensi():
    import pandas as pd
    import io
    from flask import send_file
    
    data = [
        {
            'NRP': '7179',
            'Date': '2026-08-31',
            'Check-In': '2026-08-31 14:56:51',
            'Check-Out': ''
        }
    ]
    df = pd.DataFrame(data, columns=['NRP', 'Date', 'Check-In', 'Check-Out'])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template Absensi')
    output.seek(0)
    
    return send_file(output, as_attachment=True, download_name='absensi_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@schedule_bp.route('/import_absensi/<int:site_id>', methods=['POST'])
@login_required
def import_absensi(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    import pandas as pd
    from models import User, AttendanceRecord, UserShift
    
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('schedule.site_schedule', site_id=site_id))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('schedule.site_schedule', site_id=site_id))
        
    if not file.filename.endswith(('.xls', '.xlsx')):
        flash('Invalid file format', 'danger')
        return redirect(url_for('schedule.site_schedule', site_id=site_id))
        
    try:
        df = pd.read_excel(file)
        required_cols = ['NRP', 'Date', 'Check-In', 'Check-Out']
        for col in required_cols:
            if col not in df.columns:
                flash(f'Missing column: {col}', 'danger')
                return redirect(url_for('schedule.site_schedule', site_id=site_id))
                
        users = User.query.filter_by(site_id=site_id).all()
        user_map = {str(u.nrp).strip(): u for u in users}
        
        success_count = 0
        from datetime import datetime, time, timedelta
        
        for index, row in df.iterrows():
            nrp_val = str(row['NRP']).strip()
            if nrp_val.endswith('.0'): nrp_val = nrp_val[:-2]
            
            user = user_map.get(nrp_val)
            if not user:
                continue
                
            in_val = row['Check-In']
            out_val = row['Check-Out']
            
            # Skip if there's no attendance data
            if (pd.isna(in_val) or str(in_val).strip() in ['', '-']) and (pd.isna(out_val) or str(out_val).strip() in ['', '-']):
                continue
                
            date_val = row['Date']
            try:
                if isinstance(date_val, str):
                    date_val = datetime.strptime(date_val, '%Y-%m-%d').date()
                elif isinstance(date_val, datetime):
                    date_val = date_val.date()
                else:
                    date_val = pd.to_datetime(date_val).date()
            except Exception:
                continue
            
            dt_in = None
            if pd.notna(in_val) and str(in_val).strip() not in ['', '-']:
                if isinstance(in_val, str):
                    try:
                        dt_in = datetime.strptime(str(in_val).strip(), '%Y-%m-%d %H:%M:%S')
                    except:
                        try:
                            t = datetime.strptime(str(in_val).strip(), '%H:%M:%S').time()
                            dt_in = datetime.combine(date_val, t)
                        except:
                            pass
                elif isinstance(in_val, datetime):
                    dt_in = in_val
                elif isinstance(in_val, time):
                    dt_in = datetime.combine(date_val, in_val)
                elif hasattr(in_val, 'time'): 
                    # If it's something like pd.Timestamp
                    try:
                        dt_in = in_val.to_pydatetime()
                    except:
                        dt_in = datetime.combine(date_val, in_val.time())
            
            dt_out = None
            if pd.notna(out_val) and str(out_val).strip() not in ['', '-']:
                if isinstance(out_val, str):
                    try:
                        dt_out = datetime.strptime(str(out_val).strip(), '%Y-%m-%d %H:%M:%S')
                    except:
                        try:
                            t = datetime.strptime(str(out_val).strip(), '%H:%M:%S').time()
                            dt_out = datetime.combine(date_val, t)
                        except:
                            pass
                elif isinstance(out_val, datetime):
                    dt_out = out_val
                elif isinstance(out_val, time):
                    dt_out = datetime.combine(date_val, out_val)
                elif hasattr(out_val, 'time'):
                    try:
                        dt_out = out_val.to_pydatetime()
                    except:
                        dt_out = datetime.combine(date_val, out_val.time())
                    
            if dt_in and dt_out and dt_out < dt_in:
                dt_out = dt_out + timedelta(days=1)
                
            ushift = UserShift.query.filter_by(user_id=user.id, date=date_val).first()
            ushift_id = ushift.id if ushift else None
            
            # Calculate status
            status = 'Tidak Ada Jadwal'
            if ushift and ushift.shift:
                shift = ushift.shift
                if shift.is_off_day:
                    from models import EmployeeOvertime
                    has_ot = EmployeeOvertime.query.filter_by(site_id=site_id, user_id=user.id, status='Approved').filter(EmployeeOvertime.start_date <= date_val, EmployeeOvertime.end_date >= date_val).first()
                    status = 'Lembur Hari Libur' if (dt_in and has_ot) else ('Hadir dalam Waktu Libur' if dt_in else 'Libur')
                else:
                    status_list = []
                    if dt_in and dt_in.time() > shift.start_time:
                        status_list.append('Terlambat')
                    if dt_out:
                        shift_end_dt = datetime.combine(date_val, shift.end_time)
                        if shift.end_time <= shift.start_time:
                            shift_end_dt += timedelta(days=1)
                        if dt_out < shift_end_dt:
                            status_list.append('Pulang Cepat')
                    if not dt_in: status_list.append('Tidak Absen Masuk')
                    if not dt_out: status_list.append('Tidak Absen Pulang')
                    if status_list:
                        status = ' & '.join(status_list)
                    else:
                        status = 'Sesuai Jadwal'
            
            rec = AttendanceRecord.query.filter_by(user_id=user.id, date=date_val).first()
            if not rec:
                rec = AttendanceRecord(user_id=user.id, date=date_val, nrp=user.nrp, nama=user.name)
                db.session.add(rec)
            
            if dt_in: rec.jam_masuk = dt_in
            if dt_out: rec.jam_pulang = dt_out
            if ushift_id: rec.user_shift_id = ushift_id
            rec.status = status
            
            success_count += 1
            
        db.session.commit()
        flash(f'Successfully imported {success_count} attendance records.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing file: {str(e)}', 'danger')
        
    return redirect(url_for('schedule.site_schedule', site_id=site_id))

@schedule_bp.route('/api/attendance/sync', methods=['POST'])
def sync_attendance():
    from models import User, UserShift, Shift, AttendanceRecord, db
    
    # We can secure this endpoint with a token if needed
    data = request.get_json()
    if not data or 'attendances' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid payload, expected {"attendances": [...]}'}), 400
        
    attendances_list = data['attendances']
    processed_count = 0
    
    for item in attendances_list:
        nrp_val = item.get('nrp')
        nama_val = item.get('nama')
        jam_masuk_str = item.get('jam_masuk')
        jam_pulang_str = item.get('jam_pulang')
        
        if not nrp_val or not jam_masuk_str:
            continue
            
        try:
            # Parse datetime
            jam_masuk_dt = datetime.strptime(jam_masuk_str, '%Y-%m-%d %H:%M:%S')
            jam_pulang_dt = datetime.strptime(jam_pulang_str, '%Y-%m-%d %H:%M:%S') if jam_pulang_str else None
            date_val = jam_masuk_dt.date()
        except ValueError:
            continue
            
        # Find User
        user = User.query.filter_by(nrp=nrp_val).first()
        user_id = user.id if user else None
        
        # Find UserShift
        user_shift = None
        status = 'Tidak Ada Jadwal'
        
        if user:
            from models import Site
            user_shift = UserShift.query.filter_by(user_id=user_id, date=date_val).first()
            if not user_shift:
                kp = Site.query.filter(Site.name.ilike('%Kantor Pusat%')).first()
                if kp and (user.site_id == kp.id or user.site_id is None):
                    user_shift = get_or_create_kantor_pusat_user_shift(user.id, date_val, kp.id)
            if user_shift:
                shift = user_shift.shift
                if shift:
                    if shift.is_off_day:
                        from models import EmployeeOvertime
                        has_ot = EmployeeOvertime.query.filter_by(user_id=user_id, status='Approved').filter(EmployeeOvertime.start_date <= date_val, EmployeeOvertime.end_date >= date_val).first()
                        status = 'Lembur Hari Libur' if (jam_masuk_dt and has_ot) else ('Hadir dalam Waktu Libur' if jam_masuk_dt else 'Libur')
                    else:
                        status_list = []
                        
                        if jam_masuk_dt.time() > shift.start_time:
                            status_list.append('Terlambat')
                            
                        if jam_pulang_dt:
                            from datetime import timedelta
                            shift_end_dt = datetime.combine(date_val, shift.end_time)
                            # Handle overnight shift (e.g., 22:00 to 06:00 or 16:00 to 00:00)
                            if shift.end_time <= shift.start_time:
                                shift_end_dt += timedelta(days=1)
                                
                            if jam_pulang_dt < shift_end_dt:
                                status_list.append('Pulang Cepat')
                        if not jam_masuk_dt: status_list.append('Tidak Absen Masuk')
                        if not jam_pulang_dt: status_list.append('Tidak Absen Pulang')
                                
                        if status_list:
                            status = ' & '.join(status_list)
                        else:
                            status = 'Sesuai Jadwal'
        
        # Upsert AttendanceRecord
        record = AttendanceRecord.query.filter_by(nrp=nrp_val, date=date_val).first()
        if not record:
            record = AttendanceRecord(nrp=nrp_val, date=date_val)
            db.session.add(record)
            
        record.nama = nama_val
        record.jam_masuk = jam_masuk_dt
        record.jam_pulang = jam_pulang_dt
        record.status = status
        record.user_id = user_id
        record.user_shift_id = user_shift.id if user_shift else None
        
        processed_count += 1
        
    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': f'Processed {processed_count} attendance records'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@schedule_bp.route('/attendance_recap')
@login_required
def attendance_recap():
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    from models import AttendanceRecord, User, Site, UserShift, Shift
    
    # Optional filtering
    site_id = request.args.get('site_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = db.session.query(UserShift, AttendanceRecord, User, Shift) \
        .join(User, UserShift.user_id == User.id) \
        .join(Shift, UserShift.shift_id == Shift.id) \
        .outerjoin(AttendanceRecord, db.and_(
            AttendanceRecord.date == UserShift.date,
            AttendanceRecord.user_id == UserShift.user_id
        ))
    
    from sqlalchemy import case
    if current_user.site_id:
        query = query.filter(User.site_id == current_user.site_id)
        sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        if site_id:
            kp = Site.query.filter(Site.name.ilike('%Kantor Pusat%')).first()
            if kp and site_id == kp.id:
                query = query.filter((User.site_id == site_id) | (User.site_id.is_(None)))
            else:
                query = query.filter(User.site_id == site_id)
        sites = Site.query.order_by(
            case((Site.name.ilike('%Kantor Pusat%'), 0), else_=1),
            Site.name.asc()
        ).all()
        
    if start_date:
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(UserShift.date >= s_date)
        except ValueError:
            pass
            
    if end_date:
        try:
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(UserShift.date <= e_date)
        except ValueError:
            pass
            
    # Sort ascending by date, then name
    query = query.order_by(UserShift.date.asc(), User.name.asc())
    
    # Pagination or all records? Let's limit to 1000 for safety
    records = query.limit(1000).all()
    
    formatted_records = []
    today = datetime.now().date()
    
    for ushift, rec, user, shift in records:
        shift_name = shift.name if shift else '-'
        shift_time = '-'
        if shift:
            if shift.is_off_day:
                shift_time = "Off Day / Libur"
            else:
                shift_time = f"{shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}"
                
        jam_masuk = '-'
        jam_pulang = '-'
        status = 'Belum Hadir'
        cepat_masuk = '-'
        telat_masuk = '-'
        cepat_pulang = '-'
        telat_pulang = '-'
        
        if rec:
            jam_masuk = rec.jam_masuk.strftime('%H:%M:%S') if rec.jam_masuk else '-'
            jam_pulang = rec.jam_pulang.strftime('%H:%M:%S') if rec.jam_pulang else '-'
            status = rec.status
            
            if shift and not shift.is_off_day:
                from datetime import datetime as dt, timedelta
                if rec.jam_masuk:
                    s_start = dt.combine(rec.date, shift.start_time)
                    a_in = rec.jam_masuk
                    
                    if a_in < s_start:
                        cepat_masuk = str(s_start - a_in).split('.')[0]
                        if len(cepat_masuk) == 7: cepat_masuk = "0" + cepat_masuk
                    elif a_in > s_start:
                        telat_masuk = str(a_in - s_start).split('.')[0]
                        if len(telat_masuk) == 7: telat_masuk = "0" + telat_masuk
                        
                if rec.jam_pulang:
                    s_end = dt.combine(rec.date, shift.end_time)
                    if shift.end_time < shift.start_time:
                        s_end += timedelta(days=1)
                        
                    a_out = rec.jam_pulang
                    
                    if a_out < s_end:
                        cepat_pulang = str(s_end - a_out).split('.')[0]
                        if len(cepat_pulang) == 7: cepat_pulang = "0" + cepat_pulang
                    elif a_out > s_end:
                        telat_pulang = str(a_out - s_end).split('.')[0]
                        if len(telat_pulang) == 7: telat_pulang = "0" + telat_pulang
                        
                if not status:
                    status_list = []
                    if telat_masuk != '-': status_list.append('Terlambat')
                    if cepat_pulang != '-': status_list.append('Pulang Cepat')
                    if not rec.jam_masuk: status_list.append('Tidak Absen Masuk')
                    if not rec.jam_pulang: status_list.append('Tidak Absen Pulang')
                    status = ' & '.join(status_list) if status_list else 'Sesuai Jadwal'
            
            elif shift and shift.is_off_day:
                if not status or status == 'Lembur Hari Libur':
                    from models import EmployeeOvertime
                    has_ot = EmployeeOvertime.query.filter_by(user_id=ushift.user_id, status='Approved').filter(EmployeeOvertime.start_date <= ushift.date, EmployeeOvertime.end_date >= ushift.date).first()
                    status = 'Lembur Hari Libur' if (rec.jam_masuk and has_ot) else ('Hadir dalam Waktu Libur' if rec.jam_masuk else 'Libur')
            else:
                if not status:
                    status = 'Tidak Ada Jadwal'
            
            if not status:
                status = 'Unknown'
        else:
            if ushift.date < today and not (shift and shift.is_off_day):
                status = 'Tidak Hadir'
            elif shift and shift.is_off_day:
                status = 'Libur'
            
        formatted_records.append({
            'id': rec.id if rec else f"ushift-{ushift.id}",
            'date': ushift.date.strftime('%Y-%m-%d'),
            'nrp': user.nrp,
            'nama': user.name,
            'shift_name': shift_name,
            'shift_time': shift_time,
            'jam_masuk': jam_masuk,
            'cepat_masuk': cepat_masuk,
            'telat_masuk': telat_masuk,
            'jam_pulang': jam_pulang,
            'cepat_pulang': cepat_pulang,
            'telat_pulang': telat_pulang,
            'status': status,
            'site_name': user.site.name if user and user.site else 'Kantor Pusat'
        })
    export_format = request.args.get('export')
    if export_format == 'excel':
        import pandas as pd
        from io import BytesIO
        from flask import send_file
        
        # Build Summary Data
        summary_data = {}
        for r in formatted_records:
            nama = r['nama']
            if nama not in summary_data:
                summary_data[nama] = {
                    'Nama': nama,
                    'Jml Hadir wkt Libur': 0,
                    'Total Kehadiran': 0,
                    'Total tdk Hadir': 0,
                    'Cuti': 0
                }
            
            is_present = (r['jam_masuk'] != '-' or r['jam_pulang'] != '-')
            is_off_day = (r['shift_time'] == 'Off Day / Libur' or 'Libur' in str(r['status']))
            
            if is_present:
                if is_off_day:
                    summary_data[nama]['Jml Hadir wkt Libur'] += 1
                
                summary_data[nama]['Total Kehadiran'] += 1
            else:
                if 'cuti' in str(r['status']).lower() or 'cuti' in str(r['shift_name']).lower():
                    summary_data[nama]['Cuti'] += 1
                elif not is_off_day and r['status'] != 'Tidak Ada Jadwal':
                    summary_data[nama]['Total tdk Hadir'] += 1

        df = pd.DataFrame(formatted_records)
        if df.empty:
            df = pd.DataFrame(columns=['date', 'nrp', 'nama', 'site_name', 'shift_name', 'shift_time', 'jam_masuk', 'cepat_masuk', 'telat_masuk', 'jam_pulang', 'cepat_pulang', 'telat_pulang', 'status'])
        else:
            df = df.drop(columns=['id'])
            df = df[['date', 'nrp', 'nama', 'site_name', 'shift_name', 'shift_time', 'jam_masuk', 'cepat_masuk', 'telat_masuk', 'jam_pulang', 'cepat_pulang', 'telat_pulang', 'status']]
            
        df.columns = ['Date', 'NRP', 'Name', 'Site', 'Expected Shift', 'Shift Time', 'Clock In', 'Cepat Masuk', 'Telat Masuk', 'Clock Out', 'Cepat Pulang', 'Telat Pulang', 'Status']
        
        summary_df = pd.DataFrame(list(summary_data.values()))
        if summary_df.empty:
            summary_df = pd.DataFrame(columns=['Nama', 'Jml Hadir wkt Libur', 'Total Kehadiran', 'Total tdk Hadir', 'Cuti'])
            
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Attendance Recap')
            summary_df.to_excel(writer, index=False, sheet_name='Sheet1')
        
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='Attendance_Recap.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    elif export_format == 'detail_excel':
        import xlsxwriter
        from io import BytesIO
        from flask import send_file
        
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Add formats
        header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True})
        data_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        data_center_fmt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
        bold_fmt = workbook.add_format({'bold': True})
        
        # Group by NRP
        users_data = {}
        for r in formatted_records:
            nrp = r['nrp']
            if nrp not in users_data:
                users_data[nrp] = []
            users_data[nrp].append(r)
            
        for nrp, records_list in users_data.items():
            sheet_name = f"{records_list[0]['nama'].split()[0]}_{nrp}"[:31]
            for ch in ['*', ':', '?', '[', ']', '/']:
                sheet_name = sheet_name.replace(ch, '')
            
            ws = workbook.add_worksheet(sheet_name)
            
            ws.write(1, 4, "JAYA TEKNIK INDONESIA", title_fmt)
            ws.write(3, 0, "LAPORAN PER PERIODE KEHADIRAN", bold_fmt)
            
            ws.write(5, 0, "NRP", bold_fmt)
            ws.write(5, 1, f"'{nrp}")
            ws.write(6, 0, "Employee Name", bold_fmt)
            ws.write(6, 1, records_list[0]['nama'])
            ws.write(7, 0, "Site", bold_fmt)
            ws.write(7, 1, records_list[0]['site_name'])
            
            dates = [r['date'] for r in records_list]
            period_str = f"{min(dates)} - {max(dates)}" if dates else "-"
            ws.write(7, 4, "Periode:", bold_fmt)
            ws.write(7, 5, period_str)
            
            # Table headers
            ws.merge_range(9, 0, 10, 0, "Tanggal", header_fmt)
            ws.merge_range(9, 1, 9, 2, "Jadwal", header_fmt)
            ws.write(10, 1, "Masuk", header_fmt)
            ws.write(10, 2, "Pulang", header_fmt)
            
            ws.merge_range(9, 3, 9, 4, "Jam Kerja Aktual", header_fmt)
            ws.write(10, 3, "Masuk", header_fmt)
            ws.write(10, 4, "Pulang", header_fmt)
            
            ws.merge_range(9, 5, 9, 6, "Ket. Masuk", header_fmt)
            ws.write(10, 5, "Cepat", header_fmt)
            ws.write(10, 6, "Telat", header_fmt)
            
            ws.merge_range(9, 7, 9, 8, "Ket. Pulang", header_fmt)
            ws.write(10, 7, "Cepat", header_fmt)
            ws.write(10, 8, "Lebih", header_fmt)
            
            ws.merge_range(9, 9, 10, 9, "Jml Jam Kerja", header_fmt)
            ws.merge_range(9, 10, 10, 10, "Keterangan", header_fmt)
            
            ws.set_column(0, 0, 12)
            ws.set_column(1, 4, 10)
            ws.set_column(5, 8, 10)
            ws.set_column(9, 10, 15)
            
            row = 11
            
            s_kehadiran = 0
            s_hadir_libur = 0
            s_ontime = 0
            s_terlambat = 0
            s_pulang_cepat = 0
            s_tidak_absen_pulang = 0
            
            from datetime import timedelta
            for r in records_list:
                tgl = r['date']
                s_in, s_out = '-', '-'
                if r['shift_time'] != 'Off Day / Libur' and r['shift_time'] != '-':
                    parts = r['shift_time'].split(' - ')
                    if len(parts) == 2:
                        s_in, s_out = parts
                        
                a_in = r['jam_masuk']
                a_out = r['jam_pulang']
                c_in = r['cepat_masuk']
                t_in = r['telat_masuk']
                c_out = r['cepat_pulang']
                t_out = r['telat_pulang']
                status = r['status']
                
                jml_jam = '-'
                if a_in != '-' and a_out != '-':
                    try:
                        t1 = datetime.strptime(a_in, '%H:%M:%S')
                        t2 = datetime.strptime(a_out, '%H:%M:%S')
                        if t2 < t1:
                            t2 = t2 + timedelta(days=1)
                        diff = str(t2 - t1).split('.')[0]
                        if len(diff) == 7: diff = "0" + diff
                        jml_jam = diff
                    except:
                        pass
                
                ket = status
                if ket == 'Tidak Hadir' or ket == 'Belum Hadir': ket = 'TH'
                
                ws.write(row, 0, tgl, data_center_fmt)
                ws.write(row, 1, s_in, data_center_fmt)
                ws.write(row, 2, s_out, data_center_fmt)
                ws.write(row, 3, a_in, data_center_fmt)
                ws.write(row, 4, a_out, data_center_fmt)
                ws.write(row, 5, c_in, data_center_fmt)
                ws.write(row, 6, t_in, data_center_fmt)
                ws.write(row, 7, c_out, data_center_fmt)
                ws.write(row, 8, t_out, data_center_fmt)
                ws.write(row, 9, jml_jam, data_center_fmt)
                ws.write(row, 10, ket, data_fmt)
                
                is_present = (a_in != '-' or a_out != '-')
                is_off_day = (r['shift_time'] == 'Off Day / Libur' or 'Libur' in str(status))
                if is_present:
                    if is_off_day:
                        s_hadir_libur += 1
                    else:
                        s_kehadiran += 1
                    
                    if t_in != '-' or 'Terlambat' in str(status):
                        s_terlambat += 1
                    if c_out != '-' or 'Pulang Cepat' in str(status):
                        s_pulang_cepat += 1
                    if a_out == '-' or 'Tidak Absen Pulang' in str(status):
                        s_tidak_absen_pulang += 1
                        
                    if not is_off_day and (status == 'Sesuai Jadwal' or (t_in == '-' and c_out == '-' and a_in != '-' and a_out != '-' and 'Terlambat' not in str(status) and 'Pulang Cepat' not in str(status))):
                        s_ontime += 1
                        
                row += 1
                
            row += 2
            ws.write(row, 0, "Keterangan", bold_fmt)
            row += 1
            start_sig_row = row
            ws.write(row, 0, "Jml Kehadiran")
            ws.write(row, 2, s_kehadiran)
            ws.write(row, 3, "Jadwal asli")
            
            row += 1
            ws.write(row, 0, "Jml Hadir wkt Libur")
            ws.write(row, 2, s_hadir_libur)
            ws.write(row, 3, "HDL")
            
            row += 1
            ws.write(row, 0, "Total Kehadiran")
            ws.write(row, 2, s_ontime)
            ws.write(row, 3, "Jumlah ontime")
            
            row += 1
            ws.write(row, 0, "Terlambat")
            ws.write(row, 2, s_terlambat)
            
            row += 1
            ws.write(row, 0, "Pulang Cepat")
            ws.write(row, 2, s_pulang_cepat)
            
            row += 1
            end_sig_row = row
            ws.write(row, 0, "Tidak Absen Pulang")
            ws.write(row, 2, s_tidak_absen_pulang)
            
            ws.write(start_sig_row, 4, "Dibuat oleh")
            ws.write(start_sig_row, 6, "Disetujui")
            ws.write(start_sig_row, 8, "Mengetahui")
            
            ws.write(end_sig_row, 4, "Admin / HR")
            ws.write(end_sig_row, 6, "Manager")
            ws.write(end_sig_row, 8, "Site Manager")
            
        workbook.close()
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='Rekap_Detail_Karyawan.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    elif export_format == 'pdf':
        from pdf_utils import SafeFPDF as FPDF
        from io import BytesIO
        from flask import send_file
        
        class PDF(FPDF):
            def __init__(self):
                super().__init__(orientation='L')
                
            def header(self):
                self.set_font('helvetica', 'B', 12)
                self.cell(0, 10, 'Attendance Recap', align='C')
                self.ln(15)
                # Table Header
                self.set_font('helvetica', 'B', 8)
                self.cell(18, 8, 'Date', border=1)
                self.cell(15, 8, 'NRP', border=1)
                self.cell(35, 8, 'Name', border=1)
                self.cell(25, 8, 'Site', border=1)
                self.cell(20, 8, 'Shift', border=1)
                self.cell(18, 8, 'In', border=1)
                self.cell(18, 8, 'Cepat Msk', border=1)
                self.cell(18, 8, 'Telat Msk', border=1)
                self.cell(18, 8, 'Out', border=1)
                self.cell(18, 8, 'Cepat Plg', border=1)
                self.cell(18, 8, 'Telat Plg', border=1)
                self.cell(20, 8, 'Status', border=1)
                self.ln()
                
            def footer(self):
                self.set_y(-15)
                self.set_font('helvetica', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', align='C')
                
        pdf = PDF()
        pdf.add_page()
        pdf.set_font('helvetica', '', 7)
        
        for r in formatted_records:
            pdf.cell(18, 8, str(r['date']), border=1)
            pdf.cell(15, 8, str(r['nrp']), border=1)
            name = str(r['nama'])[:18]
            pdf.cell(35, 8, name, border=1)
            site = str(r['site_name'])[:12]
            pdf.cell(25, 8, site, border=1)
            shift = str(r['shift_name'])[:10]
            pdf.cell(20, 8, shift, border=1)
            pdf.cell(18, 8, str(r['jam_masuk']), border=1)
            pdf.cell(18, 8, str(r['cepat_masuk']), border=1)
            pdf.cell(18, 8, str(r['telat_masuk']), border=1)
            pdf.cell(18, 8, str(r['jam_pulang']), border=1)
            pdf.cell(18, 8, str(r['cepat_pulang']), border=1)
            pdf.cell(18, 8, str(r['telat_pulang']), border=1)
            status = str(r['status'])[:10]
            pdf.cell(20, 8, status, border=1)
            pdf.ln()
            
        pdf_out = pdf.output(dest='S')
        if isinstance(pdf_out, str):
            pdf_bytes = pdf_out.encode('latin1')
        else:
            pdf_bytes = bytes(pdf_out)
            
        output = BytesIO(pdf_bytes)
        return send_file(output, as_attachment=True, download_name='Attendance_Recap.pdf', mimetype='application/pdf')

    return render_template('schedule/attendance_recap.html', records=formatted_records, sites=sites, current_site_id=site_id, start_date=start_date, end_date=end_date)

def fetch_odoo_attendance_raw(date_from=None, date_to=None, nrp=None):
    from models import SystemSetting
    import requests
    from datetime import datetime

    sync_method_setting = SystemSetting.query.filter_by(setting_key='ATTENDANCE_SYNC_METHOD').first()
    sync_method = sync_method_setting.setting_value.strip() if sync_method_setting and sync_method_setting.setting_value else 'pull'

    today_str = get_wib_now().strftime('%Y-%m-%d')
    if not date_from:
        date_from = today_str
    if not date_to:
        date_to = date_from

    if sync_method == 'zkteco':
        try:
            from zk import ZK
        except ImportError:
            return None, 'Library pyzk belum diinstal. Jalankan pip install pyzk.'
            
        ip_setting = SystemSetting.query.filter_by(setting_key='ATTENDANCE_ZKTECO_IP').first()
        ip = ip_setting.setting_value.strip() if ip_setting and ip_setting.setting_value else '192.168.1.12'

        port_setting = SystemSetting.query.filter_by(setting_key='ATTENDANCE_ZKTECO_PORT').first()
        try:
            port = int(port_setting.setting_value.strip())
        except:
            port = 4370
            
        zk_conn = ZK(ip, port=port, timeout=10, password=0, force_udp=False, ommit_ping=False)
        conn = None
        try:
            conn = zk_conn.connect()
            attendances = conn.get_attendance()
            
            def parse_d(d_str):
                if not d_str: return None
                for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        return datetime.strptime(d_str, fmt).date()
                    except ValueError:
                        pass
                return None
                
            df = parse_d(date_from)
            dt = parse_d(date_to)
            
            results = []
            if attendances:
                for att in attendances:
                    att_date = att.timestamp.date()
                    if df and att_date < df:
                        continue
                    if dt and att_date > dt:
                        continue
                    
                    if nrp and str(nrp).strip() != str(att.user_id):
                        continue
                        
                    time_str = att.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    results.append({
                        'nrp': str(att.user_id),
                        'nama_karyawan': str(att.user_id),
                        'check_in': time_str,
                        'check_out': time_str,
                        'date': att.timestamp.strftime('%Y-%m-%d')
                    })
                
            return results, None
        except Exception as e:
            return None, f"Gagal terhubung ke mesin ZKTeco ({ip}:{port}): {str(e)}"
        finally:
            if conn:
                try:
                    conn.disconnect()
                except:
                    pass

    api_url_setting = SystemSetting.query.filter_by(setting_key='ATTENDANCE_API_URL').first()
    if not api_url_setting or not api_url_setting.setting_value:
        return None, 'API URL Odoo belum dikonfigurasi di Pengaturan.'

    api_url = api_url_setting.setting_value.strip()
    
    token_setting = SystemSetting.query.filter_by(setting_key='ATTENDANCE_API_BEARER_TOKEN').first()
    token = token_setting.setting_value.strip() if token_setting and token_setting.setting_value else 'GxP1UohqbRGmJWSvurcrqIMNMKI-GLzKHHBxEoLC1z4'

    params = {
        'date_from': date_from,
        'date_to': date_to
    }
    if nrp:
        params['nrp'] = str(nrp).strip()

    headers = {
        'Origin': 'https://cmms.basjti.com/',
        'Referer': 'https://cmms.basjti.com/',
        'User-Agent': 'CMMS-Attendance-Sync/1.0'
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=60)
    except Exception as e:
        return None, f'Gagal menghubungi server API Odoo: {str(e)}'

    if resp.status_code != 200:
        return None, f'API Odoo merespons HTTP {resp.status_code}: {resp.text[:200]}'

    try:
        res_json = resp.json()
    except Exception as e:
        return None, f'Gagal mengurai respons JSON: {str(e)}'

    raw_results = res_json.get('results', [])
    return raw_results, None

def execute_odoo_attendance_pull(date_from=None, date_to=None, nrp=None):
    from models import db, User, UserShift, Shift, AttendanceRecord
    from datetime import datetime, date as dt_date, timedelta

    raw_results, error_msg = fetch_odoo_attendance_raw(date_from=date_from, date_to=date_to, nrp=nrp)
    if error_msg:
        return {'status': 'error', 'message': error_msg}

    if not raw_results:
        return {
            'status': 'success',
            'message': f'Tidak ada data absensi yang ditemukan untuk periode {date_from} s/d {date_to}.',
            'total_fetched': 0,
            'processed': 0,
            'matched_users': 0
        }

    def parse_dt(dt_val):
        if not dt_val or dt_val is False or str(dt_val).strip().lower() in ['false', 'none', 'null', '']:
            return None
        s = str(dt_val).strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass
        return None

    def parse_d(d_val):
        if not d_val:
            return None
        s = str(d_val).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        return None

    # Group by (nrp, date)
    grouped = {}
    for item in raw_results:
        item_nrp = str(item.get('nrp', '')).strip()
        if not item_nrp:
            continue

        dt_masuk = parse_dt(item.get('check_in'))
        dt_pulang = parse_dt(item.get('check_out'))
        d_val = parse_d(item.get('date'))
        if not d_val and dt_masuk:
            d_val = dt_masuk.date()
        if not d_val:
            continue

        key = (item_nrp, d_val)
        if key not in grouped:
            grouped[key] = {
                'nama': item.get('nama_karyawan') or item.get('nama', ''),
                'check_in': dt_masuk,
                'check_out': dt_pulang
            }
        else:
            if dt_masuk:
                if grouped[key]['check_in'] is None or dt_masuk < grouped[key]['check_in']:
                    grouped[key]['check_in'] = dt_masuk
            if dt_pulang:
                if grouped[key]['check_out'] is None or dt_pulang > grouped[key]['check_out']:
                    grouped[key]['check_out'] = dt_pulang

    all_users = User.query.filter(User.nrp.isnot(None), User.nrp != '').all()
    user_nrp_map = {}
    for u in all_users:
        if u.nrp:
            clean_nrp = str(u.nrp).strip()
            user_nrp_map[clean_nrp] = u
            user_nrp_map[clean_nrp.lstrip('0')] = u
            user_nrp_map[clean_nrp.zfill(5)] = u
            user_nrp_map[clean_nrp.zfill(6)] = u

    processed_count = 0
    matched_cmms_users = 0
    today_date = dt_date.today()

    for (emp_nrp, att_date), info in grouped.items():
        # Cari user berdasarkan NRP di database CMMS
        user = user_nrp_map.get(emp_nrp) or user_nrp_map.get(emp_nrp.lstrip('0'))

        # JIKA KARYAWAN TIDAK ADA DI DATABASE CMMS -> OTOMATIS DI-IGNORE / DILEWATI
        if not user:
            continue

        matched_cmms_users += 1
        user_id = user.id

        jam_masuk_dt = info['check_in']
        jam_pulang_dt = info['check_out']

        user_shift = None
        status = 'Tidak Ada Jadwal'

        user_shift = UserShift.query.filter_by(user_id=user.id, date=att_date).first()
        if not user_shift:
            from models import Site
            kp = Site.query.filter(Site.name.ilike('%Kantor Pusat%')).first()
            if kp and (user.site_id == kp.id or user.site_id is None):
                user_shift = get_or_create_kantor_pusat_user_shift(user.id, att_date, kp.id)
        if user_shift and user_shift.shift:
            shift = user_shift.shift
            if shift.is_off_day:
                from models import EmployeeOvertime
                has_ot = EmployeeOvertime.query.filter_by(user_id=user.id, status='Approved').filter(EmployeeOvertime.start_date <= att_date, EmployeeOvertime.end_date >= att_date).first()
                status = 'Lembur Hari Libur' if (jam_masuk_dt and has_ot) else ('Hadir dalam Waktu Libur' if jam_masuk_dt else 'Libur')
            else:
                status_list = []
                if jam_masuk_dt:
                    if jam_masuk_dt.time() > shift.start_time:
                        status_list.append('Terlambat')
                else:
                    status_list.append('Tidak Absen Masuk')

                if jam_pulang_dt:
                    shift_end_dt = datetime.combine(att_date, shift.end_time)
                    if shift.end_time <= shift.start_time:
                        shift_end_dt += timedelta(days=1)
                    if jam_pulang_dt < shift_end_dt:
                        status_list.append('Pulang Cepat')
                else:
                    if att_date < today_date:
                        status_list.append('Tidak Absen Pulang')
                    else:
                        status_list.append('Belum Absen Pulang')

                if status_list:
                    status = ' & '.join(status_list)
                else:
                    status = 'Sesuai Jadwal'
        else:
            status = 'Tidak Ada Jadwal'

        # Upsert AttendanceRecord
        record = AttendanceRecord.query.filter_by(user_id=user_id, date=att_date).first()
        if not record:
            record = AttendanceRecord.query.filter_by(nrp=emp_nrp, date=att_date).first()

        if not record:
            record = AttendanceRecord(nrp=emp_nrp, date=att_date)
            db.session.add(record)

        record.nama = user.name or info['nama']
        record.jam_masuk = jam_masuk_dt
        record.jam_pulang = jam_pulang_dt
        record.status = status
        record.user_id = user_id
        record.user_shift_id = user_shift.id if user_shift else None

        processed_count += 1

    try:
        db.session.commit()
        return {
            'status': 'success',
            'message': f'Berhasil memproses {processed_count} data absensi ({matched_cmms_users} teknisi CMMS cocok dengan jadwal) untuk periode {date_from} s/d {date_to}.',
            'total_fetched': len(raw_results),
            'processed': processed_count,
            'matched_users': matched_cmms_users
        }
    except Exception as e:
        db.session.rollback()
        return {'status': 'error', 'message': f'Database error: {str(e)}'}


@schedule_bp.route('/api/attendance/pull', methods=['POST'])
@login_required
def pull_attendance():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    from models import SystemSetting
    sync_method = SystemSetting.query.filter_by(setting_key='ATTENDANCE_SYNC_METHOD').first()
    if sync_method and sync_method.setting_value == 'push':
        return jsonify({'status': 'error', 'message': 'Sistem saat ini disetel ke mode Push (menunggu data dikirim IT Team). Ubah ke Pull di Settings.'}), 400

    data = request.get_json(silent=True) or {}
    date_from = data.get('date_from') or request.form.get('date_from') or request.args.get('date_from')
    date_to = data.get('date_to') or request.form.get('date_to') or request.args.get('date_to')
    nrp = data.get('nrp') or request.form.get('nrp') or request.args.get('nrp')

    try:
        result = execute_odoo_attendance_pull(date_from=date_from, date_to=date_to, nrp=nrp)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Terjadi kesalahan saat memproses data Odoo: {str(e)}'}), 500


@schedule_bp.route('/api/attendance/raw_json', methods=['GET', 'POST'])
@login_required
def get_raw_odoo_attendance_json():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    date_from = request.args.get('date_from') or data.get('date_from')
    date_to = request.args.get('date_to') or data.get('date_to')
    nrp = request.args.get('nrp') or data.get('nrp')

    raw_results, error_msg = fetch_odoo_attendance_raw(date_from=date_from, date_to=date_to, nrp=nrp)
    if error_msg:
        return jsonify({'status': 'error', 'message': error_msg}), 400

    if request.args.get('raw') in ['1', 'true', 'True']:
        return jsonify(raw_results if raw_results is not None else [])

    return jsonify({
        'status': 'success',
        'date_from': date_from,
        'date_to': date_to,
        'nrp': nrp,
        'count': len(raw_results) if raw_results is not None else 0,
        'results': raw_results or []
    })


@schedule_bp.route('/api/attendance/export_raw_odoo', methods=['GET'])
@login_required
def export_raw_odoo_attendance():
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Unauthorized', 'danger')
        return redirect(url_for('schedule.attendance_recap'))

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    nrp = request.args.get('nrp')

    raw_results, error_msg = fetch_odoo_attendance_raw(date_from=date_from, date_to=date_to, nrp=nrp)
    if error_msg:
        flash(f"Gagal menarik data dari Odoo: {error_msg}", 'danger')
        return redirect(url_for('schedule.attendance_recap'))

    if not raw_results:
        flash(f'Tidak ada data absensi mentah yang ditemukan dari Odoo untuk periode {date_from or "-"} s/d {date_to or "-"}.', 'warning')
        return redirect(url_for('schedule.attendance_recap'))

    import xlsxwriter
    from io import BytesIO
    from flask import send_file
    from datetime import datetime
    from models import User

    # Mapping user CMMS
    all_users = User.query.filter(User.nrp.isnot(None), User.nrp != '').all()
    user_nrp_map = {}
    for u in all_users:
        if u.nrp:
            clean_nrp = str(u.nrp).strip()
            user_nrp_map[clean_nrp] = u
            user_nrp_map[clean_nrp.lstrip('0')] = u

    rows = []
    for idx, item in enumerate(raw_results, 1):
        item_nrp = str(item.get('nrp', '')).strip()
        cmms_user = user_nrp_map.get(item_nrp) or user_nrp_map.get(item_nrp.lstrip('0'))
        
        status_match = "Cocok di CMMS" if cmms_user else "Tidak Terdaftar di CMMS"
        site_name = cmms_user.site.name if (cmms_user and cmms_user.site) else "-"
        cmms_name = cmms_user.name if cmms_user else "-"

        row = {
            'No': idx,
            'NRP (Odoo)': item_nrp,
            'Nama Karyawan (Odoo)': item.get('nama_karyawan') or item.get('nama') or '-',
            'Tanggal': str(item.get('date') or '-'),
            'Clock In (Odoo)': str(item.get('check_in') or '-'),
            'Clock Out (Odoo)': str(item.get('check_out') or '-'),
            'Status Integrasi CMMS': status_match,
            'Site (CMMS)': site_name,
            'Nama Teknisi (CMMS)': cmms_name,
        }
        # Add any extra raw fields returned by Odoo
        for k, v in item.items():
            if k not in ['nrp', 'nama_karyawan', 'nama', 'date', 'check_in', 'check_out']:
                row[f"Odoo: {k}"] = str(v) if v is not None else '-'
        rows.append(row)

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = workbook.add_worksheet('Data Mentah Odoo')

    # Styles
    title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#1e293b'})
    subtitle_fmt = workbook.add_format({'font_size': 10, 'font_color': '#64748b'})
    header_fmt = workbook.add_format({
        'bold': True,
        'font_color': '#ffffff',
        'bg_color': '#1e40af',
        'align': 'center',
        'valign': 'vcenter',
        'border': 1,
        'text_wrap': True
    })
    cell_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter'})
    cell_center_fmt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})

    ws.write(0, 0, "PT JAYA TEKNIK INDONESIA", title_fmt)
    ws.write(1, 0, f"Data Mentah Absensi (Log API Odoo) | Periode: {date_from or '-'} s/d {date_to or '-'}", subtitle_fmt)
    ws.write(2, 0, f"Total Log Ditarik: {len(rows)} baris | Diunduh Pada: {get_wib_now().strftime('%d/%m/%Y %H:%M:%S')} WIB", subtitle_fmt)

    if rows:
        headers = list(rows[0].keys())
        start_row = 4
        for col_num, h in enumerate(headers):
            ws.write(start_row, col_num, h, header_fmt)

        for row_num, row_data in enumerate(rows, start=start_row + 1):
            for col_num, h in enumerate(headers):
                val = row_data.get(h, '')
                if h in ['No', 'NRP (Odoo)', 'Tanggal', 'Clock In (Odoo)', 'Clock Out (Odoo)', 'Status Integrasi CMMS', 'Site (CMMS)']:
                    ws.write(row_num, col_num, val, cell_center_fmt)
                else:
                    ws.write(row_num, col_num, val, cell_fmt)

        for col_num, h in enumerate(headers):
            max_len = max([len(str(r.get(h, ''))) for r in rows] + [len(h)])
            ws.set_column(col_num, col_num, min(max(max_len + 3, 10), 45))

    workbook.close()
    output.seek(0)
    filename = f"Data_Mentah_Absensi_Odoo_{date_from or 'all'}_sd_{date_to or 'all'}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@schedule_bp.route('/api/shifts/<int:site_id>/user_daily_shifts', methods=['GET'])
@login_required
def api_user_daily_shifts(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Tanggal wajib diisi'}), 400
        
    try:
        from models import User, Shift, UserShift, Site
        site = Site.query.get(site_id)
        is_kp = bool(site and 'kantor pusat' in site.name.lower())
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        if is_kp:
            users = User.query.filter(
                (User.site_id == site_id) | (User.site_id.is_(None))
            ).order_by(User.name).all()
        else:
            users = User.query.filter_by(site_id=site_id).order_by(User.name).all()
        user_ids = [u.id for u in users]
        
        shifts = Shift.query.filter_by(site_id=site_id).all()
        shift_dict = {s.id: s for s in shifts}
        
        assignments = UserShift.query.filter(
            UserShift.user_id.in_(user_ids),
            UserShift.date == target_date
        ).all()
        
        assign_map = {a.user_id: a for a in assignments}
        
        result = []
        for u in users:
            a = assign_map.get(u.id)
            if a and a.shift_id in shift_dict:
                s = shift_dict[a.shift_id]
                time_str = "Off Day" if s.is_off_day else (f"{s.start_time.strftime('%H:%M')} - {s.end_time.strftime('%H:%M')}" if s.start_time and s.end_time else "-")
                result.append({
                    'id': u.id,
                    'name': u.name,
                    'nrp': u.nrp,
                    'shift_id': s.id,
                    'shift_name': s.name,
                    'shift_time': time_str,
                    'is_off_day': s.is_off_day
                })
            else:
                result.append({
                    'id': u.id,
                    'name': u.name,
                    'nrp': u.nrp,
                    'shift_id': None,
                    'shift_name': 'Belum Ada Jadwal',
                    'shift_time': '-',
                    'is_off_day': False
                })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@schedule_bp.route('/api/shifts/<int:site_id>/swap', methods=['POST'])
@login_required
def api_swap_shifts(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json or {}
    swap_type = data.get('swap_type', 'swap')
    date_str = data.get('date')
    notes = data.get('notes', '')
    
    if not date_str:
        return jsonify({'success': False, 'error': 'Tanggal wajib diisi'}), 400
        
    try:
        from models import User, Shift, UserShift
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        if swap_type == 'swap':
            user_id_1 = data.get('user_id_1')
            user_id_2 = data.get('user_id_2')
            
            if not user_id_1 or not user_id_2:
                return jsonify({'success': False, 'error': 'Pilih kedua karyawan yang akan ditukar shiftnya'}), 400
            if user_id_1 == user_id_2:
                return jsonify({'success': False, 'error': 'Karyawan 1 dan Karyawan 2 tidak boleh orang yang sama'}), 400
                
            u1 = User.query.get(user_id_1)
            u2 = User.query.get(user_id_2)
            if not u1 or u1.site_id != site_id or not u2 or u2.site_id != site_id:
                return jsonify({'success': False, 'error': 'Karyawan tidak valid untuk site ini'}), 400
                
            shift_assign_1 = UserShift.query.filter_by(user_id=user_id_1, date=target_date).first()
            shift_assign_2 = UserShift.query.filter_by(user_id=user_id_2, date=target_date).first()
            
            s1_id = shift_assign_1.shift_id if shift_assign_1 else None
            s2_id = shift_assign_2.shift_id if shift_assign_2 else None
            
            if not s1_id and not s2_id:
                return jsonify({'success': False, 'error': 'Kedua karyawan belum memiliki jadwal shift pada tanggal ini'}), 400
                
            # Berikan shift 2 ke user 1
            if s2_id:
                if shift_assign_1:
                    shift_assign_1.shift_id = s2_id
                else:
                    db.session.add(UserShift(user_id=user_id_1, shift_id=s2_id, date=target_date))
            else:
                if shift_assign_1:
                    db.session.delete(shift_assign_1)
                    
            # Berikan shift 1 ke user 2
            if s1_id:
                if shift_assign_2:
                    shift_assign_2.shift_id = s1_id
                else:
                    db.session.add(UserShift(user_id=user_id_2, shift_id=s1_id, date=target_date))
            else:
                if shift_assign_2:
                    db.session.delete(shift_assign_2)
                    
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Berhasil menukar shift antara {u1.name} dan {u2.name} pada {target_date.strftime("%d/%m/%Y")}.'
            })
            
        elif swap_type == 'change':
            user_id = data.get('user_id')
            target_shift_id = data.get('target_shift_id')
            
            if not user_id or not target_shift_id:
                return jsonify({'success': False, 'error': 'Karyawan dan Shift Tujuan wajib dipilih'}), 400
                
            u = User.query.get(user_id)
            if not u or u.site_id != site_id:
                return jsonify({'success': False, 'error': 'Karyawan tidak valid'}), 400
                
            target_shift = Shift.query.get(target_shift_id)
            if not target_shift or target_shift.site_id != site_id:
                return jsonify({'success': False, 'error': 'Shift tujuan tidak valid'}), 400
                
            user_shift = UserShift.query.filter_by(user_id=user_id, date=target_date).first()
            if user_shift:
                user_shift.shift_id = target_shift.id
            else:
                db.session.add(UserShift(user_id=user_id, shift_id=target_shift.id, date=target_date))
                
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Berhasil mengubah shift {u.name} menjadi {target_shift.name} pada {target_date.strftime("%d/%m/%Y")}.'
            })
        else:
            return jsonify({'success': False, 'error': 'Tipe pergantian tidak valid'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/api/performance/<int:site_id>')
@login_required
def api_performance(site_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'error': 'Unauthorized'}), 403

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        now = datetime.now()
        year = year or now.year
        month = month or now.month

    try:
        from models import User, UserShift, Shift, AttendanceRecord, EmployeeOvertime, EmployeeLeave, Site
        from sqlalchemy import extract
        from sqlalchemy.orm import joinedload, selectinload
        from datetime import timedelta, date
        site = Site.query.get(site_id)
        is_kp = bool(site and 'kantor pusat' in (site.name or '').lower())
        
        # 1. Base users registered to this site
        if is_kp:
            base_users = User.query.filter(
                (User.site_id == site_id) | (User.site_id.is_(None))
            ).filter(User.role != 'Admin').all()
            if not base_users:
                base_users = User.query.filter(
                    (User.site_id == site_id) | (User.site_id.is_(None))
                ).all()
        else:
            base_users = User.query.filter(User.site_id == site_id, User.role != 'Admin').all()

        # 2. Get all shifts belonging to this site
        site_shifts = Shift.query.filter_by(site_id=site_id).all()
        site_shift_ids = [s.id for s in site_shifts]

        # 3. Find any other users who have shift assignments at this site during this month/year
        users_with_shifts = []
        if site_shift_ids:
            extra_uids = [r[0] for r in db.session.query(UserShift.user_id).filter(
                UserShift.shift_id.in_(site_shift_ids),
                extract('year', UserShift.date) == year,
                extract('month', UserShift.date) == month
            ).distinct().all() if r[0]]
            if extra_uids:
                users_with_shifts = User.query.filter(User.id.in_(extra_uids)).all()

        # Combine into unique users dictionary
        user_dict = {u.id: u for u in base_users}
        for u in users_with_shifts:
            user_dict[u.id] = u
        users = list(user_dict.values())
        user_ids = [u.id for u in users]
        
        # 4. Get User Shifts for the month at this site
        shifts_query = []
        if user_ids and site_shift_ids:
            shifts_query = UserShift.query.options(
                joinedload(UserShift.shift),
                selectinload(UserShift.attendance_records)
            ).join(Shift).filter(
                UserShift.user_id.in_(user_ids),
                UserShift.shift_id.in_(site_shift_ids),
                extract('year', UserShift.date) == year,
                extract('month', UserShift.date) == month,
                Shift.is_off_day == False
            ).all()
        elif user_ids:
            shifts_query = UserShift.query.options(
                joinedload(UserShift.shift),
                selectinload(UserShift.attendance_records)
            ).join(Shift).filter(
                UserShift.user_id.in_(user_ids),
                extract('year', UserShift.date) == year,
                extract('month', UserShift.date) == month,
                Shift.is_off_day == False
            ).all()
        
        # Group shifts by user
        user_shifts_map = {u.id: [] for u in users}
        for us in shifts_query:
            if us.user_id in user_shifts_map:
                user_shifts_map[us.user_id].append(us)
            
        # Get Overtime for the month
        ot_filter = (EmployeeOvertime.site_id == site_id)
        if is_kp:
            ot_filter = ot_filter | (EmployeeOvertime.site_id.is_(None))
            
        ot_query = []
        if user_ids:
            ot_query = EmployeeOvertime.query.filter(
                EmployeeOvertime.user_id.in_(user_ids),
                ot_filter,
                extract('year', EmployeeOvertime.start_date) == year,
                extract('month', EmployeeOvertime.start_date) == month,
                EmployeeOvertime.status == 'Approved'
            ).all()
        
        user_ot_map = {u.id: 0.0 for u in users}
        for ot in ot_query:
            if ot.user_id in user_ot_map:
                user_ot_map[ot.user_id] += float(ot.duration_hours or 0)
            
        # Load approved leaves for this site
        if is_kp:
            site_leaves = EmployeeLeave.query.filter(
                (EmployeeLeave.site_id == site_id) | (EmployeeLeave.site_id.is_(None))
            ).filter_by(status='Approved').all()
        else:
            site_leaves = EmployeeLeave.query.filter_by(site_id=site_id, status='Approved').all()
            
        leave_set = set()
        for l in site_leaves:
            if not l.start_date or not l.end_date:
                continue
            curr_d = l.start_date if isinstance(l.start_date, date) else l.start_date.date()
            end_d = l.end_date if isinstance(l.end_date, date) else l.end_date.date()
            while curr_d <= end_d:
                leave_set.add((l.user_id, curr_d))
                curr_d += timedelta(days=1)
            
        results = []
        today = datetime.now().date()
        
        for u in users:
            total_shifts = len(user_shifts_map.get(u.id, []))
            ontime = 0
            late = 0
            alpha = 0
            
            for us in user_shifts_map.get(u.id, []):
                us_date = us.date if isinstance(us.date, date) else (us.date.date() if us.date else None)
                if not us_date:
                    continue
                # Check attendance
                if us_date > today:
                    continue # Future dates not counted
                    
                # If on approved leave or shift is cuti, do not count as alpha
                shift_name = us.shift.name if us.shift and us.shift.name else ''
                if 'cuti' in shift_name.lower() or (us.user_id, us_date) in leave_set:
                    continue
                    
                att = us.attendance_records
                if not att:
                    alpha += 1
                else:
                    rec = att[0]
                    rec_status = rec.status
                    if not rec_status:
                        is_late = False
                        if rec.jam_masuk and us.shift and us.shift.start_time:
                            expected_start = datetime.combine(us_date, us.shift.start_time)
                            if rec.jam_masuk > expected_start:
                                is_late = True
                        
                        if is_late:
                            late += 1
                        else:
                            ontime += 1
                    else:
                        if 'Terlambat' in rec_status or 'Pulang Cepat' in rec_status:
                            late += 1
                        else:
                            ontime += 1
                            
            evaluated_shifts = ontime + late + alpha
            rate = 0
            if evaluated_shifts > 0:
                rate = round(((ontime + late) / evaluated_shifts) * 100, 1)
                
            results.append({
                'id': u.id,
                'name': u.name,
                'total_shifts': evaluated_shifts,
                'ontime': ontime,
                'late': late,
                'alpha': alpha,
                'lembur_hours': user_ot_map.get(u.id, 0.0),
                'attendance_rate': rate
            })
            
        # Sort by attendance rate desc, then ontime desc, then name asc
        results.sort(key=lambda x: (-x['attendance_rate'], -x['ontime'], x['name']))
        return jsonify(results)
    except Exception as e:
        current_app.logger.error(f"[API Performance Error] site_id={site_id}: {e}", exc_info=True)
        return jsonify({'error': str(e), 'data': []}), 500


@schedule_bp.route('/api/attendance/check_user_sync', methods=['GET', 'POST'])
@login_required
def check_user_sync():
    if current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    date_from = request.args.get('date_from') or data.get('date_from')
    date_to = request.args.get('date_to') or data.get('date_to')
    site_id = request.args.get('site_id', type=int) or data.get('site_id')

    today_str = get_wib_now().strftime('%Y-%m-%d')
    if not date_from:
        date_from = today_str
    if not date_to:
        date_to = date_from

    from models import User, Site
    raw_results, error_msg = fetch_odoo_attendance_raw(date_from=date_from, date_to=date_to)
    if error_msg:
        return jsonify({'status': 'error', 'message': error_msg}), 400

    # Group Odoo records by cleaned NRP
    odoo_by_nrp = {}
    for r in (raw_results or []):
        nrp_raw = str(r.get('nrp', '')).strip()
        if not nrp_raw:
            continue
        if nrp_raw not in odoo_by_nrp:
            odoo_by_nrp[nrp_raw] = []
        odoo_by_nrp[nrp_raw].append(r)

    # Query CMMS Users
    user_query = User.query
    if current_user.site_id:
        user_query = user_query.filter(User.site_id == current_user.site_id)
    elif site_id:
        user_query = user_query.filter(User.site_id == int(site_id))

    cmms_users = user_query.order_by(User.name.asc()).all()

    user_list = []
    matched_odoo_nrps = set()
    count_has_data = 0
    count_no_data = 0
    count_no_nrp = 0

    for idx, u in enumerate(cmms_users, 1):
        site_name = u.site.name if u.site else '-'
        nrp_val = str(u.nrp).strip() if u.nrp else ''
        
        has_data = False
        nama_odoo = '-'
        first_in = '-'
        last_out = '-'
        log_count = 0

        if not nrp_val:
            count_no_nrp += 1
            status_label = 'NRP Kosong di CMMS'
        else:
            # Match with Odoo NRP variations
            matched_logs = (
                odoo_by_nrp.get(nrp_val) or
                odoo_by_nrp.get(nrp_val.lstrip('0')) or
                odoo_by_nrp.get(nrp_val.zfill(5)) or
                odoo_by_nrp.get(nrp_val.zfill(6)) or
                []
            )

            if matched_logs:
                has_data = True
                count_has_data += 1
                status_label = 'Sudah Ada'
                log_count = len(matched_logs)
                
                # Get Odoo Name
                nama_odoo = matched_logs[0].get('nama_karyawan') or matched_logs[0].get('nama') or '-'
                
                # Sort logs by check_in
                ins = [l.get('check_in') for l in matched_logs if l.get('check_in') and str(l.get('check_in')).strip() not in ['-', 'None', 'False', '']]
                outs = [l.get('check_out') for l in matched_logs if l.get('check_out') and str(l.get('check_out')).strip() not in ['-', 'None', 'False', '']]
                
                if ins:
                    first_in = str(sorted(ins)[0])
                if outs:
                    last_out = str(sorted(outs)[-1])

                # Mark NRPs as matched
                for k in [nrp_val, nrp_val.lstrip('0'), nrp_val.zfill(5), nrp_val.zfill(6)]:
                    if k in odoo_by_nrp:
                        matched_odoo_nrps.add(k)
            else:
                count_no_data += 1
                status_label = 'Belum Ada'

        user_list.append({
            'user_id': u.id,
            'nrp': nrp_val or '-',
            'name': u.name,
            'role': u.role or '-',
            'site_name': site_name,
            'has_data': has_data,
            'status_label': status_label,
            'nama_odoo': nama_odoo,
            'first_in': first_in,
            'last_out': last_out,
            'log_count': log_count
        })

    # Find Odoo records not registered in CMMS
    unregistered_odoo = []
    for nrp_k, logs in odoo_by_nrp.items():
        if nrp_k not in matched_odoo_nrps and nrp_k.lstrip('0') not in matched_odoo_nrps:
            sample = logs[0]
            unregistered_odoo.append({
                'nrp': nrp_k,
                'nama_odoo': sample.get('nama_karyawan') or sample.get('nama') or '-',
                'date': sample.get('date') or '-',
                'check_in': sample.get('check_in') or '-',
                'check_out': sample.get('check_out') or '-',
                'log_count': len(logs)
            })

    return jsonify({
        'status': 'success',
        'date_from': date_from,
        'date_to': date_to,
        'summary': {
            'total_cmms_users': len(cmms_users),
            'total_has_data': count_has_data,
            'total_no_data': count_no_data,
            'total_no_nrp': count_no_nrp,
            'total_odoo_logs': len(raw_results or []),
            'total_unregistered_odoo': len(unregistered_odoo)
        },
        'users': user_list,
        'unregistered_odoo': unregistered_odoo
    })


@schedule_bp.route('/api/attendance/export_user_sync_check', methods=['GET'])
@login_required
def export_user_sync_check():
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Unauthorized', 'danger')
        return redirect(url_for('settings.index'))

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    site_id = request.args.get('site_id', type=int)

    today_str = get_wib_now().strftime('%Y-%m-%d')
    if not date_from:
        date_from = today_str
    if not date_to:
        date_to = date_from

    from models import User, Site
    raw_results, error_msg = fetch_odoo_attendance_raw(date_from=date_from, date_to=date_to)
    if error_msg:
        flash(f"Gagal menarik data dari Odoo: {error_msg}", 'danger')
        return redirect(url_for('settings.index') + '#system')

    # Group Odoo records by cleaned NRP
    odoo_by_nrp = {}
    for r in (raw_results or []):
        nrp_raw = str(r.get('nrp', '')).strip()
        if not nrp_raw:
            continue
        if nrp_raw not in odoo_by_nrp:
            odoo_by_nrp[nrp_raw] = []
        odoo_by_nrp[nrp_raw].append(r)

    # Query CMMS Users
    user_query = User.query
    if current_user.site_id:
        user_query = user_query.filter(User.site_id == current_user.site_id)
    elif site_id:
        user_query = user_query.filter(User.site_id == int(site_id))

    cmms_users = user_query.order_by(User.name.asc()).all()

    import xlsxwriter
    from io import BytesIO
    from flask import send_file

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    # Formats
    title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#1e293b'})
    subtitle_fmt = workbook.add_format({'font_size': 10, 'font_color': '#64748b'})
    header_fmt = workbook.add_format({
        'bold': True,
        'font_color': '#ffffff',
        'bg_color': '#1e40af',
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })
    cell_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter'})
    cell_center_fmt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
    
    badge_green_fmt = workbook.add_format({
        'border': 1, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#dcfce7', 'font_color': '#166534', 'bold': True
    })
    badge_red_fmt = workbook.add_format({
        'border': 1, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#fee2e2', 'font_color': '#991b1b', 'bold': True
    })
    badge_gray_fmt = workbook.add_format({
        'border': 1, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#f1f5f9', 'font_color': '#475569', 'bold': True
    })

    # Sheet 1: Status User CMMS
    ws1 = workbook.add_worksheet('Status User CMMS')
    ws1.write(0, 0, "PT JAYA TEKNIK INDONESIA - CMMS", title_fmt)
    ws1.write(1, 0, f"Laporan Cek Kelengkapan Data Absensi Odoo | Periode: {date_from} s/d {date_to}", subtitle_fmt)
    ws1.write(2, 0, f"Diunduh Pada: {get_wib_now().strftime('%d/%m/%Y %H:%M:%S')} WIB | Total User CMMS: {len(cmms_users)}", subtitle_fmt)

    headers1 = [
        'No', 'NRP', 'Nama Karyawan (CMMS)', 'Site', 'Role', 
        'Status Data Odoo', 'Nama di Odoo', 'Clock In Pertama', 'Clock Out Terakhir', 'Jumlah Log Odoo'
    ]
    for c_idx, h in enumerate(headers1):
        ws1.write(4, c_idx, h, header_fmt)

    matched_odoo_nrps = set()
    unregistered_odoo_list = []

    for r_idx, u in enumerate(cmms_users, start=5):
        site_name = u.site.name if u.site else '-'
        nrp_val = str(u.nrp).strip() if u.nrp else ''
        
        status_label = 'Belum Ada'
        nama_odoo = '-'
        first_in = '-'
        last_out = '-'
        log_count = 0
        fmt_to_use = badge_red_fmt

        if not nrp_val:
            status_label = 'NRP Kosong'
            fmt_to_use = badge_gray_fmt
        else:
            matched_logs = (
                odoo_by_nrp.get(nrp_val) or
                odoo_by_nrp.get(nrp_val.lstrip('0')) or
                odoo_by_nrp.get(nrp_val.zfill(5)) or
                odoo_by_nrp.get(nrp_val.zfill(6)) or
                []
            )
            if matched_logs:
                status_label = 'Sudah Ada'
                fmt_to_use = badge_green_fmt
                log_count = len(matched_logs)
                nama_odoo = matched_logs[0].get('nama_karyawan') or matched_logs[0].get('nama') or '-'
                
                ins = [l.get('check_in') for l in matched_logs if l.get('check_in') and str(l.get('check_in')).strip() not in ['-', 'None', 'False', '']]
                outs = [l.get('check_out') for l in matched_logs if l.get('check_out') and str(l.get('check_out')).strip() not in ['-', 'None', 'False', '']]
                if ins:
                    first_in = str(sorted(ins)[0])
                if outs:
                    last_out = str(sorted(outs)[-1])

                for k in [nrp_val, nrp_val.lstrip('0'), nrp_val.zfill(5), nrp_val.zfill(6)]:
                    if k in odoo_by_nrp:
                        matched_odoo_nrps.add(k)

        ws1.write(r_idx, 0, r_idx - 4, cell_center_fmt)
        ws1.write(r_idx, 1, nrp_val or '-', cell_center_fmt)
        ws1.write(r_idx, 2, u.name or '-', cell_fmt)
        ws1.write(r_idx, 3, site_name, cell_fmt)
        ws1.write(r_idx, 4, u.role or '-', cell_center_fmt)
        ws1.write(r_idx, 5, status_label, fmt_to_use)
        ws1.write(r_idx, 6, nama_odoo, cell_fmt)
        ws1.write(r_idx, 7, first_in, cell_center_fmt)
        ws1.write(r_idx, 8, last_out, cell_center_fmt)
        ws1.write(r_idx, 9, log_count, cell_center_fmt)

    # Column widths for Sheet 1
    col_widths1 = [6, 16, 28, 25, 15, 18, 28, 22, 22, 16]
    for c_idx, w in enumerate(col_widths1):
        ws1.set_column(c_idx, c_idx, w)

    # Sheet 2: Data Odoo Belum Terdaftar di CMMS
    for nrp_k, logs in odoo_by_nrp.items():
        if nrp_k not in matched_odoo_nrps and nrp_k.lstrip('0') not in matched_odoo_nrps:
            sample = logs[0]
            unregistered_odoo_list.append({
                'nrp': nrp_k,
                'nama': sample.get('nama_karyawan') or sample.get('nama') or '-',
                'date': sample.get('date') or '-',
                'check_in': sample.get('check_in') or '-',
                'check_out': sample.get('check_out') or '-',
                'log_count': len(logs)
            })

    if unregistered_odoo_list:
        ws2 = workbook.add_worksheet('Odoo Belum di CMMS')
        ws2.write(0, 0, "Data Karyawan Odoo yang Belum Ada di Akun CMMS", title_fmt)
        ws2.write(1, 0, f"Periode: {date_from} s/d {date_to} | Total: {len(unregistered_odoo_list)} Karyawan", subtitle_fmt)
        
        headers2 = ['No', 'NRP (Odoo)', 'Nama Karyawan (Odoo)', 'Tanggal', 'Clock In', 'Clock Out', 'Jumlah Log', 'Keterangan']
        for c_idx, h in enumerate(headers2):
            ws2.write(3, c_idx, h, header_fmt)

        for r_idx, item in enumerate(unregistered_odoo_list, start=4):
            ws2.write(r_idx, 0, r_idx - 3, cell_center_fmt)
            ws2.write(r_idx, 1, item['nrp'], cell_center_fmt)
            ws2.write(r_idx, 2, item['nama'], cell_fmt)
            ws2.write(r_idx, 3, str(item['date']), cell_center_fmt)
            ws2.write(r_idx, 4, str(item['check_in']), cell_center_fmt)
            ws2.write(r_idx, 5, str(item['check_out']), cell_center_fmt)
            ws2.write(r_idx, 6, item['log_count'], cell_center_fmt)
            ws2.write(r_idx, 7, 'Belum didaftarkan di CMMS Settings > Users', cell_fmt)

        col_widths2 = [6, 16, 28, 15, 22, 22, 14, 40]
        for c_idx, w in enumerate(col_widths2):
            ws2.set_column(c_idx, c_idx, w)

    workbook.close()
    output.seek(0)
    filename = f"Cek_Status_Absensi_User_CMMS_{date_from}_sd_{date_to}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

