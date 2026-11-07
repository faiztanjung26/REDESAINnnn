from flask import Blueprint, render_template, request, make_response
from flask_login import login_required
from models import db, WorkOrder, Asset, StockLevel, PurchaseOrder, Site, WorkOrderStatus
from sqlalchemy import func
import csv
from io import StringIO
from datetime import datetime, timezone

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
@login_required
def index():
    report_categories = [
        {'name': 'Work Order Reports', 'icon': 'bi-tools', 'reports': [
            {'id': 'monthly_wo', 'title': 'Laporan Bulanan Work Order (PDF)', 'desc': 'Laporan komprehensif WO bulanan gabungan (Judul, Chiller Details, REPORT WO, Foto Lampiran).', 'custom_url': 'reports.wo_monthly_report'},
            {'id': 'open_wos', 'title': 'All Open Work Orders', 'desc': 'Displays the list of all open work orders.'},
            {'id': 'completed_wos', 'title': 'Completed Work Orders', 'desc': 'Summary of all closed work orders.'},
            {'id': 'wo_by_type', 'title': 'Work Orders by Type', 'desc': 'Breakdown of work orders by maintenance type.'}
        ]},
        {'name': 'Asset Reports', 'icon': 'bi-box-seam', 'reports': [
            {'id': 'offline_assets', 'title': 'Offline Assets', 'desc': 'List of all assets currently marked as Offline.'},
            {'id': 'asset_summary', 'title': 'Site Asset Summary', 'desc': 'Summary of assets by site.'}
        ]},
        {'name': 'Inventory Reports', 'icon': 'bi-box', 'reports': [
            {'id': 'low_stock', 'title': 'Low Stock Inventory', 'desc': 'Parts in stock that are below minimum levels.'},
            {'id': 'inventory_valuation', 'title': 'Inventory Valuation', 'desc': 'Total value of parts on hand.'}
        ]},
        {'name': 'Performance & KPIs', 'icon': 'bi-graph-up', 'reports': [
            {'id': 'mttr_summary', 'title': 'Average MTTR by Site', 'desc': 'Mean Time To Repair grouped by Site.'},
            {'id': 'pm_compliance', 'title': 'PM Compliance', 'desc': 'Preventive Maintenance completion performance.'}
        ]}
    ]
    count = sum(len(c['reports']) for c in report_categories)
    return render_template('reports/index.html', categories=report_categories, count=count)

def get_report_data(report_id, start_date_str=None, end_date_str=None, site_id=None):
    # This helper function will fetch data so it can be used for both view and CSV export
    from flask_login import current_user
    
    # Enforce current_user site restriction if applicable
    if current_user.site_id:
        site_id = current_user.site_id
    data = []
    columns = []
    title = "Report"
    
    # Parse dates if provided
    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # Set end_date to end of day
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    if report_id == 'open_wos':
        title = "All Open Work Orders"
        columns = ['Code', 'Description', 'Priority', 'Type', 'Status', 'Asset', 'Assigned To', 'Date Created']
        
        active_statuses = [s.id for s in WorkOrderStatus.query.filter_by(control_type='Active').all()]
        query = WorkOrder.query
        if site_id:
            query = query.join(Asset).filter(Asset.site_id == site_id)
        if active_statuses:
            query = query.filter(WorkOrder.status_id.in_(active_statuses))
        else:
            query = query.filter(WorkOrder.status_id != None) # fallback
            
        if start_date:
            query = query.filter(WorkOrder.date_created >= start_date)
        if end_date:
            query = query.filter(WorkOrder.date_created <= end_date)
            
        for wo in query.all():
            data.append([
                wo.code, wo.description, wo.priority, wo.maintenance_type, 
                wo.current_status.name if wo.current_status else 'Unknown', 
                wo.asset.name if wo.asset else '-',
                wo.assignee.name if wo.assignee else 'Unassigned',
                wo.date_created.strftime('%Y-%m-%d') if wo.date_created else '-'
            ])
            
    elif report_id == 'completed_wos':
        title = "Completed/Closed Work Orders"
        columns = ['Code', 'Description', 'Type', 'Status', 'Start Date', 'End Date', 'Repair Hours']
        closed_statuses = [s.id for s in WorkOrderStatus.query.filter_by(control_type='Closed').all()]
        query = WorkOrder.query
        if site_id:
            query = query.join(Asset).filter(Asset.site_id == site_id)
        if closed_statuses:
            query = query.filter(WorkOrder.status_id.in_(closed_statuses))
            
        if start_date:
            query = query.filter(WorkOrder.end_date >= start_date)
        if end_date:
            query = query.filter(WorkOrder.end_date <= end_date)
            
        for wo in query.all():
            hours = "-"
            if wo.start_date and wo.end_date:
                hours = round((wo.end_date - wo.start_date).total_seconds() / 3600, 2)
            data.append([
                wo.code, wo.description, wo.maintenance_type, 
                wo.current_status.name if wo.current_status else 'Unknown',
                wo.start_date.strftime('%Y-%m-%d %H:%M') if wo.start_date else '-',
                wo.end_date.strftime('%Y-%m-%d %H:%M') if wo.end_date else '-',
                hours
            ])
            
    elif report_id == 'wo_by_type':
        title = "Work Orders by Type"
        columns = ['Maintenance Type', 'Total Count']
        query = db.session.query(WorkOrder.maintenance_type, func.count(WorkOrder.id))
        if site_id:
            query = query.join(Asset).filter(Asset.site_id == site_id)
        if start_date:
            query = query.filter(WorkOrder.date_created >= start_date)
        if end_date:
            query = query.filter(WorkOrder.date_created <= end_date)
        query = query.group_by(WorkOrder.maintenance_type).all()
        
        for row in query:
            data.append([row[0] or 'Unknown', row[1]])

    elif report_id == 'offline_assets':
        title = "Offline Assets"
        columns = ['Asset Name', 'Code', 'Site', 'Criticality']
        query = Asset.query.filter_by(status='Offline')
        if site_id:
            query = query.filter_by(site_id=site_id)
        for a in query.all():
            data.append([a.name, a.code, a.site.name if a.site else '-', a.criticality])
            
    elif report_id == 'asset_summary':
        title = "Site Asset Summary"
        columns = ['Site Name', 'Total Assets', 'Online', 'Offline', 'In Repair']
        if site_id:
            sites = Site.query.filter_by(id=site_id).all()
        else:
            sites = Site.query.all()
        for s in sites:
            total = s.assets.count()
            online = s.assets.filter_by(status='Online').count()
            offline = s.assets.filter_by(status='Offline').count()
            in_repair = s.assets.filter_by(status='In Repair').count()
            data.append([s.name, total, online, offline, in_repair])
            
    elif report_id == 'low_stock':
        title = "Low Stock Inventory"
        columns = ['Part Name', 'Part Code', 'Site', 'On Hand', 'Min Qty']
        query = StockLevel.query.filter(StockLevel.qty_on_hand <= StockLevel.min_qty)
        if site_id:
            query = query.filter_by(site_id=site_id)
        for sl in query.all():
            data.append([
                sl.part.name, sl.part.code, sl.site.name if sl.site else '-',
                sl.qty_on_hand, sl.min_qty
            ])
            
    elif report_id == 'inventory_valuation':
        title = "Inventory Valuation"
        columns = ['Part Name', 'Location', 'Qty On Hand', 'Unit Cost', 'Total Value']
        query = StockLevel.query
        if site_id:
            query = query.filter_by(site_id=site_id)
        for sl in query.all():
            val = sl.qty_on_hand * (sl.part.unit_cost or 0)
            data.append([
                sl.part.name, sl.site.name if sl.site else '-', sl.qty_on_hand, 
                f"${sl.part.unit_cost:.2f}", f"${val:.2f}"
            ])
            
    elif report_id == 'mttr_summary':
        title = "Average MTTR by Site"
        columns = ['Site Name', 'Completed WOs', 'Total Repair Hours', 'Avg MTTR (Hours)']
        closed_statuses = [s.id for s in WorkOrderStatus.query.filter_by(control_type='Closed').all()]
        
        if site_id:
            sites = Site.query.filter_by(id=site_id).all()
        else:
            sites = Site.query.all()
        for s in sites:
            # Get completed WOs for this site
            wos = WorkOrder.query.join(Asset).filter(Asset.site_id == s.id)
            if closed_statuses:
                wos = wos.filter(WorkOrder.status_id.in_(closed_statuses))
            if start_date:
                wos = wos.filter(WorkOrder.end_date >= start_date)
            if end_date:
                wos = wos.filter(WorkOrder.end_date <= end_date)
                
            completed = wos.all()
            total_hours = 0
            count = 0
            for wo in completed:
                if wo.start_date and wo.end_date and wo.end_date > wo.start_date:
                    total_hours += (wo.end_date - wo.start_date).total_seconds() / 3600
                    count += 1
            
            avg_mttr = round(total_hours / count, 2) if count > 0 else 0
            data.append([s.name, len(completed), round(total_hours, 2), avg_mttr])
            
    elif report_id == 'pm_compliance':
        title = "Preventive Maintenance Compliance"
        columns = ['Compliant WOs', 'Overdue WOs', 'Compliance %']
        
        query = WorkOrder.query.filter(WorkOrder.maintenance_type == 'Preventive', WorkOrder.suggested_completion_date != None)
        if site_id:
            query = query.join(Asset).filter(Asset.site_id == site_id)
        if start_date:
            query = query.filter(WorkOrder.date_created >= start_date)
        if end_date:
            query = query.filter(WorkOrder.date_created <= end_date)
            
        all_pms = query.all()
        compliant = 0
        overdue = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        for wo in all_pms:
            if wo.current_status and wo.current_status.control_type == 'Closed':
                if wo.end_date and wo.end_date <= wo.suggested_completion_date:
                    compliant += 1
                else:
                    overdue += 1
            else:
                if now > wo.suggested_completion_date:
                    overdue += 1
                else:
                    compliant += 1
                    
        total = compliant + overdue
        perc = round((compliant / total * 100), 1) if total > 0 else 0
        data.append([compliant, overdue, f"{perc}%"])

    else:
        title = "Report Not Found"
        
    return title, columns, data

@reports_bp.route('/view/<report_id>')
@login_required
def view_report(report_id):
    start_dt = request.args.get('start_date')
    end_dt = request.args.get('end_date')
    
    site_id = request.args.get('site_id', type=int)
    
    title, columns, data = get_report_data(report_id, start_dt, end_dt, site_id)
    
    # Reports that support date filtering
    supports_date = report_id in ['open_wos', 'completed_wos', 'wo_by_type', 'mttr_summary', 'pm_compliance']
    
    return render_template('reports/view.html', 
                           title=title, columns=columns, data=data, 
                           report_id=report_id,
                           start_date=start_dt or '', end_date=end_dt or '',
                           supports_date=supports_date)

@reports_bp.route('/export/<report_id>')
@login_required
def export_csv(report_id):
    start_dt = request.args.get('start_date')
    end_dt = request.args.get('end_date')
    site_id = request.args.get('site_id', type=int)
    title, columns, data = get_report_data(report_id, start_dt, end_dt, site_id)
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(columns)
    cw.writerows(data)
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={report_id}_export.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@reports_bp.route('/client_report')
@login_required
def client_report():
    from flask import flash, jsonify
    from datetime import timedelta
    from flask_login import current_user
    
    site_id = request.args.get('site_id', type=int)
    
    # If user is restricted to a site, enforce it
    if current_user.site_id:
        site_id = current_user.site_id
        
    time_range = request.args.get('time_range', 'this_month')
    start_dt_str = request.args.get('start_date')
    end_dt_str = request.args.get('end_date')
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = None
    end_date = None
    
    # Calculate Date Range
    if time_range == 'today':
        now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
        today_date = now_wib.date()
        start_date = datetime(today_date.year, today_date.month, today_date.day, 0, 0, 0) - timedelta(hours=7)
        end_date = datetime(today_date.year, today_date.month, today_date.day, 23, 59, 59) - timedelta(hours=7)
    elif time_range == 'this_month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # End of month
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
        end_date = end_date.replace(hour=23, minute=59, second=59)
    elif time_range == 'last_month':
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = this_month_start - timedelta(days=1)
        end_date = end_date.replace(hour=23, minute=59, second=59)
        start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif time_range == 'this_year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(month=12, day=31, hour=23, minute=59, second=59)
    elif time_range == 'custom' and start_dt_str and end_dt_str:
        try:
            start_date = datetime.strptime(start_dt_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_dt_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass
            
    # Base Query
    query = WorkOrder.query
    if site_id:
        query = query.join(Asset).filter(Asset.site_id == site_id)
        
    if start_date and end_date:
        from sqlalchemy import func
        query = query.filter(
            db.or_(
                func.coalesce(WorkOrder.suggested_completion_date, WorkOrder.date_created).between(start_date, end_date),
                func.coalesce(WorkOrder.suggested_start_date, WorkOrder.date_created).between(start_date, end_date)
            )
        )
        
    all_wos = query.all()
    total_wos = len(all_wos)
    
    # Get Status IDs for "Pending" / "On Hold" logic
    pending_statuses = WorkOrderStatus.query.filter(WorkOrderStatus.control_type.in_(['On Hold', 'Pending'])).all()
    pending_status_ids = [s.id for s in pending_statuses]
    
    closed_wos_count = 0
    constrained_wos_count = 0
    overdue_wos_count = 0
    
    # Overdue = WOs not closed, and suggested_completion_date < start of current month
    # This ensures "this month" WOs are never overdue, but "last month" WOs are.
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    overdue_query = WorkOrder.query.join(WorkOrderStatus, WorkOrder.status_id == WorkOrderStatus.id).filter(
        WorkOrderStatus.control_type != 'Closed'
    )
    if site_id:
        overdue_query = overdue_query.join(Asset).filter(Asset.site_id == site_id)
        
    overdue_wos_global = overdue_query.filter(WorkOrder.suggested_completion_date < current_month_start).all()
        
    for wo in all_wos:
        if wo.current_status and wo.current_status.control_type == 'Closed':
            closed_wos_count += 1
        elif wo.status_id in pending_status_ids:
            constrained_wos_count += 1
            
        # Count overdue ONLY from the WOs created in this period
        if wo.current_status and wo.current_status.control_type != 'Closed' and wo.suggested_completion_date and wo.suggested_completion_date < now:
            overdue_wos_count += 1
            
    # Strictly use only WOs from this period
    all_report_wos = {wo.id: wo for wo in all_wos}
        
    all_report_wos_list = list(all_report_wos.values())
    all_report_wos_list.sort(key=lambda x: x.date_created, reverse=True)
    
    # Percentages strictly reflect the selected period's performance
    calc_total = len(all_wos)
    
    perc_completed = round((closed_wos_count / calc_total * 100), 1) if calc_total > 0 else 0
    perc_constrained = round((constrained_wos_count / calc_total * 100), 1) if calc_total > 0 else 0
    perc_overdue = round((overdue_wos_count / calc_total * 100), 1) if calc_total > 0 else 0

    # Calculate MTTR
    completed_wos = [wo for wo in all_wos if wo.current_status and wo.current_status.control_type == 'Closed']
    total_repair_hours = 0
    for wo in completed_wos:
        if wo.start_date and wo.end_date and wo.end_date > wo.start_date:
            total_repair_hours += (wo.end_date - wo.start_date).total_seconds() / 3600
    mttr_hours = round(total_repair_hours / len(completed_wos), 1) if len(completed_wos) > 0 else 0

    # Calculate MTBF
    corrective_wos = [w for w in all_wos if w.maintenance_type == 'Corrective']
    period_hours = 30 * 24 # Fallback
    if start_date and end_date:
        period_hours = (end_date - start_date).total_seconds() / 3600
    
    if site_id:
        total_assets = Asset.query.filter_by(site_id=site_id).count()
    else:
        total_assets = Asset.query.count()
        
    total_uptime_hours = total_assets * period_hours
    mtbf_hours = round(total_uptime_hours / len(corrective_wos), 1) if len(corrective_wos) > 0 else round(total_uptime_hours, 1)

    # PM Compliance
    pm_wos = [w for w in all_wos if w.maintenance_type == 'Preventive' and w.suggested_completion_date]
    compliant_pm = 0
    for wo in pm_wos:
        if wo.current_status and wo.current_status.control_type == 'Closed':
            if wo.end_date and wo.end_date <= wo.suggested_completion_date:
                compliant_pm += 1
        else:
            if now <= wo.suggested_completion_date:
                compliant_pm += 1
                
    pm_compliance = round((compliant_pm / len(pm_wos) * 100), 1) if len(pm_wos) > 0 else 0

    if current_user.site_id:
        sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        sites = Site.query.all()
    
    existing_reasons_q = db.session.query(WorkOrder.delay_reason).filter(WorkOrder.delay_reason.isnot(None), WorkOrder.delay_reason != '').distinct().all()
    existing_reasons = [r[0] for r in existing_reasons_q]
    
    return render_template('reports/client_report.html',
                           wos=all_report_wos_list,
                           perc_completed=perc_completed,
                           perc_constrained=perc_constrained,
                           perc_overdue=perc_overdue,
                           count_completed=closed_wos_count,
                           count_constrained=constrained_wos_count,
                           count_overdue=overdue_wos_count,
                           count_total=calc_total,
                           count_pm_total=len(pm_wos),
                           count_pm_compliant=compliant_pm,
                           mttr=mttr_hours,
                           mtbf=mtbf_hours,
                           pm_compliance=pm_compliance,
                           sites=sites,
                           selected_site_id=site_id,
                           time_range=time_range,
                           start_date_str=start_dt_str or '',
                           end_date_str=end_dt_str or '',
                           now=now,
                           current_month_start=current_month_start,
                           existing_reasons=existing_reasons)

@reports_bp.route('/client_report/update_reason/<int:id>', methods=['POST'])
@login_required
def update_delay_reason(id):
    from flask import request, jsonify
    wo = WorkOrder.query.get_or_404(id)
    data = request.get_json()
    if 'delay_reason' in data:
        wo.delay_reason = data['delay_reason']
        db.session.commit()
        return jsonify({'success': True, 'message': 'Reason updated successfully'})
    return jsonify({'success': False, 'message': 'No reason provided'}), 400

@reports_bp.route('/ai_summary', methods=['POST'])
@login_required
def ai_summary():
    import os
    import requests
    from flask import request, jsonify
    from models import SystemSetting
    
    data = request.get_json() or {}
    db_key_setting = SystemSetting.query.filter_by(setting_key='GROQ_API_KEY').first()
    api_key = (db_key_setting.setting_value.strip() if db_key_setting and db_key_setting.setting_value else None) or os.environ.get('GROQ_API_KEY')
    
    if not api_key:
        return jsonify({'success': False, 'message': 'API Key Groq belum disetting di System Settings atau .env'}), 500
        
    real_reasons = data.get('real_reasons', [])
    reasons_text = ""
    if real_reasons:
        reasons_text = "\n- Berikut adalah rangkuman alasan/kendala aktual dari lapangan yang menyebabkan penundaan:\n  * " + "\n  * ".join(real_reasons)

    prompt = f"""
Anda adalah perwakilan Tim Operasional dari PT Jaya Teknik Indonesia. Tugas Anda adalah menulis Surat Pengantar Laporan Kinerja (Progress Report) formal yang ditujukan kepada Manajemen / Pemilik Fasilitas {data.get('site')}.

Buatlah surat yang komprehensif, analitis, dan sangat profesional berdasarkan data pemeliharaan berikut:
- Periode: {data.get('period')}
- Total Work Order (WO): {data.get('total')}
- Selesai (Completed): {data.get('completed_count')} ({data.get('completed_perc')})
- Terkendala/Tertunda: {data.get('constrained_count')} ({data.get('constrained_perc')}){reasons_text}
- Waktu Perbaikan Rata-rata (MTTR): {data.get('mttr')} Jam

Instruksi Penulisan Surat:
1. Awali surat dengan sapaan hormat (contoh: Yth. Manajemen / Pemilik Fasilitas {data.get('site')}).
2. Jelaskan tujuan surat ini, yaitu melaporkan efektivitas pemeliharaan fasilitas secara transparan melalui sistem CMMS.
3. Jabarkan analisis performa ke dalam poin-poin bernomor (1, 2, 3). Berikan "Insight Analitis" yang cerdas pada tiap poin. Misalnya:
   - Evaluasi efisiensi tim teknis dari angka MTTR.
   - Penjelasan spesifik MENGAPA ada WO yang tertunda berdasarkan alasan aktual dari lapangan yang diberikan di atas (jangan mengarang alasan jika data aktual sudah diberikan).
4. Tegaskan komitmen Jaya Teknik untuk terus menjaga keandalan operasional fasilitas.
5. Akhiri dengan salam penutup: Hormat kami, Tim Operasional PT Jaya Teknik Indonesia.

Tulis murni hanya isi surat. Gunakan format Markdown yang rapi (bold untuk penekanan, bullet/numbering yang terstruktur). Jangan menggunakan heading besar (seperti # SURAT PENGANTAR), jadikan ini seperti teks surat biasa.
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    candidate_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    last_err = ""
    for model_name in candidate_models:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a professional business representative writing a formal progress report letter to a client. Write exclusively in Markdown formatting."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 1500
        }
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                ai_text = result['choices'][0]['message']['content']
                return jsonify({'success': True, 'report': ai_text})
            
            error_data = {}
            try:
                error_data = response.json().get('error', {})
            except Exception:
                pass
            last_err = error_data.get('message', response.text)
            if response.status_code == 401:
                return jsonify({'success': False, 'message': f'API Key Groq tidak valid: {last_err}'}), 401
        except Exception as e:
            last_err = str(e)
            
    return jsonify({'success': False, 'message': f'Groq API Error: {last_err}'}), 500

@reports_bp.route('/ai_pdf_report', methods=['POST'])
@login_required
def ai_pdf_report():
    import os
    import requests, json
    from flask import request, jsonify
    from models import SystemSetting
    
    data = request.get_json() or {}
    db_key_setting = SystemSetting.query.filter_by(setting_key='GROQ_API_KEY').first()
    api_key = (db_key_setting.setting_value.strip() if db_key_setting and db_key_setting.setting_value else None) or os.environ.get('GROQ_API_KEY')
    
    if not api_key:
        return jsonify({'success': False, 'message': 'API Key Groq belum disetting di System Settings atau .env'}), 500
        
    wos_text = ""
    for w in data.get('wos', []):
        wos_text += f"- {w.get('kode')} | {w.get('aset')} | {w.get('status')} | Tenggat: {w.get('tenggat')}\n"
        
    prompt = f"""
Anda adalah Web Designer dan Data Analyst tingkat lanjut. Tugas Anda adalah membuat SEBUAH FILE HTML LENGKAP dengan inline CSS (atau block <style>) yang berfungsi sebagai Dokumen Laporan Pemeliharaan (Maintenance Report) resmi untuk dicetak menjadi PDF (ukuran A4).

Klien: Jaya Teknik
Periode: {data.get('period')}
Lokasi: {data.get('site')}

Data KPI:
- Total WO: {data.get('total')}
- Selesai: {data.get('completed_count')} ({data.get('completed_perc')})
- Tertunda: {data.get('constrained_count')} ({data.get('constrained_perc')})
- Overdue: {data.get('overdue_count')} ({data.get('overdue_perc')})
- MTTR: {data.get('mttr')} Jam
- MTBF: {data.get('mtbf')} Jam
- Kepatuhan PM: {data.get('pm_compliance')}

Data Work Order (Sebagian):
{wos_text}

Instruksi Desain HTML:
1. Buat layout yang elegan, modern, dan profesional menggunakan CSS murni. Jangan pakai framework external (seperti bootstrap), tulis CSS di dalam tag <style>.
2. Tuliskan Header (Kop Laporan) yang memukau.
3. Tuliskan paragraf Laporan Eksekutif singkat (analisis cerdas atas data KPI di atas) di bagian atas dokumen.
4. Buatkan kotak-kotak metrik (cards) untuk menampilkan KPI dengan desain visual modern.
5. Buatkan tabel rapi bergaris untuk menampilkan daftar Work Order. Terapkan striping (zebra).
6. Sediakan area tanda tangan di bagian paling bawah.
7. Kembalikan HANYA KODE HTML TANPA AWALAN/AKHIRAN MARKDOWN (jangan pakai ```html). Harus langsung berupa kode <!DOCTYPE html>...</html> yang valid dan bersih.
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    candidate_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    last_err = ""
    for model_name in candidate_models:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a web designer. Output ONLY valid raw HTML code without markdown code blocks. NO explanation, NO introduction."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 5000
        }
        
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                result = response.json()
                html_code = result['choices'][0]['message']['content'].strip()
                
                # Bersihkan dari markdown wrapper jika AI membandel
                if html_code.startswith('```html'):
                    html_code = html_code[7:]
                if html_code.startswith('```'):
                    html_code = html_code[3:]
                if html_code.endswith('```'):
                    html_code = html_code[:-3]
                    
                return jsonify({'success': True, 'html': html_code.strip()})
                
            error_data = {}
            try:
                error_data = response.json().get('error', {})
            except Exception:
                pass
            last_err = error_data.get('message', response.text)
            if response.status_code == 401:
                return jsonify({'success': False, 'message': f'API Key Groq tidak valid: {last_err}'}), 401
        except Exception as e:
            last_err = str(e)
            
    return jsonify({'success': False, 'message': f'Groq API Error: {last_err}'}), 500


# ==============================================================================
# Laporan Bulanan Work Order (Portrait PDF)
# ==============================================================================

@reports_bp.route('/wo_monthly', methods=['GET'])
@login_required
def wo_monthly_report():
    """Halaman pemilihan dan filter untuk Laporan Bulanan Work Order"""
    from flask_login import current_user
    from sqlalchemy import func
    from datetime import timedelta
    
    # Hak akses site (jika user dibatasi pada site tertentu)
    selected_site_id = request.args.get('site_id', type=int)
    if current_user.site_id and current_user.role != 'Supergod':
        selected_site_id = current_user.site_id
        available_sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        available_sites = Site.query.order_by(Site.name).all()

    # Waktu / Periode Bulan & Tahun
    now = datetime.now()
    selected_month = request.args.get('month', type=int) or now.month
    selected_year = request.args.get('year', type=int) or now.year

    # Rentang tanggal bulan terpilih
    start_date = datetime(selected_year, selected_month, 1, 0, 0, 0)
    if selected_month == 12:
        next_month = datetime(selected_year + 1, 1, 1, 0, 0, 0)
    else:
        next_month = datetime(selected_year, selected_month + 1, 1, 0, 0, 0)
    end_date = next_month - timedelta(seconds=1)

    # Filter Status & Tipe
    selected_status = request.args.get('status_control', 'All')
    selected_type = request.args.get('maintenance_type', 'All')

    # Query Work Order
    query = WorkOrder.query
    if selected_site_id:
        query = query.join(Asset, WorkOrder.asset_id == Asset.id).filter(Asset.site_id == selected_site_id)

    # Filter rentang waktu berdasarkan tanggal realisasi / rencana / buat
    date_col = func.coalesce(WorkOrder.start_date, WorkOrder.suggested_start_date, WorkOrder.date_created)
    query = query.filter(date_col >= start_date, date_col <= end_date)

    if selected_status != 'All':
        query = query.join(WorkOrderStatus, WorkOrder.status_id == WorkOrderStatus.id).filter(WorkOrderStatus.control_type == selected_status)

    if selected_type != 'All':
        query = query.filter(WorkOrder.maintenance_type == selected_type)

    work_orders = query.order_by(date_col.asc(), WorkOrder.code.asc()).all()

    # Hitung ketersediaan foto untuk tiap WO
    wo_data = []
    for wo in work_orders:
        photo_count = 0
        procs = wo.procedures.all() if hasattr(wo.procedures, 'all') else list(wo.procedures)
        for proc in procs:
            if proc.attachment_path:
                paths = [p.strip() for p in proc.attachment_path.split('|') if p.strip()]
                if paths:
                    photo_count += 1
        if photo_count == 0 and hasattr(wo, 'attachments'):
            atts = wo.attachments.all() if hasattr(wo.attachments, 'all') else list(wo.attachments)
            for att in atts:
                if getattr(att, 'file_path', None) and att.file_path.strip():
                    photo_count += 1
        wo_data.append({
            'wo': wo,
            'photo_count': photo_count
        })

    # Data bulan & tahun untuk dropdown
    months = [
        (1, 'Januari'), (2, 'Februari'), (3, 'Maret'), (4, 'April'),
        (5, 'Mei'), (6, 'Juni'), (7, 'Juli'), (8, 'Agustus'),
        (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'Desember')
    ]
    years = list(range(now.year - 2, now.year + 3))

    # Bulan lalu shortcut
    if now.month == 1:
        last_month_num = 12
        last_month_year = now.year - 1
    else:
        last_month_num = now.month - 1
        last_month_year = now.year

    return render_template(
        'reports/monthly_wo_report.html',
        available_sites=available_sites,
        selected_site_id=selected_site_id,
        selected_month=selected_month,
        selected_year=selected_year,
        selected_status=selected_status,
        selected_type=selected_type,
        months=months,
        years=years,
        current_now=now,
        last_month_num=last_month_num,
        last_month_year=last_month_year,
        work_orders=work_orders,
        wo_data=wo_data
    )


@reports_bp.route('/wo_monthly/export_pdf', methods=['POST', 'GET'])
@login_required
def wo_monthly_export_pdf():
    """Menghasilkan file PDF Portrait Laporan Bulanan Work Order"""
    from flask import flash, redirect, url_for, current_app, Response
    from flask_login import current_user
    try:
        from monthly_wo_report_pdf import MonthlyWOReportPDF
    except ImportError as e:
        flash(f'Gagal memuat generator PDF: {e}. Silakan pastikan paket "fpdf2" sudah terinstall: pip install fpdf2', 'danger')
        return redirect(url_for('reports.wo_monthly_report', **request.args))

    # Ambil ID Work Order yang dipilih
    if request.method == 'POST':
        selected_wo_ids = request.form.getlist('selected_wo_ids')
        if not selected_wo_ids:
            raw_ids = request.form.get('wo_ids_str')
            if raw_ids:
                selected_wo_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
        include_cover = request.form.get('include_cover') == '1'
        site_id_req = request.form.get('site_id', type=int)
        period_str = request.form.get('period_str')
    else:
        selected_wo_ids = request.args.getlist('selected_wo_ids')
        raw_ids = request.args.get('wo_ids')
        if raw_ids:
            selected_wo_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
        include_cover = request.args.get('include_cover', '1') == '1'
        site_id_req = request.args.get('site_id', type=int)
        period_str = request.args.get('period_str')

    int_ids = [int(i) for i in selected_wo_ids if str(i).isdigit()]
    if not int_ids:
        flash('Silakan pilih minimal 1 Work Order untuk dibuatkan laporan PDF.', 'warning')
        return redirect(url_for('reports.wo_monthly_report', site_id=site_id_req))

    # Query WO yang dipilih dengan memperhatikan site user
    query = WorkOrder.query.filter(WorkOrder.id.in_(int_ids))
    if current_user.site_id and current_user.role != 'Supergod':
        query = query.join(Asset, WorkOrder.asset_id == Asset.id).filter(Asset.site_id == current_user.site_id)

    from sqlalchemy import func
    date_col = func.coalesce(WorkOrder.start_date, WorkOrder.suggested_start_date, WorkOrder.date_created)
    wos = query.order_by(date_col.asc(), WorkOrder.code.asc()).all()
    if not wos:
        flash('Tidak ada Work Order yang ditemukan atau Anda tidak memiliki akses.', 'danger')
        return redirect(url_for('reports.wo_monthly_report'))

    # Tentukan Nama Site untuk Cover & Header
    site_names = {w.asset.site.name for w in wos if w.asset and w.asset.site}
    if len(site_names) == 1:
        site_name = list(site_names)[0]
    elif site_names:
        site_name = "MULTI-SITE"
    else:
        site_name = "ALL SITES"

    if not period_str:
        period_str = datetime.now().strftime('%B %Y').upper()

    try:
        pdf_gen = MonthlyWOReportPDF(
            site_name=site_name,
            period_str=period_str,
            include_cover=include_cover,
            root_path=current_app.root_path
        )
        pdf_bytes = pdf_gen.build_pdf(wos)

        clean_site = site_name.replace(' ', '_').replace('/', '_')
        clean_period = period_str.replace(' ', '_').replace('/', '_')
        filename = f"Laporan_WO_Bulanan_{clean_site}_{clean_period}.pdf"

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Gagal membuat PDF Laporan Bulanan: {str(e)}', 'danger')
        return redirect(url_for('reports.wo_monthly_report', site_id=site_id_req))


@reports_bp.route('/wo_monthly/export_ppt', methods=['POST', 'GET'])
@login_required
def wo_monthly_export_ppt():
    """Menghasilkan file PowerPoint Portrait Laporan Bulanan Work Order"""
    from flask import flash, redirect, url_for, current_app, Response
    from flask_login import current_user
    try:
        from monthly_wo_report_ppt import MonthlyWOReportPPT
    except ImportError as e:
        flash(f'Gagal memuat generator PPTX: {e}. Silakan pastikan paket "python-pptx" sudah terinstall: pip install python-pptx', 'danger')
        return redirect(url_for('reports.wo_monthly_report', **request.args))

    # Ambil ID Work Order yang dipilih
    if request.method == 'POST':
        selected_wo_ids = request.form.getlist('selected_wo_ids')
        if not selected_wo_ids:
            raw_ids = request.form.get('wo_ids_str')
            if raw_ids:
                selected_wo_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
        include_cover = request.form.get('include_cover') == '1'
        site_id_req = request.form.get('site_id', type=int)
        period_str = request.form.get('period_str')
    else:
        selected_wo_ids = request.args.getlist('selected_wo_ids')
        raw_ids = request.args.get('wo_ids')
        if raw_ids:
            selected_wo_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
        include_cover = request.args.get('include_cover', '1') == '1'
        site_id_req = request.args.get('site_id', type=int)
        period_str = request.args.get('period_str')

    int_ids = [int(i) for i in selected_wo_ids if str(i).isdigit()]
    if not int_ids:
        flash('Silakan pilih minimal 1 Work Order untuk dibuatkan laporan PowerPoint.', 'warning')
        return redirect(url_for('reports.wo_monthly_report', site_id=site_id_req))

    # Query WO yang dipilih dengan memperhatikan site user
    query = WorkOrder.query.filter(WorkOrder.id.in_(int_ids))
    if current_user.site_id and current_user.role != 'Supergod':
        query = query.join(Asset, WorkOrder.asset_id == Asset.id).filter(Asset.site_id == current_user.site_id)

    from sqlalchemy import func
    date_col = func.coalesce(WorkOrder.start_date, WorkOrder.suggested_start_date, WorkOrder.date_created)
    wos = query.order_by(date_col.asc(), WorkOrder.code.asc()).all()
    if not wos:
        flash('Tidak ada Work Order yang ditemukan atau Anda tidak memiliki akses.', 'danger')
        return redirect(url_for('reports.wo_monthly_report'))

    # Tentukan Nama Site untuk Cover & Header
    site_names = {w.asset.site.name for w in wos if w.asset and w.asset.site}
    if len(site_names) == 1:
        site_name = list(site_names)[0]
    elif site_names:
        site_name = "MULTI-SITE"
    else:
        site_name = "ALL SITES"

    if not period_str:
        period_str = datetime.now().strftime('%B %Y').upper()

    try:
        ppt_gen = MonthlyWOReportPPT(
            site_name=site_name,
            period_str=period_str,
            include_cover=include_cover,
            root_path=current_app.root_path
        )
        ppt_io = ppt_gen.build_ppt(wos)

        clean_site = site_name.replace(' ', '_').replace('/', '_')
        clean_period = period_str.replace(' ', '_').replace('/', '_')
        filename = f"Laporan_WO_Bulanan_{clean_site}_{clean_period}.pptx"

        return Response(
            ppt_io.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Gagal membuat PowerPoint Laporan Bulanan: {str(e)}', 'danger')
        return redirect(url_for('reports.wo_monthly_report', site_id=site_id_req))


