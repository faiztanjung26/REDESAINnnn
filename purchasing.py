from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Vendor, PurchaseOrder, POItem, Part, Site

purchasing_bp = Blueprint('purchasing', __name__, url_prefix='/purchasing')

@purchasing_bp.before_request
@login_required
def restrict_to_admin():
    if current_user.role != 'Admin':
        flash('Akses ditolak. Fitur Purchasing hanya diperuntukkan bagi Administrator.', 'danger')
        return redirect(url_for('dashboard'))

@purchasing_bp.route('/')
@login_required
def index():
    if current_user.site_id:
        pos = PurchaseOrder.query.filter_by(site_id=current_user.site_id).all()
    else:
        pos = PurchaseOrder.query.all()
    return render_template('purchasing/index.html', pos=pos)

@purchasing_bp.route('/vendors', methods=['GET', 'POST'])
@login_required
def vendors():
    if request.method == 'POST':
        name = request.form.get('name')
        trade = request.form.get('trade')
        contact_info = request.form.get('contact_info')
        
        new_vendor = Vendor(name=name, trade=trade, contact_info=contact_info)
        db.session.add(new_vendor)
        db.session.commit()
        flash('Vendor added successfully.', 'success')
        return redirect(url_for('purchasing.vendors'))
        
    vendors_list = Vendor.query.all()
    return render_template('purchasing/vendors.html', vendors=vendors_list)

@purchasing_bp.route('/vendor/<int:id>/delete', methods=['POST'])
@login_required
def delete_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    db.session.delete(vendor)
    db.session.commit()
    flash('Vendor deleted successfully.', 'success')
    return redirect(url_for('purchasing.vendors'))

@purchasing_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_po():
    if request.method == 'POST':
        po_number = request.form.get('po_number')
        vendor_id = request.form.get('vendor_id')
        site_id = request.form.get('site_id')
        
        # basic auto generation if empty
        if not po_number:
            import random
            po_number = f"PO-{random.randint(10000, 99999)}"
            
        new_po = PurchaseOrder(
            po_number=po_number,
            vendor_id=vendor_id,
            site_id=site_id,
            requested_by=current_user.id
        )
        db.session.add(new_po)
        db.session.commit()
        flash('Purchase Order created. Now add items.', 'success')
        return redirect(url_for('purchasing.view_po', id=new_po.id))
        
    vendors_list = Vendor.query.all()
    if current_user.site_id:
        sites = Site.query.filter_by(id=current_user.site_id).all()
    else:
        sites = Site.query.all()
    return render_template('purchasing/create.html', vendors=vendors_list, sites=sites)

@purchasing_bp.route('/<int:id>')
@login_required
def view_po(id):
    po = PurchaseOrder.query.get_or_404(id)
    if current_user.site_id and po.site_id != current_user.site_id:
        flash('Access denied. PO belongs to another site.', 'danger')
        return redirect(url_for('purchasing.index'))
        
    parts = Part.query.all()
    return render_template('purchasing/view.html', po=po, parts=parts)

@purchasing_bp.route('/<int:po_id>/add_item', methods=['POST'])
@login_required
def add_item(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    if current_user.site_id and po.site_id != current_user.site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('purchasing.index'))
        
    part_id = request.form.get('part_id')
    quantity = float(request.form.get('quantity', 1.0))
    unit_cost = float(request.form.get('unit_cost', 0.0))
    
    line_total = quantity * unit_cost
    
    new_item = POItem(
        po_id=po_id,
        part_id=part_id,
        quantity=quantity,
        unit_cost=unit_cost,
        line_total=line_total
    )
    db.session.add(new_item)
    
    # Update PO total cost
    po.total_cost += line_total
    
    db.session.commit()
    flash('Item added to PO.', 'success')
    return redirect(url_for('purchasing.view_po', id=po_id))

@purchasing_bp.route('/<int:po_id>/status', methods=['POST'])
@login_required
def get_po_status(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    if current_user.site_id and po.site_id != current_user.site_id:
        return {'error': 'Unauthorized'}, 403
    return {'status': po.status}

@purchasing_bp.route('/<int:po_id>/update_status', methods=['POST'])
@login_required
def update_status(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    if current_user.site_id and po.site_id != current_user.site_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('purchasing.index'))
    new_status = request.form.get('status')
    
    # Basic logic: If receiving items, we should ideally add to Stock.
    # For simplicity, we just change the status in Phase 2 unless specifically requested.
    po.status = new_status
    db.session.commit()
    
    flash(f'PO status updated to {new_status}.', 'success')
    return redirect(url_for('purchasing.view_po', id=po_id))
