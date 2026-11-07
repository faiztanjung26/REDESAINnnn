import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response, send_file, jsonify
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user
from models import db, WorkOrder, Asset, User, Part, StockLevel, WorkOrderPart, WorkOrderStatus, WorkOrderLog, ProjectCode, Tasklist, TasklistProcedure, WorkOrderProcedure, WorkOrderChecklistParameter, Checklist, ChecklistParameterTemplate, Team, Site
from datetime import datetime, timezone
from utils import supervisor_or_admin_required, send_whatsapp_notification, save_optimized_image
import pandas as pd
import io
import tempfile
from pdf_utils import SafeFPDF as FPDF, clean_pdf_text, calc_num_lines
from PIL import Image

def check_wo_access(wo):
    if current_user.role == 'Technician' and current_user.id not in [a.id for a in wo.assignees]:
        return False
    return True

def get_all_project_codes():
    codes_map = {}
    for pc in ProjectCode.query.order_by(ProjectCode.code).all():
        if pc.code and pc.code.strip():
            codes_map[pc.code.strip()] = pc
            
    class DummyProjectCode:
        def __init__(self, c):
            self.id = 0
            self.code = c
            self.description = ''

    # Fast distinct queries instead of full table scans (Asset has 4400+ rows)
    site_codes = db.session.query(Site.project_code).filter(Site.project_code.isnot(None), Site.project_code != '').distinct().all()
    for (sc,) in site_codes:
        if sc and sc.strip() and sc.strip() not in codes_map:
            codes_map[sc.strip()] = DummyProjectCode(sc.strip())
            
    asset_codes = db.session.query(Asset.project_code).filter(Asset.project_code.isnot(None), Asset.project_code != '').distinct().all()
    for (ac,) in asset_codes:
        if ac and ac.strip() and ac.strip() not in codes_map:
            codes_map[ac.strip()] = DummyProjectCode(ac.strip())
            
    return [codes_map[k] for k in sorted(codes_map.keys())]

def generate_dynamic_wo_code(asset_id=None, project_code=None, maintenance_type='Corrective', target_date=None, extra_offset=0):
    """
    Format: WO - Running Number - site - 4 kode terakhir project code - PM/CM - Bulan tahun
    Contoh: WO - 1162 - Supermall Karawaci - 0015 - PM - 09 - 2026
    Collision-free dynamic running number.
    """
    # 1. Site Name
    site_name = None
    if asset_id:
        try:
            asset = db.session.get(Asset, int(asset_id))
            if asset and asset.site:
                site_name = asset.site.name
        except:
            pass
    if not site_name and getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'site', None):
        site_name = current_user.site.name
    if not site_name:
        site_name = 'Site'

    # 2. 4 kode terakhir project code
    proj_code_str = str(project_code).strip() if project_code else ''
    if proj_code_str and proj_code_str.lower() != 'none':
        proj_code_last4 = proj_code_str[-4:] if len(proj_code_str) >= 4 else proj_code_str.zfill(4)
    else:
        proj_code_last4 = '0000'

    # 3. Type code PM / CM / HM
    mt = str(maintenance_type or '').strip().lower()
    if mt in ['preventive', 'pm']:
        type_code = 'PM'
    elif mt in ['handling', 'hm']:
        type_code = 'HM'
    else:
        type_code = 'CM'

    # 4. Bulan dan Tahun dari target_date
    if not target_date:
        target_date = datetime.now(timezone.utc).replace(tzinfo=None)
    month_str = target_date.strftime("%m")
    year_str = target_date.strftime("%Y")

    # 5. Dynamic Running Number (anti-tabrakan)
    max_id = db.session.query(db.func.max(WorkOrder.id)).scalar() or 0
    candidate_num = max_id + 1 + extra_offset
    
    while True:
        running_str = f"{candidate_num:04d}" if candidate_num < 10000 else str(candidate_num)
        code_candidate = f"WO - {running_str} - {site_name} - {proj_code_last4} - {type_code} - {month_str} - {year_str}"
        
        # Cek apakah nomor atau kode sudah ada
        exists = db.session.query(WorkOrder.id).filter(
            db.or_(
                WorkOrder.code == code_candidate,
                WorkOrder.code.like(f"WO - {running_str} - %"),
                WorkOrder.code.like(f"WO-{running_str}-%")
            )
        ).first()
        
        if not exists:
            return code_candidate, running_str
        candidate_num += 1

work_orders_bp = Blueprint('work_orders', __name__, url_prefix='/work-orders')

@work_orders_bp.route('/')
@login_required
def index():
    from models import Site, SavedWorkOrderView
    status_filter = request.args.get('status')
    assigned_filter = request.args.get('assigned_to')
    site_filter = request.args.get('site_id', type=int)
    mt_filter = request.args.get('maintenance_type')
    search_query = request.args.get('q', '').strip()
    completeness_filter = request.args.get('completeness')
    
    from sqlalchemy.orm import selectinload
    query = WorkOrder.query.options(
        selectinload(WorkOrder.asset).selectinload(Asset.site),
        selectinload(WorkOrder.team),
        selectinload(WorkOrder.current_status),
        selectinload(WorkOrder.tasklist)
    )
    
    # Time Range Filtering
    time_range = request.args.get('time_range', 'this_month')
    from datetime import datetime, timezone, timedelta
    import calendar
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = None
    end_date = None
    
    if time_range == 'today':
        now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
        today_date = now_wib.date()
        start_date = datetime(today_date.year, today_date.month, today_date.day, 0, 0, 0) - timedelta(hours=7)
        end_date = datetime(today_date.year, today_date.month, today_date.day, 23, 59, 59) - timedelta(hours=7)
    elif time_range == 'this_month':
        start_date = datetime(now.year, now.month, 1)
        _, last_day = calendar.monthrange(now.year, now.month)
        end_date = datetime(now.year, now.month, last_day, 23, 59, 59)
    elif time_range == 'last_month':
        last_month = now.month - 1 if now.month > 1 else 12
        year = now.year if now.month > 1 else now.year - 1
        start_date = datetime(year, last_month, 1)
        _, last_day = calendar.monthrange(year, last_month)
        end_date = datetime(year, last_month, last_day, 23, 59, 59)
    elif time_range == 'this_year':
        start_date = datetime(now.year, 1, 1)
        end_date = datetime(now.year, 12, 31, 23, 59, 59)
    elif time_range == 'custom':
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')
        if start_str and end_str:
            try:
                from datetime import timedelta
                start_date = datetime.strptime(start_str, '%Y-%m-%d') - timedelta(hours=7)
                end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) - timedelta(hours=7)
            except ValueError:
                pass
                
    if start_date and end_date:
        from sqlalchemy import func
        query = query.filter(
            db.or_(
                func.coalesce(WorkOrder.suggested_completion_date, WorkOrder.date_created).between(start_date, end_date),
                func.coalesce(WorkOrder.suggested_start_date, WorkOrder.date_created).between(start_date, end_date)
            )
        )
        
    # Site filtering
    if current_user.site_id:
        query = query.join(Asset).filter(Asset.site_id == current_user.site_id)
    elif site_filter:
        query = query.join(Asset).filter(Asset.site_id == site_filter)
    
    # RBAC: Technicians only see their own assigned work orders
    if current_user.role == 'Technician':
        query = query.filter(WorkOrder.assignees.any(id=current_user.id))
    
    if status_filter:
        if status_filter in ['Active', 'Pending', 'Closed', 'Draft']:
            query = query.join(WorkOrderStatus).filter(WorkOrderStatus.control_type == status_filter)
        else:
            if str(status_filter).isdigit():
                query = query.filter(WorkOrder.status_id == int(status_filter))
            else:
                query = query.join(WorkOrderStatus).filter(WorkOrderStatus.name == status_filter)
    if assigned_filter:
        query = query.filter(WorkOrder.assignees.any(id=assigned_filter))
    if mt_filter:
        query = query.filter(WorkOrder.maintenance_type == mt_filter)
    if completeness_filter == 'no_tasklist':
        query = query.filter(WorkOrder.tasklist_id == None)
    elif completeness_filter == 'no_checklist':
        query = query.filter(WorkOrder.checklist_id == None)
    elif completeness_filter == 'no_both':
        query = query.filter(db.and_(WorkOrder.tasklist_id == None, WorkOrder.checklist_id == None))
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            db.or_(
                WorkOrder.code.ilike(search_term),
                WorkOrder.description.ilike(search_term)
            )
        )
        
    work_orders = query.all()
    statuses = WorkOrderStatus.query.all()
    users = User.query.all()
    
    # Get available sites for filter (only for users without fixed site)
    available_sites = []
    if not current_user.site_id:
        available_sites = Site.query.order_by(Site.name).all()
        
    # Get unique maintenance types
    db_types = db.session.query(WorkOrder.maintenance_type).distinct().all()
    maintenance_types = [dt[0] for dt in db_types if dt[0]]
    if not maintenance_types:
        maintenance_types = ['Corrective', 'Preventive']
    elif 'Corrective' not in maintenance_types:
        maintenance_types.append('Corrective')
    elif 'Preventive' not in maintenance_types:
        maintenance_types.append('Preventive')
    
    view_mode = request.args.get('view', 'list')
    
    # Prepare JSON data for advanced views
    work_orders_data = []
    for wo in work_orders:
        work_orders_data.append({
            'id': wo.id,
            'code': wo.code,
            'description': wo.description,
            'priority': wo.priority or '-',
            'maintenance_type': wo.maintenance_type or '-',
            'asset': wo.asset.name if wo.asset else '-',
            'site': wo.asset.site.name if wo.asset and wo.asset.site else '-',
            'assignees': [a.name for a in wo.assignees] if wo.assignees else [],
            'team': wo.team.name if wo.team else '-',
            'status': wo.current_status.name if wo.current_status else 'Draft',
            'status_control': wo.current_status.control_type if wo.current_status else 'Draft',
            'project': wo.project_code or '-',
            'tasklist': wo.tasklist.name if wo.tasklist else '-',
            'customer_name': wo.customer_name or '-',
            'estimated_hours': wo.estimated_hours or 0,
            'date_created': str(wo.date_created.date()) if wo.date_created else '-',
            'start_date': str((wo.suggested_start_date or wo.start_date).date()) if (wo.suggested_start_date or wo.start_date) else '-',
            'target_date': str((wo.suggested_completion_date or wo.end_date).date()) if (wo.suggested_completion_date or wo.end_date) else '-',
        })
    work_orders_json = json.dumps(work_orders_data)
    if time_range == 'today':
        now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
        start_date_str = now_wib.strftime('%Y-%m-%d')
        end_date_str = now_wib.strftime('%Y-%m-%d')
    elif time_range == 'custom':
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')
    else:
        start_date_str = start_date.strftime('%Y-%m-%d') if start_date else ''
        end_date_str = end_date.strftime('%Y-%m-%d') if end_date else ''
    

    
    # Fetch saved views
    saved_views = SavedWorkOrderView.query.filter(
        db.or_(SavedWorkOrderView.is_public == True, SavedWorkOrderView.user_id == current_user.id)
    ).order_by(SavedWorkOrderView.name).all()

    return render_template('work_orders/index.html', work_orders=work_orders, statuses=statuses, users=users, available_sites=available_sites, selected_site_id=site_filter, maintenance_types=maintenance_types, selected_mt=mt_filter, search_query=search_query, completeness_filter=completeness_filter, view_mode=view_mode, work_orders_json=work_orders_json, time_range=time_range, start_date_str=start_date_str, end_date_str=end_date_str, saved_views=saved_views)

@work_orders_bp.route('/save-view', methods=['POST'])
@login_required
def save_view():
    from models import SavedWorkOrderView
    from flask import jsonify
    name = request.form.get('name')
    is_public = request.form.get('is_public') == 'true'
    view_mode = request.form.get('view_mode', 'pivot')
    pivot_row = request.form.get('pivot_row', '')
    pivot_col = request.form.get('pivot_col', '')
    filters = request.form.get('filters', '{}')
    
    if not name:
        return jsonify({'success': False, 'message': 'Name is required'}), 400
        
    new_view = SavedWorkOrderView(
        name=name,
        user_id=current_user.id,
        is_public=is_public,
        view_mode=view_mode,
        pivot_row=pivot_row,
        pivot_col=pivot_col,
        filters=filters
    )
    db.session.add(new_view)
    db.session.commit()
    
    return jsonify({'success': True, 'id': new_view.id, 'name': new_view.name})

@work_orders_bp.route('/delete-view/<int:id>', methods=['POST'])
@login_required
def delete_view(id):
    from models import SavedWorkOrderView
    from flask import jsonify
    view = SavedWorkOrderView.query.get_or_404(id)
    if view.user_id != current_user.id and current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    db.session.delete(view)
    db.session.commit()
    return jsonify({'success': True})

@work_orders_bp.route('/export')
@login_required
@supervisor_or_admin_required
def export_all():
    from models import Site
    status_filter = request.args.get('status')
    assigned_filter = request.args.get('assigned_to')
    site_filter = request.args.get('site_id', type=int)
    mt_filter = request.args.get('maintenance_type')
    format = request.args.get('format', 'excel')
    
    query = WorkOrder.query
    
    # Site filtering
    if current_user.site_id:
        query = query.join(Asset).filter(Asset.site_id == current_user.site_id)
    elif site_filter:
        query = query.join(Asset).filter(Asset.site_id == site_filter)
    
    # RBAC: Technicians only see their own assigned work orders (though supervisor_or_admin_required is active)
    if current_user.role == 'Technician':
        query = query.filter(WorkOrder.assignees.any(id=current_user.id))
    
    if status_filter:
        if status_filter in ['Active', 'Pending', 'Closed', 'Draft']:
            query = query.join(WorkOrderStatus).filter(WorkOrderStatus.control_type == status_filter)
        else:
            if str(status_filter).isdigit():
                query = query.filter(WorkOrder.status_id == int(status_filter))
            else:
                query = query.join(WorkOrderStatus).filter(WorkOrderStatus.name == status_filter)
    if assigned_filter:
        query = query.filter(WorkOrder.assignees.any(id=assigned_filter))
    if mt_filter:
        query = query.filter(WorkOrder.maintenance_type == mt_filter)
        
    work_orders = query.all()
    
    data = []
    for wo in work_orders:
        # Detailed sub-data concatenation
        procedures_list = []
        for p in wo.procedures:
            status = "Done" if p.is_completed else "Pending"
            procedures_list.append(f"- {p.name} ({status})")
        procedures_text = "\n".join(procedures_list)

        checklist_list = []
        for c in wo.checklist_parameters:
            val = c.value if c.value else "N/A"
            checklist_list.append(f"- {c.parameter}: {val} (Std: {c.standard})")
        checklist_text = "\n".join(checklist_list)

        parts_list = []
        for up in wo.used_parts:
            parts_list.append(f"- {up.part.name} (Qty: {up.quantity_used})")
        parts_text = "\n".join(parts_list)

        data.append({
            'Code': wo.code,
            'Description': wo.description,
            'Status': wo.current_status.name if wo.current_status else '',
            'Priority': wo.priority,
            'Maintenance Type': wo.maintenance_type,
            'Asset Code': wo.asset.code if wo.asset else '',
            'Asset Name': wo.asset.name if wo.asset else '',
            'Site': wo.asset.site.name if wo.asset and wo.asset.site else '',
            'Assigned Technicians': ", ".join([u.name for u in wo.assignees]),
            'Project Code': wo.project_code,
            'Start Date': wo.start_date.strftime('%Y-%m-%d %H:%M') if wo.start_date else '',
            'End Date': wo.end_date.strftime('%Y-%m-%d %H:%M') if wo.end_date else '',
            'Suggested Start': wo.suggested_start_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_start_date else '',
            'Suggested Completion': wo.suggested_completion_date.strftime('%Y-%m-%d %H:%M') if wo.suggested_completion_date else '',
            'Estimated Hours': wo.estimated_hours,
            'Tasklist': wo.tasklist.name if wo.tasklist else '',
            'Checklist': wo.checklist.name if wo.checklist else '',
            'Procedures/Tasks': procedures_text,
            'Checklist Results': checklist_text,
            'Parts Used': parts_text
        })
        
    df = pd.DataFrame(data)
    
    if format == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Work Orders')
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f'work_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=work_orders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"})

@work_orders_bp.route('/template')
@login_required
@supervisor_or_admin_required
def download_template():
    columns = [
        'Code', 'Description', 'Asset Name', 'Priority', 'Maintenance Type', 
        'Assignee Name', 'Project Code', 'Tasklist Name', 'Checklist Name',
        'Suggested Start Date', 'Suggested Completion Date'
    ]
    df = pd.DataFrame(columns=columns)
    
    # Add an example row
    example_row = {
        'Code': 'WO-AUTO-001',
        'Description': 'Example maintenance task',
        'Asset Name': 'Chiller 1',
        'Priority': 'Medium',
        'Maintenance Type': 'Corrective',
        'Assignee Name': 'John Doe',
        'Project Code': 'PROJ-01',
        'Tasklist Name': 'General Maintenance',
        'Checklist Name': 'Safety Checklist',
        'Suggested Start Date': datetime.now().strftime('%Y-%m-%d 08:00'),
        'Suggested Completion Date': datetime.now().strftime('%Y-%m-%d 17:00')
    }
    df = pd.concat([df, pd.DataFrame([example_row])], ignore_index=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Template')
        
        # --- Add Dropdowns using DataValidation ---
        worksheet = writer.sheets['Template']
        
        # Fetch lookup data (filter by site if Supervisor)
        if current_user.role != 'Admin' and current_user.site_id:
            assets = Asset.query.filter_by(site_id=current_user.site_id).all()
            users = User.query.filter(
                db.or_(User.site_id == current_user.site_id, User.site_id == None)
            ).all()
        else:
            assets = Asset.query.all()
            users = User.query.all()
            
        asset_names = [a.name for a in assets if a.name]
        user_names = [u.name for u in users if u.name]
        
        projects = ProjectCode.query.all()
        project_codes = [p.code for p in projects if p.code]
        
        tasklists = Tasklist.query.all()
        tasklist_names = [t.name for t in tasklists if t.name]
        
        checklists = Checklist.query.all()
        checklist_names = [c.name for c in checklists if c.name]
        
        priorities = ['Highest', 'High', 'Medium', 'Low', 'None']
        maintenance_types = ['Preventive', 'Corrective', 'Inspection', 'Other']
        
        # Create a hidden 'Lookups' sheet
        wb = writer.book
        lookup_sheet = wb.create_sheet('Lookups')
        lookup_sheet.sheet_state = 'hidden'
        
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation
        
        def write_lookup_col(col_idx, header, data_list):
            lookup_sheet.cell(row=1, column=col_idx, value=header)
            for r_idx, val in enumerate(data_list, start=2):
                lookup_sheet.cell(row=r_idx, column=col_idx, value=val)
            
            col_letter = get_column_letter(col_idx)
            if data_list:
                return f"Lookups!${col_letter}$2:${col_letter}${len(data_list)+1}"
            return None
            
        # Create named range for all assets
        all_assets_range = write_lookup_col(1, 'Asset Names', asset_names)
        if all_assets_range:
            wb.create_named_range('All_Assets', lookup_sheet, all_assets_range.split('!')[1])
            
        priority_range = write_lookup_col(2, 'Priorities', priorities)
        maint_type_range = write_lookup_col(3, 'Maintenance Types', maintenance_types)
        nrp_range = write_lookup_col(4, 'Assignee Names', user_names)
        proj_range = write_lookup_col(5, 'Project Codes', project_codes)
        tasklist_range = write_lookup_col(6, 'Tasklist Names', tasklist_names)
        checklist_range = write_lookup_col(7, 'Checklist Names', checklist_names)
        
        # Create named ranges for each project's assets
        col_offset = 8
        import re
        for project in project_codes:
            proj_assets = [a.name for a in assets if a.project_code == project and a.name]
            if proj_assets:
                rng = write_lookup_col(col_offset, f"{project} Assets", proj_assets)
                # Sanitize name for Excel Named Range (no spaces, hyphens, etc.)
                safe_name = re.sub(r'[^A-Za-z0-9_]', '_', project)
                if not safe_name[0].isalpha() and safe_name[0] != '_':
                    safe_name = '_' + safe_name
                wb.create_named_range(safe_name, lookup_sheet, rng.split('!')[1])
                col_offset += 1
        
        def add_dv(dv_range, cols_str, formula=None):
            f1 = formula if formula else dv_range
            if f1:
                dv = DataValidation(type="list", formula1=f1, allow_blank=True, showErrorMessage=True, errorTitle="Invalid Input", error="Please select a value from the dropdown list.")
                worksheet.add_data_validation(dv)
                dv.add(cols_str)
                
        # Apply to Template sheet columns
        # Asset Name dependent on Project Code (Column G)
        asset_formula = '=IF(ISBLANK(G2), All_Assets, INDIRECT(SUBSTITUTE(SUBSTITUTE(G2, " ", "_"), "-", "_")))'
        add_dv(None, "C2:C1000", formula=asset_formula)
        add_dv(priority_range, "D2:D1000")
        add_dv(maint_type_range, "E2:E1000")
        add_dv(nrp_range, "F2:F1000")
        add_dv(proj_range, "G2:G1000")
        add_dv(tasklist_range, "H2:H1000")
        add_dv(checklist_range, "I2:I1000")
        
        # Add column widths for better UX
        for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']:
            worksheet.column_dimensions[col].width = 20
        worksheet.column_dimensions['B'].width = 30 # Description
        
    output.seek(0)
    return send_file(output, as_attachment=True, download_name='wo_import_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@work_orders_bp.route('/import', methods=['POST'])
@login_required
@supervisor_or_admin_required
def import_all():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('work_orders.index'))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('work_orders.index'))
        
    if file:
        filename = file.filename
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith('.xlsx') or filename.endswith('.xls'):
                df = pd.read_excel(file)
            else:
                flash('Unsupported file format. Please upload CSV or Excel.', 'danger')
                return redirect(url_for('work_orders.index'))
                
            success_count = 0
            error_count = 0
            errors = []
            created_wos = []
            
            # Pre-fetch statuses to avoid repeated queries
            draft_status = WorkOrderStatus.query.filter_by(name='Draft').first()
            assigned_status = WorkOrderStatus.query.filter(WorkOrderStatus.name.in_(['Assigned', 'Confirmed'])).first()
            
            for index, row in df.iterrows():
                try:
                    description = row.get('Description')
                    asset_name = row.get('Asset Name')
                    
                    if pd.isna(description) or pd.isna(asset_name):
                        error_count += 1
                        errors.append(f"Row {index+2}: Description or Asset Name is missing.")
                        continue
                    
                    # Find Asset
                    asset = Asset.query.filter_by(name=str(asset_name).strip()).first()
                    if not asset:
                        error_count += 1
                        errors.append(f"Row {index+2}: Asset with name '{asset_name}' not found.")
                        continue
                        
                    # Find Tasklist if name is provided
                    tasklist = None
                    tl_name = row.get('Tasklist Name')
                    if not pd.isna(tl_name):
                        tasklist = Tasklist.query.filter_by(name=str(tl_name).strip()).first()
                        
                    # Find Checklist if name is provided
                    checklist = None
                    cl_name = row.get('Checklist Name')
                    if not pd.isna(cl_name):
                        checklist = Checklist.query.filter_by(name=str(cl_name).strip()).first()
                        
                    # Find Assignee if Name is provided
                    assignee = None
                    assignee_name = row.get('Assignee Name')
                    if not pd.isna(assignee_name):
                        assignee = User.query.filter_by(name=str(assignee_name).strip()).first()
                        
                    # Handle Dates
                    def parse_date(date_val):
                        if pd.isna(date_val): return None
                        from datetime import timedelta
                        dt = None
                        if isinstance(date_val, datetime): dt = date_val
                        else:
                            try:
                                dt = datetime.strptime(str(date_val).strip(), '%Y-%m-%d %H:%M')
                            except:
                                try:
                                    dt = datetime.strptime(str(date_val).strip(), '%Y-%m-%d')
                                except:
                                    pass
                        if dt:
                            return dt - timedelta(hours=7)
                        return None
                                
                    suggested_start = parse_date(row.get('Suggested Start Date'))
                    suggested_end = parse_date(row.get('Suggested Completion Date'))
                    
                    # Generate Code if not provided
                    code = row.get('Code')
                    if pd.isna(code) or not str(code).strip():
                        proj_val = str(row.get('Project Code', '')).strip() if not pd.isna(row.get('Project Code')) else ''
                        mt_val = str(row.get('Maintenance Type', 'CM')).strip() if not pd.isna(row.get('Maintenance Type')) else 'CM'
                        ref_date = suggested_start or datetime.now(timezone.utc).replace(tzinfo=None)
                        code, _ = generate_dynamic_wo_code(
                            asset_id=asset.id if asset else None,
                            project_code=proj_val,
                            maintenance_type=mt_val,
                            target_date=ref_date,
                            extra_offset=success_count
                        )
                    else:
                        code = str(code).strip()
                        
                    # Check if WO code already exists
                    existing_wo = WorkOrder.query.filter_by(code=code).first()
                    if existing_wo:
                        error_count += 1
                        errors.append(f"Row {index+2}: Work Order with code '{code}' already exists.")
                        continue
                        
                    # Initial Status
                    status_id = assigned_status.id if (assignee and assigned_status) else (draft_status.id if draft_status else None)
                    
                    # Create Work Order
                    new_wo = WorkOrder(
                        code=code,
                        description=str(description),
                        asset_id=asset.id,
                        status_id=status_id,
                        priority=str(row.get('Priority', 'Medium')) if not pd.isna(row.get('Priority')) else 'Medium',
                        maintenance_type=str(row.get('Maintenance Type', 'Corrective')) if not pd.isna(row.get('Maintenance Type')) else 'Corrective',
                        project_code=str(row.get('Project Code')) if not pd.isna(row.get('Project Code')) else None,
                        tasklist_id=tasklist.id if tasklist else None,
                        checklist_id=checklist.id if checklist else None,
                        suggested_start_date=suggested_start,
                        suggested_completion_date=suggested_end
                    )
                    
                    if assignee:
                        new_wo.assignees.append(assignee)
                        
                    db.session.add(new_wo)
                    db.session.flush() # Get the new WO ID
                    
                    # Log Creation
                    l = WorkOrderLog(work_order_id=new_wo.id, user_id=current_user.id, log_text="Work Order created (Imported).")
                    db.session.add(l)
                    db.session.flush() # Generate ID
                    
                    # Copy procedures if tasklist
                    if tasklist:
                        for proc in tasklist.procedures.order_by(TasklistProcedure.position.asc(), TasklistProcedure.id.asc()):
                            new_proc = WorkOrderProcedure(
                                work_order_id=new_wo.id,
                                tasklist_name=tasklist.name,
                                name=proc.name,
                                requires_attachment=proc.requires_attachment,
                                min_photos=proc.min_photos,
                                estimated_minutes=proc.estimated_minutes
                            )
                            db.session.add(new_proc)
                            
                    # Copy checklist parameters if checklist
                    if checklist:
                        for param in checklist.parameters.order_by(ChecklistParameterTemplate.position.asc(), ChecklistParameterTemplate.id.asc()):
                            new_chk = WorkOrderChecklistParameter(
                                work_order_id=new_wo.id,
                                checklist_name=checklist.name,
                                parameter=param.parameter,
                                standard=param.standard
                            )
                            db.session.add(new_chk)
                            
                    success_count += 1
                    created_wos.append(new_wo)
                    
                except Exception as e:
                    error_count += 1
                    errors.append(f"Row {index+2}: Internal error - {str(e)}")
                    
            db.session.commit()

            # Auto sync imported work orders to schedule
            try:
                from schedule import sync_work_order_to_schedule
                for w in created_wos:
                    sync_work_order_to_schedule(w)
            except Exception as e:
                current_app.logger.warning(f"Could not sync imported WOs to schedule: {e}")
            
            if error_count > 0:
                error_msg = f"Import completed with {error_count} errors. {success_count} work orders created."
                if errors:
                    error_msg += " First few errors: " + "; ".join(errors[:3])
                flash(error_msg, 'warning')
            else:
                flash(f'Successfully imported {success_count} work orders.', 'success')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing file: {str(e)}', 'danger')
            
    return redirect(url_for('work_orders.index'))

@work_orders_bp.route('/create', methods=['GET', 'POST'])
@login_required
@supervisor_or_admin_required
def create():
    if request.method == 'POST':
        code = request.form.get('code')
        description = request.form.get('description')
        status_id = request.form.get('status_id')
        priority = request.form.get('priority', 'Medium')
        maintenance_type = request.form.get('maintenance_type', 'Corrective')
        asset_id = request.form.get('asset_id')
        team_id = request.form.get('team_id') or None
        
        assignees = []
        user_ids = set(request.form.getlist('assigned_to'))
        
        # If team is selected, add its members
        if team_id:
            team = db.session.get(Team, team_id)
            if team:
                for u in team.users:
                    user_ids.add(str(u.id))
        
        for uid in user_ids:
            if uid:
                u = db.session.get(User, uid)
                if u:
                    assignees.append(u)
        
        project_code = request.form.get('project_code') or None
            
        tasklist_id = request.form.get('tasklist_id') or None
        if tasklist_id:
            tasklist_id = int(tasklist_id)
            
        checklist_id = request.form.get('checklist_id') or None
        if checklist_id:
            checklist_id = int(checklist_id)
            
        helpdesk_ticket_id = request.form.get('helpdesk_ticket_id') or None
        if helpdesk_ticket_id:
            helpdesk_ticket_id = int(helpdesk_ticket_id)
        
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        suggested_start_date_str = request.form.get('suggested_start_date')
        suggested_date_str = request.form.get('suggested_completion_date')

        # Mandatory Field Validation
        project_code = request.form.get('project_code')
        user_site_id = getattr(current_user, 'site_id', None)
        if user_site_id:
            user_site = Site.query.get(user_site_id)
            if user_site and user_site.project_code:
                project_code = user_site.project_code
                
        asset_id = request.form.get('asset_id')
        tasklist_id = request.form.get('tasklist_id')
        checklist_id = request.form.get('checklist_id')
        custom_proc_json = request.form.get('custom_procedures_json', '[]')
        custom_chk_json = request.form.get('custom_checklists_json', '[]')

        with open('debug.txt', 'a') as f:
            f.write(f"POST received. form keys: {list(request.form.keys())}\n")
            f.write(f"proc_json: {custom_proc_json}\n")
            f.write(f"chk_json: {custom_chk_json}\n")
            f.write(f"tasklist_id: {tasklist_id}\n")

        errors = []
        if not asset_id:
            errors.append("Asset selection is mandatory.")
        if not project_code:
            errors.append("Project Code selection is mandatory.")
        if not suggested_start_date_str:
            errors.append("Suggested Start Date is mandatory.")
        if not suggested_date_str:
            errors.append("Suggested End Date is mandatory.")
        
        # Check if tasklist is provided either via template or custom tasks
        has_tasks = False
        if tasklist_id:
            has_tasks = True
        else:
            try:
                if json.loads(custom_proc_json):
                    has_tasks = True
            except: pass
        if not has_tasks:
            errors.append("Tasklist is mandatory (select a template or add custom tasks).")

        # Check if checklist is provided either via template or custom parameters
        has_checklists = False
        if checklist_id:
            has_checklists = True
        else:
            try:
                if json.loads(custom_chk_json):
                    has_checklists = True
            except: pass
        if not has_checklists:
            errors.append("Checklist is mandatory (select a template or add custom parameters).")

        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('work_orders.create', **request.args))
        
        from datetime import timedelta
        start_date = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if end_date_str else None
        suggested_start_date = datetime.strptime(suggested_start_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if suggested_start_date_str else None
        suggested_completion_date = datetime.strptime(suggested_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if suggested_date_str else None
        
        estimated_hours = None
        if start_date and end_date:
            estimated_hours = round((end_date - start_date).total_seconds() / 3600, 2)
        
        # Dynamic collision-free WO code generation
        target_date_for_code = suggested_start_date or start_date or datetime.now(timezone.utc).replace(tzinfo=None)
        code, _ = generate_dynamic_wo_code(
            asset_id=asset_id,
            project_code=project_code,
            maintenance_type=maintenance_type,
            target_date=target_date_for_code
        )
            
        # State Machine Auto Status handling
        now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        target_date = suggested_completion_date or suggested_start_date or start_date or now_dt
        is_future_month = (target_date.year > now_dt.year) or (target_date.year == now_dt.year and target_date.month > now_dt.month)

        if is_future_month:
            status = WorkOrderStatus.query.filter_by(name='Draft').first()
        elif assignees:
            status = WorkOrderStatus.query.filter(WorkOrderStatus.name.in_(['Assigned', 'Confirmed'])).first()
        else:
            status = WorkOrderStatus.query.filter_by(name='Draft').first()
            
        if not status:
            target_name = 'Draft' if (is_future_month or not assignees) else 'Assigned'
            status = WorkOrderStatus(name=target_name, control_type='Draft' if target_name == 'Draft' else 'Pending')
            db.session.add(status)
            db.session.flush()
            
        status_id = status.id if status else None
        
        new_wo = WorkOrder(
            code=code, 
            description=description, 
            status_id=status_id, 
            priority=priority, 
            maintenance_type=maintenance_type,
            asset_id=asset_id,
            team_id=team_id,
            assignees=assignees,
            project_code=project_code,
            tasklist_id=tasklist_id,
            checklist_id=checklist_id,
            start_date=start_date,
            end_date=end_date,
            suggested_start_date=suggested_start_date,
            suggested_completion_date=suggested_completion_date,
            estimated_hours=estimated_hours,
            helpdesk_ticket_id=helpdesk_ticket_id
        )
        db.session.add(new_wo)
        db.session.flush()
                    
        import json
        
        # Parse custom procedures
        custom_proc_json = request.form.get('custom_procedures_json', '[]')
        custom_procs_list = []
        try:
            custom_procs_list = json.loads(custom_proc_json)
        except:
            pass
            
        if custom_procs_list:
            for cp in custom_procs_list:
                if isinstance(cp, dict) and cp.get('name'):
                    new_cp = WorkOrderProcedure(
                        work_order=new_wo,
                        tasklist_name='Custom Task',
                        name=cp.get('name'),
                        estimated_minutes=cp.get('estimated_minutes', 0),
                        requires_attachment=cp.get('requires_attachment', False),
                        min_photos=cp.get('min_photos', 0)
                    )
                    db.session.add(new_cp)
        elif tasklist_id:
            # Fallback Native Template Copying
            tasklist = db.session.get(Tasklist, tasklist_id)
            if tasklist:
                for proc in tasklist.procedures.order_by(TasklistProcedure.position.asc(), TasklistProcedure.id.asc()):
                    new_proc = WorkOrderProcedure(work_order=new_wo, tasklist_name=tasklist.name, name=proc.name, requires_attachment=proc.requires_attachment, min_photos=proc.min_photos)
                    db.session.add(new_proc)
                    
        # Parse custom checklists
        custom_chk_json = request.form.get('custom_checklists_json', '[]')
        custom_chks_list = []
        try:
            custom_chks_list = json.loads(custom_chk_json)
        except:
            pass
            
        if custom_chks_list:
            for cc in custom_chks_list:
                if isinstance(cc, dict) and cc.get('parameter'):
                    new_cc = WorkOrderChecklistParameter(
                        work_order=new_wo,
                        checklist_name='Custom Parameter',
                        parameter=cc.get('parameter'),
                        standard=cc.get('standard', '')
                    )
                    db.session.add(new_cc)
        elif checklist_id:
            # Fallback Native Template Copying
            checklist = db.session.get(Checklist, checklist_id)
            if checklist:
                for param in checklist.parameters.order_by(ChecklistParameterTemplate.position.asc(), ChecklistParameterTemplate.id.asc()):
                    new_chk = WorkOrderChecklistParameter(work_order=new_wo, checklist_name=checklist.name, parameter=param.parameter, standard=param.standard)
                    db.session.add(new_chk)
                    

                    

        # Process custom parts
        custom_parts_json = request.form.get('custom_parts_json', '[]')
        custom_parts_list = []
        try:
            custom_parts_list = json.loads(custom_parts_json)
        except:
            pass
            
        parts_flash_msg = ""
        if custom_parts_list:
            for cv in custom_parts_list:
                if isinstance(cv, dict):
                    pid = cv.get('part_id')
                    qty = float(cv.get('qty', 0))
                    if pid and qty > 0:
                        part_id = int(pid)
                        # Verify stock — only if asset is loaded and has a site
                        asset_site_id = new_wo.asset.site_id if new_wo.asset else None
                        if asset_site_id:
                            stock = StockLevel.query.filter_by(part_id=part_id, site_id=asset_site_id).first()
                        else:
                            stock = None
                        if stock and stock.qty_on_hand >= qty:
                            stock.qty_on_hand -= qty
                            wo_part = WorkOrderPart.query.filter_by(work_order_id=new_wo.id, part_id=part_id).first()
                            if wo_part:
                                wo_part.quantity_used += qty
                            else:
                                wo_part = WorkOrderPart(work_order_id=new_wo.id, part_id=part_id, quantity_used=qty)
                                db.session.add(wo_part)
                        else:
                            parts_flash_msg = " Some parts were not added due to insufficient stock."
                            
        # Log Creation
        l = WorkOrderLog(work_order_id=new_wo.id, user_id=current_user.id, log_text="Work Order created.")
        db.session.add(l)
                            
        db.session.commit()

        # Auto Sync to Team Schedule
        try:
            from schedule import sync_work_order_to_schedule
            sync_work_order_to_schedule(new_wo)
        except Exception as e:
            current_app.logger.warning(f"Could not auto-sync WO {new_wo.code} to schedule: {e}")
        
        # WhatsApp Notification
        for tech in new_wo.assignees:
            if tech.phone_number:
                wa_msg = f"*MAINTENANCE BARU (WO)*\n\nKode: {new_wo.code}\nDeskripsi: {new_wo.description}\nPrioritas: {new_wo.priority}\nAsset: {new_wo.asset.name if new_wo.asset else '-'}\n\nSilakan cek jadwal di sistem."
                send_whatsapp_notification(tech.phone_number, wa_msg)
                
        flash('Work Order created successfully!' + parts_flash_msg, 'success')
        return redirect(url_for('work_orders.index'))
        
    current_date = datetime.now(timezone.utc).replace(tzinfo=None)
    month_year = current_date.strftime("%m-%Y")
    month_str = current_date.strftime("%m")
    year_str = current_date.strftime("%Y")
        
    user_site_id = getattr(current_user, 'site_id', None)
    user_site = None
    if user_site_id:
        assets = Asset.query.filter_by(site_id=user_site_id).all()
        teams = Team.query.filter_by(site_id=user_site_id).all()
        users = User.query.filter(db.or_(User.site_id == user_site_id, User.site_id == None)).all()
        
        user_site = Site.query.get(user_site_id)
        if user_site and user_site.project_code:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == user_site.project_code, Tasklist.project_code == None, Tasklist.project_code == '')).order_by(Tasklist.name).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == user_site.project_code, Checklist.project_code == None, Checklist.project_code == '')).order_by(Checklist.name).all()
        else:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == None, Tasklist.project_code == '')).order_by(Tasklist.name).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == None, Checklist.project_code == '')).order_by(Checklist.name).all()
    else:
        assets = Asset.query.all()
        teams = Team.query.all()
        users = User.query.all()
        tasklists = Tasklist.query.order_by(Tasklist.name).all()
        checklists = Checklist.query.order_by(Checklist.name).all()
        
    import json
    assets_json = json.dumps([{'id': a.id, 'name': a.name, 'code': a.code, 'site_name': (a.site.name if a.site else ''), 'project_code': (a.site.project_code if a.site and a.site.project_code else a.project_code)} for a in assets])

    statuses = WorkOrderStatus.query.all()
    for t in tasklists:
        t.project_code_group = t.project_code if t.project_code else ""
    for c in checklists:
        c.project_code_group = c.project_code if c.project_code else ""
    parts = Part.query.order_by(Part.name).all()
    
    tasklists_json = json.dumps([{'id': t.id, 'name': t.name, 'project_code': t.project_code} for t in tasklists])
    checklists_json = json.dumps([{'id': c.id, 'name': c.name, 'project_code': c.project_code} for c in checklists])
    
    copy_from_id = request.args.get('copy_from')
    source_wo = None
    source_procedures_json = '[]'
    source_checklists_json = '[]'
    source_parts_json = '[]'
    source_assignee_ids = []
    
    if copy_from_id:
        try:
            source_wo = db.session.get(WorkOrder, int(copy_from_id))
            if source_wo:
                source_assignee_ids = [u.id for u in source_wo.assignees]
                
                procs = []
                for p in source_wo.procedures.order_by(WorkOrderProcedure.id.asc()).all():
                    procs.append({
                        'name': p.name,
                        'estimated_minutes': p.estimated_minutes or 0,
                        'requires_attachment': bool(p.requires_attachment),
                        'min_photos': int(p.min_photos or 0)
                    })
                source_procedures_json = json.dumps(procs)
                
                chks = []
                for c in source_wo.checklist_parameters.order_by(WorkOrderChecklistParameter.id.asc()).all():
                    chks.append({
                        'parameter': c.parameter,
                        'standard': c.standard or ''
                    })
                source_checklists_json = json.dumps(chks)
                
                parts_data = []
                for wp in source_wo.used_parts.all():
                    if wp.part:
                        parts_data.append({
                            'part_id': wp.part_id,
                            'name': wp.part.name,
                            'code': getattr(wp.part, 'code', '') or getattr(wp.part, 'part_number', ''),
                            'qty': wp.quantity_used
                        })
                source_parts_json = json.dumps(parts_data)
        except Exception as e:
            pass

    # Recent work orders for quick copy selector
    recent_wo_query = WorkOrder.query
    if user_site_id:
        recent_wo_query = recent_wo_query.join(Asset).filter(Asset.site_id == user_site_id)
    recent_work_orders = recent_wo_query.order_by(WorkOrder.id.desc()).limit(15).all()

    ticket = None
    ticket_id = request.args.get('ticket_id')
    if ticket_id:
        from models import HelpdeskTicket
        ticket = db.session.get(HelpdeskTicket, ticket_id)

    user_site_project_code = user_site.project_code if (user_site and user_site.project_code) else None
    
    target_maint_type = 'Handling' if ticket else (source_wo.maintenance_type if source_wo else 'Preventive')
    target_project_code = (source_wo.project_code if source_wo and source_wo.project_code else user_site_project_code)
    target_date_for_code = (source_wo.suggested_start_date if source_wo and source_wo.suggested_start_date else current_date)
    
    # When duplicating, leave initial asset empty so user explicitly selects the new asset
    first_asset_id = None if source_wo else (assets[0].id if assets else None)
    initial_code, running_number_str = generate_dynamic_wo_code(
        asset_id=first_asset_id,
        project_code=target_project_code,
        maintenance_type=target_maint_type,
        target_date=target_date_for_code
    )
    
    return render_template('work_orders/create.html', ticket=ticket, parts=parts, assets=assets, assets_json=assets_json, users=users, teams=teams, statuses=statuses, project_codes=get_all_project_codes(), tasklists=tasklists, tasklists_json=tasklists_json, checklists=checklists, checklists_json=checklists_json, month_year=month_year, month_str=month_str, year_str=year_str, running_number_str=running_number_str, initial_code=initial_code, source_wo=source_wo, source_procedures_json=source_procedures_json, source_checklists_json=source_checklists_json, source_parts_json=source_parts_json, source_assignee_ids=source_assignee_ids, recent_work_orders=recent_work_orders)

@work_orders_bp.route('/api/next-code', methods=['GET'])
@login_required
def get_next_wo_code_api():
    asset_id = request.args.get('asset_id')
    project_code = request.args.get('project_code')
    maintenance_type = request.args.get('maintenance_type', 'Preventive')
    date_str = request.args.get('date')
    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        except:
            try:
                target_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            except:
                pass
    code, running_str = generate_dynamic_wo_code(asset_id, project_code, maintenance_type, target_date)
    return jsonify({'code': code, 'running_number': running_str})

@work_orders_bp.route('/api/tasklist/<int:id>', methods=['GET'])
@login_required
def get_tasklist_api(id):
    tasklist = Tasklist.query.get_or_404(id)
    procs = []
    for p in tasklist.procedures.order_by(TasklistProcedure.position.asc(), TasklistProcedure.id.asc()):
        procs.append({
            'name': p.name,
            'estimated_minutes': p.estimated_minutes,
            'requires_attachment': p.requires_attachment,
            'min_photos': int(p.min_photos or 0)
        })
    from flask import jsonify
    return jsonify(procs)

@work_orders_bp.route('/api/checklist/<int:id>', methods=['GET'])
@login_required
def get_checklist_api(id):
    chk = Checklist.query.get_or_404(id)
    params = []
    for p in chk.parameters.order_by(ChecklistParameterTemplate.position.asc(), ChecklistParameterTemplate.id.asc()):
        params.append({
            'parameter': p.parameter,
            'standard': p.standard
        })
    from flask import jsonify
    return jsonify(params)

@work_orders_bp.route('/api/team/<int:id>/members', methods=['GET'])
@login_required
def get_team_members_api(id):
    team = Team.query.get_or_404(id)
    members = []
    for u in team.users:
        members.append({
            'id': u.id,
            'name': u.name,
            'nrp': u.nrp,
            'role': u.role
        })
    from flask import jsonify
    return jsonify(members)

@work_orders_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    wo = WorkOrder.query.options(
        db.joinedload(WorkOrder.asset).joinedload(Asset.site),
        db.joinedload(WorkOrder.current_status)
    ).get_or_404(id)
    if not check_wo_access(wo):
        flash('Access denied. You can only access work orders assigned to you.', 'danger')
        return redirect(url_for('work_orders.index'))
        
    # Self-healing logic for WOs created without a status
    if not wo.status_id:
        target_name = 'Assigned' if wo.assignees else 'Draft'
        status = WorkOrderStatus.query.filter(WorkOrderStatus.name.in_(['Assigned', 'Confirmed'])).first() if target_name == 'Assigned' else WorkOrderStatus.query.filter_by(name='Draft').first()
        if not status:
            status = WorkOrderStatus(name=target_name, control_type='Draft' if target_name == 'Draft' else 'Pending')
            db.session.add(status)
            db.session.flush()
        wo.status_id = status.id
        db.session.commit()
        
    if request.method == 'POST':
        # Prevent edits if WO is in terminal state, but allow signature updates
        if wo.current_status and wo.current_status.name in ['Solved', 'Completed', 'Closed', 'Incompleted']:
            if not request.form.get('customer_signature') and not request.form.get('technician_signature') and not request.form.get('customer_name'):
                flash('This Work Order is already solved/completed and cannot be modified.', 'danger')
                return redirect(url_for('work_orders.edit', id=wo.id))
            else:
                # Process only signature fields and return early
                signature_added = False
                if request.form.get('customer_name') is not None:
                    wo.customer_name = request.form.get('customer_name')
                if request.form.get('customer_title') is not None:
                    wo.customer_title = request.form.get('customer_title')
                    
                c_sig = request.form.get('customer_signature')
                if c_sig and c_sig.startswith('data:image'):
                    wo.customer_signature = c_sig
                    signature_added = True
                    
                t_sig = request.form.get('technician_signature')
                if t_sig and t_sig.startswith('data:image'):
                    wo.technician_signature = t_sig
                    signature_added = True
                    
                if signature_added:
                    try:
                        from models import DigitalSignature
                        existing_sig = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
                        if not existing_sig:
                            signer = (wo.customer_name or (current_user.name if current_user.is_authenticated else 'Technician'))
                            title = (wo.customer_title or 'Technician')
                            import uuid, hashlib, time
                            sig_id = str(uuid.uuid4())
                            ts = str(time.time())
                            data_to_hash = f"{wo.code}|{signer}|{ts}"
                            doc_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
                            new_sig = DigitalSignature(
                                id=sig_id, work_order_id=wo.id, signer_name=signer, 
                                signer_title=title, signed_at=datetime.utcnow(), 
                                document_hash=doc_hash, status='Valid'
                            )
                            db.session.add(new_sig)
                    except Exception as sig_err:
                        current_app.logger.warning(f"Could not create DigitalSignature log: {sig_err}")
                        
                db.session.commit()
                flash('Signatures saved successfully.', 'success')
                return redirect(url_for('work_orders.edit', id=wo.id) + '#signature')

        desc = request.form.get('description')
        if desc is not None:
            wo.description = desc
            
        tasklist_note = request.form.get('tasklist_note')
        if tasklist_note is not None:
            wo.tasklist_note = tasklist_note.strip() if tasklist_note else None
            
        prio = request.form.get('priority')
        if prio is not None:
            wo.priority = prio
            
        m_type = request.form.get('maintenance_type')
        if m_type is not None:
            wo.maintenance_type = m_type
            
        team_id = request.form.get('team_id')
        if team_id is not None:
            wo.team_id = team_id or None
        
        new_asset = request.form.get('asset_id')
        if new_asset and (not wo.current_status or wo.current_status.name == 'Draft'):
            wo.asset_id = new_asset
            
        new_tl_id = request.form.get('tasklist_id') or None
        if new_tl_id:
            new_tl_id = int(new_tl_id)
            
        new_cl_id = request.form.get('checklist_id') or None
        if new_cl_id:
            new_cl_id = int(new_cl_id)
            
        # Handle Tasklist Change
        if wo.tasklist_id != new_tl_id:
            wo.tasklist_id = new_tl_id
            for proc in wo.procedures:
                db.session.delete(proc)
            if new_tl_id:
                curr_tl = db.session.get(Tasklist, new_tl_id)
                if curr_tl:
                    for proc in curr_tl.procedures.order_by(TasklistProcedure.position.asc(), TasklistProcedure.id.asc()):
                        new_proc = WorkOrderProcedure(work_order=wo, tasklist_name=curr_tl.name, name=proc.name, requires_attachment=proc.requires_attachment, min_photos=proc.min_photos, estimated_minutes=proc.estimated_minutes)
                        db.session.add(new_proc)
                        
        # Handle Checklist Change
        if wo.checklist_id != new_cl_id:
            wo.checklist_id = new_cl_id
            for chk in wo.checklist_parameters:
                db.session.delete(chk)
            if new_cl_id:
                curr_cl = db.session.get(Checklist, new_cl_id)
                if curr_cl:
                    for param in curr_cl.parameters.order_by(ChecklistParameterTemplate.position.asc(), ChecklistParameterTemplate.id.asc()):
                        new_chk = WorkOrderChecklistParameter(work_order=wo, checklist_name=curr_cl.name, parameter=param.parameter, standard=param.standard)
                        db.session.add(new_chk)
        
        assigned = request.form.getlist('assigned_to')
        if 'assigned_to' in request.form:
            new_assignees = []
            for uid in assigned:
                if uid:
                    u = db.session.get(User, uid)
                    if u:
                        new_assignees.append(u)
            
            # Auto Upgrade Draft to Assigned if assigning a technician
            if new_assignees and wo.current_status and wo.current_status.name == 'Draft':
                assigned = WorkOrderStatus.query.filter(WorkOrderStatus.name.in_(['Assigned', 'Confirmed'])).first()
                if assigned:
                    wo.status_id = assigned.id
                    l = WorkOrderLog(work_order_id=wo.id, user_id=current_user.id, log_text="Status changed to Assigned (Auto-assigned).")
                    db.session.add(l)
                    
            # Auto Downgrade to Draft if unassigning while Assigned
            if not new_assignees and wo.current_status and wo.current_status.name in ['Assigned', 'Confirmed']:
                draft_status = WorkOrderStatus.query.filter_by(name='Draft').first()
                if draft_status:
                    wo.status_id = draft_status.id
                    l = WorkOrderLog(work_order_id=wo.id, user_id=current_user.id, log_text="Status changed to Draft (Unassigned).")
                    db.session.add(l)
                    
            wo.assignees = new_assignees
            
        p_code = request.form.get('project_code')
        user_site_id = getattr(current_user, 'site_id', None)
        if user_site_id:
            user_site = Site.query.get(user_site_id)
            if user_site and user_site.project_code:
                p_code = user_site.project_code
                
        if p_code is not None:
            wo.project_code = p_code or None
        
        from datetime import timedelta
        if 'start_date' in request.form:
            start_date_str = request.form.get('start_date')
            wo.start_date = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if start_date_str else None
            
        if 'end_date' in request.form:
            end_date_str = request.form.get('end_date')
            wo.end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if end_date_str else None
            
        if 'suggested_start_date' in request.form:
            suggested_start_date_str = request.form.get('suggested_start_date')
            wo.suggested_start_date = datetime.strptime(suggested_start_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if suggested_start_date_str else None
            
        if 'suggested_completion_date' in request.form:
            suggested_date_str = request.form.get('suggested_completion_date')
            wo.suggested_completion_date = datetime.strptime(suggested_date_str, '%Y-%m-%dT%H:%M') - timedelta(hours=7) if suggested_date_str else None
        
        if wo.start_date and wo.end_date:
            wo.estimated_hours = round((wo.end_date - wo.start_date).total_seconds() / 3600, 2)
        else:
            wo.estimated_hours = None
            
        # Signatures
        signature_added = False
        if request.form.get('customer_name') is not None:
            wo.customer_name = request.form.get('customer_name')
        if request.form.get('customer_title') is not None:
            wo.customer_title = request.form.get('customer_title')
            
        c_sig = request.form.get('customer_signature')
        if c_sig and c_sig.startswith('data:image'):
            wo.customer_signature = c_sig
            signature_added = True
            
        t_sig = request.form.get('technician_signature')
        if t_sig and t_sig.startswith('data:image'):
            wo.technician_signature = t_sig
            signature_added = True
            
        if signature_added:
            try:
                from models import DigitalSignature
                existing_sig = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
                if not existing_sig:
                    signer = (wo.customer_name or (current_user.name if current_user.is_authenticated else 'Technician'))
                    title = (wo.customer_title or 'Technician')
                    import uuid, hashlib, time
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
            except Exception as sig_err:
                current_app.logger.warning(f"Could not create DigitalSignature log: {sig_err}")
            
        # File Upload Handling
        if 'wo_attachment' in request.files:
            file = request.files['wo_attachment']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                
                # Ensure uploads dir exists
                uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(uploads_dir, exist_ok=True)
                
                # Save file (with auto optimization/compression)
                file_path_sys = os.path.join(uploads_dir, filename)
                save_optimized_image(file, file_path_sys)
                
                # DB relative path for URL generation
                db_path = f'uploads/{filename}'
                
                # Create attachment record
                from models import WorkOrderAttachment
                desc = request.form.get('wo_attachment_description') or request.form.get('description') or request.form.get('note')
                new_att = WorkOrderAttachment(work_order_id=wo.id, file_name=filename, file_path=db_path, description=desc.strip() if desc and desc.strip() else None)
                db.session.add(new_att)
        
        db.session.commit()

        # Auto Sync to Team Schedule
        try:
            from schedule import sync_work_order_to_schedule
            sync_work_order_to_schedule(wo)
        except Exception as e:
            current_app.logger.warning(f"Could not auto-sync WO {wo.code} to schedule: {e}")

        flash('Work Order updated successfully!', 'success')
        return redirect(url_for('work_orders.edit', id=wo.id))
        
    import json
    is_draft = not wo or not wo.current_status or wo.current_status.name == 'Draft'
    user_site_id = getattr(current_user, 'site_id', None)

    # Optimasi Asset: Jika WO bukan Draft, asset sudah terkunci dan tidak bisa diubah di form.
    # Hindari query dan serialisasi JSON 4.400+ asset yang membebani memori dan menambah payload HTML hingga 600KB+.
    if is_draft:
        if user_site_id:
            assets_query = Asset.query.options(db.joinedload(Asset.site)).filter_by(site_id=user_site_id)
        elif wo.project_code:
            assets_query = Asset.query.options(db.joinedload(Asset.site)).filter(
                db.or_(Asset.project_code == wo.project_code, Asset.site.has(project_code=wo.project_code))
            )
        else:
            assets_query = Asset.query.options(db.joinedload(Asset.site))
        assets = assets_query.all()
        assets_json = json.dumps([{'id': a.id, 'name': a.name, 'code': a.code, 'site_name': (a.site.name if a.site else ''), 'project_code': (a.site.project_code if a.site and a.site.project_code else a.project_code)} for a in assets])
    else:
        assets = [wo.asset] if wo.asset else []
        assets_json = '[]'

    # Optimasi User: gunakan joinedload untuk site agar terhindar dari N+1 query
    users_query = User.query.options(db.joinedload(User.site))
    if user_site_id:
        users = users_query.filter(db.or_(User.site_id == user_site_id, User.site_id == None)).all()
        user_site = Site.query.get(user_site_id)
        if user_site and user_site.project_code:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == user_site.project_code, Tasklist.project_code == None, Tasklist.project_code == '')).order_by(Tasklist.name).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == user_site.project_code, Checklist.project_code == None, Checklist.project_code == '')).order_by(Checklist.name).all()
        else:
            tasklists = Tasklist.query.filter(db.or_(Tasklist.project_code == None, Tasklist.project_code == '')).order_by(Tasklist.name).all()
            checklists = Checklist.query.filter(db.or_(Checklist.project_code == None, Checklist.project_code == '')).order_by(Checklist.name).all()
    else:
        users = users_query.all()
        tasklists = Tasklist.query.order_by(Tasklist.name).all()
        checklists = Checklist.query.order_by(Checklist.name).all()
        
    statuses = WorkOrderStatus.query.all()
    for t in tasklists:
        t.project_code_group = t.project_code if t.project_code else ""
    for c in checklists:
        c.project_code_group = c.project_code if c.project_code else ""
    
    tasklists_json = json.dumps([{'id': t.id, 'name': t.name, 'project_code': t.project_code} for t in tasklists])
    checklists_json = json.dumps([{'id': c.id, 'name': c.name, 'project_code': c.project_code} for c in checklists])
    users_json = json.dumps([{'id': u.id, 'name': u.name, 'role': u.role, 'project_code': u.site.project_code if u.site and u.site.project_code else None} for u in users])
    
    if wo.asset and wo.asset.site_id:
        available_stock = StockLevel.query.options(db.joinedload(StockLevel.part)).filter_by(site_id=wo.asset.site_id).all()
        teams = Team.query.filter_by(site_id=wo.asset.site_id).all()
    else:
        available_stock = []
        teams = Team.query.all()
        
    return render_template('work_orders/edit.html', wo=wo, assets=assets, assets_json=assets_json, users=users, users_json=users_json, teams=teams, available_stock=available_stock, statuses=statuses, project_codes=get_all_project_codes(), tasklists=tasklists, tasklists_json=tasklists_json, checklists=checklists, checklists_json=checklists_json)


@work_orders_bp.route('/<int:id>/export_pdf', methods=['GET'])
@login_required
def export_pdf(id):
    import os
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        flash('Access denied.', 'danger')
        return redirect(url_for('work_orders.index'))
        
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # --- 0. COVER PAGE ---
    pdf.add_page()
    
    # Background Image
    title_image_path = os.path.join(current_app.root_path, 'static', 'images', 'judul.png')
    if os.path.exists(title_image_path):
        pdf.image(title_image_path, x=0, y=0, w=pdf.w, h=pdf.h)
    
    # Get Site Name and Period
    site_name = wo.asset.site.name if wo.asset and wo.asset.site else "Unknown Site"
    wo_date = wo.suggested_start_date or wo.start_date or datetime.now()
    month_map = {
        1: "JANUARI", 2: "FEBRUARI", 3: "MARET", 4: "APRIL", 5: "MEI", 6: "JUNI",
        7: "JULI", 8: "AGUSTUS", 9: "SEPTEMBER", 10: "OKTOBER", 11: "NOVEMBER", 12: "DESEMBER"
    }
    periode_str = f"{month_map.get(wo_date.month, '')} {wo_date.year}"
    
    mt_type = wo.maintenance_type.upper() if wo.maintenance_type else ""
    if "MAINTENANCE" not in mt_type:
        mt_type += " MAINTENANCE"
    
    line1 = f"LAPORAN WORK ORDER"
    line1_sub = mt_type
    line2 = f"{site_name.upper()}"
    line3 = f"{wo.asset.name.upper() if wo.asset else ''}"
    line4 = f"{wo.code}"
    
    # Positioning text at bottom left
    pdf.set_y(-105) # Moved slightly up to accommodate extra line
    pdf.set_left_margin(20)
    
    pdf.set_font('helvetica', 'B', 24) # Reduced size slightly for line1
    pdf.cell(0, 12, line1, 0, 1, 'L')
    pdf.set_font('helvetica', 'B', 24)
    pdf.cell(0, 12, line1_sub, 0, 1, 'L')
    
    pdf.set_font('helvetica', 'B', 18) # Reduced size for others
    pdf.cell(0, 10, line2, 0, 1, 'L')
    
    pdf.set_font('helvetica', 'B', 18)
    pdf.cell(0, 10, line3, 0, 1, 'L')
    
    pdf.set_font('helvetica', 'B', 18)
    pdf.cell(0, 10, line4, 0, 1, 'L')
    
    # Reset for main report
    pdf.set_left_margin(10)
    
    # --- CHILLER DETAILS PAGE (If asset is Chiller) ---
    from utils import get_wo_chiller_details
    chiller_info = get_wo_chiller_details(wo.asset)
    if chiller_info:
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, f"Laporan Chiller - {chiller_info['site_name']}", 0, 1, 'C')
        pdf.cell(0, 10, f"Chiller: {chiller_info['chiller_num']}", 0, 1, 'C')
        pdf.ln(10)

        # Determine chiller image based on category or image_filename
        image_filename = chiller_info.get('image_filename') or 'chiller.png'
        image_path = os.path.join(current_app.root_path, 'static', 'images', image_filename)
        if not os.path.exists(image_path):
            image_path = os.path.join(current_app.root_path, 'static', 'images', 'chiller.png')

        if os.path.exists(image_path):
            image_width = 150
            page_width = pdf.w - pdf.l_margin - pdf.r_margin
            x_centered = pdf.l_margin + (page_width - image_width) / 2
            pdf.image(image_path, x=x_centered, y=pdf.get_y(), w=image_width)
            pdf.ln(85)

        pdf.set_font('helvetica', 'B', 12)
        pdf.cell(0, 10, 'Chiller Details', 0, 1, 'C')
        pdf.ln(5)
        pdf.set_font('helvetica', '', 10)
        table_width = 150
        col_width_key = 60
        col_width_value = 90
        start_x = (pdf.w - table_width) / 2

        for key, value in chiller_info['details_to_show'].items():
            if value is not None and str(value).strip():
                pdf.set_x(start_x)
                pdf.cell(col_width_key, 10, f'{key}:', 1, 0)
                pdf.cell(col_width_value, 10, str(value), 1, 1)
        pdf.ln(10)

    pdf.add_page()
    # --- END COVER PAGE ---
    
    try:
        from datetime import datetime, timezone, timedelta
        pdf.set_font("helvetica", style="B", size=10)
    except:
        pdf.set_font("Arial", style="B", size=10)
        
    start_x = pdf.get_x()
    start_y = pdf.get_y()
    
    # 1. NEW HEADER
    pdf.cell(35, 24, "", border=1) # Logo area box
    
    logo_path = os.path.join(current_app.root_path, 'static', 'images', 'Logo Jaya Teknik.png')
    if os.path.exists(logo_path):
        try:
            pdf.image(logo_path, x=start_x + 2, y=start_y + 2, w=31)
        except:
            pass
    
    # Title
    pdf.set_font("helvetica", style="B", size=14)
    pdf.set_xy(start_x + 35, start_y)
    pdf.cell(105, 24, "", border=1)
   
    pdf.set_xy(start_x + 35, start_y + 12)
    pdf.cell(105, 8, "REPORT WORK ORDER", align="C")
    
    # Info box right
    pdf.set_font("helvetica", size=8)
    pdf.set_xy(start_x + 140, start_y)
    pdf.cell(20, 6, "No.Dok", border=1)
    pdf.cell(30, 6, "RP - JT - 26", border=1)
    
    pdf.set_xy(start_x + 140, start_y + 6)
    pdf.cell(20, 6, "Ref.", border=1)
    pdf.cell(30, 6, "7; 7.1.3 & 7.1.4", border=1)
    
    pdf.set_xy(start_x + 140, start_y + 12)
    pdf.cell(20, 6, "Rev.", border=1)
    pdf.cell(30, 6, "Original", border=1)
    
    pdf.set_xy(start_x + 140, start_y + 18)
    pdf.cell(20, 6, "Tanggal", border=1)
    printed_date = datetime.now().strftime("%d %b %Y")
    pdf.cell(30, 6, printed_date, border=1)
    
    # Details Body
    pdf.set_xy(start_x, start_y + 24)
    pdf.set_font("helvetica", size=9)
    pdf.cell(190, 24, "", border=1)
    pdf.set_xy(start_x, start_y + 24)
    
    def fmt_dt(dt, convert=True):
        from datetime import timedelta
        if dt:
            if convert:
                dt_wib = dt + timedelta(hours=7)
                return dt_wib.strftime('%d-%m-%Y %H:%M')
            return dt.strftime('%d-%m-%Y %H:%M')
        return '-'
        
    form_val = getattr(wo, 'maintenance_type', 'SERVICE')
    nomor_val = wo.code or '-'
    asset_val = f"{wo.asset.name} ({wo.asset.code})" if wo.asset else '-'
    tech_val = ", ".join([a.name for a in wo.assignees]) if getattr(wo, 'assignees', None) else "N/A"
    
    # Responsible is the user who changed the status to Completed
    completed_by_user = None
    try:
        logs = wo.logs.all() if hasattr(wo.logs, 'all') else list(wo.logs)
        for log in logs:
            if log.log_text and "status changed to completed" in log.log_text.lower():
                if log.user and log.user.name:
                    completed_by_user = log.user.name
                    break
    except Exception as e:
        print(f"Error fetching completed_by from logs: {e}")

    resp_val = completed_by_user or tech_val
    
    proj_val = (wo.asset.project_code if wo.asset and wo.asset.project_code else wo.project_code) or '-'
    
    loc_val = '-'
    if wo.asset and hasattr(wo.asset, 'location') and wo.asset.location:
        loc_val = wo.asset.location.name if hasattr(wo.asset.location, 'name') else str(wo.asset.location)
    
    sched_val = f"{fmt_dt(wo.suggested_start_date)} s/d {fmt_dt(wo.suggested_completion_date)}"
    act_val = f"{fmt_dt(wo.start_date)} s/d {fmt_dt(wo.end_date)}"
    
    # Line 1
    pdf.cell(20, 6, "Form", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(form_val)[:35], border=0)
    pdf.cell(20, 6, "Project", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(proj_val)[:35], border=0, ln=1)
    
    # Line 2
    pdf.cell(20, 6, "Nomor", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(nomor_val)[:35], border=0)
    pdf.cell(20, 6, "Location", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(loc_val)[:35], border=0, ln=1)
    
    # Line 3
    pdf.cell(20, 6, "Asset", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(asset_val)[:35], border=0)
    pdf.cell(20, 6, "Schedule", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(sched_val)[:40], border=0, ln=1)
    
    # Line 4
    pdf.cell(20, 6, "Responsible", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(resp_val)[:35], border=0)
    pdf.cell(20, 6, "Actual Date", border=0)
    pdf.cell(5, 6, ":", border=0)
    pdf.cell(70, 6, str(act_val)[:40], border=0, ln=1)
    
    pdf.ln(5)
    
    # 1.5 TECHNICIAN (Restored)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("helvetica", style="B", size=10)
    pdf.cell(190, 6, "TECHNICIAN", border=1, align="C", fill=True, ln=1)
    pdf.cell(190, 6, "Name", border=1, align="C", fill=True, ln=1)
    pdf.set_font("helvetica", size=9)
    tech_str = str(tech_val) if tech_val else "N/A"
    lines_tech = calc_num_lines(pdf, tech_str, 190)
    pdf.multi_cell(190, 5, tech_str, border=1, align="L")
    pdf.ln(5)
    
    # 2. CHECKING REPORT
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("helvetica", style="B", size=10)
    pdf.cell(190, 6, "CHECKING REPORT", border=1, align="C", fill=True, ln=1)
    
    def print_checking_header():
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("helvetica", style="B", size=8)
        pdf.cell(75, 8, "Description (Unit Check)", border=1, align="C", fill=True)
        pdf.cell(25, 8, "Standard", border=1, align="C", fill=True)
        pdf.cell(25, 8, "Actual", border=1, align="C", fill=True)
        pdf.cell(25, 8, "Check", border=1, align="C", fill=True)
        pdf.cell(40, 8, "Note", border=1, align="C", fill=True, ln=1)
        pdf.set_font("helvetica", size=8)

    print_checking_header()
    line_h = 4.5
    for param in wo.checklist_parameters:
        desc = str(param.parameter or "")
        std_val = str(param.standard) if (param.standard is not None and str(param.standard).strip() != "") else "-"
        actual_val = str(param.value) if (param.value is not None and str(param.value).strip() != "") else "-"
        check_val = "OK" if (actual_val != "-" and str(actual_val).strip() != "") else "-"
        note_val = str(param.note or "")
        
        lines_desc = calc_num_lines(pdf, desc, 75)
        lines_std = calc_num_lines(pdf, std_val, 25)
        lines_act = calc_num_lines(pdf, actual_val, 25)
        lines_note = calc_num_lines(pdf, note_val, 40)
        
        max_lines = max(lines_desc, lines_std, lines_act, lines_note, 1)
        row_height = max(6.0, max_lines * line_h + 1.5)
        
        if pdf.get_y() + row_height > 275:
            pdf.add_page()
            print_checking_header()
            
        x = 10
        y = pdf.get_y()
        
        # Draw outer borders for each cell in the row
        pdf.rect(x, y, 75, row_height)
        pdf.rect(x + 75, y, 25, row_height)
        pdf.rect(x + 100, y, 25, row_height)
        pdf.rect(x + 125, y, 25, row_height)
        pdf.rect(x + 150, y, 40, row_height)
        
        # Description
        y_off_desc = y + (row_height - (lines_desc * line_h)) / 2
        pdf.set_xy(x + 1.5, y_off_desc)
        pdf.multi_cell(72, line_h, desc, border=0, align="L")
        
        # Standard
        y_off_std = y + (row_height - (lines_std * line_h)) / 2
        pdf.set_xy(x + 75 + 1, y_off_std)
        pdf.multi_cell(23, line_h, std_val, border=0, align="C")
        
        # Actual
        y_off_act = y + (row_height - (lines_act * line_h)) / 2
        pdf.set_xy(x + 100 + 1, y_off_act)
        pdf.multi_cell(23, line_h, actual_val, border=0, align="C")
        
        # Check
        pdf.set_xy(x + 125, y)
        pdf.cell(25, row_height, check_val, border=0, align="C")
        
        # Note
        y_off_note = y + (row_height - (lines_note * line_h)) / 2
        pdf.set_xy(x + 150 + 1.5, y_off_note)
        pdf.multi_cell(37, line_h, note_val, border=0, align="L")
        
        # Advance cursor to bottom of current row
        pdf.set_xy(x, y + row_height)
    
    pdf.ln(5)
    
    # 3. TASKLIST REPORT
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("helvetica", style="B", size=10)
    pdf.cell(190, 6, "TASKLIST REPORT", border=1, align="C", fill=True, ln=1)
    
    def print_tasklist_header():
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("helvetica", style="B", size=8)
        pdf.cell(70, 8, "Step Name", border=1, align="C", fill=True)
        pdf.cell(90, 8, "Description", border=1, align="C", fill=True)
        pdf.cell(30, 8, "State", border=1, align="C", fill=True, ln=1)
        pdf.set_font("helvetica", size=8)

    print_tasklist_header()
    for proc in wo.procedures:
        step_name = proc.name or ''
        desc = proc.notes or getattr(proc, 'description', '') or ''
        
        lines_step = calc_num_lines(pdf, step_name, 70)
        lines_desc = calc_num_lines(pdf, desc, 90)
        
        max_lines = max(lines_step, lines_desc, 1)
        row_height = max(6.0, max_lines * 5.0 + 1.5)
        
        # Check page break
        if pdf.get_y() + row_height > 275:
            pdf.add_page()
            print_tasklist_header()
            
        x_start = 10
        y_start = pdf.get_y()
        
        # Draw borders for the row
        pdf.rect(x_start, y_start, 70, row_height)
        pdf.rect(x_start + 70, y_start, 90, row_height)
        pdf.rect(x_start + 160, y_start, 30, row_height)
        
        # Print Step Name
        y_off_step = y_start + (row_height - (lines_step * 5.0)) / 2
        pdf.set_xy(x_start + 1.5, y_off_step)
        pdf.multi_cell(67, 5.0, step_name, border=0)
        
        # Print Description
        y_off_desc = y_start + (row_height - (lines_desc * 5.0)) / 2
        pdf.set_xy(x_start + 70 + 1.5, y_off_desc)
        pdf.multi_cell(87, 5.0, desc, border=0)
        
        # Print State
        pdf.set_xy(x_start + 160, y_start)
        pdf.cell(30, row_height, "Done" if getattr(proc, 'is_completed', False) else "Pending", border=0, align="C")
        
        pdf.set_xy(x_start, y_start + row_height)
        
    pdf.ln(3)
    
    # 3.5 NOTE (Tasklist Global Note)
    note_txt = (getattr(wo, 'tasklist_note', None) or '').strip()
    if note_txt:
        lines_note = max(1, int(pdf.get_string_width(note_txt) / 184) + 1) + note_txt.count('\n')
        note_box_h = max(18.0, lines_note * 4.5 + 6.0)
    else:
        note_box_h = 18.0

    if pdf.get_y() + 6.0 + note_box_h > 275:
        pdf.add_page()

    pdf.set_font("helvetica", style="B", size=9)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(190, 6, "NOTE", border=1, align="C", fill=True, ln=1)

    y_n = pdf.get_y()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.3)
    pdf.rect(10, y_n, 190, note_box_h)

    pdf.set_xy(12, y_n + 2)
    pdf.set_font("helvetica", size=8.5)
    if note_txt:
        pdf.multi_cell(186, 4.5, note_txt)
    else:
        pdf.cell(186, 5, "-", ln=1)

    pdf.set_xy(10, y_n + note_box_h + 3)

    pdf.ln(3)

    # 3.6 SIGNATURES
    pdf.ln(2)
    
    first_tech = wo.assignees[0] if getattr(wo, 'assignees', []) else None
    tech_name = first_tech.name if first_tech else "....."
    tech_role = first_tech.role if first_tech else "....."
    site_name = wo.asset.site.name.upper() if wo.asset and getattr(wo.asset, 'site', None) else "....."
    
    if pdf.get_y() > 240:
        pdf.add_page()
        
    sig_y = pdf.get_y()
    
    # Helper to decode signature
    import tempfile
    import base64
    def save_temp_image(b64_str):
        if not b64_str or ',' not in b64_str: return None
        try:
            _, encoded = b64_str.split(",", 1)
            data = base64.b64decode(encoded)
            fd, temp_path = tempfile.mkstemp(suffix='.png')
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            return temp_path
        except:
            return None

    c_name_print = getattr(wo, 'customer_name', None) or "....."
    c_title_print = getattr(wo, 'customer_title', None) or "....."

    # Fetch Digital Signature first
    from models import DigitalSignature
    ds = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
    
    # Left Column (Pihak Pertama)
    pdf.set_xy(15, sig_y)
    pdf.set_font("helvetica", style="B", size=9)
    pdf.cell(90, 5, "PIHAK PERTAMA,", ln=1)
    pdf.set_x(15)
    pdf.cell(90, 5, site_name, ln=1)
    
    if not ds:
        c_img_path = save_temp_image(getattr(wo, 'customer_signature', None))
        if c_img_path:
            try:
                pdf.image(c_img_path, x=15, y=sig_y + 12, h=16)
                os.remove(c_img_path)
            except: pass

    pdf.set_xy(15, sig_y + 35)
    pdf.set_font("helvetica", size=9)
    pdf.cell(90, 5, f"Nama : {c_name_print}", ln=1)
    pdf.set_x(15)
    pdf.cell(90, 5, f"Jabatan : {c_title_print}", ln=1)
    
    # Right Column (Pihak Kedua)
    pdf.set_xy(110, sig_y)
    pdf.set_font("helvetica", style="B", size=9)
    pdf.cell(85, 5, "PIHAK KEDUA,", ln=1)
    pdf.set_x(110)
    pdf.cell(85, 5, "PT JAYA TEKNIK INDONESIA", ln=1)
    
    if not ds:
        t_img_path = save_temp_image(getattr(wo, 'technician_signature', None))
        if t_img_path:
            try:
                pdf.image(t_img_path, x=110, y=sig_y + 12, h=16)
                os.remove(t_img_path)
            except: pass

    pdf.set_xy(110, sig_y + 35)
    pdf.set_font("helvetica", size=9)
    pdf.cell(85, 5, f"Nama : {tech_name}", ln=1)
    pdf.set_x(110)
    pdf.cell(85, 5, f"Jabatan : {tech_role}", ln=1)
    
    # Center Column (Digital Signature QR)
    if ds:
        import qrcode
        import tempfile
        from flask import request
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=1,
        )
        verify_url = f"{request.url_root.rstrip('/')}/verify/doc?id={ds.id}"
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        fd, temp_path = tempfile.mkstemp(suffix='.png')
        with os.fdopen(fd, 'wb') as f:
            img.save(f)
            
        pdf.image(temp_path, x=135, y=sig_y + 10, h=18)
        os.remove(temp_path)
        
        pdf.set_xy(125, sig_y + 29)
        pdf.set_font("helvetica", size=6, style="B")
        pdf.set_text_color(0, 150, 0) # Green text for verification
        pdf.cell(38, 3, "DIGITALLY SIGNED", ln=1, align="C")
        pdf.set_xy(125, sig_y + 32)
        pdf.cell(38, 3, "& VERIFIED", ln=1, align="C")
        pdf.set_text_color(0, 0, 0)
    
    pdf.set_y(sig_y + 45)
       # 4. PHOTOS / LAMPIRAN
    def _resolve_img_path(raw_p):
        if not raw_p:
            return None
        clean = raw_p.replace('\\', '/').strip()
        candidates = [
            os.path.join(current_app.root_path, 'static', clean),
            os.path.join(current_app.root_path, clean),
            clean
        ]
        if clean.startswith('uploads/') or clean.startswith('static/'):
            sub = clean.split('/', 1)[1]
            candidates.append(os.path.join(current_app.root_path, 'static', sub))
            candidates.append(os.path.join(current_app.root_path, sub))
        for c in candidates:
            if os.path.exists(c) and os.path.isfile(c):
                return c
        return None

    photo_groups = []
    # 4.1 Collect photos from procedures
    procedures_list = wo.procedures.all() if hasattr(wo.procedures, 'all') else list(wo.procedures)
    for proc in procedures_list:
        if getattr(proc, 'attachment_path', None):
            paths = [p.strip() for p in proc.attachment_path.split('|') if p.strip()]
            valid_paths = []
            for p in paths:
                resolved = _resolve_img_path(p)
                if resolved:
                    valid_paths.append(resolved)
            if valid_paths:
                title = proc.name.strip() if proc.name else 'Prosedur'
                if not title.lower().startswith("lampiran"):
                    title = f"Lampiran {title}"
                photo_groups.append({'title': title, 'paths': valid_paths})

    # 4.2 Collect photos from general attachments
    attachments_list = wo.attachments.all() if hasattr(wo.attachments, 'all') else list(wo.attachments)
    for att in attachments_list:
        if getattr(att, 'file_path', None):
            resolved = _resolve_img_path(att.file_path)
            if resolved and resolved.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                title = att.description.strip() if att.description and att.description.strip() else (att.file_name or 'Berkas')
                if not title.lower().startswith("lampiran"):
                    title = f"Lampiran {title}"
                if photo_groups and photo_groups[-1]['title'] == title:
                    photo_groups[-1]['paths'].append(resolved)
                else:
                    photo_groups.append({'title': title, 'paths': [resolved]})

    if photo_groups:
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        
        PAGE_BOTTOM_LIMIT = 282
        y_cursor = 10
        img_w = 48
        img_h = 52
        gap_x = 11.5
        gap_y = 6.0

        def _draw_photo_box(p_path, px, py, pw, ph):
            rendered = False
            try:
                from PIL import Image as PILImage, ImageOps
                with PILImage.open(p_path) as im:
                    im = ImageOps.exif_transpose(im)
                    w, h = im.size
                    target_aspect = pw / ph
                    aspect = w / h
                    if aspect > target_aspect:
                        new_w = int(h * target_aspect)
                        left = (w - new_w) // 2
                        im = im.crop((left, 0, left + new_w, h))
                    else:
                        new_h = int(w / target_aspect)
                        top = (h - new_h) // 2
                        im = im.crop((0, top, w, top + new_h))
                    im = im.resize((480, int(480 / target_aspect)))
                    
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    if im.mode != 'RGB':
                        im = im.convert('RGB')
                    im.save(tmp.name, 'JPEG', quality=85)
                    tmp.close()
                    
                    pdf.image(tmp.name, x=px, y=py, w=pw, h=ph)
                    os.unlink(tmp.name)
                    
                    pdf.set_draw_color(220, 220, 220)
                    pdf.rect(px, py, pw, ph)
                    pdf.set_draw_color(0, 0, 0)
                    rendered = True
            except Exception as e:
                print(f"Error processing image {p_path}: {e}")
                
            if not rendered:
                pdf.set_fill_color(240, 240, 240)
                pdf.set_draw_color(200, 200, 200)
                pdf.rect(px, py, pw, ph, style='FD')
                pdf.set_font('helvetica', 'I', 7)
                pdf.set_text_color(150, 150, 150)
                pdf.set_xy(px, py + ph / 2 - 2)
                pdf.cell(pw, 4, "[Foto]", align='C')
                pdf.set_text_color(0, 0, 0)
                pdf.set_draw_color(0, 0, 0)

        def _calc_title_lines(txt, max_w):
            words = txt.split(' ')
            lines = 1
            cur_line = ''
            for w in words:
                test_line = cur_line + (' ' if cur_line else '') + w
                if pdf.get_string_width(test_line) <= max_w:
                    cur_line = test_line
                else:
                    lines += 1
                    cur_line = w
            return max(1, lines)

        # Batch consecutive single-photo groups into rows of up to 3 columns
        render_blocks = []
        current_single_batch = []
        for grp in photo_groups:
            if len(grp.get('paths', [])) == 1:
                current_single_batch.append(grp)
                if len(current_single_batch) == 3:
                    render_blocks.append({'type': 'single_row', 'items': current_single_batch})
                    current_single_batch = []
            else:
                if current_single_batch:
                    render_blocks.append({'type': 'single_row', 'items': current_single_batch})
                    current_single_batch = []
                render_blocks.append({'type': 'multi_section', 'grp': grp})
        if current_single_batch:
            render_blocks.append({'type': 'single_row', 'items': current_single_batch})

        for block in render_blocks:
            if block['type'] == 'single_row':
                items = block['items']
                n_items = len(items)
                col_w = 190.0 / n_items
                title_font_size = 8.0 if n_items == 3 else 9.0
                pdf.set_font('helvetica', 'B', title_font_size)
                
                max_title_lines = 1
                for item in items:
                    lines = _calc_title_lines(item['title'], col_w - 6)
                    if lines > max_title_lines:
                        max_title_lines = lines
                
                title_text_h = max_title_lines * 4.0
                padding_top = 3.5
                padding_mid = 3.0
                padding_bottom = 4.0
                row_h = padding_top + title_text_h + padding_mid + img_h + padding_bottom
                
                avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                if avail_h < row_h:
                    pdf.add_page()
                    y_cursor = 10
                    avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                
                for i, item in enumerate(items):
                    col_x = 10.0 + i * col_w
                    cur_col_w = col_w if i < n_items - 1 else (200.0 - col_x)
                    
                    # 1. Outer box for this column
                    pdf.set_draw_color(0, 0, 0)
                    pdf.set_line_width(0.3)
                    pdf.rect(col_x, y_cursor, cur_col_w, row_h)
                    
                    # 2. Section Header Title (Centered)
                    pdf.set_font('helvetica', 'B', title_font_size)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_xy(col_x + 2, y_cursor + padding_top)
                    pdf.multi_cell(cur_col_w - 4, 4.0, item['title'], align='C')
                    
                    # 3. Photo
                    photo_x = col_x + (cur_col_w - img_w) / 2
                    photo_y = y_cursor + padding_top + title_text_h + padding_mid
                    _draw_photo_box(item['paths'][0], photo_x, photo_y, img_w, img_h)
                    
                y_cursor += row_h
                pdf.set_xy(10, y_cursor)
            else:
                grp = block['grp']
                group_title = grp['title']
                all_paths = list(grp['paths'])
                is_cont = False
                
                while all_paths:
                    avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                    pdf.set_font('helvetica', 'B', 10)
                    curr_title = group_title if not is_cont else f"{group_title} (Lanjutan)"
                    title_lines = max(1, int(pdf.get_string_width(curr_title) / 180) + 1)
                    title_text_h = title_lines * 4.5
                    title_total_h = 3.5 + title_text_h + 3.5
                    padding_bottom = 5.0
                    
                    min_sec_h = title_total_h + img_h + padding_bottom
                    if avail_h < min_sec_h:
                        pdf.add_page()
                        y_cursor = 10
                        avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                        
                    avail_for_rows = avail_h - title_total_h - padding_bottom
                    max_rows = max(1, int((avail_for_rows + gap_y) // (img_h + gap_y)))
                    max_photos = max_rows * 3
                    
                    chunk = all_paths[:max_photos]
                    all_paths = all_paths[max_photos:]
                    
                    n_photos = len(chunk)
                    n_rows = (n_photos + 2) // 3
                    photos_total_h = n_rows * img_h + (n_rows - 1) * gap_y
                    section_h = title_total_h + photos_total_h + padding_bottom
                    
                    # 1. Section Outer Box
                    pdf.set_draw_color(0, 0, 0)
                    pdf.set_line_width(0.3)
                    pdf.rect(10, y_cursor, 190, section_h)
                    
                    # 2. Section Header Title (Centered)
                    pdf.set_font('helvetica', 'B', 10)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_xy(10, y_cursor + 3.5)
                    pdf.multi_cell(190, 4.5, curr_title, align='C')
                    
                    # 3. Grid of Photos
                    y_photo_start = y_cursor + title_total_h
                    for r in range(n_rows):
                        row_paths = chunk[r*3 : (r+1)*3]
                        n_in_row = len(row_paths)
                        y_row = y_photo_start + r * (img_h + gap_y)
                        
                        if n_in_row == 3:
                            x_positions = [10 + gap_x + i * (img_w + gap_x) for i in range(3)]
                        elif n_in_row == 2:
                            row_w = 2 * img_w + gap_x
                            start_x = 10 + (190 - row_w) / 2
                            x_positions = [start_x, start_x + img_w + gap_x]
                        else: # 1
                            x_positions = [10 + (190 - img_w) / 2]
                            
                        for c, p in enumerate(row_paths):
                            _draw_photo_box(p, x_positions[c], y_row, img_w, img_h)
                                
                    y_cursor += section_h
                    pdf.set_xy(10, y_cursor)
                    is_cont = True
    
    try:
        out = pdf.output(dest='S')
    except TypeError:
        out = pdf.output()
    pdf_out = out.encode('latin-1') if isinstance(out, str) else bytes(out)
    
    if ds and not ds.pdf_path:
        sig_dir = os.path.join(current_app.root_path, 'static', 'signatures')
        os.makedirs(sig_dir, exist_ok=True)
        pdf_filename = f"signed_{wo.code}_{ds.id[:8]}.pdf".replace('/', '_')
        pdf_filepath = os.path.join(sig_dir, pdf_filename)
        with open(pdf_filepath, 'wb') as f:
            f.write(pdf_out)
        ds.pdf_path = f"signatures/{pdf_filename}"
        db.session.commit()

    return Response(pdf_out, mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename="Report_WO_{wo.code}.pdf"'})

@work_orders_bp.route('/<int:id>/export_ppt', methods=['GET'])
@login_required
def export_ppt(id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        flash('Access denied.', 'danger')
        return redirect(url_for('work_orders.index'))
    
    from work_order_ppt import generate_work_order_ppt
    ppt_io, filename = generate_work_order_ppt(wo, current_app=current_app, request=request)
    
    return send_file(
        ppt_io,
        mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        as_attachment=True,
        download_name=filename
    )

@work_orders_bp.route('/<int:id>/status', methods=['POST'])
@login_required
def change_status(id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        flash('Access denied.', 'danger')
        return redirect(url_for('work_orders.index'))
        
    action = request.form.get('action') # 'start', 'hold', 'resume', 'solve', 'incomplete', 'complete', 'approve'
    reason = request.form.get('reason') # for hold or incomplete
    
    # Check permissions logic
    from flask import abort
    if current_user.role not in ['Admin', 'Supervisor'] and action in ['incomplete', 'complete', 'approve']:
        abort(403)
        
    action_map = {
        'start': 'In Progress',
        'hold': 'Hold',
        'resume': 'In Progress',
        'solve': 'Solved',
        'incomplete': 'Incompleted',
        'complete': 'Completed',
        'approve': 'Completed',
        'cancel_to_draft': 'Draft'
    }
    
    target_status_name = action_map.get(action)
    if not target_status_name:
        flash('Invalid status action.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id))
        
    target_status = WorkOrderStatus.query.filter_by(name=target_status_name).first()
    if not target_status:
        ctrl = 'Closed' if target_status_name in ['Completed', 'Solved', 'Closed'] else ('Draft' if target_status_name == 'Draft' else 'Active')
        target_status = WorkOrderStatus(name=target_status_name, control_type=ctrl)
        db.session.add(target_status)
        db.session.flush()

    if target_status:
        wo.status_id = target_status.id
        
        # Start Progress Logic -> Populate start_date, Clear end_date
        if action in ['start', 'resume']:
            if action == 'start' and not wo.start_date:
                wo.start_date = datetime.now(timezone.utc).replace(tzinfo=None)
            wo.end_date = None
            wo.estimated_hours = None
            
        # Complete / Solve Logic -> Populate end_date and Verify
        if action in ['solve', 'complete', 'approve']:
            # Validation: Tasklist Procedures and Checklists
            incomplete_procs = []
            for proc in wo.procedures:
                num_photos = 0
                if proc.attachment_path:
                    num_photos = len([p for p in proc.attachment_path.split('|') if p])
                
                if not proc.is_completed:
                    incomplete_procs.append(proc.name)
                elif proc.requires_attachment and not proc.attachment_path:
                    incomplete_procs.append(f"{proc.name} (Missing Photo)")
                elif proc.min_photos > 0 and num_photos < proc.min_photos:
                    incomplete_procs.append(f"{proc.name} (Photos: {num_photos}/{proc.min_photos})")
                    
            if incomplete_procs:    
                flash(f'Cannot {action}: Incomplete procedures or missing photos: {", ".join(incomplete_procs)}', 'danger')
                return redirect(url_for('work_orders.edit', id=wo.id))
                
            missing_chks = [c.parameter for c in wo.checklist_parameters if not c.value]
            if missing_chks:
                flash(f'Cannot {action}: Missing values for checklist parameters: {", ".join(missing_chks)}', 'danger')
                return redirect(url_for('work_orders.edit', id=wo.id))
            
            if not wo.start_date:
                wo.start_date = wo.created_at or datetime.now(timezone.utc).replace(tzinfo=None)
            wo.end_date = datetime.now(timezone.utc).replace(tzinfo=None)
                
            if wo.start_date and wo.end_date:
                wo.estimated_hours = round((wo.end_date - wo.start_date).total_seconds() / 3600, 2)
                
            # Digital Signature Logic
            from models import DigitalSignature
            if getattr(wo, 'customer_signature', None) or getattr(wo, 'technician_signature', None):
                # Check if already has signature
                existing_sig = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
                if not existing_sig:
                    import uuid
                    import hashlib
                    import time
                    
                    signer = (wo.customer_name or current_user.name)
                    title = (wo.customer_title or 'Technician')
                    
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
            
        # Log Status Change
        log_title = f"Status changed to {target_status_name}"
        if reason:
            log_title += f". Reason: {reason}"
            
        l = WorkOrderLog(work_order_id=wo.id, user_id=current_user.id, log_text=log_title)
        db.session.add(l)
            
        db.session.commit()
        flash(f'Work order status changed to {target_status_name}.', 'success')
        
    return redirect(url_for('work_orders.edit', id=wo.id))

@work_orders_bp.route('/<int:id>/add_part', methods=['POST'])
@login_required
def add_part(id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    if wo.current_status and wo.current_status.name in ['Solved', 'Completed', 'Closed', 'Incompleted']:
        flash('Cannot add parts to a Work Order that is already solved or completed.', 'warning')
        return redirect(url_for('work_orders.edit', id=wo.id))
        
    part_id = request.form.get('part_id')
    qty = float(request.form.get('qty', 1))
    
    if not part_id or qty <= 0:
        flash('Invalid part or quantity.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id))
        
    # Verify stock availability at the site
    stock = StockLevel.query.filter_by(part_id=part_id, site_id=wo.asset.site_id).first()
    if not stock or stock.qty_on_hand < qty:
        flash('Insufficient stock available at this site.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id))
        
    # Deduct stock
    qty_before = stock.qty_on_hand
    stock.qty_on_hand -= qty
    qty_after = stock.qty_on_hand
    
    # Log Transaction
    from models import StockTransaction
    from datetime import datetime
    tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    transaction = StockTransaction(
        transaction_code=tx_code,
        part_id=part_id,
        site_id=wo.asset.site_id,
        user_id=current_user.id,
        action='WORK ORDER',
        qty_before=qty_before,
        qty_after=qty_after,
        qty_change=-qty,
        notes=f"Used in WO: {wo.ticket_code}"
    )
    db.session.add(transaction)
    
    # Check if part already exists in this WO
    wo_part = WorkOrderPart.query.filter_by(work_order_id=wo.id, part_id=part_id).first()
    if wo_part:
        wo_part.quantity_used += qty
    else:
        wo_part = WorkOrderPart(work_order_id=wo.id, part_id=part_id, quantity_used=qty)
        db.session.add(wo_part)
        
    db.session.commit()
    flash(f'{qty} units of part added successfully. Stock deducted.', 'success')
    return redirect(url_for('work_orders.edit', id=wo.id))

@work_orders_bp.route('/<int:id>/remove_part/<int:part_id>', methods=['POST'])
@login_required
def remove_part(id, part_id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    wo_part = WorkOrderPart.query.filter_by(work_order_id=wo.id, part_id=part_id).first_or_404()
    
    if wo.current_status and wo.current_status.name in ['Solved', 'Completed', 'Closed', 'Incompleted']:
        flash('Cannot remove parts from a Work Order that is already solved or completed.', 'warning')
        return redirect(url_for('work_orders.edit', id=wo.id))
    
    # Restore stock
    stock = StockLevel.query.filter_by(part_id=part_id, site_id=wo.asset.site_id).first()
    qty_before = 0
    if stock:
        qty_before = stock.qty_on_hand
        stock.qty_on_hand += wo_part.quantity_used
    else:
        # If stock level entry was deleted somehow, recreate it
        stock = StockLevel(part_id=part_id, site_id=wo.asset.site_id, qty_on_hand=wo_part.quantity_used)
        db.session.add(stock)
        
    qty_after = stock.qty_on_hand
    
    # Log Transaction
    from models import StockTransaction
    from datetime import datetime
    tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    transaction = StockTransaction(
        transaction_code=tx_code,
        part_id=part_id,
        site_id=wo.asset.site_id,
        user_id=current_user.id,
        action='RETURN',
        qty_before=qty_before,
        qty_after=qty_after,
        qty_change=wo_part.quantity_used,
        notes=f"Returned from WO: {wo.ticket_code}"
    )
    db.session.add(transaction)
        
    db.session.delete(wo_part)
    db.session.commit()
    
    flash('Part removed from Work Order. Stock refunded.', 'info')
    return redirect(url_for('work_orders.edit', id=wo.id))

@work_orders_bp.route('/<int:id>/delete_attachment/<int:attachment_id>', methods=['POST'])
@login_required
def delete_attachment(id, attachment_id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    from models import WorkOrderAttachment
    att = WorkOrderAttachment.query.filter_by(id=attachment_id, work_order_id=wo.id).first_or_404()
    
    # Optional: Delete actual file from disk here if desired
    # file_path_sys = os.path.join(current_app.root_path, 'static', att.file_path)
    # if os.path.exists(file_path_sys):
    #     os.remove(file_path_sys)
        
    db.session.delete(att)
    db.session.commit()
    
    flash('Attachment removed successfully.', 'info')
    return redirect(url_for('work_orders.edit', id=wo.id) + '#files')

@work_orders_bp.route('/<int:id>/attachment/<int:attachment_id>/edit_description', methods=['POST'])
@login_required
def edit_attachment_description(id, attachment_id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    from models import WorkOrderAttachment
    att = WorkOrderAttachment.query.filter_by(id=attachment_id, work_order_id=wo.id).first_or_404()
    desc = request.form.get('description')
    att.description = desc.strip() if desc and desc.strip() else None
    db.session.commit()
    flash('Catatan foto/lampiran berhasil diperbarui.', 'success')
    return redirect(url_for('work_orders.edit', id=wo.id) + '#files')

@work_orders_bp.route('/<int:id>/add_log', methods=['POST'])
@login_required
def add_log(id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    log_text = request.form.get('log_text')
    
    if not log_text or log_text.strip() == '':
        flash('Log cannot be empty.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id))
        
    new_log = WorkOrderLog(
        work_order_id=wo.id,
        user_id=current_user.id,
        log_text=log_text.strip()
    )
    db.session.add(new_log)
    db.session.commit()
    
    flash('Work log added successfully.', 'success')
    return redirect(url_for('work_orders.edit', id=wo.id) + '#log')

@work_orders_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@supervisor_or_admin_required
def delete(id):
    wo = WorkOrder.query.get_or_404(id)
    wo_code = wo.code
    db.session.delete(wo)
    db.session.commit()

    # Revert technician deployment in Team Schedule
    try:
        from schedule import remove_work_order_from_schedule
        remove_work_order_from_schedule(wo_code)
    except Exception as e:
        current_app.logger.warning(f"Could not remove WO {wo_code} from schedule: {e}")

    flash('Work Order deleted successfully!', 'success')
    return redirect(url_for('work_orders.index'))

def _build_procedure_json(proc, wo, message, success=True, warning=False):
    all_photos = [p for p in (proc.attachment_path or '').split('|') if p]
    req_min = proc.min_photos if proc.min_photos > 0 else (1 if proc.requires_attachment else 0)
    
    photo_objs = []
    for p in all_photos:
        photo_objs.append({
            'path': p,
            'raw': url_for('static', filename=p),
            'preview': url_for('image_preview', filename=p, w=900),
            'thumb': url_for('image_preview', filename=p, w=140)
        })
        
    completed_at_str = ''
    if proc.completed_at:
        try:
            from app import to_jakarta_filter
            completed_at_str = to_jakarta_filter(proc.completed_at, '%H:%M %d/%m')
        except Exception:
            completed_at_str = proc.completed_at.strftime('%H:%M %d/%m')

    return jsonify({
        'success': success,
        'warning': warning,
        'message': message,
        'proc_id': proc.id,
        'name': proc.name,
        'is_completed': bool(proc.is_completed),
        'status': proc.status or 'Pending',
        'notes': proc.notes or '',
        'completed_at': completed_at_str,
        'completed_by': proc.completed_by.name if proc.completed_by else (current_user.name if proc.is_completed else ''),
        'attachment_path': proc.attachment_path or '',
        'photos': photo_objs,
        'photo_count': len(all_photos),
        'req_min': req_min,
        'requires_attachment': bool(proc.requires_attachment or proc.min_photos > 0),
        'wo_completed_count': wo.procedures.filter_by(is_completed=True).count(),
        'wo_total_count': wo.procedures.count()
    })


@work_orders_bp.route('/<int:id>/procedure/<int:proc_id>/complete', methods=['POST'])
@login_required
def complete_procedure(id, proc_id):
    wo = WorkOrder.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.form.get('is_ajax') == '1'

    if not check_wo_access(wo):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        return redirect(url_for('work_orders.index'))
        
    proc = WorkOrderProcedure.query.filter_by(id=proc_id, work_order_id=wo.id).first_or_404()
    
    action = request.form.get('action', 'complete')
    notes_val = request.form.get('notes')

    # Allow updating notes as long as the work order is not Closed
    if action == 'update_notes':
        if wo.current_status and wo.current_status.control_type == 'Closed':
            if is_ajax:
                return jsonify({'success': False, 'message': 'Work order is Closed'}), 400
            flash('Cannot modify tasks on Closed Work Order.', 'danger')
            return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

        if notes_val is not None:
            proc.notes = notes_val.strip() if notes_val.strip() else None
        db.session.commit()

        if is_ajax:
            return jsonify({'success': True, 'notes': proc.notes or '', 'proc_id': proc.id, 'message': 'Catatan berhasil disimpan'})
        flash(f"Keterangan task '{proc.name}' berhasil diperbarui.", 'success')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    if not wo.current_status or wo.current_status.control_type != 'Active':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Work Order must be In Progress (Active) to modify tasks.'}), 400
        flash('Work Order must be In Progress (Active) to modify tasks.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    if action == 'uncomplete':
        proc.is_completed = False
        proc.status = 'Pending'
        proc.completed_at = None
        proc.completed_by_id = None
        db.session.commit()
        if is_ajax:
            return _build_procedure_json(proc, wo, f"Task '{proc.name}' dibatalkan.")
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    # Handle Skip / Fail
    if action == 'delete_photo':
        return delete_procedure_photo(id, proc_id)
    if action == 'fail':
        if not notes_val or not notes_val.strip():
            if is_ajax:
                return jsonify({'success': False, 'message': f"Note is required when skipping procedure '{proc.name}'."}), 400
            flash(f"Note is required when skipping procedure '{proc.name}'.", 'danger')
            return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')
        
        proc.status = 'Failed'
        proc.notes = notes_val.strip()
        proc.is_completed = True
        proc.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        proc.completed_by_id = current_user.id
        db.session.commit()
        if is_ajax:
            return _build_procedure_json(proc, wo, f"Task '{proc.name}' di-skip dengan catatan.", warning=True)
        flash(f"Procedure '{proc.name}' was skipped/failed successfully with a note.", 'warning')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    # Handle photo upload (action == 'complete' or action == 'append_photo')
    saved_paths = []
    if 'proc_attachment' in request.files:
        files = request.files.getlist('proc_attachment')
        import uuid
        for file in files:
            if file and file.filename != '':
                filename = secure_filename(f"wo{wo.id}_proc{proc.id}_{uuid.uuid4().hex[:6]}_{file.filename}")
                uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(uploads_dir, exist_ok=True)
                file_path_sys = os.path.join(uploads_dir, filename)
                save_optimized_image(file, file_path_sys)
                saved_paths.append(f'uploads/{filename}')

    if saved_paths:
        current_paths = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]
        for sp in saved_paths:
            if sp not in current_paths:
                current_paths.append(sp)
        proc.attachment_path = '|'.join(current_paths)

    if notes_val and notes_val.strip():
        proc.notes = notes_val.strip()

    # Calculate total photo count
    all_photos = [p for p in (proc.attachment_path or '').split('|') if p]
    total_photos = len(all_photos)
    req_min = proc.min_photos if proc.min_photos > 0 else (1 if proc.requires_attachment else 0)

    if req_min > 0 and total_photos < req_min:
        proc.is_completed = False
        proc.status = 'Pending'
        db.session.commit()
        msg = f"Foto tersimpan ({total_photos}/{req_min}). Tambahkan {req_min - total_photos} foto lagi untuk menyelesaikan task '{proc.name}'."
        if is_ajax:
            return _build_procedure_json(proc, wo, msg, warning=True)
        flash(msg, 'warning')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    proc.is_completed = True
    proc.status = 'Done'
    proc.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    proc.completed_by_id = current_user.id
    db.session.commit()
    msg = f"Procedure '{proc.name}' completed successfully ({total_photos}/{req_min} photos)." if req_min > 0 else f"Procedure '{proc.name}' completed successfully."
    if is_ajax:
        return _build_procedure_json(proc, wo, msg)
    flash(msg, 'success')
    return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')


@work_orders_bp.route('/<int:id>/procedure/<int:proc_id>/photo/delete', methods=['POST'])
@login_required
def delete_procedure_photo(id, proc_id):
    wo = WorkOrder.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.form.get('is_ajax') == '1'

    if not check_wo_access(wo):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        flash('Access denied.', 'danger')
        return redirect(url_for('work_orders.index'))

    if wo.current_status and wo.current_status.control_type == 'Closed':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Work Order sudah ditutup, tidak dapat mengubah foto'}), 400
        flash('Work Order sudah ditutup, tidak dapat mengubah foto.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    proc = WorkOrderProcedure.query.filter_by(id=proc_id, work_order_id=wo.id).first_or_404()

    data = request.get_json(silent=True) or request.form
    photo_path = data.get('photo_path')
    photo_index = data.get('photo_index')

    current_photos = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]
    deleted_photo = None

    if photo_path:
        norm_path = photo_path.replace('/static/', '').strip()
        for p in list(current_photos):
            if p == norm_path or p.endswith(norm_path) or norm_path.endswith(p):
                deleted_photo = p
                current_photos.remove(p)
                break
    elif photo_index is not None:
        try:
            idx = int(photo_index)
            if 0 <= idx < len(current_photos):
                deleted_photo = current_photos.pop(idx)
        except (ValueError, TypeError):
            pass

    if not deleted_photo:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Foto tidak ditemukan atau sudah dihapus'}), 404
        flash('Foto tidak ditemukan.', 'warning')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')

    # Try to delete physical file if inside static/uploads
    try:
        file_sys = os.path.join(current_app.root_path, 'static', deleted_photo.replace('/', os.sep))
        if os.path.isfile(file_sys):
            os.remove(file_sys)
    except Exception as e:
        current_app.logger.error(f"[Delete Proc Photo] Gagal hapus file fisik {deleted_photo}: {e}")

    # Update attachment_path
    proc.attachment_path = '|'.join(current_photos) if current_photos else None

    # Check minimum photo requirement
    req_min = proc.min_photos if proc.min_photos > 0 else (1 if proc.requires_attachment else 0)
    total_photos = len(current_photos)
    if req_min > 0 and total_photos < req_min:
        proc.is_completed = False
        proc.status = 'Pending'

    db.session.commit()

    if is_ajax:
        return _build_procedure_json(proc, wo, 'Foto berhasil dihapus.')

    flash(f"Foto berhasil dihapus dari task '{proc.name}'.", 'success')
    return redirect(url_for('work_orders.edit', id=wo.id) + '#procedures_panel')


@work_orders_bp.route('/<int:id>/tasklist_note', methods=['POST'])
@login_required
def save_tasklist_note(id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    if wo.current_status and wo.current_status.control_type == 'Closed':
        return jsonify({'success': False, 'message': 'Work order sudah ditutup, tidak dapat mengubah catatan'}), 400
        
    data = request.get_json(silent=True) or request.form
    note = (data.get('tasklist_note') or '').strip()
    wo.tasklist_note = note if note else None
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Catatan tasklist berhasil disimpan.',
        'tasklist_note': wo.tasklist_note or ''
    })


@work_orders_bp.route('/<int:id>/checklist_param/<int:chk_id>/save', methods=['POST'])
@login_required
def save_checklist_parameter(id, chk_id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    if not wo.current_status or wo.current_status.control_type != 'Active':
        flash('Work Order must be In Progress (Active) to modify checklists.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#checklist_panel')
        
    chk = WorkOrderChecklistParameter.query.filter_by(id=chk_id, work_order_id=wo.id).first_or_404()
    
    val = request.form.get('value')
    if val:
        chk.value = val
        db.session.commit()
        flash(f'Checklist "{chk.parameter}" set to {val}.', 'success')
        
    return redirect(url_for('work_orders.edit', id=id) + '#checklist_panel')

@work_orders_bp.route('/<int:id>/checklist/bulk_save', methods=['POST'])
@login_required
def bulk_save_checklist(id):
    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return redirect(url_for('work_orders.index'))
        
    if not wo.current_status or wo.current_status.control_type != 'Active':
        flash('Work Order must be In Progress (Active) to modify checklists.', 'danger')
        return redirect(url_for('work_orders.edit', id=wo.id) + '#checklist_panel')
        
    for chk in wo.checklist_parameters:
        val = request.form.get(f'value_{chk.id}')
        note = request.form.get(f'note_{chk.id}')
        # We update even if empty if it was sent in the form
        if val is not None:
            chk.value = val
        if note is not None:
            chk.note = note
            
    db.session.commit()
    flash('All checklist parameters saved successfully.', 'success')
    return redirect(url_for('work_orders.edit', id=wo.id) + '#checklist_panel')


@work_orders_bp.route('/<int:id>/scan_checklist_ai', methods=['POST'])
@login_required
def scan_checklist_ai(id):
    from flask import jsonify
    import json
    import base64
    import io
    import re
    import requests
    from PIL import Image as PILImage, ImageOps
    from models import SystemSetting, WorkOrderChecklistParameter

    wo = WorkOrder.query.get_or_404(id)
    if not check_wo_access(wo):
        return jsonify({'success': False, 'message': 'Akses ditolak.'}), 403

    if wo.current_status and wo.current_status.control_type == 'Closed' and current_user.role not in ['Admin', 'Supervisor']:
        return jsonify({'success': False, 'message': 'Work Order ini sudah ditutup (Closed).'}), 400

    file = request.files.get('checklist_image')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Silakan pilih atau ambil foto lembar checklist terlebih dahulu.'}), 400

    chk_list = wo.checklist_parameters.order_by(WorkOrderChecklistParameter.id.asc()).all()
    if not chk_list:
        return jsonify({'success': False, 'message': 'Work Order ini belum memiliki parameter checklist.'}), 400

    param_lines = "\n".join([f"- [{c.id}] {c.parameter} (std: {c.standard or '-'})" for c in chk_list])

    # Resize gambar ke max 1600px untuk optimasi transfer dan resolusi OCR
    try:
        img = PILImage.open(file.stream)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        max_dim = 1600
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        b64_image = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        return jsonify({'success': False, 'message': f'Gagal memproses file gambar: {str(e)}'}), 400

    def get_setting(key, default=None):
        s = SystemSetting.query.filter_by(setting_key=key).first()
        if s and s.setting_value and s.setting_value.strip():
            return s.setting_value.strip()
        val = os.environ.get(key)
        return val.strip() if val else default

    sumopod_key = get_setting('SUMOPOD_API_KEY')
    sumopod_url = get_setting('SUMOPOD_BASE_URL', 'https://ai.sumopod.com')
    gemini_key = get_setting('GEMINI_API_KEY')
    openai_key = get_setting('OPENAI_API_KEY')

    prompt = f"""Anda adalah asisten AI teknis pembaca formulir checklist maintenance (CMMS maintenance OCR).
Tugas Anda adalah membaca gambar lembar kertas formulir checklist fisik yang telah diisi teknisi.

Daftar parameter checklist unit ini:
{param_lines}

Instruksi:
1. Cocokkan baris formulir kertas dengan parameter di atas.
2. Baca nilai tulisan tangan / angka / centang:
   - Jika tertulis angka (misal: 220, 380, 5.5, 40, 1.2), kembalikan angkanya.
   - Jika tertulis centang / ceklis / huruf V / tanda OK / normal, kembalikan "OK".
3. Kembalikan HANYA format JSON ringkas seperti berikut (hanya sertakan ID parameter yang memiliki nilai atau catatan):
{{
    "values": {{
        "<id_parameter>": "<nilai_terbaca_atau_OK>"
    }},
    "notes": {{
        "<id_parameter>": "<catatan_terbaca>"
    }}
}}
"""

    values_dict = {}
    notes_dict = {}
    provider_used = "AI Vision"
    ai_raw_content = ""
    last_error = ""

    # Klien Vision: Gunakan Gemini Flash Vision (Sumopod / Google AI Studio / OpenAI)
    clients_to_try = []
    if gemini_key:
        clients_to_try.append({
            'name': 'Google Gemini Vision',
            'url': 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
            'key': gemini_key.strip(),
            'models': ['gemini-2.0-flash', 'gemini-1.5-flash']
        })

    if sumopod_key:
        clients_to_try.append({
            'name': 'Gemini Flash Vision',
            'url': f'{sumopod_url.rstrip("/")}/v1/chat/completions',
            'key': sumopod_key.strip(),
            'models': ['gemini/gemini-3.5-flash-lite', 'gemini/gemini-3.5-flash', 'gpt-4o-mini']
        })

    if openai_key:
        clients_to_try.append({
            'name': 'OpenAI Vision',
            'url': 'https://api.openai.com/v1/chat/completions',
            'key': openai_key.strip(),
            'models': ['gpt-4o-mini', 'gpt-4o']
        })

    if not clients_to_try:
        return jsonify({
            'success': False,
            'message': 'API Key AI Vision belum diatur. Pastikan SUMOPOD_API_KEY atau GEMINI_API_KEY aktif di menu System Settings atau file .env.'
        }), 400

    api_success = False
    for client in clients_to_try:
        if api_success:
            break
        for model_name in client['models']:
            payload = {
                'model': model_name,
                'messages': [
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': prompt},
                            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64_image}'}}
                        ]
                    }
                ],
                'temperature': 0.1,
                'max_tokens': 8192
            }
            try:
                res = requests.post(
                    client['url'],
                    headers={'Authorization': f'Bearer {client["key"]}', 'Content-Type': 'application/json'},
                    json=payload,
                    timeout=60
                )
                if res.status_code == 200:
                    resp_json = res.json()
                    raw_msg = resp_json.get('choices', [{}])[0].get('message', {})
                    ai_raw_content = raw_msg.get('content') or ""
                    if ai_raw_content and ai_raw_content.strip():
                        provider_used = f"{client['name']} ({model_name})"
                        api_success = True
                        break
                    else:
                        last_error = f"Model {model_name} mengembalikan respons kosong."
                else:
                    err_info = res.json() if res.headers.get('content-type', '').startswith('application/json') else {}
                    last_error = err_info.get('error', {}).get('message', res.text)
            except Exception as e:
                last_error = str(e)

    if not api_success or not ai_raw_content:
        return jsonify({'success': False, 'message': f'Gagal memproses gambar melalui AI Vision: {last_error}'}), 500

    # Parse JSON dari output AI secara aman dan tangguh
    def parse_ai_json(raw_text):
        if not raw_text or not raw_text.strip():
            return None
        text = raw_text.strip()
        
        # 1. Coba cari di dalam code fence ```json ... ```
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
        candidate = m.group(1).strip() if m else None
        
        # 2. Jika tidak ada code fence, cari blok { ... } terluar
        if not candidate:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                candidate = text[start:end+1].strip()
            elif start != -1:
                candidate = text[start:].strip().rstrip(', \n\r\t') + '\n}}'

        candidates_to_try = [candidate] if candidate else []
        candidates_to_try.append(text)
        
        for c in candidates_to_try:
            if not c:
                continue
            try:
                return json.loads(c)
            except Exception:
                pass
            try:
                return json.loads(c, strict=False)
            except Exception:
                pass
            cleaned = re.sub(r',\s*([\}\]])', r'\1', c)
            try:
                return json.loads(cleaned, strict=False)
            except Exception:
                pass
                
        return None

    parsed = parse_ai_json(ai_raw_content)
    if not parsed or not isinstance(parsed, dict):
        return jsonify({'success': False, 'message': 'AI tidak mengembalikan format JSON yang dapat dibaca.'}), 500

    if 'values' in parsed or 'notes' in parsed:
        raw_v = parsed.get('values', {}) or {}
        raw_n = parsed.get('notes', {}) or {}
        for k, v in raw_v.items():
            if v is not None and str(v).strip():
                values_dict[str(k)] = str(v).strip()
        for k, n in raw_n.items():
            if n is not None and str(n).strip():
                notes_dict[str(k)] = str(n).strip()
    elif 'results' in parsed and isinstance(parsed['results'], list):
        for item in parsed['results']:
            pid = str(item.get('id', ''))
            if pid:
                if item.get('value'):
                    values_dict[pid] = str(item.get('value')).strip()
                if item.get('note'):
                    notes_dict[pid] = str(item.get('note')).strip()
    else:
        for k, v in parsed.items():
            if str(k).isdigit() and v is not None and str(v).strip():
                values_dict[str(k)] = str(v).strip()

    return jsonify({
        'success': True,
        'provider': provider_used,
        'values': values_dict,
        'notes': notes_dict,
        'count': len([v for v in values_dict.values() if v and str(v).strip()])
    })

@work_orders_bp.route('/<int:id>/procedure/add', methods=['POST'])
@login_required
def add_wo_procedure(id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('work_orders.edit', id=id))
        
    wo = WorkOrder.query.get_or_404(id)
    name = request.form.get('name')
    try:
        estimated_minutes = float(request.form.get('estimated_minutes', 0))
    except:
        estimated_minutes = 0
    try:
        min_photos = int(request.form.get('min_photos', 0))
    except:
        min_photos = 0
    requires_attachment = ('requires_attachment' in request.form) or (min_photos > 0)
    notes = request.form.get('notes')
    
    if name:
        new_proc = WorkOrderProcedure(work_order=wo, tasklist_name='Custom Task', name=name, requires_attachment=requires_attachment, min_photos=min_photos, estimated_minutes=estimated_minutes, notes=notes)
        db.session.add(new_proc)
        db.session.commit()
        flash(f'Custom procedure "{name}" added successfully.', 'success')
        
    return redirect(url_for('work_orders.edit', id=id) + '#procedures_panel')

@work_orders_bp.route('/<int:id>/procedure/<int:proc_id>/edit', methods=['POST'])
@login_required
def edit_wo_procedure(id, proc_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('work_orders.edit', id=id))
        
    wo = WorkOrder.query.get_or_404(id)
    proc = WorkOrderProcedure.query.filter_by(id=proc_id, work_order_id=wo.id).first_or_404()
    
    name = request.form.get('name')
    if name:
        proc.name = name
    try:
        proc.estimated_minutes = float(request.form.get('estimated_minutes', 0))
    except:
        pass
    try:
        proc.min_photos = int(request.form.get('min_photos', 0))
    except:
        pass
    proc.requires_attachment = ('requires_attachment' in request.form) or (proc.min_photos > 0)
    if 'notes' in request.form:
        proc.notes = request.form.get('notes')
    
    db.session.commit()
    flash('Procedure updated successfully.', 'success')
    return redirect(url_for('work_orders.edit', id=id) + '#procedures_panel')

@work_orders_bp.route('/<int:id>/procedure/<int:proc_id>/delete', methods=['POST'])
@login_required
def delete_wo_procedure(id, proc_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('work_orders.edit', id=id))
        
    wo = WorkOrder.query.get_or_404(id)
    proc = WorkOrderProcedure.query.filter_by(id=proc_id, work_order_id=wo.id).first_or_404()
    
    db.session.delete(proc)
    db.session.commit()
    flash('Procedure deleted successfully.', 'success')
    return redirect(url_for('work_orders.edit', id=id) + '#procedures_panel')

@work_orders_bp.route('/<int:id>/checklist/add', methods=['POST'])
@login_required
def add_wo_checklist(id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('work_orders.edit', id=id))
        
    wo = WorkOrder.query.get_or_404(id)
    parameter = request.form.get('parameter')
    standard = request.form.get('standard')
    
    if parameter and standard:
        new_chk = WorkOrderChecklistParameter(work_order=wo, checklist_name='Custom Check', parameter=parameter, standard=standard)
        db.session.add(new_chk)
        db.session.commit()
        flash('Custom parameter added successfully.', 'success')
        
    return redirect(url_for('work_orders.edit', id=id) + '#checklist_panel')

@work_orders_bp.route('/<int:id>/checklist/<int:chk_id>/edit', methods=['POST'])
@login_required
def edit_wo_checklist(id, chk_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('work_orders.edit', id=id))
        
    wo = WorkOrder.query.get_or_404(id)
    chk = WorkOrderChecklistParameter.query.filter_by(id=chk_id, work_order_id=wo.id).first_or_404()
    
    parameter = request.form.get('parameter')
    standard = request.form.get('standard')
    
    if parameter:
        chk.parameter = parameter
    if standard:
        chk.standard = standard
        
    db.session.commit()
    flash('Checklist parameter updated successfully.', 'success')
    return redirect(url_for('work_orders.edit', id=id) + '#checklist_panel')

@work_orders_bp.route('/<int:id>/checklist/<int:chk_id>/delete', methods=['POST'])
@login_required
def delete_wo_checklist(id, chk_id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Permission denied.', 'danger')
        return redirect(url_for('work_orders.edit', id=id))
        
    wo = WorkOrder.query.get_or_404(id)
    chk = WorkOrderChecklistParameter.query.filter_by(id=chk_id, work_order_id=wo.id).first_or_404()
    
    db.session.delete(chk)
    db.session.commit()
    flash('Checklist parameter deleted successfully.', 'success')
    return redirect(url_for('work_orders.edit', id=id) + '#checklist_panel')
