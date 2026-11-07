import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models import db, HelpdeskTicket, User, Site, SubCategory, Location, HelpdeskModule, HelpdeskLocation, HelpdeskProgress, HelpdeskProgressFile, HelpdeskTicketLog, Asset, Customer, Tasklist, Checklist, HelpdeskProcedure, HelpdeskChecklistParameter, HelpdeskPart, StockLevel, StockTransaction, Part, Team
import json
import pandas as pd
import io
from datetime import datetime
from utils import send_whatsapp_notification, save_optimized_image

helpdesk_bp = Blueprint('helpdesk', __name__, url_prefix='/helpdesk')

@helpdesk_bp.route('/api/master_data')
@login_required
def get_master_data():
    site_name = request.args.get('site_name')
    site = Site.query.filter_by(name=site_name).first()
    
    if not site:
        return jsonify({'modules': [], 'locations': []})
        
    modules = HelpdeskModule.query.filter_by(site_id=site.id).all()
    locations = Location.query.filter_by(site_id=site.id).all()
    
    # Mengambil technicians untuk site spesifik atau user tanpa spesifik site
    technicians = User.query.filter((User.site_id == site.id) | (User.site_id.is_(None))).all()
    
    return jsonify({
        'modules': [{'id': m.id, 'name': m.name} for m in modules],
        'locations': [{'id': l.id, 'name': l.name} for l in locations],
        'technicians': [{'id': u.id, 'name': u.name, 'role': u.role} for u in technicians]
    })

@helpdesk_bp.route('/api/assets')
@login_required
def get_assets_by_location():
    site_name = request.args.get('site_name')
    loc_name = request.args.get('location_name')
    
    query = Asset.query
    if site_name:
        site = Site.query.filter_by(name=site_name).first()
        if site:
            query = query.filter_by(site_id=site.id)
    
    if loc_name:
        loc = Location.query.filter_by(name=loc_name).first()
        if loc:
            query = query.filter_by(location_id=loc.id)
            
    assets = query.all()
    return jsonify({
        'assets': [{'id': a.id, 'name': a.name, 'code': a.code} for a in assets]
    })

@helpdesk_bp.route('/api/create_module', methods=['POST'])
@login_required
def create_module_ajax():
    data = request.json
    name = data.get('name')
    site_name = data.get('site_name')
    
    if not name or not site_name:
        return jsonify({'success': False, 'msg': 'Missing name or site'}), 400
        
    site = Site.query.filter_by(name=site_name).first()
    if not site:
        return jsonify({'success': False, 'msg': 'Site not found'}), 404
        
    # Check if exists
    existing = HelpdeskModule.query.filter_by(name=name, site_id=site.id).first()
    if not existing:
        new_mod = HelpdeskModule(name=name, site_id=site.id)
        db.session.add(new_mod)
        db.session.commit()
        return jsonify({'success': True, 'name': name})
    
    return jsonify({'success': True, 'name': name, 'msg': 'Already exists'})

@helpdesk_bp.route('/api/create_location', methods=['POST'])
@login_required
def create_location_ajax():
    data = request.json
    name = data.get('name')
    site_name = data.get('site_name')
    
    if not name or not site_name:
        return jsonify({'success': False, 'msg': 'Missing name or site'}), 400
        
    site = Site.query.filter_by(name=site_name).first()
    if not site:
        return jsonify({'success': False, 'msg': 'Site not found'}), 404
        
    existing = HelpdeskLocation.query.filter_by(name=name, site_id=site.id).first()
    if not existing:
        new_loc = HelpdeskLocation(name=name, site_id=site.id)
        db.session.add(new_loc)
        db.session.commit()
        return jsonify({'success': True, 'name': name})
        
    return jsonify({'success': True, 'name': name, 'msg': 'Already exists'})

@helpdesk_bp.route('/')
@login_required
def index():
    if current_user.site_id and current_user.site:
        tickets = HelpdeskTicket.query.filter_by(divisi_tujuan=current_user.site.name).order_by(HelpdeskTicket.created_at.desc()).all()
    else:
        tickets = HelpdeskTicket.query.order_by(HelpdeskTicket.created_at.desc()).all()
    statuses = [
        "New", "Initial respon", "Action Plan", "Tunggu Spare Parts By JTI", 
        "Tunggu Spare Parts By Customer", "Tunggu Jadwal", "In Progress", 
        "Done", "Closed", "Cancelled", "Reopened"
    ]
    
    # Serialize for frontend views
    tickets_json = []
    for t in tickets:
        tickets_json.append({
            'id': t.id,
            'code': t.ticket_code,
            'subject': t.subject,
            'status': t.status if t.status else 'New',
            'priority': t.priority.capitalize() if t.priority else 'Normal',
            'type': t.ticket_type if t.ticket_type else 'Other',
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
            'url': url_for('helpdesk.edit', id=t.id)
        })
        
    return render_template('helpdesk/index.html', tickets=tickets, statuses=statuses, tickets_json=tickets_json)

@helpdesk_bp.route('/export')
@login_required
def export_all():
    format = request.args.get('format', 'excel')
    query = HelpdeskTicket.query
    
    if current_user.site_id:
        query = query.filter(HelpdeskTicket.divisi_tujuan == current_user.site.name)
        
    tickets = query.order_by(HelpdeskTicket.created_at.desc()).all()
    
    data = []
    for t in tickets:
        primary_tech = t.assigned_user.name if t.assigned_user else ''
        techs = ", ".join([u.name for u in t.technicians])
        data.append({
            'Ticket Code': t.ticket_code,
            'Subject': t.subject,
            'Description': t.description,
            'Complain Type': t.complain_type,
            'Divisi Tujuan': t.divisi_tujuan,
            'Module': t.modul,
            'Location': t.location_subject,
            'Asset': t.asset,
            'Material Type': t.ticket_type,
            'Priority Level': t.priority,
            'Company': t.company,
            'Partner Organization': t.partner,
            'Contact Name': t.person_name,
            'Email': t.email,
            'Mobile': t.mobile,
            'Team': t.team,
            'Primary Technician': primary_tech,
            'Technician(s)': techs,
            'Status': t.status,
            'Created At': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else ''
        })
        
    df = pd.DataFrame(data)
    
    if format == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Helpdesk Tickets')
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='helpdesk_tickets.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    return redirect(url_for('helpdesk.index'))

@helpdesk_bp.route('/template')
@login_required
def download_template():
    columns = [
        'Ticket Code', 'Subject', 'Description', 'Complain Type', 'Divisi Tujuan', 'Module', 
        'Location', 'Asset', 'Material Type', 'Priority Level', 'Company', 
        'Partner Organization', 'Contact Name', 'Email', 'Mobile', 'Team',
        'Primary Technician', 'Technician(s)', 'Status', 'Created At'
    ]
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template')
        worksheet = writer.sheets['Template']
        for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T']:
            worksheet.column_dimensions[col].width = 20
        
    output.seek(0)
    return send_file(output, as_attachment=True, download_name='helpdesk_import_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@helpdesk_bp.route('/import', methods=['POST'])
@login_required
def import_all():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('helpdesk.index'))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('helpdesk.index'))
        
    if file:
        filename = file.filename
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith('.xlsx') or filename.endswith('.xls'):
                df = pd.read_excel(file)
            else:
                flash('Unsupported file format. Please upload CSV or Excel.', 'danger')
                return redirect(url_for('helpdesk.index'))
                
            success_count = 0
            error_count = 0
            error_details = []
            
            for index, row in df.iterrows():
                try:
                    subject = str(row.get('Subject', ''))
                    if not subject or pd.isna(subject) or subject.lower() == 'nan':
                        raise ValueError("Kolom 'Subject' wajib diisi")
                        
                    site_val = str(row.get('Divisi Tujuan', ''))
                    if pd.isna(site_val) or site_val.lower() == 'nan':
                        site_val = None
                        
                    import time
                    now = datetime.now()
                    
                    # Ticket Code
                    excel_ticket_code = str(row.get('Ticket Code', ''))
                    if pd.isna(row.get('Ticket Code')) or excel_ticket_code.lower() == 'nan' or not excel_ticket_code:
                        year_month = now.strftime('%y%m')
                        site_code = site_val[:3].upper() if site_val else 'HLP'
                        ticket_code = f"TICKET/{site_code}/{year_month}/{int(time.time()*1000 + index)}"
                    else:
                        ticket_code = excel_ticket_code
                    
                    # Assigned Personnel
                    primary_tech_name = str(row.get('Primary Technician', '')) if not pd.isna(row.get('Primary Technician')) and str(row.get('Primary Technician')).lower() != 'nan' else ''
                    assigned_user = None
                    if primary_tech_name:
                        user = User.query.filter_by(name=primary_tech_name).first()
                        if user:
                            assigned_user = user.id
                            
                    techs_str = str(row.get('Technician(s)', '')) if not pd.isna(row.get('Technician(s)')) and str(row.get('Technician(s)')).lower() != 'nan' else ''
                    tech_users = []
                    if techs_str:
                        tech_names = [name.strip() for name in techs_str.split(',')]
                        for name in tech_names:
                            u = User.query.filter_by(name=name).first()
                            if u:
                                tech_users.append(u)
                                
                    # Status & Created At
                    status_val = str(row.get('Status', '')) if not pd.isna(row.get('Status')) and str(row.get('Status')).lower() != 'nan' else 'New'
                    if not status_val:
                        status_val = 'New'
                        
                    created_at_val = now
                    created_at_str = str(row.get('Created At', ''))
                    if not pd.isna(row.get('Created At')) and created_at_str.lower() != 'nan' and created_at_str:
                        try:
                            created_at_val = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M')
                        except ValueError:
                            pass
                    
                    # Upsert Logic
                    ticket = HelpdeskTicket.query.filter_by(ticket_code=ticket_code).first()
                    is_new = False
                    if not ticket:
                        ticket = HelpdeskTicket(ticket_code=ticket_code)
                        is_new = True
                        
                    ticket.subject = subject
                    ticket.description = str(row.get('Description', '')) if not pd.isna(row.get('Description')) and str(row.get('Description')).lower() != 'nan' else ''
                    ticket.complain_type = str(row.get('Complain Type', '')) if not pd.isna(row.get('Complain Type')) and str(row.get('Complain Type')).lower() != 'nan' else ''
                    ticket.divisi_tujuan = site_val
                    ticket.modul = str(row.get('Module', '')) if not pd.isna(row.get('Module')) and str(row.get('Module')).lower() != 'nan' else ''
                    ticket.location_subject = str(row.get('Location', '')) if not pd.isna(row.get('Location')) and str(row.get('Location')).lower() != 'nan' else ''
                    ticket.asset = str(row.get('Asset', '')) if not pd.isna(row.get('Asset')) and str(row.get('Asset')).lower() != 'nan' else ''
                    ticket.ticket_type = str(row.get('Material Type', '')) if not pd.isna(row.get('Material Type')) and str(row.get('Material Type')).lower() != 'nan' else ''
                    ticket.priority = str(row.get('Priority Level', '')) if not pd.isna(row.get('Priority Level')) and str(row.get('Priority Level')).lower() != 'nan' else ''
                    ticket.company = str(row.get('Company', '')) if not pd.isna(row.get('Company')) and str(row.get('Company')).lower() != 'nan' else ''
                    ticket.partner = str(row.get('Partner Organization', '')) if not pd.isna(row.get('Partner Organization')) and str(row.get('Partner Organization')).lower() != 'nan' else ''
                    ticket.person_name = str(row.get('Contact Name', '')) if not pd.isna(row.get('Contact Name')) and str(row.get('Contact Name')).lower() != 'nan' else ''
                    ticket.email = str(row.get('Email', '')) if not pd.isna(row.get('Email')) and str(row.get('Email')).lower() != 'nan' else ''
                    ticket.mobile = str(row.get('Mobile', '')) if not pd.isna(row.get('Mobile')) and str(row.get('Mobile')).lower() != 'nan' else ''
                    ticket.team = str(row.get('Team', '')) if not pd.isna(row.get('Team')) and str(row.get('Team')).lower() != 'nan' else ''
                    ticket.assigned_user_id = assigned_user
                    ticket.status = status_val
                    if is_new:
                        ticket.created_at = created_at_val
                    
                    if tech_users:
                        ticket.technicians = tech_users
                        
                    if is_new:
                        db.session.add(ticket)
                    
                    db.session.flush()
                    
                    action_verb = "imported" if is_new else "updated"
                    log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text=f"Ticket {action_verb} from Excel with status '{status_val}'")
                    db.session.add(log)
                    
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    error_details.append(f"Row {index+1}: {str(e)}")
                    print(f"Row error: {e}")
            
            db.session.commit()
            if success_count > 0:
                flash(f'Successfully imported {success_count} tickets.', 'success')
            if error_count > 0:
                error_msg = f'Failed to import {error_count} rows. Errors: ' + ' | '.join(error_details[:5])
                if len(error_details) > 5:
                    error_msg += ' ... (and more)'
                flash(error_msg, 'danger')
                
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'danger')
            
    return redirect(url_for('helpdesk.index'))

@helpdesk_bp.route('/<int:id>/update_status_ajax', methods=['POST'])
@login_required
def update_status_ajax(id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    
    if request.is_json:
        new_status = request.json.get('status')
    else:
        new_status = request.form.get('status')
    
    if new_status and new_status != ticket.status:
        old_status = ticket.status
        ticket.status = new_status
        
        if new_status == 'Closed':
            ticket.actual_end_date = datetime.now()
            
        log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text=f"Status changed from '{old_status}' to '{new_status}' (via Board)")
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'msg': 'Status updated'})
    return jsonify({'success': False, 'msg': 'Missing status'}), 400

@helpdesk_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        photo = request.files.get('damage_photo')
        damage_note = request.form.get('damage_note')
        # Removed mandatory checks for photo and note
            
        # Parse custom procedures and checklists
        custom_proc_json = request.form.get('custom_procedures_json', '[]')
        custom_chk_json = request.form.get('custom_checklists_json', '[]')
        try:
            custom_procs_list = json.loads(custom_proc_json)
        except:
            custom_procs_list = []
        try:
            custom_chks_list = json.loads(custom_chk_json)
        except:
            custom_chks_list = []
            
        primary_tech_id = request.form.get('primary_technician_id')
        tech_ids = request.form.getlist('technician_ids')
        if not primary_tech_id and not tech_ids:
            flash('At least one primary technician or technician is required.', 'error')
            return redirect(url_for('helpdesk.create'))
            
        if not request.form.get('tasklist_id') and not custom_procs_list:
            flash('Tasklist is mandatory (select a template or add custom tasks).', 'error')
            return redirect(url_for('helpdesk.create'))
            
        if not request.form.get('checklist_id') and not custom_chks_list:
            flash('Checklist is mandatory (select a template or add custom parameters).', 'error')
            return redirect(url_for('helpdesk.create'))
            
        # Generate custom ticket code
        def clean_str(s):
            if not s: return 'XXX'
            # Capital each word and remove spaces (PascalCase)
            return s.strip().title().replace(' ', '')

        site_val = request.form.get('divisi_tujuan') or 'SITE'
        mod_val = request.form.get('modul') or 'MOD'
        loc_val = request.form.get('location_subject') or 'LOC'
        
        now = datetime.now()
        date_str = now.strftime('%m%y')
        
        c_site = clean_str(site_val)
        c_mod = clean_str(mod_val)
        c_loc = clean_str(loc_val)
        
        # Hitung jumlah tiket di site yang sama sebelumnya untuk urutan nomor
        site_count = HelpdeskTicket.query.filter_by(divisi_tujuan=site_val).count() + 1
        running_num = f"{site_count:03d}"
        
        new_code = f"Ticket/{c_site}/{c_mod}/{c_loc}/{date_str}/{running_num}"
        
        # Get start/end dates
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                return None
        
        scheduled_start_date = parse_date(request.form.get('scheduled_start_date'))
        scheduled_end_date = parse_date(request.form.get('scheduled_end_date'))
        actual_end_date = parse_date(request.form.get('actual_end_date'))
        
        ticket = HelpdeskTicket(
            ticket_code=new_code,
            subject=request.form.get('subject'),
            description=request.form.get('description'),
            
            company=request.form.get('company'),
            is_internal='is_internal' in request.form,
            divisi_tujuan=request.form.get('divisi_tujuan'),
            modul=request.form.get('modul'),
            location_subject=request.form.get('location_subject'),
            asset=request.form.get('asset'),
            ticket_type=request.form.get('ticket_type'),
            complain_type=request.form.get('complain_type'),
            damage_note=request.form.get('damage_note'),
            
            partner=request.form.get('partner'),
            person_name=request.form.get('person_name'),
            email=request.form.get('email'),
            mobile=request.form.get('mobile'),
            
            priority=request.form.get('priority'),
            team=request.form.get('team'),
            
            tags=request.form.get('tags'),
            scheduled_start_date=scheduled_start_date,
            scheduled_end_date=scheduled_end_date,
            actual_end_date=actual_end_date,
            
            status='New'
        )
        
        # Handle multiple technicians
        tech_ids = request.form.getlist('technician_ids')
        if tech_ids:
            technicians = User.query.filter(User.id.in_(tech_ids)).all()
            ticket.technicians = technicians
            
        primary_tech_id = request.form.get('primary_technician_id')
        if primary_tech_id:
            ticket.assigned_user_id = primary_tech_id
            
        ticket.tasklist_id = request.form.get('tasklist_id') or None
        ticket.checklist_id = request.form.get('checklist_id') or None

        db.session.add(ticket)
        db.session.flush() # dapatkan ID
        
        # Save Procedures
        if custom_procs_list:
            for cp in custom_procs_list:
                new_proc = HelpdeskProcedure(
                    ticket_id=ticket.id,
                    tasklist_name=cp.get('tasklist_name', 'Custom Tasklist'),
                    name=cp.get('name', ''),
                    requires_attachment=str(cp.get('requires_attachment', 'false')).lower() == 'true',
                    estimated_minutes=int(cp.get('estimated_minutes', 0)),
                    min_photos=int(cp.get('min_photos', 0))
                )
                db.session.add(new_proc)
        
        # Save Checklists
        if custom_chks_list:
            for cc in custom_chks_list:
                new_chk = HelpdeskChecklistParameter(
                    ticket_id=ticket.id,
                    checklist_name=cc.get('checklist_name', 'Custom Checklist'),
                    parameter=cc.get('parameter', ''),
                    standard=cc.get('standard', '')
                )
                db.session.add(new_chk)

        photo = request.files.get('damage_photo')
        if photo and photo.filename:
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'helpdesk')
            os.makedirs(upload_folder, exist_ok=True)
            filename = secure_filename(f"ticket_{ticket.id}_damage_{int(datetime.now().timestamp())}_{photo.filename}")
            file_path = os.path.join(upload_folder, filename)
            save_optimized_image(photo, file_path)
            ticket.damage_photo = f"uploads/helpdesk/{filename}"
        
        log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text=f"Ticket created with status 'New'")
        db.session.add(log)
        
        db.session.commit()
        
        # WhatsApp Notification
        for tech in ticket.technicians:
            if tech.phone_number:
                wa_msg = f"*TIKET HELPDESK BARU*\n\nKode: {ticket.ticket_code}\nSubjek: {ticket.subject}\nPrioritas: {ticket.priority}\nLokasi: {ticket.location_subject}\n\nSilakan cek detail di sistem."
                send_whatsapp_notification(tech.phone_number, wa_msg)
        
        flash('Helpdesk Ticket created successfully', 'success')
        return redirect(url_for('helpdesk.edit', id=ticket.id))
        
    if current_user.site_id:
        users = User.query.filter(db.or_(User.site_id == current_user.site_id, User.site_id == None)).all()
        sites = Site.query.filter_by(id=current_user.site_id).all()
        hd_modules = HelpdeskModule.query.filter(db.or_(HelpdeskModule.site_id == current_user.site_id, HelpdeskModule.site_id == None)).all()
        hd_locations = HelpdeskLocation.query.filter(db.or_(HelpdeskLocation.site_id == current_user.site_id, HelpdeskLocation.site_id == None)).all()
        teams = Team.query.filter_by(site_id=current_user.site_id).all()
        
        user_site = Site.query.get(current_user.site_id)
        if user_site and user_site.project_code:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == user_site.project_code, Tasklist.project_code == None, Tasklist.project_code == '')).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == user_site.project_code, Checklist.project_code == None, Checklist.project_code == '')).all()
        else:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == None, Tasklist.project_code == '')).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == None, Checklist.project_code == '')).all()
    else:
        users = User.query.all()
        sites = Site.query.all()
        hd_modules = HelpdeskModule.query.all()
        hd_locations = HelpdeskLocation.query.all()
        teams = Team.query.all()
        tasklists = Tasklist.query.all()
        checklists = Checklist.query.all()
        
    customers = Customer.query.all()
    
    for t in tasklists:
        t.project_code_group = t.project_code if t.project_code else ""
    for c in checklists:
        c.project_code_group = c.project_code if c.project_code else ""
    
    # Pre-calculate tasklists and checklists json for template
    tasklists_json = json.dumps([{
        'id': t.id,
        'name': t.name,
        'procedures': [{'name': p.name, 'requires_attachment': p.requires_attachment, 'estimated_minutes': p.estimated_minutes, 'min_photos': p.min_photos} for p in t.procedures.all()]
    } for t in tasklists])
    
    checklists_json = json.dumps([{
        'id': c.id,
        'name': c.name,
        'parameters': [{'parameter': p.parameter, 'standard': p.standard} for p in c.parameters.all()]
    } for c in checklists])

    return render_template('helpdesk/create.html', users=users, sites=sites, hd_modules=hd_modules, hd_locations=hd_locations, customers=customers, tasklists=tasklists, checklists=checklists, tasklists_json=tasklists_json, checklists_json=checklists_json, teams=teams)

@helpdesk_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    
    # Handle status change only action if provided in post
    if request.method == 'POST' and 'update_status' in request.form:
        new_status = request.form.get('status')
        if new_status and new_status != ticket.status:
            old_status = ticket.status
            ticket.status = new_status
            
            if new_status == 'Closed':
                ticket.actual_end_date = datetime.now()
            
            log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text=f"Status changed from '{old_status}' to '{new_status}'")
            db.session.add(log)
            
            db.session.commit()
            flash(f'Ticket status updated to {new_status}', 'success')
            return redirect(url_for('helpdesk.edit', id=id))

    if request.method == 'POST':
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                return None
        
        ticket.description = request.form.get('description')
        
        # Admin / Supervisor Only edits
        if current_user.role != 'Technician':
            damage_note = request.form.get('damage_note')
            photo = request.files.get('damage_photo')
            # Removed mandatory checks for photo and note
                
            primary_tech_id = request.form.get('primary_technician_id')
            tech_ids = request.form.getlist('technician_ids')
            if not primary_tech_id and not tech_ids:
                flash('At least one primary technician or technician is required.', 'error')
                return redirect(url_for('helpdesk.edit', id=id))
                
            custom_proc_json = request.form.get('custom_procedures_json', '[]')
            custom_chk_json = request.form.get('custom_checklists_json', '[]')
            try:
                custom_procs_list = json.loads(custom_proc_json)
            except:
                custom_procs_list = []
            try:
                custom_chks_list = json.loads(custom_chk_json)
            except:
                custom_chks_list = []
                
            # If changing template (using master tasklist_id/checklist_id or custom json), validate.
            # But they might have existing ones in the DB.
            has_existing_tasklist = ticket.procedures.count() > 0
            has_existing_checklist = ticket.checklists.count() > 0
            
            wants_new_tasklist = request.form.get('tasklist_id') or custom_procs_list
            wants_new_checklist = request.form.get('checklist_id') or custom_chks_list
            
            if not has_existing_tasklist and not wants_new_tasklist:
                flash('Tasklist is mandatory.', 'error')
                return redirect(url_for('helpdesk.edit', id=id))
                
            if not has_existing_checklist and not wants_new_checklist:
                flash('Checklist is mandatory.', 'error')
                return redirect(url_for('helpdesk.edit', id=id))
                
            ticket.subject = request.form.get('subject') # Optional if tech can edit subject
            ticket.company = request.form.get('company')
            ticket.is_internal = 'is_internal' in request.form
            ticket.divisi_tujuan = request.form.get('divisi_tujuan')
            ticket.modul = request.form.get('modul')
            ticket.location_subject = request.form.get('location_subject')
            ticket.asset = request.form.get('asset')
            ticket.ticket_type = request.form.get('ticket_type')
            ticket.complain_type = request.form.get('complain_type')
            ticket.damage_note = damage_note
            
            photo = request.files.get('damage_photo')
            if photo and photo.filename:
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'helpdesk')
                os.makedirs(upload_folder, exist_ok=True)
                filename = secure_filename(f"ticket_{ticket.id}_damage_{int(datetime.now().timestamp())}_{photo.filename}")
                file_path = os.path.join(upload_folder, filename)
                save_optimized_image(photo, file_path)
                ticket.damage_photo = f"uploads/helpdesk/{filename}"
            
            ticket.partner = request.form.get('partner')
            ticket.person_name = request.form.get('person_name')
            ticket.email = request.form.get('email')
            ticket.mobile = request.form.get('mobile')
            
            ticket.priority = request.form.get('priority')
            ticket.team = request.form.get('team')
        
            # Handle multiple technicians
            tech_ids = request.form.getlist('technician_ids')
            if tech_ids:
                technicians = User.query.filter(User.id.in_(tech_ids)).all()
                ticket.technicians = technicians
                
            primary_tech_id = request.form.get('primary_technician_id')
            if primary_tech_id:
                ticket.assigned_user_id = primary_tech_id
                
            # Handle Tasklist & Checklist Updates only if status is New or Initial respon
            if ticket.status in ['New', 'Initial respon']:
                if wants_new_tasklist and request.form.get('tasklist_id') != str(ticket.tasklist_id):
                    ticket.procedures.delete()
                    ticket.tasklist_id = request.form.get('tasklist_id') or None
                    for cp in custom_procs_list:
                        new_proc = HelpdeskProcedure(
                            ticket_id=ticket.id,
                            tasklist_name=cp.get('tasklist_name', 'Custom Tasklist'),
                            name=cp.get('name', ''),
                            requires_attachment=str(cp.get('requires_attachment', 'false')).lower() == 'true',
                            estimated_minutes=int(cp.get('estimated_minutes', 0)),
                            min_photos=int(cp.get('min_photos', 0))
                        )
                        db.session.add(new_proc)
                        
                # Handle Checklist Updates
                if wants_new_checklist and request.form.get('checklist_id') != str(ticket.checklist_id):
                    ticket.checklists.delete()
                    ticket.checklist_id = request.form.get('checklist_id') or None
                    for cc in custom_chks_list:
                        new_chk = HelpdeskChecklistParameter(
                            ticket_id=ticket.id,
                            checklist_name=cc.get('checklist_name', 'Custom Checklist'),
                            parameter=cc.get('parameter', ''),
                            standard=cc.get('standard', '')
                        )
                        db.session.add(new_chk)
                
            ticket.tags = request.form.get('tags')
            ticket.scheduled_start_date = parse_date(request.form.get('scheduled_start_date'))
            ticket.scheduled_end_date = parse_date(request.form.get('scheduled_end_date'))
            ticket.actual_end_date = parse_date(request.form.get('actual_end_date'))
        
        log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text="Ticket details updated")
        db.session.add(log)
        
        db.session.commit()
        flash('Helpdesk Ticket updated successfully', 'success')
        return redirect(url_for('helpdesk.edit', id=id))
        
    if current_user.site_id:
        users = User.query.filter(db.or_(User.site_id == current_user.site_id, User.site_id == None)).all()
        sites = Site.query.filter_by(id=current_user.site_id).all()
        hd_modules = HelpdeskModule.query.filter(db.or_(HelpdeskModule.site_id == current_user.site_id, HelpdeskModule.site_id == None)).all()
        hd_locations = HelpdeskLocation.query.filter(db.or_(HelpdeskLocation.site_id == current_user.site_id, HelpdeskLocation.site_id == None)).all()
    else:
        users = User.query.all()
        sites = Site.query.all()
        hd_modules = HelpdeskModule.query.all()
        hd_locations = HelpdeskLocation.query.all()
    
    # All possible statuses according to the screenshot
    statuses = [
        "New", "Initial respon", "Action Plan", "Tunggu Spare Parts By JTI", 
        "Tunggu Spare Parts By Customer", "Tunggu Jadwal", "In Progress", 
        "Done", "Closed", "Cancelled", "Reopened"
    ]
    
    if current_user.site_id:
        user_site = Site.query.get(current_user.site_id)
        if user_site and user_site.project_code:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == user_site.project_code, Tasklist.project_code == None, Tasklist.project_code == '')).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == user_site.project_code, Checklist.project_code == None, Checklist.project_code == '')).all()
        else:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == None, Tasklist.project_code == '')).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == None, Checklist.project_code == '')).all()
    else:
        tasklists = Tasklist.query.all()
        checklists = Checklist.query.all()
    
    for t in tasklists:
        t.project_code_group = t.project_code if t.project_code else ""
    for c in checklists:
        c.project_code_group = c.project_code if c.project_code else ""
    
    # Pre-calculate tasklists and checklists json for template
    tasklists_json = json.dumps([{
        'id': t.id,
        'name': t.name,
        'procedures': [{'name': p.name, 'requires_attachment': p.requires_attachment, 'estimated_minutes': p.estimated_minutes, 'min_photos': p.min_photos} for p in t.procedures.all()]
    } for t in tasklists])
    
    checklists_json = json.dumps([{
        'id': c.id,
        'name': c.name,
        'parameters': [{'parameter': p.parameter, 'standard': p.standard} for p in c.parameters.all()]
    } for c in checklists])
    
    customers = Customer.query.all()
    if current_user.site_id:
        teams = Team.query.filter_by(site_id=current_user.site_id).all()
    else:
        teams = Team.query.all()
    available_stock = []
    if ticket.company:
        site = Site.query.filter_by(name=ticket.company).first()
        if site:
            available_stock = StockLevel.query.filter_by(site_id=site.id).all()
            
    return render_template('helpdesk/edit.html', ticket=ticket, users=users, sites=sites, hd_modules=hd_modules, hd_locations=hd_locations, statuses=statuses, customers=customers, tasklists=tasklists, checklists=checklists, tasklists_json=tasklists_json, checklists_json=checklists_json, available_stock=available_stock, teams=teams)

@helpdesk_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    db.session.delete(ticket)
    db.session.commit()
    flash('Helpdesk Ticket deleted successfully', 'success')
    return redirect(url_for('helpdesk.index'))

@helpdesk_bp.route('/<int:id>/add_progress', methods=['POST'])
@login_required
def add_progress(id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    description = request.form.get('progress_desc')
    
    if not description:
        flash('Progress description is required.', 'danger')
        return redirect(url_for('helpdesk.edit', id=id))

    progress = HelpdeskProgress(ticket_id=ticket.id, user_id=current_user.id, description=description)
    db.session.add(progress)
    db.session.flush() # Mendapatkan id sebelum menyimpan file

    # Simpan folder upload
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'helpdesk')
    os.makedirs(upload_folder, exist_ok=True)

    photos = request.files.getlist('photos')
    for photo in photos:
        if photo and photo.filename:
            filename = secure_filename(f"{ticket.id}_{progress.id}_{int(datetime.now().timestamp())}_{photo.filename}")
            file_path = os.path.join(upload_folder, filename)
            save_optimized_image(photo, file_path)
            
            # Simpan path relatif ke static folder
            relative_path = f"uploads/helpdesk/{filename}"
            progress_file = HelpdeskProgressFile(progress_id=progress.id, file_path=relative_path)
            db.session.add(progress_file)

    db.session.commit()
    flash('Progress added successfully', 'success')
    return redirect(url_for('helpdesk.edit', id=id))
@helpdesk_bp.route('/<int:id>/complete_procedure/<int:proc_id>', methods=['POST'])
@login_required
def complete_hd_procedure(id, proc_id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    proc = HelpdeskProcedure.query.filter_by(id=proc_id, ticket_id=id).first_or_404()
    
    if ticket.status not in ['In Progress']:
        flash('Procedures can only be completed when ticket is In Progress.', 'warning')
        return redirect(url_for('helpdesk.edit', id=id))
        
    action = request.form.get('action')
    if action == 'uncomplete':
        proc.is_completed = False
        proc.completed_at = None
        proc.completed_by_id = None
        proc.status = 'Pending'
        # Optional: could remove attachment, but keeping it is safer
        db.session.commit()
        flash('Procedure un-completed.', 'info')
        return redirect(url_for('helpdesk.edit', id=id))

    note = request.form.get('note', '')
    proc.notes = note

    photo = request.files.get('proc_attachment')
    if proc.requires_attachment and not photo and not proc.attachment_path:
        flash('Photo attachment is required for this procedure.', 'error')
        return redirect(url_for('helpdesk.edit', id=id))
        
    if photo and photo.filename:
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'helpdesk', 'procedures')
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(f"ticket_{id}_proc_{proc_id}_{int(datetime.now().timestamp())}_{photo.filename}")
        file_path = os.path.join(upload_folder, filename)
        save_optimized_image(photo, file_path)
        proc.attachment_path = f"uploads/helpdesk/procedures/{filename}"
        
    proc.is_completed = True
    proc.status = 'Done'
    proc.completed_at = datetime.utcnow()
    proc.completed_by_id = current_user.id
    
    db.session.commit()
    flash('Procedure completed successfully.', 'success')
    return redirect(url_for('helpdesk.edit', id=id))

@helpdesk_bp.route('/<int:id>/update_checklist/<int:chk_id>', methods=['POST'])
@login_required
def update_hd_checklist(id, chk_id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    chk = HelpdeskChecklistParameter.query.filter_by(id=chk_id, ticket_id=id).first_or_404()
    
    if ticket.status not in ['In Progress']:
        flash('Checklists can only be updated when ticket is In Progress.', 'warning')
        return redirect(url_for('helpdesk.edit', id=id))
        
    chk.value = request.form.get('value', '')
    chk.note = request.form.get('note', '')
    db.session.commit()
    
    flash('Checklist parameter saved.', 'success')
    return redirect(url_for('helpdesk.edit', id=id))

@helpdesk_bp.route('/<int:id>/add_part', methods=['POST'])
@login_required
def add_part(id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    
    if ticket.status in ['Closed', 'Done']:
        flash('Cannot add parts to a ticket that is already closed or done.', 'warning')
        return redirect(url_for('helpdesk.edit', id=ticket.id))
        
    part_id = request.form.get('part_id')
    qty = float(request.form.get('qty', 1))
    
    if not part_id or qty <= 0:
        flash('Invalid part or quantity.', 'danger')
        return redirect(url_for('helpdesk.edit', id=ticket.id))
        
    # Find ticket site
    site = None
    if ticket.company:
        site = Site.query.filter_by(name=ticket.company).first()
        
    if not site:
        flash('Ticket has no associated site to deduct stock from.', 'danger')
        return redirect(url_for('helpdesk.edit', id=ticket.id))
        
    # Verify stock availability at the site
    stock = StockLevel.query.filter_by(part_id=part_id, site_id=site.id).first()
    if not stock or stock.qty_on_hand < qty:
        flash('Insufficient stock available at this site.', 'danger')
        return redirect(url_for('helpdesk.edit', id=ticket.id))
        
    # Deduct stock
    qty_before = stock.qty_on_hand
    stock.qty_on_hand -= qty
    qty_after = stock.qty_on_hand
    
    # Log Transaction
    tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    transaction = StockTransaction(
        transaction_code=tx_code,
        part_id=part_id,
        site_id=site.id,
        user_id=current_user.id,
        action='HELPDESK',
        qty_before=qty_before,
        qty_after=qty_after,
        qty_change=-qty,
        notes=f"Used in Helpdesk Ticket #{ticket.ticket_code}"
    )
    db.session.add(transaction)
    
    # Add to HelpdeskPart
    hd_part = HelpdeskPart(ticket_id=ticket.id, part_id=part_id, quantity_used=qty)
    db.session.add(hd_part)
    
    # Add activity log
    part = Part.query.get(part_id)
    log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text=f"Added {qty}x {part.name} from warehouse.")
    db.session.add(log)
    
    db.session.commit()
    flash('Part added to ticket and stock deducted successfully.', 'success')
    return redirect(url_for('helpdesk.edit', id=ticket.id))

@helpdesk_bp.route('/<int:id>/remove_part/<int:part_id>', methods=['POST'])
@login_required
def remove_part(id, part_id):
    ticket = HelpdeskTicket.query.get_or_404(id)
    hd_part = HelpdeskPart.query.filter_by(id=part_id, ticket_id=ticket.id).first_or_404()
    
    if ticket.status in ['Closed', 'Done']:
        flash('Cannot remove parts from a ticket that is already closed or done.', 'warning')
        return redirect(url_for('helpdesk.edit', id=ticket.id))
        
    site = None
    if ticket.company:
        site = Site.query.filter_by(name=ticket.company).first()
        
    if site:
        stock = StockLevel.query.filter_by(part_id=hd_part.part_id, site_id=site.id).first()
        if stock:
            qty_before = stock.qty_on_hand
            stock.qty_on_hand += hd_part.quantity_used
            qty_after = stock.qty_on_hand
            
            tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            transaction = StockTransaction(
                transaction_code=tx_code,
                part_id=hd_part.part_id,
                site_id=site.id,
                user_id=current_user.id,
                action='HELPDESK RETURN',
                qty_before=qty_before,
                qty_after=qty_after,
                qty_change=hd_part.quantity_used,
                notes=f"Returned from Helpdesk Ticket #{ticket.ticket_code}"
            )
            db.session.add(transaction)
            
    # Add log
    part_name = hd_part.part.name
    qty = hd_part.quantity_used
    log = HelpdeskTicketLog(ticket_id=ticket.id, user_id=current_user.id, log_text=f"Removed {qty}x {part_name} from ticket and returned to warehouse.")
    db.session.add(log)
    
    db.session.delete(hd_part)
    db.session.commit()
    
    flash('Part removed from ticket and stock returned successfully.', 'success')
    return redirect(url_for('helpdesk.edit', id=ticket.id))
