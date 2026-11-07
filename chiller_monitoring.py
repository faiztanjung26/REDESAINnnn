from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify, Response
from flask_login import login_required
from models import Site, db, Asset, AssetMeter
import requests

chiller_monitoring_bp = Blueprint('chiller_monitoring', __name__, url_prefix='/monitoring')

@chiller_monitoring_bp.before_request
def restrict_to_admin():
    from flask_login import current_user
    if current_user.is_authenticated and current_user.role != 'Admin':
        flash('Fitur IoT Monitor hanya tersedia untuk Admin.', 'danger')
        return redirect(url_for('dashboard'))

@chiller_monitoring_bp.route('/')
@login_required
def index():
    active_site_id = session.get('active_site_id')
    api_site_id = None
    if active_site_id and active_site_id != '0':
        site = db.session.get(Site, int(active_site_id))
        if site and site.api_site_id:
            api_site_id = site.api_site_id
            
    # Auto-redirect if restricted to a specific API site
    if api_site_id:
        return redirect(url_for('chiller_monitoring.site', site_id=api_site_id))
        
    assets = Asset.query.all()
    from models import Site
    sites = Site.query.all()
    return render_template('monitoring/sites.html', assets=assets, sites=sites)

@chiller_monitoring_bp.route('/add_topic', methods=['POST'])
@login_required
def add_topic():
    asset_id = request.form.get('asset_id')
    meter_name = request.form.get('name')
    unit = request.form.get('unit')
    broker = request.form.get('broker')
    port = request.form.get('port', 1883, type=int)
    topic = request.form.get('topic')
    
    # Handle multi-select JSON Payload Keys
    payload_keys = request.form.getlist('payload_key')
    
    if payload_keys and len(payload_keys) > 0:
        for key in payload_keys:
            # If multiple are selected, append key for uniqueness
            m_name = meter_name if len(payload_keys) == 1 else f"{meter_name} - {key}"
            new_meter = AssetMeter(
                asset_id=asset_id,
                name=m_name,
                unit=unit,
                mqtt_broker=broker,
                mqtt_port=port,
                mqtt_topic=topic,
                mqtt_payload_key=key
            )
            db.session.add(new_meter)
    else:
        new_meter = AssetMeter(
            asset_id=asset_id,
            name=meter_name,
            unit=unit,
            mqtt_broker=broker,
            mqtt_port=port,
            mqtt_topic=topic,
            mqtt_payload_key=None
        )
        db.session.add(new_meter)
        
    db.session.commit()
    
    from flask import current_app
    try:
        from mqtt_client import refresh_mqtt_managers
        refresh_mqtt_managers(current_app)
    except Exception as e:
        print("Could not start mqtt client:", e)
        
    flash('MQTT Topic / Meter added successfully!', 'success')
    return redirect(url_for('chiller_monitoring.index'))

@chiller_monitoring_bp.route('/link_site', methods=['POST'])
@login_required
def link_site():
    from models import Site
    site_id = request.form.get('site_id', type=int)
    api_site_id = request.form.get('api_site_id', '').strip() or None
    
    if site_id:
        site = Site.query.get_or_404(site_id)
        site.api_site_id = api_site_id
        db.session.commit()
        flash(f'Site "{site.name}" linked to IoT ID "{api_site_id}" successfully!', 'success')
    else:
        flash('Invalid site selection.', 'danger')
        
    return redirect(url_for('chiller_monitoring.index'))

@chiller_monitoring_bp.route('/site/<string:site_id>')
@login_required
def site(site_id):
    active_site_id = session.get('active_site_id')
    
    # Enforce security if a user accesses a different site via URL
    if active_site_id and active_site_id != '0':
        db_site = db.session.get(Site, int(active_site_id))
        if db_site and db_site.api_site_id != site_id:
            flash("You do not have permission to view that site's telemetry.", "danger")
            return redirect(url_for('chiller_monitoring.index'))
            
    from models import Site, Asset
    # Query database site to get its assets
    db_site = Site.query.filter((Site.api_site_id == site_id) | (Site.name == site_id)).first()
    if db_site:
        assets = Asset.query.filter_by(site_id=db_site.id).all()
    else:
        assets = Asset.query.all()
        
    return render_template('monitoring/index.html', site_id=site_id, assets=assets)

@chiller_monitoring_bp.route('/dashboard/<string:chiller_id>')
@login_required
def dashboard(chiller_id):
    return render_template('monitoring/dashboard.html', chiller_id=chiller_id)

@chiller_monitoring_bp.route('/api/safe_ranges/<string:api_site_id>')
@login_required
def api_safe_ranges(api_site_id):
    site = Site.query.filter_by(api_site_id=api_site_id).first()
    if not site:
        return {}
        
    ranges = {}
    for r in site.safe_ranges:
        # Ignore empty values
        if r.min_value is None and r.max_value is None:
            continue
        ranges[r.parameter_key] = {
            "min": r.min_value,
            "max": r.max_value
        }
        
    return ranges

@chiller_monitoring_bp.route('/api/fault_mappings/<string:chiller_type>')
@login_required
def api_fault_mappings(chiller_type):
    from models import ChillerFaultCode
    faults = ChillerFaultCode.query.filter_by(chiller_type=chiller_type).all()
    
    mapping = {}
    for f in faults:
        if f.category not in mapping:
            mapping[f.category] = {}
        mapping[f.category][f.fault_code] = f.description
        
    return mapping

@chiller_monitoring_bp.route('/api_proxy/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def api_proxy(endpoint):
    chiller_api_base = os.environ.get('CHILLER_API_BASE_URL', 'http://127.0.0.1:8000')
    target_url = f"{chiller_api_base}/{endpoint}"
    try:
        # Pass query args
        query_str = request.query_string.decode('utf-8')
        if query_str:
            target_url = f"{target_url}?{query_str}"

        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={key: value for (key, value) in request.headers if key != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=15
        )

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]

        return Response(resp.content, resp.status_code, headers)
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to connect to internal IoT gateway: {str(e)}"}), 502
