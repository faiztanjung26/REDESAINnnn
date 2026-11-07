from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from models import db, MaterialRequisition, MaterialRequisitionItem, MaterialRequisitionLog, Site, Part, StockLevel, StockTransaction, User
from datetime import datetime, date
import json

ppm_bp = Blueprint('ppm', __name__, url_prefix='/warehouse/ppm')

def log_ppm_activity(ppm_id, action, notes=None, user_id=None):
    try:
        uid = user_id or (current_user.id if current_user.is_authenticated else None)
        log_entry = MaterialRequisitionLog(
            requisition_id=ppm_id,
            user_id=uid,
            action=action,
            notes=notes
        )
        db.session.add(log_entry)
    except Exception as e:
        print(f"Error logging PPM activity: {e}")

def int_to_roman(n):
    roman_numerals = {
        1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI',
        7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X', 11: 'XI', 12: 'XII'
    }
    return roman_numerals.get(n, str(n))

def generate_ppm_number(site_id, division_code, req_date=None):
    if not req_date:
        req_date = date.today()
        
    year = req_date.year
    month_roman = int_to_roman(req_date.month)
    
    site = Site.query.get(site_id) if site_id else None
    site_code = "JTI"
    if site:
        if site.project_code:
            site_code = site.project_code.split('.')[0] if '.' in site.project_code else site.project_code
        elif "MRT" in site.name.upper():
            site_code = "MRT"
        else:
            # take first letters of site name words (max 4)
            site_code = "".join([w[0] for w in site.name.split() if w])[:4].upper()
            
    div_code = division_code.upper() if division_code else "OT"
    
    # Count existing requisitions for this site and year
    count = MaterialRequisition.query.filter(
        MaterialRequisition.site_id == site_id,
        db.extract('year', MaterialRequisition.request_date) == year
    ).count() + 1
    
    seq_str = str(count).zfill(3)
    return f"{seq_str}/{site_code}/{div_code}/{month_roman}/{year}"

@ppm_bp.route('/')
@login_required
def index():
    site_id = request.args.get('site_id', type=int)
    status = request.args.get('status')
    division = request.args.get('division')
    delivery_type = request.args.get('delivery_type')
    q = request.args.get('q', '').strip()
    
    query = MaterialRequisition.query
    
    if current_user.site_id:
        query = query.filter(MaterialRequisition.site_id == current_user.site_id)
        sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        if site_id:
            query = query.filter(MaterialRequisition.site_id == site_id)
        sites = Site.query.all()
        
    if status:
        query = query.filter(MaterialRequisition.status == status)
    if division:
        query = query.filter(MaterialRequisition.category_division == division)
    if delivery_type:
        query = query.filter(MaterialRequisition.delivery_type == delivery_type)
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            db.or_(
                MaterialRequisition.requisition_no.ilike(search_pattern),
                MaterialRequisition.project_code.ilike(search_pattern),
                MaterialRequisition.drawing_ref.ilike(search_pattern),
                MaterialRequisition.items.any(MaterialRequisitionItem.item_name.ilike(search_pattern))
            )
        )
        
    # Visibility isolation: Drafts are ONLY visible to their creator (unless Admin)
    if current_user.role != 'Admin':
        query = query.filter(
            db.or_(
                MaterialRequisition.status != 'Draft',
                MaterialRequisition.requester_id == current_user.id
            )
        )
        
    ppms = query.order_by(MaterialRequisition.created_at.desc()).all()
    
    # Metrics calculation
    base_metric_query = MaterialRequisition.query
    if current_user.site_id:
        base_metric_query = base_metric_query.filter(MaterialRequisition.site_id == current_user.site_id)
    if current_user.role != 'Admin':
        base_metric_query = base_metric_query.filter(
            db.or_(
                MaterialRequisition.status != 'Draft',
                MaterialRequisition.requester_id == current_user.id
            )
        )
        
    total_count = base_metric_query.count()
    pending_approval_count = base_metric_query.filter(MaterialRequisition.status == 'Submitted').count()
    purchasing_count = base_metric_query.filter(MaterialRequisition.status.in_(['Approved', 'Purchasing'])).count()
    transit_count = base_metric_query.filter(MaterialRequisition.status.in_(['Arrived_JTI', 'Shipped_to_Site'])).count()
    completed_count = base_metric_query.filter(MaterialRequisition.status == 'Received_Site').count()
    hold_count = base_metric_query.filter(MaterialRequisition.status == 'On_Hold').count()
    
    return render_template(
        'warehouse/ppm/index.html',
        ppms=ppms,
        sites=sites,
        selected_site_id=site_id,
        selected_status=status,
        selected_division=division,
        selected_delivery=delivery_type,
        q=q,
        metrics={
            'total': total_count,
            'pending_approval': pending_approval_count,
            'purchasing': purchasing_count,
            'transit': transit_count,
            'completed': completed_count,
            'hold': hold_count
        }
    )

@ppm_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        site_id = request.form.get('site_id', type=int)
        requisition_no = request.form.get('requisition_no', '').strip()
        request_date_str = request.form.get('request_date')
        category_division = request.form.get('category_division', 'OT')
        delivery_type = request.form.get('delivery_type', 'DIRECT_SITE')
        drawing_ref = request.form.get('drawing_ref', '').strip()
        is_draft = request.form.get('is_draft') == '1'
        requester_signature = request.form.get('requester_signature', '').strip()
        
        # Enforce site security
        if current_user.site_id and site_id != current_user.site_id:
            flash('Akses ditolak: Site tidak sesuai.', 'danger')
            return redirect(url_for('ppm.create'))
            
        if not site_id:
            flash('Harap pilih Proyek / Site.', 'danger')
            return redirect(url_for('ppm.create'))
            
        # Signature validation if submitting directly
        if not is_draft and (not requester_signature or len(requester_signature) < 50):
            flash('Tanda tangan digital pemohon wajib diisi sebelum mengajukan PPM. Anda dapat memilih "Simpan sebagai Draft" jika belum siap tanda tangan.', 'warning')
            return redirect(url_for('ppm.create'))
            
        site = Site.query.get(site_id)
        project_code = site.project_code if site and site.project_code else request.form.get('project_code', '')
        
        # Request date parsing
        req_date = datetime.strptime(request_date_str, '%Y-%m-%d').date() if request_date_str else date.today()
        
        if not requisition_no:
            requisition_no = generate_ppm_number(site_id, category_division, req_date)
            
        # Check duplicate requisition_no
        existing = MaterialRequisition.query.filter_by(requisition_no=requisition_no).first()
        if existing:
            requisition_no = f"{requisition_no}-{int(datetime.now().timestamp()) % 1000}"
            
        has_valid_sig = bool(requester_signature and len(requester_signature) >= 50)
        new_ppm = MaterialRequisition(
            requisition_no=requisition_no,
            request_date=req_date,
            site_id=site_id,
            project_code=project_code,
            category_division=category_division,
            delivery_type=delivery_type,
            drawing_ref=drawing_ref,
            status='Draft' if is_draft else 'Submitted',
            requester_id=current_user.id,
            requester_signature=requester_signature if has_valid_sig else None,
            requester_signed_at=datetime.utcnow() if has_valid_sig else None
        )
        db.session.add(new_ppm)
        db.session.flush() # get new_ppm.id
        
        # Process items
        item_names = request.form.getlist('item_name[]')
        part_ids = request.form.getlist('part_id[]')
        sizes = request.form.getlist('size_capacity[]')
        specs = request.form.getlist('spec_brand[]')
        quantities = request.form.getlist('quantity[]')
        units = request.form.getlist('unit[]')
        target_dates = request.form.getlist('target_date[]')
        notes_list = request.form.getlist('notes[]')
        
        valid_items_count = 0
        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ''
            if not name:
                continue
                
            p_id = int(part_ids[i]) if (i < len(part_ids) and part_ids[i] and part_ids[i].isdigit()) else None
            size_cap = sizes[i].strip() if i < len(sizes) else ''
            spec = specs[i].strip() if i < len(specs) else ''
            
            try:
                qty = float(quantities[i]) if i < len(quantities) else 1.0
            except (ValueError, TypeError):
                qty = 1.0
                
            unit_val = units[i].strip() if i < len(units) and units[i] else 'Pcs'
            
            t_date = None
            if i < len(target_dates) and target_dates[i]:
                try:
                    t_date = datetime.strptime(target_dates[i], '%Y-%m-%d').date()
                except ValueError:
                    t_date = None
                    
            item_note = notes_list[i].strip() if i < len(notes_list) else ''
            
            # Check current stock at site
            stock_qty = 0
            if p_id:
                stock_record = StockLevel.query.filter_by(part_id=p_id, site_id=site_id).first()
                if stock_record:
                    stock_qty = stock_record.qty_on_hand
            else:
                # search by name if matches existing Part
                matching_part = Part.query.filter(Part.name.ilike(name)).first()
                if matching_part:
                    p_id = matching_part.id
                    stock_record = StockLevel.query.filter_by(part_id=p_id, site_id=site_id).first()
                    if stock_record:
                        stock_qty = stock_record.qty_on_hand
                        
            item_obj = MaterialRequisitionItem(
                requisition_id=new_ppm.id,
                part_id=p_id,
                item_name=name,
                size_capacity=size_cap,
                spec_brand=spec,
                quantity=qty,
                unit=unit_val,
                target_date=t_date,
                warehouse_stock=stock_qty,
                notes=item_note,
                purchase_status='Pending'
            )
            db.session.add(item_obj)
            valid_items_count += 1
            
        if valid_items_count == 0:
            db.session.rollback()
            flash('Harap masukkan minimal 1 baris item material.', 'danger')
            return redirect(url_for('ppm.create'))
            
        # Log initial creation activity
        if is_draft:
            log_ppm_activity(
                new_ppm.id,
                'Draft Dibuat',
                'Dokumen disimpan sebagai draft dan bersifat privat (hanya dapat dilihat oleh pembuat).'
            )
            flash('Draft PPM berhasil disimpan. Dokumen ini bersifat privat dan hanya dapat dilihat oleh Anda sampai diajukan.', 'info')
        else:
            log_ppm_activity(
                new_ppm.id,
                'PPM Diajukan',
                'PPM ditandatangani secara digital dan diajukan ke Supervisor.'
            )
            flash(f'PPM {new_ppm.requisition_no} berhasil dibuat dan diajukan ke Supervisor.', 'success')
            
        db.session.commit()
        return redirect(url_for('ppm.view', id=new_ppm.id))
        
    # GET method
    if current_user.site_id:
        sites = Site.query.filter_by(id=current_user.site_id).all()
        selected_site = sites[0] if sites else None
    else:
        sites = Site.query.all()
        selected_site = sites[0] if sites else None
        
    parts = Part.query.order_by(Part.name.asc()).all()
    today_str = date.today().strftime('%Y-%m-%d')
    
    # Generate initial sample number
    initial_ppm_no = ""
    if selected_site:
        initial_ppm_no = generate_ppm_number(selected_site.id, 'OT', date.today())
        
    return render_template(
        'warehouse/ppm/create.html',
        sites=sites,
        selected_site=selected_site,
        parts=parts,
        today_str=today_str,
        initial_ppm_no=initial_ppm_no
    )

@ppm_bp.route('/<int:id>')
@login_required
def view(id):
    ppm = MaterialRequisition.query.get_or_404(id)
    if current_user.site_id and ppm.site_id != current_user.site_id:
        flash('Akses ditolak: Dokumen PPM milik site lain.', 'danger')
        return redirect(url_for('ppm.index'))
        
    # Draft privacy protection
    if ppm.status == 'Draft' and ppm.requester_id != current_user.id and current_user.role != 'Admin':
        flash('Akses ditolak: Dokumen Draft ini bersifat privat dan hanya dapat dilihat oleh pembuatnya.', 'warning')
        return redirect(url_for('ppm.index'))
        
    return render_template('warehouse/ppm/view.html', ppm=ppm)

@ppm_bp.route('/<int:id>/submit', methods=['POST'])
@login_required
def submit_draft(id):
    ppm = MaterialRequisition.query.get_or_404(id)
    if current_user.site_id and ppm.site_id != current_user.site_id:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('ppm.index'))
        
    # Only requester or Admin can submit draft
    if ppm.requester_id != current_user.id and current_user.role != 'Admin':
        flash('Akses ditolak: Hanya pembuat yang dapat mengajukan draft PPM ini.', 'danger')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    if ppm.status != 'Draft':
        flash('PPM sudah diajukan sebelumnya.', 'info')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    signature = request.form.get('requester_signature', '').strip()
    if not signature or len(signature) < 50:
        if not ppm.requester_signature:
            flash('Tanda tangan digital pemohon wajib diisi sebelum mengajukan PPM.', 'danger')
            return redirect(url_for('ppm.view', id=ppm.id))
    else:
        ppm.requester_signature = signature
        ppm.requester_signed_at = datetime.utcnow()
        
    ppm.status = 'Submitted'
    log_ppm_activity(ppm.id, 'PPM Diajukan', 'Draft PPM telah ditandatangani secara digital dan diajukan ke Supervisor.')
    db.session.commit()
    flash(f'PPM {ppm.requisition_no} berhasil diajukan ke Supervisor.', 'success')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/approve', methods=['POST'])
@login_required
def approve(id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Akses ditolak: Hanya Admin atau Supervisor yang dapat menyetujui PPM.', 'danger')
        return redirect(url_for('ppm.view', id=id))
        
    ppm = MaterialRequisition.query.get_or_404(id)
    supervisor_signature = request.form.get('supervisor_signature', '').strip()
    supervisor_notes = request.form.get('supervisor_notes', '').strip()
    
    if not supervisor_signature or len(supervisor_signature) < 50:
        flash('Tanda tangan digital Supervisor wajib diisi untuk persetujuan.', 'danger')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    ppm.status = 'Approved'
    ppm.supervisor_id = current_user.id
    ppm.supervisor_signature = supervisor_signature
    ppm.supervisor_signed_at = datetime.utcnow()
    ppm.supervisor_notes = supervisor_notes
    
    # Auto mark items as approved
    for item in ppm.items:
        if item.purchase_status == 'Pending':
            item.purchase_status = 'Approved for PO'
            
    log_ppm_activity(
        ppm.id,
        'Disetujui Supervisor',
        f'PPM disetujui oleh {current_user.name}. Catatan: {supervisor_notes}' if supervisor_notes else f'PPM disetujui oleh {current_user.name}.'
    )
    db.session.commit()
    flash(f'PPM {ppm.requisition_no} berhasil disetujui dan diteruskan ke Pengadaan (Purchasing).', 'success')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/reject', methods=['POST'])
@login_required
def reject(id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Akses ditolak: Hanya Admin atau Supervisor yang dapat menolak PPM.', 'danger')
        return redirect(url_for('ppm.view', id=id))
        
    ppm = MaterialRequisition.query.get_or_404(id)
    reason = request.form.get('reject_reason', '').strip()
    
    if not reason:
        flash('Harap masukkan alasan penolakan.', 'warning')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    ppm.status = 'Rejected'
    ppm.supervisor_id = current_user.id
    ppm.supervisor_notes = reason
    ppm.supervisor_signed_at = datetime.utcnow()
    
    log_ppm_activity(
        ppm.id,
        'Ditolak Supervisor',
        f'PPM ditolak oleh {current_user.name}. Alasan: {reason}'
    )
    db.session.commit()
    flash(f'PPM {ppm.requisition_no} telah ditolak.', 'warning')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/update-purchasing', methods=['POST'])
@login_required
def update_purchasing(id):
    if current_user.role not in ['Admin', 'Supervisor']:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('ppm.view', id=id))
        
    ppm = MaterialRequisition.query.get_or_404(id)
    po_number = request.form.get('po_number', '').strip()
    purchasing_notes = request.form.get('purchasing_notes', '').strip()
    
    ppm.po_number = po_number
    ppm.purchasing_notes = purchasing_notes
    ppm.status = 'Purchasing'
    
    # Update individual items status
    for item in ppm.items:
        item_status = request.form.get(f'item_status_{item.id}')
        if item_status:
            item.purchase_status = item_status
        else:
            item.purchase_status = 'In PO Process'
            
    log_ppm_activity(
        ppm.id,
        'Update Purchasing',
        f'No. PO: {po_number}. Catatan: {purchasing_notes}' if po_number else f'Catatan: {purchasing_notes}'
    )
    db.session.commit()
    flash('Informasi pengadaan/pembelian berhasil diperbarui.', 'success')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/receive-jti', methods=['POST'])
@login_required
def receive_jti(id):
    ppm = MaterialRequisition.query.get_or_404(id)
    if ppm.delivery_type != 'VIA_JTI':
        flash('PPM ini memiliki jalur pengiriman langsung ke Site.', 'warning')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    notes = request.form.get('jti_notes', '').strip()
    ppm.status = 'Arrived_JTI'
    ppm.jti_receiver_id = current_user.id
    ppm.jti_received_at = datetime.utcnow()
    ppm.jti_notes = notes
    
    # Handle JTI Photo Proof
    jti_photo = request.files.get('jti_photo')
    if jti_photo and jti_photo.filename:
        import os
        from werkzeug.utils import secure_filename
        from flask import current_app
        filename = secure_filename(jti_photo.filename)
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'warehouse', 'ppm')
        os.makedirs(upload_folder, exist_ok=True)
        photo_name = f"jti_{ppm.id}_{int(datetime.now().timestamp())}_{filename}"
        jti_photo.save(os.path.join(upload_folder, photo_name))
        ppm.jti_receiver_photo = photo_name
    
    for item in ppm.items:
        qty_received = request.form.get(f'qty_received_jti_{item.id}')
        if qty_received:
            try:
                item.qty_received_jti = float(qty_received)
            except ValueError:
                item.qty_received_jti = item.quantity
        else:
            item.qty_received_jti = item.quantity
        item.purchase_status = 'Arrived at JTI Warehouse'
        
    log_ppm_activity(
        ppm.id,
        'Tiba di Gudang JTI (QC)',
        f'Material tiba di Gudang/Workshop JTI (dikonfirmasi oleh {current_user.name}). Catatan: {notes}' if notes else f'Material tiba di Gudang/Workshop JTI (dikonfirmasi oleh {current_user.name}).'
    )
    db.session.commit()
    flash('Barang berhasil dicatat tiba di Gudang/Workshop JTI (Tahap Staging/QC).', 'success')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/dispatch-site', methods=['POST'])
@login_required
def dispatch_site(id):
    ppm = MaterialRequisition.query.get_or_404(id)
    ppm.status = 'Shipped_to_Site'
    
    for item in ppm.items:
        item.purchase_status = 'In Transit to Site'
        
    log_ppm_activity(
        ppm.id,
        'Pengiriman ke Site',
        f'Material diberangkatkan menuju Site {ppm.site.name} oleh {current_user.name}.'
    )
    db.session.commit()
    flash(f'Material telah diberangkatkan dan dalam pengiriman menuju Site {ppm.site.name}.', 'info')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/receive-site', methods=['POST'])
@login_required
def receive_site(id):
    ppm = MaterialRequisition.query.get_or_404(id)
    if current_user.site_id and ppm.site_id != current_user.site_id:
        flash('Akses ditolak: Konfirmasi terima barang harus dilakukan oleh tim di site bersangkutan.', 'danger')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    site_receiver_signature = request.form.get('site_receiver_signature', '').strip()
    site_notes = request.form.get('site_notes', '').strip()
    auto_restock = request.form.get('auto_restock') == '1'
    
    if not site_receiver_signature or len(site_receiver_signature) < 50:
        flash('Tanda tangan digital penerima di site wajib diisi.', 'danger')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    # Handle Site Photo Proof
    receiver_photo = request.files.get('receiver_photo')
    if receiver_photo and receiver_photo.filename:
        import os
        from werkzeug.utils import secure_filename
        from flask import current_app
        filename = secure_filename(receiver_photo.filename)
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'warehouse', 'ppm')
        os.makedirs(upload_folder, exist_ok=True)
        photo_name = f"site_{ppm.id}_{int(datetime.now().timestamp())}_{filename}"
        receiver_photo.save(os.path.join(upload_folder, photo_name))
        ppm.site_receiver_photo = photo_name
        
    ppm.status = 'Received_Site'
    ppm.site_receiver_id = current_user.id
    ppm.site_receiver_signature = site_receiver_signature
    ppm.site_received_at = datetime.utcnow()
    ppm.site_notes = site_notes
    
    # Auto-restock to StockLevel and create StockTransaction
    restocked_count = 0
    if auto_restock:
        base_tx_code = f"TRX-PPM-{ppm.id}-{int(datetime.now().timestamp())}"
        
        for index, item in enumerate(ppm.items):
            qty_rec = request.form.get(f'qty_received_site_{item.id}')
            try:
                received_qty = float(qty_rec) if qty_rec else item.quantity
            except ValueError:
                received_qty = item.quantity
                
            item.qty_received_site = received_qty
            item.purchase_status = 'Received at Site (Restocked)'
            
            # Check or create Part
            target_part = item.part
            if not target_part:
                # Find part by exact name or create new
                target_part = Part.query.filter(Part.name == item.item_name).first()
                if not target_part:
                    clean_code = f"PRT-{ppm.site.id}-{int(datetime.now().timestamp()) % 10000}-{index+1}"
                    target_part = Part(
                        name=item.item_name,
                        code=clean_code,
                        unit=item.unit,
                        site_id=ppm.site_id
                    )
                    db.session.add(target_part)
                    db.session.flush()
                item.part_id = target_part.id
                
            # Update StockLevel
            stock = StockLevel.query.filter_by(part_id=target_part.id, site_id=ppm.site_id).first()
            qty_before = 0
            if stock:
                qty_before = stock.qty_on_hand
                stock.qty_on_hand = qty_before + int(received_qty)
                stock.last_restock_date = date.today()
                stock.pic_id = current_user.id
                stock.source_from = f"PPM {ppm.requisition_no}"
            else:
                stock = StockLevel(
                    part_id=target_part.id,
                    site_id=ppm.site_id,
                    qty_on_hand=int(received_qty),
                    last_restock_date=date.today(),
                    pic_id=current_user.id,
                    source_from=f"PPM {ppm.requisition_no}"
                )
                db.session.add(stock)
                
            qty_after = stock.qty_on_hand
            
            # Record StockTransaction
            tx = StockTransaction(
                transaction_code=f"{base_tx_code}-{index+1}",
                part_id=target_part.id,
                site_id=ppm.site_id,
                user_id=current_user.id,
                action='INCOMING_PPM',
                qty_before=qty_before,
                qty_after=qty_after,
                qty_change=int(received_qty),
                source_from=f"PPM {ppm.requisition_no}",
                notes=f"Penerimaan material PPM {ppm.requisition_no}. Proyek: {ppm.site.name}"
            )
            db.session.add(tx)
            restocked_count += 1
            
    log_ppm_activity(
        ppm.id,
        'Diterima di Site',
        f'Material diterima di site dengan tanda tangan digital oleh {current_user.name}. {restocked_count} item otomatis ditambahkan ke stok gudang.'
    )
    db.session.commit()
    flash(f'Penerimaan material PPM {ppm.requisition_no} berhasil dikonfirmasi dan {restocked_count} item telah otomatis ditambahkan ke stok gudang!', 'success')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/hold', methods=['POST'])
@login_required
def hold(id):
    if current_user.role != 'Admin':
        flash('Akses ditolak: Hanya Admin yang dapat menahan (Hold) proses PPM.', 'danger')
        return redirect(url_for('ppm.view', id=id))
        
    ppm = MaterialRequisition.query.get_or_404(id)
    if ppm.status in ['Received_Site', 'Rejected', 'Cancelled', 'On_Hold']:
        flash(f'PPM dalam status {ppm.status} tidak dapat ditahan.', 'warning')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    hold_reason = request.form.get('hold_reason', '').strip()
    if not hold_reason:
        flash('Alasan penahanan (Hold) proses PPM wajib diisi.', 'danger')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    ppm.previous_status = ppm.status
    ppm.status = 'On_Hold'
    ppm.hold_reason = hold_reason
    ppm.held_by_id = current_user.id
    ppm.held_at = datetime.utcnow()
    
    log_ppm_activity(
        ppm.id,
        'PPM Ditahan (On Hold)',
        f'Proses PPM ditahan oleh Admin ({current_user.name}). Alasan: {hold_reason}'
    )
    db.session.commit()
    flash(f'PPM {ppm.requisition_no} berhasil ditahan (On Hold).', 'warning')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/unhold', methods=['POST'])
@login_required
def unhold(id):
    if current_user.role != 'Admin':
        flash('Akses ditolak: Hanya Admin yang dapat melanjutkan kembali proses PPM.', 'danger')
        return redirect(url_for('ppm.view', id=id))
        
    ppm = MaterialRequisition.query.get_or_404(id)
    if ppm.status != 'On_Hold':
        flash('PPM ini tidak sedang dalam status Ditahan (On Hold).', 'info')
        return redirect(url_for('ppm.view', id=ppm.id))
        
    resume_notes = request.form.get('resume_notes', '').strip()
    target_status = ppm.previous_status or 'Submitted'
    ppm.status = target_status
    
    note_msg = f'Penahanan dicabut dan proses PPM dilanjutkan kembali ke status {target_status} oleh Admin ({current_user.name}).'
    if resume_notes:
        note_msg += f' Catatan: {resume_notes}'
        
    log_ppm_activity(
        ppm.id,
        'PPM Dilanjutkan (Resumed)',
        note_msg
    )
    ppm.hold_reason = None
    db.session.commit()
    flash(f'PPM {ppm.requisition_no} telah dilanjutkan kembali (Status: {target_status}).', 'success')
    return redirect(url_for('ppm.view', id=ppm.id))

@ppm_bp.route('/<int:id>/print')
@login_required
def print_doc(id):
    ppm = MaterialRequisition.query.get_or_404(id)
    if current_user.site_id and ppm.site_id != current_user.site_id:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('ppm.index'))
        
    return render_template('warehouse/ppm/print.html', ppm=ppm)

# API Endpoints
@ppm_bp.route('/api/check-stock')
@login_required
def check_stock_api():
    part_id = request.args.get('part_id', type=int)
    site_id = request.args.get('site_id', type=int)
    
    if not part_id or not site_id:
        return jsonify({'stock': 0, 'unit': 'Pcs', 'found': False})
        
    part = Part.query.get(part_id)
    if not part:
        return jsonify({'stock': 0, 'unit': 'Pcs', 'found': False})
        
    stock = StockLevel.query.filter_by(part_id=part_id, site_id=site_id).first()
    stock_qty = stock.qty_on_hand if stock else 0
    
    return jsonify({
        'found': True,
        'part_id': part.id,
        'part_name': part.name,
        'part_code': part.code,
        'unit': part.unit or 'Pcs',
        'stock': stock_qty
    })

@ppm_bp.route('/api/generate-no')
@login_required
def generate_no_api():
    site_id = request.args.get('site_id', type=int)
    division = request.args.get('division', 'OT')
    date_str = request.args.get('date')
    
    req_date = date.today()
    if date_str:
        try:
            req_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
            
    ppm_no = generate_ppm_number(site_id, division, req_date)
    return jsonify({'ppm_no': ppm_no})
