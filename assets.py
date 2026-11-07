from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, Response
from flask_login import login_required, current_user
from models import db, Asset, Site, Category, Location, SubCategory, ProjectCode
from datetime import datetime
import pandas as pd
import io
from utils import admin_required, supervisor_or_admin_required
from app import limiter

def get_all_project_codes():
    codes_map = {}
    for pc in ProjectCode.query.order_by(ProjectCode.code).all():
        if pc.code and pc.code.strip():
            codes_map[pc.code.strip()] = pc
            
    for s in Site.query.all():
        if s.project_code and s.project_code.strip() and s.project_code.strip() not in codes_map:
            class DummyProjectCode:
                def __init__(self, c):
                    self.id = 0
                    self.code = c
                    self.description = ''
            codes_map[s.project_code.strip()] = DummyProjectCode(s.project_code.strip())
            
    for a in Asset.query.all():
        if a.project_code and a.project_code.strip() and a.project_code.strip() not in codes_map:
            class DummyProjectCode:
                def __init__(self, c):
                    self.id = 0
                    self.code = c
                    self.description = ''
            codes_map[a.project_code.strip()] = DummyProjectCode(a.project_code.strip())
            
    return [codes_map[k] for k in sorted(codes_map.keys())]

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')

@assets_bp.route('/api/by_site/<int:site_id>')
@login_required
def api_by_site(site_id):
    from models import Asset
    from flask import jsonify
    assets = Asset.query.filter_by(site_id=site_id).all()
    return jsonify([{'id': a.id, 'code': a.code, 'name': a.name} for a in assets])

@assets_bp.before_request
def restrict_technicians():

    if not current_user.is_authenticated or current_user.role not in ['Admin', 'Supervisor']:
        flash('Access denied. Technicians cannot access the Assets module.', 'danger')
        return redirect(url_for('dashboard'))

@assets_bp.route('/')
@login_required
def index():
    from sqlalchemy import or_
    
    site_id = request.args.get('site_id', type=int)
    location_id = request.args.get('location_id', type=int)
    category_id = request.args.get('category_id', type=int)
    status_filter = request.args.get('status', '').strip()
    q = request.args.get('q', '').strip()
    active_tab = request.args.get('tab', 'tree')
    page = request.args.get('page', 1, type=int)
    
    # Asset Query
    query = Asset.query
    if current_user.site_id:
        query = query.filter(Asset.site_id == current_user.site_id)
    elif site_id:
        query = query.filter(Asset.site_id == site_id)
        
    if location_id:
        query = query.filter(Asset.location_id == location_id)
    if category_id:
        query = query.filter(Asset.category_id == category_id)
    if status_filter:
        query = query.filter(Asset.status == status_filter)
        
    if q:
        query = query.outerjoin(Category, Asset.category_id == Category.id)\
                     .outerjoin(SubCategory, Asset.subcategory_id == SubCategory.id)\
                     .outerjoin(Location, Asset.location_id == Location.id)\
                     .filter(or_(
                         Asset.name.ilike(f'%{q}%'),
                         Asset.code.ilike(f'%{q}%'),
                         Asset.serial_number.ilike(f'%{q}%'),
                         Asset.barcode.ilike(f'%{q}%'),
                         Asset.model.ilike(f'%{q}%'),
                         Asset.make.ilike(f'%{q}%'),
                         Asset.description.ilike(f'%{q}%'),
                         Category.name.ilike(f'%{q}%'),
                         SubCategory.name.ilike(f'%{q}%'),
                         Location.name.ilike(f'%{q}%')
                     ))
        
    assets = query.order_by(Asset.name.asc()).paginate(page=page, per_page=20, error_out=False)
    
    # Sites List
    if current_user.site_id:
        sites_query = Site.query.filter_by(id=current_user.site_id)
    else:
        sites_query = Site.query
    if not site_id and q:
        sites_query = sites_query.filter(or_(
            Site.name.ilike(f'%{q}%'),
            Site.address.ilike(f'%{q}%')
        ))
    sites = sites_query.order_by(Site.name.asc()).all()
    
    current_site_obj = db.session.get(Site, site_id) if site_id else None
    
    paginated_locations = None
    all_locations = None
    unassigned_assets = None
    locations_for_filter = []
    
    if site_id:
        locations_for_filter = Location.query.filter_by(site_id=site_id).order_by(Location.name.asc()).all()
        
        # Paginated locations for Locations tab
        loc_query = Location.query.filter_by(site_id=site_id)
        if q:
            loc_query = loc_query.filter(or_(
                Location.name.ilike(f'%{q}%'),
                Location.description.ilike(f'%{q}%')
            ))
        paginated_locations = loc_query.order_by(Location.name.asc()).paginate(page=page, per_page=15, error_out=False)
        
        # Locations with filtered assets for Tree tab
        raw_locations = Location.query.filter_by(site_id=site_id).order_by(Location.name.asc()).all()
        all_locations = []
        for loc in raw_locations:
            loc_assets_q = Asset.query.filter_by(location_id=loc.id)
            if category_id:
                loc_assets_q = loc_assets_q.filter_by(category_id=category_id)
            if status_filter:
                loc_assets_q = loc_assets_q.filter_by(status=status_filter)
            if q:
                loc_assets_q = loc_assets_q.outerjoin(Category, Asset.category_id == Category.id)\
                                           .outerjoin(SubCategory, Asset.subcategory_id == SubCategory.id)\
                                           .filter(or_(
                                               Asset.name.ilike(f'%{q}%'),
                                               Asset.code.ilike(f'%{q}%'),
                                               Asset.serial_number.ilike(f'%{q}%'),
                                               Asset.barcode.ilike(f'%{q}%'),
                                               Asset.model.ilike(f'%{q}%'),
                                               Asset.make.ilike(f'%{q}%'),
                                               Category.name.ilike(f'%{q}%'),
                                               SubCategory.name.ilike(f'%{q}%'),
                                               Asset.description.ilike(f'%{q}%')
                                           ))
            filtered_loc_assets = loc_assets_q.order_by(Asset.name.asc()).all()
            total_loc_assets = loc.assets.count()
            loc_name_match = bool(q and q.lower() in (loc.name or '').lower())
            
            if (not q and not status_filter and not category_id) or loc_name_match or len(filtered_loc_assets) > 0:
                all_locations.append({
                    'id': loc.id,
                    'name': loc.name,
                    'description': loc.description,
                    'assets': filtered_loc_assets if (q or status_filter or category_id) else loc.assets.order_by(Asset.name.asc()).all(),
                    'total_count': total_loc_assets,
                    'has_match': bool(q or status_filter or category_id)
                })
                
        # Unassigned assets for Tree tab
        unassigned_q = Asset.query.filter_by(site_id=site_id, location_id=None)
        if category_id:
            unassigned_q = unassigned_q.filter_by(category_id=category_id)
        if status_filter:
            unassigned_q = unassigned_q.filter_by(status=status_filter)
        if q:
            unassigned_q = unassigned_q.outerjoin(Category, Asset.category_id == Category.id)\
                                       .outerjoin(SubCategory, Asset.subcategory_id == SubCategory.id)\
                                       .filter(or_(
                                           Asset.name.ilike(f'%{q}%'),
                                           Asset.code.ilike(f'%{q}%'),
                                           Asset.serial_number.ilike(f'%{q}%'),
                                           Asset.barcode.ilike(f'%{q}%'),
                                           Asset.model.ilike(f'%{q}%'),
                                           Asset.make.ilike(f'%{q}%'),
                                           Category.name.ilike(f'%{q}%'),
                                           SubCategory.name.ilike(f'%{q}%'),
                                           Asset.description.ilike(f'%{q}%')
                                       ))
        unassigned_assets = unassigned_q.order_by(Asset.name.asc()).all()

    categories = Category.query.order_by(Category.name.asc()).all()
    statuses = ['Online', 'Offline', 'In Repair', 'Standby']

    return render_template(
        'assets/index.html',
        assets=assets,
        sites=sites,
        current_site=site_id,
        current_loc=location_id,
        current_category=category_id,
        current_status=status_filter,
        search_query=q,
        current_site_obj=current_site_obj,
        active_tab=active_tab,
        paginated_locations=paginated_locations,
        all_locations=all_locations,
        unassigned_assets=unassigned_assets,
        categories=categories,
        locations_for_filter=locations_for_filter,
        statuses=statuses
    )

@assets_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        status = request.form.get('status')
        criticality = request.form.get('criticality')
        site_id = request.form.get('site_id')
        
        category_input = request.form.get('category_input')
        category_id = None
        if category_input:
            cat = Category.query.filter(Category.name.ilike(category_input)).first()
            if not cat:
                cat = Category(name=category_input)
                db.session.add(cat)
                db.session.flush()
            category_id = cat.id

        subcategory_input = request.form.get('subcategory_input')
        subcategory_id = None
        if subcategory_input and category_id:
            subcat = SubCategory.query.filter(SubCategory.name.ilike(subcategory_input), SubCategory.category_id == category_id).first()
            if not subcat:
                subcat = SubCategory(name=subcategory_input, category_id=category_id)
                db.session.add(subcat)
                db.session.flush()
            subcategory_id = subcat.id

        location_input = request.form.get('location_input')
        location_id = None
        if location_input and site_id:
            loc = Location.query.filter(Location.name.ilike(location_input), Location.site_id == site_id).first()
            if not loc:
                loc = Location(name=location_input, site_id=site_id)
                db.session.add(loc)
                db.session.flush()
            location_id = loc.id
            
        project_code = request.form.get('project_code') or None
        
        new_asset = Asset(
            name=name, code=code, status=status, criticality=criticality, 
            site_id=site_id, location_id=location_id, category_id=category_id, subcategory_id=subcategory_id,
            project_code=project_code,
            description=request.form.get('description'),
            make=request.form.get('make'),
            model=request.form.get('model'),
            serial_number=request.form.get('serial_number'),
            barcode=request.form.get('barcode'),
            storage_aisle=request.form.get('storage_aisle'),
            storage_row=request.form.get('storage_row'),
            storage_bin=request.form.get('storage_bin'),
            notes=request.form.get('notes'),
            is_chiller='is_chiller' in request.form,
            api_chiller_id=request.form.get('api_chiller_id')
        )
        db.session.add(new_asset)
        db.session.commit()
        flash('Asset created successfully!', 'success')
        return redirect(url_for('assets.index'))
        
    if current_user.site_id:
        sites = Site.query.filter_by(id=current_user.site_id).all()
        locations = Location.query.filter_by(site_id=current_user.site_id).all()
    else:
        sites = Site.query.all()
        locations = Location.query.all()
        
    categories = Category.query.all()
    subcategories = SubCategory.query.all()
    
    return render_template('assets/create.html', sites=sites, categories=categories, subcategories=subcategories, locations=locations, project_codes=get_all_project_codes())

@assets_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    asset = Asset.query.get_or_404(id)
    if request.method == 'POST':
        asset.name = request.form.get('name')
        asset.code = request.form.get('code')
        asset.status = request.form.get('status')
        asset.criticality = request.form.get('criticality')
        asset.site_id = request.form.get('site_id')
        
        category_input = request.form.get('category_input')
        if category_input:
            cat = Category.query.filter(Category.name.ilike(category_input)).first()
            if not cat:
                cat = Category(name=category_input)
                db.session.add(cat)
                db.session.flush()
            asset.category_id = cat.id

        subcategory_input = request.form.get('subcategory_input')
        if subcategory_input and asset.category_id:
            subcat = SubCategory.query.filter(SubCategory.name.ilike(subcategory_input), SubCategory.category_id == asset.category_id).first()
            if not subcat:
                subcat = SubCategory(name=subcategory_input, category_id=asset.category_id)
                db.session.add(subcat)
                db.session.flush()
            asset.subcategory_id = subcat.id
        else:
            asset.subcategory_id = None

        location_input = request.form.get('location_input')
        if location_input and asset.site_id:
            loc = Location.query.filter(Location.name.ilike(location_input), Location.site_id == asset.site_id).first()
            if not loc:
                loc = Location(name=location_input, site_id=asset.site_id)
                db.session.add(loc)
                db.session.flush()
            asset.location_id = loc.id
        else:
            asset.location_id = None
            
        asset.project_code = request.form.get('project_code') or None
        
        asset.description = request.form.get('description')
        asset.make = request.form.get('make')
        asset.model = request.form.get('model')
        asset.serial_number = request.form.get('serial_number')
        asset.barcode = request.form.get('barcode')
        asset.storage_aisle = request.form.get('storage_aisle')
        asset.storage_row = request.form.get('storage_row')
        asset.storage_bin = request.form.get('storage_bin')
        asset.notes = request.form.get('notes')
        asset.is_chiller = 'is_chiller' in request.form
        asset.api_chiller_id = request.form.get('api_chiller_id')
        
        db.session.commit()
        flash('Asset updated successfully!', 'success')
        return redirect(url_for('assets.index'))
        
    sites = Site.query.all()
    categories = Category.query.all()
    subcategories = SubCategory.query.all()
    locations = Location.query.all()
    return render_template('assets/edit.html', asset=asset, sites=sites, categories=categories, subcategories=subcategories, locations=locations, project_codes=get_all_project_codes())

@assets_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    asset = Asset.query.get_or_404(id)
    db.session.delete(asset)
    db.session.commit()
    flash('Asset deleted successfully!', 'success')
    return redirect(url_for('assets.index'))

@assets_bp.route('/<int:id>/view')
@login_required
def view(id):
    from models import Part, User, Vendor, Checklist
    asset = Asset.query.get_or_404(id)
    if asset.site_id:
        from sqlalchemy import or_
        parts = Part.query.filter(or_(Part.site_id == asset.site_id, Part.site_id == None)).all()
    else:
        parts = Part.query.all()
    from sqlalchemy import not_
    users = User.query.filter(not_(User.role == 'Guest')).all()
    vendors = Vendor.query.all()
    checklists = Checklist.query.all()
    from datetime import datetime, timedelta
    return render_template('assets/view.html', asset=asset, parts=parts, users=users, vendors=vendors, checklists=checklists, today=datetime.today().date(), timedelta=timedelta)

@assets_bp.route('/search')
@login_required
def search():
    query = request.args.get('q', '').strip()
    if not query:
        flash('Please enter a search term.', 'warning')
        return redirect(url_for('assets.index', tab='assets'))
        
    # Search by code primarily for exact code/scan matches
    asset = Asset.query.filter_by(code=query).first()
    if asset:
        return redirect(url_for('assets.view', id=asset.id))
        
    # Fallback to name/code search
    from sqlalchemy import or_
    assets = Asset.query.filter(or_(Asset.code.ilike(f'%{query}%'), Asset.name.ilike(f'%{query}%'))).all()
    if len(assets) == 1:
        return redirect(url_for('assets.view', id=assets[0].id))
    elif len(assets) > 1:
        flash(f'Found {len(assets)} assets matching "{query}".', 'info')
        return redirect(url_for('assets.index', tab='assets', q=query))
        
    flash(f'No asset found matching "{query}".', 'warning')
    return redirect(url_for('assets.index', tab='assets', q=query))

@assets_bp.route('/qr/<code>')
def qr_code(code):
    import qrcode
    from io import BytesIO
    from flask import send_file

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(code) # Encodes the asset code
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)    
    return send_file(img_io, mimetype='image/png')

@assets_bp.route('/scan/<code>')
@login_required
def scan(code):
    asset = Asset.query.filter_by(code=code).first()
    if asset:
        return redirect(url_for('assets.view', id=asset.id))
    else:
        flash(f'Asset scanned ({code}) not found in the database.', 'danger')
        return redirect(url_for('dashboard.index'))

@assets_bp.route('/export')
@login_required
@admin_required
def export_assets():
    format = request.args.get('format', 'csv')
    assets = Asset.query.all()
    
    data = []
    for asset in assets:
        data.append({
            'ID': asset.id,
            'Name': asset.name,
            'Code': asset.code,
            'Status': asset.status,
            'Criticality': asset.criticality,
            'Project Code': asset.project_code,
            'Site': asset.site.name if asset.site else '',
            'Location': asset.location.name if asset.location else '',
            'Category': asset.category.name if asset.category else '',
            'Subcategory': asset.subcategory.name if asset.subcategory else '',
            'Start Date': asset.start_date.strftime('%Y-%m-%d %H:%M:%S') if asset.start_date else '',
            'End Date': asset.end_date.strftime('%Y-%m-%d %H:%M:%S') if asset.end_date else '',
            'Estimated Hours': asset.estimated_hours
        })
        
    df = pd.DataFrame(data)
    
    if format == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Assets')
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='assets.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=assets.csv"}
        )

@assets_bp.route('/template')
@login_required
@admin_required
def download_template():
    from flask import send_file
    import pandas as pd
    import io
    from models import Site, Category, SubCategory, Location, ProjectCode
    
    columns = [
        'Name', 'Code', 'Site', 'Category', 'Sub Category', 
        'Location', 'Status', 'Criticality', 'Project Code'
    ]
    df = pd.DataFrame(columns=columns)
    
    # Add an example row
    example_row = {
        'Name': 'Chiller Example',
        'Code': 'AST-0001',
        'Site': 'Jakarta MRT',
        'Category': 'HVAC',
        'Sub Category': 'Chiller',
        'Location': 'Roof',
        'Status': 'Online',
        'Criticality': 'Medium',
        'Project Code': 'PROJ-01'
    }
    df = pd.concat([df, pd.DataFrame([example_row])], ignore_index=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Assets')
        
        workbook = writer.book
        worksheet = writer.sheets['Assets']
        ref_sheet = workbook.add_worksheet('Reference')
        
        # Get data from database
        sites = [s.name for s in Site.query.all()]
        categories = [c.name for c in Category.query.all()]
        sub_categories = [sc.name for sc in SubCategory.query.all()]
        locations = [l.name for l in Location.query.all()]
        projects = [p.code for p in ProjectCode.query.all()]
        
        # Write reference data
        ref_sheet.write_column('A1', sites if sites else ['-'])
        workbook.define_name('Sites', '=Reference!$A$1:$A$' + str(max(len(sites), 1)))
        
        ref_sheet.write_column('B1', categories if categories else ['-'])
        workbook.define_name('Categories', '=Reference!$B$1:$B$' + str(max(len(categories), 1)))
        
        ref_sheet.write_column('C1', sub_categories if sub_categories else ['-'])
        workbook.define_name('SubCategories', '=Reference!$C$1:$C$' + str(max(len(sub_categories), 1)))
        
        ref_sheet.write_column('D1', locations if locations else ['-'])
        workbook.define_name('Locations', '=Reference!$D$1:$D$' + str(max(len(locations), 1)))
        
        ref_sheet.write_column('E1', projects if projects else ['-'])
        workbook.define_name('Projects', '=Reference!$E$1:$E$' + str(max(len(projects), 1)))
        
        ref_sheet.hide()
        
        # Add Data Validation Dropdowns
        worksheet.data_validation('C2:C1000', {'validate': 'list', 'source': '=Sites'})
        worksheet.data_validation('D2:D1000', {'validate': 'list', 'source': '=Categories'})
        worksheet.data_validation('E2:E1000', {'validate': 'list', 'source': '=SubCategories'})
        worksheet.data_validation('F2:F1000', {'validate': 'list', 'source': '=Locations'})
        worksheet.data_validation('G2:G1000', {'validate': 'list', 'source': ['Online', 'Offline', 'In Repair', 'Storage']})
        worksheet.data_validation('H2:H1000', {'validate': 'list', 'source': ['High', 'Medium', 'Low']})
        worksheet.data_validation('I2:I1000', {'validate': 'list', 'source': '=Projects'})
        
        # Auto-fit columns
        for i, col in enumerate(columns):
            worksheet.set_column(i, i, max(len(col) + 2, 15))
            
    output.seek(0)
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="assets_template.xlsx"
    )

@assets_bp.route('/import', methods=['POST'])
@login_required
@admin_required
def import_assets():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('assets.index'))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('assets.index'))
        
    if file:
        filename = file.filename
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith('.xlsx') or filename.endswith('.xls'):
                df = pd.read_excel(file)
            else:
                flash('Unsupported file format. Please upload CSV or Excel.', 'danger')
                return redirect(url_for('assets.index'))
                
            # Clean up column names to prevent errors from trailing spaces
            df.columns = [str(c).strip() for c in df.columns]
                
            success_count = 0
            error_count = 0
            
            for index, row in df.iterrows():
                try:
                    if pd.isna(row.get('Name')):
                        error_count += 1
                        continue
                        
                    asset_code = None
                    if 'Code' in row and not pd.isna(row['Code']) and str(row['Code']).strip():
                        asset_code = str(row['Code']).strip()
                    else:
                        import uuid
                        asset_code = f"AST-{uuid.uuid4().hex[:6].upper()}"
                        
                    asset = Asset.query.filter_by(code=asset_code).first()
                    
                    site_name = row.get('Site')
                    site = None
                    site_name_str = "Default Site"
                    if not pd.isna(site_name) and str(site_name).strip():
                        site_name_str = str(site_name).strip()
                        
                    site = Site.query.filter_by(name=site_name_str).first()
                    if not site:
                        site = Site(name=site_name_str)
                        db.session.add(site)
                        db.session.flush() # flush to generate ID without committing
                            
                    category_name = row.get('Category')
                    category = None
                    category_name_str = "Uncategorized"
                    if not pd.isna(category_name) and str(category_name).strip():
                        category_name_str = str(category_name).strip()
                        
                    category = Category.query.filter_by(name=category_name_str).first()
                    if not category:
                        category = Category(name=category_name_str)
                        db.session.add(category)
                        db.session.flush()
                            
                    subcategory = None
                    subcat_val = None
                    if 'Sub Category' in row and not pd.isna(row['Sub Category']):
                        subcat_val = row['Sub Category']
                    elif 'Subcategory' in row and not pd.isna(row['Subcategory']):
                        subcat_val = row['Subcategory']
                        
                    if subcat_val and category:
                        subcat_name_str = str(subcat_val).strip()
                        subcategory = SubCategory.query.filter_by(name=subcat_name_str, category_id=category.id).first()
                        if not subcategory:
                            subcategory = SubCategory(name=subcat_name_str, category_id=category.id)
                            db.session.add(subcategory)
                            db.session.flush()
                            
                    location_name = row.get('Location')
                    location = None
                    if not pd.isna(location_name) and site:
                        loc_name_str = str(location_name).strip()
                        location = Location.query.filter_by(name=loc_name_str, site_id=site.id).first()
                        if not location:
                            location = Location(name=loc_name_str, site_id=site.id)
                            db.session.add(location)
                            db.session.flush()
                    
                    if not asset:
                        asset = Asset(
                           name=str(row['Name']),
                           code=asset_code,
                           status=str(row.get('Status', 'Online')) if not pd.isna(row.get('Status')) else 'Online',
                           criticality=str(row.get('Criticality', 'Medium')) if not pd.isna(row.get('Criticality')) else 'Medium',
                           site_id=site.id if site else None,
                           location_id=location.id if location else None,
                           category_id=category.id if category else None,
                           subcategory_id=subcategory.id if subcategory else None
                        )
                        # Ultra-Fuzzy Match Project Code
                        proj_val = None
                        for col_name in row.index:
                            clean_col = str(col_name).strip().lower().replace('_', ' ')
                            if clean_col in ['project code', 'projectcode', 'project id', 'project', 'project no']:
                                if not pd.isna(row[col_name]):
                                    proj_val = row[col_name]
                                    break
                                
                        if proj_val is not None and str(proj_val).strip() != "":
                           asset.project_code = str(proj_val).strip()
                               
                        db.session.add(asset)
                        success_count += 1
                    else:
                        asset.name = str(row['Name'])
                        if 'Status' in row and not pd.isna(row['Status']): asset.status = str(row['Status'])
                        if 'Criticality' in row and not pd.isna(row['Criticality']): asset.criticality = str(row['Criticality'])
                        if site: asset.site_id = site.id
                        if location: asset.location_id = location.id
                        if category: asset.category_id = category.id
                        if subcategory: asset.subcategory_id = subcategory.id
                        
                        proj_val = None
                        for col_name in row.index:
                            clean_col = str(col_name).strip().lower().replace('_', ' ')
                            if clean_col in ['project code', 'projectcode', 'project id', 'project', 'project no']:
                                if not pd.isna(row[col_name]):
                                    proj_val = row[col_name]
                                    break
                                
                        if proj_val is not None and str(proj_val).strip() != "":
                            asset.project_code = str(proj_val).strip()
                            
                        success_count += 1
                        
                except Exception as e:
                    error_count += 1
                    print(f"❌ [IMPORT ERROR] Row {index} Failed: {e}")
                    
            db.session.commit()
            
            if error_count > 0:
                flash(f'Import completed with warnings: {success_count} successful, {error_count} skipped due to missing critical columns (Name/Code) or formatting errors.', 'warning')
            else:
                flash(f'Import successful: {success_count} assets processed. Any new Sites or Categories were auto-created!', 'success')
                
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing file: {str(e)}', 'danger')
            
    return redirect(url_for('assets.index'))

# ==================== ASSET TAB ENDPOINTS ====================

@assets_bp.route('/<int:asset_id>/bom/add', methods=['POST'])
@login_required
def add_bom(asset_id):
    from models import AssetPartBOM
    part_id = request.form.get('part_id')
    quantity = request.form.get('quantity', 1.0, type=float)
    note = request.form.get('note')
    bom = AssetPartBOM(asset_id=asset_id, part_id=part_id, quantity=quantity, note=note)
    db.session.add(bom)
    db.session.commit()
    flash('Part added to BOM successfully.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='bom'))

@assets_bp.route('/bom/<int:id>/remove', methods=['POST'])
@login_required
def remove_bom(id):
    from models import AssetPartBOM
    bom = AssetPartBOM.query.get_or_404(id)
    asset_id = bom.asset_id
    db.session.delete(bom)
    db.session.commit()
    flash('Part removed from BOM.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='bom'))

@assets_bp.route('/<int:asset_id>/meter/add', methods=['POST'])
@login_required
def add_meter(asset_id):
    from models import AssetMeter
    name = request.form.get('name')
    unit = request.form.get('unit')
    
    api_url = request.form.get('api_url', '').strip() or None
    api_method = request.form.get('api_method', 'GET').strip().upper()
    api_json_key = request.form.get('api_json_key', '').strip() or None
    api_interval = request.form.get('api_interval', type=int) or 5
    
    meter = AssetMeter(
        asset_id=asset_id, 
        name=name, 
        unit=unit,
        api_url=api_url,
        api_method=api_method,
        api_json_key=api_json_key,
        api_interval=api_interval
    )
    db.session.add(meter)
    db.session.commit()
    
    flash('Meter Otomatis berhasil ditambahkan.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='monitoring'))

@assets_bp.route('/<int:asset_id>/meter/import', methods=['POST'])
@login_required
def import_meters_from_checklist(asset_id):
    from models import Asset, Checklist, AssetMeter
    asset = Asset.query.get_or_404(asset_id)
    checklist_id = request.form.get('checklist_id')
    apply_to_all = request.form.get('apply_to_all_subcategory') == '1'
    
    if not checklist_id:
        flash('Checklist tidak dipilih.', 'error')
        return redirect(url_for('assets.view', id=asset_id, tab='metering'))
    
    checklist = Checklist.query.get(checklist_id)
    if not checklist:
        flash('Checklist tidak ditemukan.', 'error')
        return redirect(url_for('assets.view', id=asset_id, tab='metering'))
        
    target_assets = [asset]
    if apply_to_all and asset.subcategory_id:
        target_assets = Asset.query.filter_by(subcategory_id=asset.subcategory_id, site_id=asset.site_id).all()
        
    total_imported = 0
    assets_affected = 0
    
    for target_asset in target_assets:
        imported_for_asset = False
        for param in checklist.parameters:
            exists = AssetMeter.query.filter_by(asset_id=target_asset.id, name=param.parameter).first()
            if not exists:
                new_meter = AssetMeter(
                    asset_id=target_asset.id,
                    name=param.parameter,
                    unit='Checklist'
                )
                db.session.add(new_meter)
                total_imported += 1
                imported_for_asset = True
        if imported_for_asset:
            assets_affected += 1
            
    db.session.commit()
    
    if apply_to_all:
        if total_imported > 0:
            flash(f'{total_imported} parameter dari checklist {checklist.name} berhasil diimport ke {assets_affected} asset dengan subkategori yang sama.', 'success')
        else:
            flash(f'Semua parameter sudah ada pada asset-asset tersebut.', 'info')
    else:
        if total_imported > 0:
            flash(f'{total_imported} parameter dari checklist {checklist.name} berhasil diimport.', 'success')
        else:
            flash(f'Semua parameter dari checklist {checklist.name} sudah ada pada asset ini.', 'info')
        
    return redirect(url_for('assets.view', id=asset_id, tab='metering'))

@assets_bp.route('/meter/<int:meter_id>/reading/add', methods=['POST'])
@login_required
def add_meter_reading(meter_id):
    from models import AssetMeter, AssetMeterReading
    from flask_login import current_user
    meter = AssetMeter.query.get_or_404(meter_id)
    reading_value = request.form.get('reading_value', type=float)
    reading = AssetMeterReading(meter_id=meter_id, reading_value=reading_value, user_id=current_user.id)
    db.session.add(reading)
    db.session.commit()
    flash('Meter reading logged successfully.', 'success')
    return redirect(url_for('assets.view', id=meter.asset_id, tab='metering'))

@assets_bp.route('/meter/<int:meter_id>/delete', methods=['POST'])
@login_required
def delete_meter(meter_id):
    from models import AssetMeter
    meter = AssetMeter.query.get_or_404(meter_id)
    asset_id = meter.asset_id
    db.session.delete(meter)
    db.session.commit()
    
    flash('Meter deleted successfully.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='metering'))

@assets_bp.route('/<int:asset_id>/meter/delete_all', methods=['POST'])
@login_required
def delete_all_meters(asset_id):
    from models import Asset, AssetMeter
    asset = Asset.query.get_or_404(asset_id)
    apply_to_all = request.form.get('apply_to_all_subcategory') == '1'
    
    target_assets = [asset]
    if apply_to_all and asset.subcategory_id:
        target_assets = Asset.query.filter_by(subcategory_id=asset.subcategory_id, site_id=asset.site_id).all()
        
    total_deleted = 0
    assets_affected = 0
    
    for target_asset in target_assets:
        meters = AssetMeter.query.filter_by(asset_id=target_asset.id).all()
        if meters:
            for m in meters:
                db.session.delete(m)
                total_deleted += 1
            assets_affected += 1
            
    db.session.commit()
    
    if apply_to_all:
        flash(f'Berhasil menghapus {total_deleted} parameter dari {assets_affected} asset dengan subkategori yang sama di site ini.', 'success')
    else:
        flash(f'Berhasil menghapus {total_deleted} parameter dari asset ini.', 'success')
        
    return redirect(url_for('assets.view', id=asset_id, tab='metering'))

@assets_bp.route('/meter/<int:meter_id>/live', methods=['GET'])
@login_required
def live_meter(meter_id):
    from models import AssetMeter
    import requests
    
    meter = AssetMeter.query.get_or_404(meter_id)
    if not meter.api_url:
        return jsonify({'error': 'No API configured for this meter'}), 400
        
    try:
        if meter.api_method == 'POST':
            response = requests.post(meter.api_url, timeout=5)
        else:
            response = requests.get(meter.api_url, timeout=5)
            
        response.raise_for_status()
        data = response.json()
        
        value = None
        if meter.api_json_key:
            keys = meter.api_json_key.split('.')
            current = data
            for k in keys:
                if isinstance(current, dict) and k in current:
                    current = current[k]
                else:
                    current = None
                    break
            value = current
        else:
            if isinstance(data, dict) and 'value' in data:
                value = data['value']
            elif isinstance(data, (int, float, str)):
                value = data
                
        if value is not None:
            try:
                numeric_val = float(value)
                return jsonify({'success': True, 'value': numeric_val})
            except ValueError:
                return jsonify({'error': 'API returned non-numeric value'}), 500
        else:
            return jsonify({'error': 'Could not extract value using the provided JSON key'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@assets_bp.route('/<int:asset_id>/personnel/add', methods=['POST'])
@login_required
def add_personnel(asset_id):
    from models import AssetPersonnel
    user_id = request.form.get('user_id')
    notify_on_status_change = bool(request.form.get('notify_on_status_change'))
    notify_on_wo = bool(request.form.get('notify_on_wo'))
    p = AssetPersonnel(asset_id=asset_id, user_id=user_id, notify_on_status_change=notify_on_status_change, notify_on_wo=notify_on_wo)
    db.session.add(p)
    db.session.commit()
    flash('Personnel assigned successfully.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='personnel'))

@assets_bp.route('/personnel/<int:id>/remove', methods=['POST'])
@login_required
def remove_personnel(id):
    from models import AssetPersonnel
    p = AssetPersonnel.query.get_or_404(id)
    asset_id = p.asset_id
    db.session.delete(p)
    db.session.commit()
    flash('Personnel assignment removed.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='personnel'))

@assets_bp.route('/<int:asset_id>/warranty/add', methods=['POST'])
@login_required
def add_warranty(asset_id):
    from models import AssetWarranty
    type_str = request.form.get('type')
    provider = request.form.get('provider')
    lifespan = request.form.get('lifespan')
    expiry_date_str = request.form.get('expiry_date')
    cert_number = request.form.get('cert_number')
    description = request.form.get('description')
    
    expiry_date = None
    if expiry_date_str:
        from datetime import datetime
        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        
    w = AssetWarranty(asset_id=asset_id, type=type_str, provider=provider, lifespan=lifespan, expiry_date=expiry_date, cert_number=cert_number, description=description)
    db.session.add(w)
    db.session.commit()
    flash('Warranty added successfully.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='warranties'))

@assets_bp.route('/warranty/<int:id>/remove', methods=['POST'])
@login_required
def remove_warranty(id):
    from models import AssetWarranty
    w = AssetWarranty.query.get_or_404(id)
    asset_id = w.asset_id
    db.session.delete(w)
    db.session.commit()
    flash('Warranty removed.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='warranties'))

@assets_bp.route('/<int:asset_id>/business/add', methods=['POST'])
@login_required
def add_business(asset_id):
    from models import AssetBusiness
    vendor_id = request.form.get('vendor_id')
    supplier_part_number = request.form.get('supplier_part_number')
    catalog = request.form.get('catalog')
    price = request.form.get('price', 0.0, type=float)
    is_preferred = bool(request.form.get('is_preferred'))
    
    b = AssetBusiness(asset_id=asset_id, vendor_id=vendor_id, supplier_part_number=supplier_part_number, catalog=catalog, price=price, is_preferred=is_preferred)
    db.session.add(b)
    db.session.commit()
    flash('Business associated successfully.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='businesses'))

@assets_bp.route('/business/<int:id>/remove', methods=['POST'])
@login_required
def remove_business(id):
    from models import AssetBusiness
    b = AssetBusiness.query.get_or_404(id)
    asset_id = b.asset_id
    db.session.delete(b)
    db.session.commit()
    flash('Business association removed.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='businesses'))

@assets_bp.route('/<int:asset_id>/update_valuation', methods=['POST'])
@login_required
@admin_required
def update_replacement_value(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    asset.replacement_value = request.form.get('replacement_value', 0.0, type=float)
    db.session.commit()
    flash('Valuation updated.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='purchasing'))

@assets_bp.route('/<int:asset_id>/custom/add', methods=['POST'])
@login_required
def add_custom_field(asset_id):
    from models import AssetCustomField
    field_name = request.form.get('field_name')
    field_value = request.form.get('field_value')
    expiry_date_str = request.form.get('expiry_date')
    
    expiry_date = None
    if expiry_date_str:
        from datetime import datetime
        try:
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        except ValueError:
            pass
    
    cf = AssetCustomField(asset_id=asset_id, field_name=field_name, field_value=field_value, expiry_date=expiry_date)
    db.session.add(cf)
    db.session.commit()
    flash('Komponen berhasil ditambahkan.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='custom'))

@assets_bp.route('/custom/<int:id>/remove', methods=['POST'])
@login_required
def remove_custom_field(id):
    from models import AssetCustomField
    cf = AssetCustomField.query.get_or_404(id)
    asset_id = cf.asset_id
    db.session.delete(cf)
    db.session.commit()
    flash('Custom field removed.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='custom'))

@assets_bp.route('/<int:asset_id>/file/add', methods=['POST'])
@login_required
def add_file(asset_id):
    from models import AssetFile
    import os
    from werkzeug.utils import secure_filename
    from flask import current_app
    
    file_name = request.form.get('file_name', 'Untitled')
    notes = request.form.get('notes')
    file_url = request.form.get('file_url')
    
    if file_url:
        f = AssetFile(asset_id=asset_id, file_name=file_name, file_path=file_url, is_url=True, notes=notes)
        db.session.add(f)
        db.session.commit()
        flash('URL attached successfully.', 'success')
    elif 'file_upload' in request.files:
        upload = request.files['file_upload']
        if upload.filename != '':
            filename = secure_filename(upload.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'assets')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, filename)
            upload.save(file_path)
            
            f = AssetFile(asset_id=asset_id, file_name=file_name, file_path=url_for('static', filename=f'uploads/assets/{filename}'), is_url=False, notes=notes)
            db.session.add(f)
            db.session.commit()
            flash('File uploaded successfully.', 'success')
        else:
            flash('No file selected.', 'warning')
            return redirect(url_for('assets.view', id=asset_id, tab='files'))
            
    return redirect(url_for('assets.view', id=asset_id, tab='files'))

@assets_bp.route('/file/<int:id>/remove', methods=['POST'])
@login_required
def remove_file(id):
    from models import AssetFile
    f = AssetFile.query.get_or_404(id)
    asset_id = f.asset_id
    db.session.delete(f)
    db.session.commit()
    flash('File reference removed.', 'info')
    return redirect(url_for('assets.view', id=asset_id, tab='files'))

@assets_bp.route('/api/mqtt/scan', methods=['POST'])
@login_required
def scan_mqtt():
    from flask import jsonify
    import json
    import paho.mqtt.client as mqtt
    import time
    
    broker = request.form.get('broker', '').strip()
    
    # Auto-sanitize prefixes
    for prefix in ['mqtt://', 'mqtts://', 'tcp://', 'tls://', 'ws://', 'wss://', 'http://', 'https://']:
        if broker.startswith(prefix):
            broker = broker[len(prefix):]
            
    port = request.form.get('port', type=int) or 1883
    topic = request.form.get('topic')
    
    if not broker or not topic:
        return jsonify({'success': False, 'error': 'Broker and Topic are required.'})
        
    result = {'keys': []}
    
    def on_message(client, userdata, msg):
        try:
            from mqtt_client import flatten_mqtt_payload
            payload = json.loads(msg.payload.decode('utf-8'))
            flat_payload = flatten_mqtt_payload(payload)
            result['keys'] = list(flat_payload.keys())
        except Exception:
            pass
        client.disconnect()
        
    client = mqtt.Client()
    client.on_message = on_message
    
    try:
        client.connect(broker, int(port), 60)
        client.subscribe(topic)
        client.loop_start()
        
        # Probe topic for up to 60 seconds waiting for the first payload broadcast
        for _ in range(600):
            if result['keys']:
                break
            time.sleep(0.1)
            
        client.loop_stop()
        
        if result['keys']:
            return jsonify({'success': True, 'keys': sorted(result['keys'])})
        else:
            return jsonify({'success': False, 'error': 'Timeout. Menunggu selama 60 detik namun tidak ada pesan JSON yang masuk di topik ini. Pastikan alat Anda menyala dan sedang rutin mengirim data.'})
    except Exception as e:
        error_msg = str(e)
        if '11001' in error_msg or 'getaddrinfo' in error_msg:
            error_msg = f"Host '{broker}' tidak ditemukan. Pastikan URL Broker diketik dengan benar dan internet Anda aktif."
        return jsonify({'success': False, 'error': error_msg})

@assets_bp.route('/<int:id>/meters/analyze', methods=['POST'])
@login_required
def analyze_meters(id):
    import os
    import requests
    from flask import jsonify
    from models import Asset, SystemSetting
    
    asset = Asset.query.get_or_404(id)
    data = request.json or {}
    
    # 1. Retrieve API key from SystemSetting (Database) or environment
    db_key_setting = SystemSetting.query.filter_by(setting_key='GROQ_API_KEY').first()
    groq_api_key = (db_key_setting.setting_value.strip() if db_key_setting and db_key_setting.setting_value else None) or os.environ.get('GROQ_API_KEY')
    
    if not groq_api_key:
        return jsonify({
            'success': False, 
            'message': 'API Key Groq belum disetting. Silakan atur GROQ_API_KEY di System Settings atau file .env.'
        }), 500
        
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({'success': False, 'message': 'Prompt analisis kosong.'}), 400
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    
    # Candidate models in order of capability & availability
    candidate_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "deepseek-r1-distill-llama-70b"
    ]
    
    last_error_message = None
    for model_name in candidate_models:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system", 
                    "content": "Anda adalah asisten ahli maintenance engineering (CMMS). Tugas Anda menganalisis kondisi aset berdasarkan pembacaan meter/sensor terbaru dan memberikan rekomendasi teknis, mendeteksi anomali, dan peringatan jika perlu. Jawablah menggunakan bahasa Indonesia secara profesional, terstruktur, dan informatif. Gunakan format Markdown."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 2048
        }
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                content = result['choices'][0]['message']['content']
                return jsonify({'success': True, 'output': content, 'model_used': model_name})
            
            # Extract detailed error from Groq response body
            error_data = {}
            try:
                error_data = resp.json().get('error', {})
            except Exception:
                pass
            
            error_msg = error_data.get('message', resp.text)
            error_code = error_data.get('code')
            
            # If 401 Unauthorized, no need to retry other models
            if resp.status_code == 401 or error_code == 'invalid_api_key':
                return jsonify({
                    'success': False,
                    'message': f'API Key Groq tidak valid: {error_msg}. Pastikan GROQ_API_KEY aktif dan benar.'
                }), 401
                
            # If 429 Rate limit
            if resp.status_code == 429:
                return jsonify({
                    'success': False,
                    'message': f'Kuota/Rate Limit Groq tercapai: {error_msg}. Silakan coba kembali dalam beberapa saat.'
                }), 429
                
            # If 404 (model not found / decommissioned), try next candidate model
            last_error_message = f"Model {model_name}: {error_msg}"
            continue
            
        except requests.exceptions.Timeout:
            last_error_message = f"Request timeout saat menghubungi model {model_name}."
            continue
        except Exception as e:
            last_error_message = str(e)
            continue
            
    return jsonify({
        'success': False,
        'message': f'Gagal menghubungi Groq API: {last_error_message}'
    }), 500

@assets_bp.route('/api/assets/<int:asset_id>/meters/latest', methods=['GET'])
@limiter.exempt
@login_required
def get_latest_meter_readings(asset_id):
    from models import AssetMeter, AssetMeterReading
    from flask import jsonify
    import datetime as dt
    
    meters = AssetMeter.query.filter_by(asset_id=asset_id).all()
    results = {}
    
    for meter in meters:
        readings = AssetMeterReading.query.filter_by(meter_id=meter.id).order_by(AssetMeterReading.reading_date.desc()).limit(5).all()
        
        meter_data = []
        for r in readings:
            meter_data.append({
                'date': (r.reading_date + dt.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S'),
                'value': r.reading_value,
                'user': r.user.name if r.user else '-'
            })
        results[meter.id] = meter_data
        
    return jsonify({'success': True, 'meters': results})

@assets_bp.route('/api/proxy')
@limiter.exempt
@login_required
def api_proxy():
    from flask import jsonify
    import requests
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    try:
        resp = requests.get(url, timeout=60)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@assets_bp.route('/<int:asset_id>/sync_iot', methods=['POST'])
@login_required
def sync_iot_api(asset_id):
    from models import AssetCustomField, Asset
    asset = Asset.query.get_or_404(asset_id)
    api_url = request.form.get('api_url')
    if not api_url:
        flash('API URL diperlukan.', 'danger')
        return redirect(url_for('assets.view', id=asset_id, tab='metering'))
    cf = AssetCustomField.query.filter_by(asset_id=asset.id, field_name='IoT API URL').first()
    if not cf:
        cf = AssetCustomField(asset_id=asset.id, field_name='IoT API URL')
        db.session.add(cf)
    cf.field_value = api_url
    db.session.commit()
    flash('URL IoT API berhasil disimpan. Data akan di-render secara live di browser.', 'success')
    return redirect(url_for('assets.view', id=asset_id, tab='metering'))
