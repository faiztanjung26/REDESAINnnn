from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, send_file
from flask_login import login_required, current_user
from models import db, Part, StockLevel, Site, Category
import io
import pandas as pd
from datetime import datetime, date

warehouse_bp = Blueprint('warehouse', __name__, url_prefix='/warehouse')

@warehouse_bp.route('/')
@login_required
def index():
    if current_user.site_id:
        sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        sites = Site.query.all()
    return render_template('warehouse/index.html', sites=sites)

@warehouse_bp.route('/site/<int:site_id>/inventory')
@login_required
def site_inventory(site_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    site = Site.query.get_or_404(site_id)
    
    parts_stocks = db.session.query(Part, StockLevel).join(StockLevel).filter(
        StockLevel.site_id == site_id
    ).all()
    return render_template('warehouse/site_parts.html', site=site, parts=parts_stocks)

@warehouse_bp.route('/add_master_part')
@login_required
def add_master_part():
    site_id = request.args.get('site_id')
    category_id = request.args.get('category_id')
    
    query = Part.query
    category = None
    if category_id:
        query = query.filter_by(category_id=category_id)
        category = Category.query.get(category_id)
        
    if site_id:
        subquery = db.session.query(StockLevel.part_id).filter_by(site_id=site_id)
        query = query.filter(~Part.id.in_(subquery))
        
    parts = query.all()
    return render_template('warehouse/add_to_warehouse.html', parts=parts, site_id=site_id, category_id=category_id, category=category)

@warehouse_bp.route('/stock/<int:part_id>/adjust', methods=['GET', 'POST'])
@login_required
def adjust_stock(part_id):
    part = Part.query.get_or_404(part_id)
    
    if request.method == 'POST':
        import os
        from werkzeug.utils import secure_filename
        from flask import current_app
        from models import StockTransaction
        site_id = request.form.get('site_id')
        qty = int(request.form.get('qty', 0))
        min_qty = int(request.form.get('min_qty', 0))
        aisle = request.form.get('aisle')
        bin_number = request.form.get('bin_number')
        row = request.form.get('row')
        
        action = request.form.get('action', 'adjust')
        source_from = request.form.get('source_from')
        
        last_restock_date_str = request.form.get('last_restock_date')
        last_restock_date = None
        if last_restock_date_str:
            from datetime import datetime
            last_restock_date = datetime.strptime(last_restock_date_str, '%Y-%m-%d').date()
        
        # Enforce site security on POST
        if current_user.site_id and str(site_id) != str(current_user.site_id):
            flash('Access denied. Cannot adjust stock for another site.', 'danger')
            return redirect(url_for('warehouse.adjust_stock', part_id=part_id))
            
        attachment = request.files.get('proof_attachment')
        attachment_path = None
        if attachment and attachment.filename:
            filename = secure_filename(attachment.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'warehouse')
            os.makedirs(upload_folder, exist_ok=True)
            attachment_path = f"{int(datetime.now().timestamp())}_{filename}"
            attachment.save(os.path.join(upload_folder, attachment_path))
            
        stock = StockLevel.query.filter_by(part_id=part_id, site_id=site_id).first()
        qty_before = 0
        if stock:
            qty_before = stock.qty_on_hand
            # Update existing stock location
            if action == 'adjust':
                stock.qty_on_hand = qty_before + qty
            else:
                stock.qty_on_hand = qty
            
            stock.min_qty = min_qty
            stock.aisle = aisle
            stock.bin_number = bin_number
            stock.row = row
            if last_restock_date:
                stock.last_restock_date = last_restock_date
            stock.pic_id = current_user.id
            if source_from:
                stock.source_from = source_from
            if attachment_path:
                stock.attachment_path = attachment_path
        else:
            # Create new stock level entry
            stock = StockLevel(
                part_id=part_id, site_id=site_id, qty_on_hand=qty, min_qty=min_qty,
                aisle=aisle, bin_number=bin_number, row=row,
                last_restock_date=last_restock_date, pic_id=current_user.id if action != 'add' else None,
                attachment_path=attachment_path, source_from=source_from
            )
            db.session.add(stock)
            
        qty_after = stock.qty_on_hand
        qty_change = qty_after - qty_before
        
        # Generate transaction code
        from datetime import datetime
        tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        transaction = StockTransaction(
            transaction_code=tx_code,
            part_id=part_id,
            site_id=site_id,
            user_id=current_user.id,
            action=action.upper(),
            qty_before=qty_before,
            qty_after=qty_after,
            qty_change=qty_change,
            source_from=source_from if action == 'add' else None,
            attachment_path=attachment_path
        )
        db.session.add(transaction)
            
        db.session.commit()
        flash(f'Stock adjusted for {part.name} at selected site!', 'success')
        return redirect(url_for('warehouse.index'))
        
    if current_user.site_id:
        sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        sites = Site.query.all()
        
    site_id_arg = request.args.get('site_id')
    action_arg = request.args.get('action', 'adjust')
    from datetime import date
    today_date = date.today().strftime('%Y-%m-%d')
        
    # passing existing stock info to the template if it exists
    stock_levels = StockLevel.query.filter_by(part_id=part_id).all()
    
    # Get current stock for prefilling
    target_site_id = site_id_arg or current_user.site_id
    current_stock = None
    if target_site_id:
        current_stock = StockLevel.query.filter_by(part_id=part_id, site_id=target_site_id).first()
    
    # Get distinct source_from for datalist
    sources = db.session.query(StockLevel.source_from).filter(StockLevel.source_from.isnot(None)).distinct().all()
    source_list = [s[0] for s in sources]
    
    return render_template('warehouse/adjust_stock.html', part=part, sites=sites, stock_levels=stock_levels, site_id_arg=site_id_arg, action=action_arg, today_date=today_date, source_list=source_list, current_stock=current_stock)

@warehouse_bp.route('/site/<int:site_id>/incoming', methods=['GET', 'POST'])
@login_required
def incoming_goods(site_id):
    site = Site.query.get_or_404(site_id)
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    categories = Category.query.all()
    
    if request.method == 'POST':
        import os
        from werkzeug.utils import secure_filename
        from flask import current_app
        from models import StockTransaction
        from datetime import datetime
        
        # Get form data
        part_name = request.form.get('part_name')
        part_code = request.form.get('part_code')
        category_id = request.form.get('category_id')
        unit = request.form.get('unit')
        price = float(request.form.get('price', 0))
        qty = int(request.form.get('qty', 0))
        source_from = request.form.get('source_from')
        
        last_restock_date_str = request.form.get('last_restock_date')
        last_restock_date = datetime.strptime(last_restock_date_str, '%Y-%m-%d').date() if last_restock_date_str else datetime.now().date()
        
        # Validate part code uniqueness
        existing_part = Part.query.filter_by(code=part_code).first()
        if existing_part:
            flash(f'Part Code {part_code} already exists!', 'danger')
            return redirect(request.url)
            
        # Handle Attachment
        attachment = request.files.get('proof_attachment')
        attachment_path = None
        if attachment and attachment.filename:
            filename = secure_filename(attachment.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'warehouse')
            os.makedirs(upload_folder, exist_ok=True)
            attachment_path = f"{int(datetime.now().timestamp())}_{filename}"
            attachment.save(os.path.join(upload_folder, attachment_path))
            
        # Create Part
        new_part = Part(
            name=part_name,
            code=part_code,
            category_id=category_id if category_id else None,
            unit=unit,
            price=price,
            site_id=site_id
        )
        db.session.add(new_part)
        db.session.flush() # get ID
        
        # Create StockLevel
        stock = StockLevel(
            part_id=new_part.id,
            site_id=site_id,
            qty_on_hand=qty,
            last_restock_date=last_restock_date,
            pic_id=current_user.id,
            attachment_path=attachment_path,
            source_from=source_from
        )
        db.session.add(stock)
        
        # Create Transaction
        tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        transaction = StockTransaction(
            transaction_code=tx_code,
            part_id=new_part.id,
            site_id=site_id,
            user_id=current_user.id,
            action='INCOMING',
            qty_before=0,
            qty_after=qty,
            qty_change=qty,
            source_from=source_from,
            attachment_path=attachment_path
        )
        db.session.add(transaction)
        
        db.session.commit()
        flash(f'Incoming goods {part_name} successfully added!', 'success')
        return redirect(url_for('warehouse.site_inventory', site_id=site_id))
        
    # Get distinct source_from for datalist
    sources = db.session.query(StockLevel.source_from).filter(StockLevel.source_from.isnot(None)).distinct().all()
    source_list = [s[0] for s in sources]
    from datetime import date
    
    return render_template('warehouse/incoming_goods.html', site=site, categories=categories, source_list=source_list, today_date=date.today().strftime('%Y-%m-%d'))
@warehouse_bp.route('/site/<int:site_id>/transactions')
@login_required
def site_transactions(site_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    site = Site.query.get_or_404(site_id)
    
    from models import StockTransaction
    from sqlalchemy.orm import joinedload
    transactions = StockTransaction.query.filter_by(site_id=site_id)\
        .options(joinedload(StockTransaction.user), joinedload(StockTransaction.part))\
        .order_by(StockTransaction.timestamp.desc())\
        .all()
    
    # Group transactions by base form number
    grouped_txs = {}
    for tx in transactions:
        base_code = tx.transaction_code
        is_bulk = False
        if '-' in tx.transaction_code:
            parts = tx.transaction_code.split('-')
            if len(parts) > 1 and parts[-1].isdigit():
                base_code = '-'.join(parts[:-1])
                is_bulk = True
                
        if base_code not in grouped_txs:
            grouped_txs[base_code] = {
                'timestamp': tx.timestamp,
                'transaction_code': base_code,
                'is_bulk': is_bulk,
                'user': tx.user,
                'action': tx.action,
                'source_from': tx.source_from,
                'attachment_path': tx.attachment_path,
                'items': []
            }
        grouped_txs[base_code]['items'].append(tx)
        
    grouped_list = list(grouped_txs.values())
    grouped_list.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('warehouse/site_transactions.html', site=site, transactions=grouped_list)

@warehouse_bp.route('/site/<int:site_id>/stock/<int:part_id>/delete', methods=['POST'])
@login_required
def delete_stock(site_id, part_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    stock = StockLevel.query.filter_by(site_id=site_id, part_id=part_id).first_or_404()
    part_name = stock.part.name
    
    db.session.delete(stock)
    db.session.commit()
    
    flash(f'{part_name} removed from this site\'s warehouse.', 'success')
    return redirect(url_for('warehouse.site_inventory', site_id=site_id))

@warehouse_bp.route('/site/<int:site_id>/stock/mass_delete', methods=['POST'])
@login_required
def mass_delete_stock(site_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    part_ids = request.form.getlist('part_ids')
    if not part_ids:
        flash('No parts selected for deletion.', 'warning')
        return redirect(url_for('warehouse.site_inventory', site_id=site_id))
        
    deleted_count = 0
    for part_id in part_ids:
        stock = StockLevel.query.filter_by(site_id=site_id, part_id=part_id).first()
        if stock:
            db.session.delete(stock)
            deleted_count += 1
            
    if deleted_count > 0:
        db.session.commit()
        flash(f'Successfully removed {deleted_count} parts from this site\'s warehouse.', 'success')
    else:
        flash('No parts were deleted.', 'info')
        
    return redirect(url_for('warehouse.site_inventory', site_id=site_id))

@warehouse_bp.route('/site/<int:site_id>/export')
@login_required
def export_site_inventory(site_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    site = Site.query.get_or_404(site_id)
    format = request.args.get('format', 'excel')
    
    stock_levels = StockLevel.query.filter_by(site_id=site_id).all()
    
    data = []
    for stock in stock_levels:
        data.append({
            'Part Code': stock.part.code,
            'Part Name': stock.part.name,
            'Quantity': stock.qty_on_hand,
            'Tanggal Masuk': stock.last_restock_date.strftime('%Y-%m-%d') if stock.last_restock_date else '',
            'Inputted By': stock.pic.name if stock.pic else ''
        })
        
    df = pd.DataFrame(data)
    
    if format == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Inventory')
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f'inventory_{site.name.replace(" ", "_")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=inventory_{site.name.replace(' ', '_')}.csv"}
        )

@warehouse_bp.route('/site/<int:site_id>/import/template')
@login_required
def download_site_template(site_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    columns = ['Part Code', 'Part Name', 'Quantity', 'Tanggal Masuk']
    all_parts = Part.query.all()
    example_rows = []
    
    if all_parts:
        example_rows.append({
            'Part Code': all_parts[0].code,
            'Part Name': all_parts[0].name,
            'Quantity': 10,
            'Tanggal Masuk': date.today().strftime('%Y-%m-%d')
        })
    else:
        example_rows.append({
            'Part Code': 'PRT-EXAMPLE',
            'Part Name': 'Example Part Name',
            'Quantity': 5,
            'Tanggal Masuk': date.today().strftime('%Y-%m-%d')
        })
        
    df = pd.DataFrame(example_rows, columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Template')
        
        workbook = writer.book
        worksheet = writer.sheets['Template']
        
        ref_sheet = workbook.add_worksheet('Reference')
        part_codes = [p.code for p in all_parts]
        part_names = [p.name for p in all_parts]
        
        ref_sheet.write_column('A1', part_codes if part_codes else ['-'])
        ref_sheet.write_column('B1', part_names if part_names else ['-'])
        
        workbook.define_name('PartCodes', '=Reference!$A$1:$A$' + str(max(len(part_codes), 1)))
        ref_sheet.hide()
        
        worksheet.data_validation('A2:A1000', {'validate': 'list', 'source': '=PartCodes'})
        
        for i, col in enumerate(columns):
            worksheet.set_column(i, i, 20)
            
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="inventory_import_template.xlsx"
    )

@warehouse_bp.route('/site/<int:site_id>/import', methods=['POST'])
@login_required
def import_site_inventory(site_id):
    if current_user.site_id and current_user.site_id != site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('warehouse.index'))
        
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('warehouse.site_inventory', site_id=site_id))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('warehouse.site_inventory', site_id=site_id))
        
    if file:
        filename = file.filename
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith('.xlsx') or filename.endswith('.xls'):
                df = pd.read_excel(file)
            else:
                flash('Unsupported file format. Please upload CSV or Excel.', 'danger')
                return redirect(url_for('warehouse.site_inventory', site_id=site_id))
                
            success_count = 0
            error_count = 0
            skipped_details = []
            
            # Generate a single base transaction code for the whole bulk import
            base_tx_code = f"TRX-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            from models import StockTransaction
            
            for index, row in df.iterrows():
                part_code = row.get('Part Code')
                qty_val = row.get('Quantity')
                date_val = row.get('Tanggal Masuk')
                
                # Check if the entire row is blank
                if pd.isna(part_code) and pd.isna(qty_val) and pd.isna(date_val):
                    continue
                    
                row_num = index + 2
                
                if pd.isna(part_code) or pd.isna(qty_val):
                    error_count += 1
                    reason = "Part Code kosong" if pd.isna(part_code) else "Quantity kosong"
                    skipped_details.append(f"Baris {row_num} ({reason})")
                    continue
                    
                part_code = str(part_code).strip()
                try:
                    qty = int(qty_val)
                except (ValueError, TypeError):
                    error_count += 1
                    skipped_details.append(f"Baris {row_num} (Quantity '{qty_val}' bukan angka)")
                    continue
                    
                part = Part.query.filter_by(code=part_code).first()
                if not part:
                    error_count += 1
                    skipped_details.append(f"Baris {row_num} (Kode Part '{part_code}' tidak terdaftar)")
                    continue
                    
                last_restock_date = None
                if not pd.isna(date_val) and str(date_val).strip():
                    try:
                        date_str = str(date_val).strip().split(' ')[0]
                        last_restock_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        try:
                            last_restock_date = pd.to_datetime(date_val).date()
                        except Exception:
                            last_restock_date = date.today()
                else:
                    last_restock_date = date.today()
                    
                stock = StockLevel.query.filter_by(part_id=part.id, site_id=site_id).first()
                qty_before = 0
                
                if stock:
                    qty_before = stock.qty_on_hand
                    stock.qty_on_hand = qty
                    stock.last_restock_date = last_restock_date
                    stock.pic_id = current_user.id
                else:
                    stock = StockLevel(
                        part_id=part.id,
                        site_id=site_id,
                        qty_on_hand=qty,
                        last_restock_date=last_restock_date,
                        pic_id=current_user.id
                    )
                    db.session.add(stock)
                    
                qty_after = qty
                qty_change = qty_after - qty_before
                
                tx_code = f"{base_tx_code}-{index}"
                
                transaction = StockTransaction(
                    transaction_code=tx_code,
                    part_id=part.id,
                    site_id=site_id,
                    user_id=current_user.id,
                    action='ADD' if qty_before == 0 else 'ADJUST',
                    qty_before=qty_before,
                    qty_after=qty_after,
                    qty_change=qty_change,
                    notes="Imported via inventory upload"
                )
                db.session.add(transaction)
                success_count += 1
                
            db.session.commit()
            
            msg = f"Successfully imported {success_count} items."
            if error_count > 0:
                msg += f" Skipped {error_count} rows due to invalid data."
                if skipped_details:
                    msg += f" Details: {', '.join(skipped_details[:10])}{'...' if len(skipped_details) > 10 else ''}"
            flash(msg, 'success' if error_count == 0 else 'warning')
            
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during import: {str(e)}', 'danger')
            
    return redirect(url_for('warehouse.site_inventory', site_id=site_id))
