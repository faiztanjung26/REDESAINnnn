from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(50), index=True, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='Technician') # Admin, Supervisor, Technician, User
    phone_number = db.Column(db.String(20), nullable=True) # Untuk notifikasi WhatsApp
    is_approved = db.Column(db.Boolean, default=False)
    
    # New Field: Site Segregation
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=True) # Null = All Sites / Kantor
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    
    # Login Tracking
    last_login = db.Column(db.DateTime, nullable=True)
    login_count = db.Column(db.Integer, default=0)
    last_active = db.Column(db.DateTime, nullable=True)
    session_token = db.Column(db.String(64), nullable=True)

    @property
    def is_online(self):
        if not self.last_active:
            return False
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7)
        return (now - self.last_active) < timedelta(minutes=5)

    # Relationships
    work_orders = db.relationship('WorkOrder', backref='assignee', lazy='dynamic')
    site = db.relationship('Site') # Link to their specific site
    team = db.relationship('Team', backref=db.backref('users', lazy='dynamic'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    @property
    def map_x(self):
        return None
        
    @property
    def map_y(self):
        return None
        
    def get_current_activity(self):
        if not self.is_online:
            return "Offline"
            
        for wo in self.work_orders:
            if wo.current_status and wo.current_status.control_type == 'Active':
                return f"Mengerjakan: {wo.code}"
                
        return "Online (Idle)"

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False) # e.g. 'LOGIN_FAILED', 'USER_CREATED', 'ROLE_CHANGED'
    target_table = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    partner_organization = db.Column(db.String(100), nullable=False)
    point_of_contact = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    mobile_number = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Site(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255))
    timezone = db.Column(db.String(50), default='UTC')
    api_site_id = db.Column(db.String(50), nullable=True) # Mapping to jti-new2 chiller.site_id
    project_code = db.Column(db.String(50), nullable=True) # Mapping to ProjectCode
    
    # Relationships
    locations = db.relationship('Location', backref='site', lazy='dynamic')
    assets = db.relationship('Asset', backref='site', lazy='dynamic')
    safe_ranges = db.relationship('SiteSafeRange', backref='site', lazy='dynamic', cascade='all, delete-orphan')
    teams = db.relationship('Team', backref='site', lazy='dynamic', cascade='all, delete-orphan')

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)

class SiteSafeRange(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    parameter_key = db.Column(db.String(100), nullable=False)
    min_value = db.Column(db.Float, nullable=True)
    max_value = db.Column(db.Float, nullable=True)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    
    # Foreign Keys
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True) # Optional back-comp
    
    # Relationships
    assets = db.relationship('Asset', backref='location', lazy='dynamic')

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), default='Asset') # Asset, Part
    
    # Relationships
    subcategories = db.relationship('SubCategory', backref='category', lazy='dynamic')
    locations = db.relationship('Location', backref='category', lazy='dynamic')
    assets = db.relationship('Asset', backref='category', lazy='dynamic')

class SubCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # Foreign Keys
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    
    # Relationships
    assets = db.relationship('Asset', backref='subcategory', lazy='dynamic')

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default='Online') # Online, Offline, In Repair
    criticality = db.Column(db.String(20), default='Medium') # Low, Medium, High, Critical
    
    # New Fields for Phase 7
    project_code = db.Column(db.String(50), nullable=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    estimated_hours = db.Column(db.Float, nullable=True)
    
    description = db.Column(db.Text, nullable=True)
    storage_aisle = db.Column(db.String(50), nullable=True)
    storage_row = db.Column(db.String(50), nullable=True)
    storage_bin = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    make = db.Column(db.String(100), nullable=True)
    model = db.Column(db.String(100), nullable=True)
    serial_number = db.Column(db.String(100), nullable=True)
    barcode = db.Column(db.String(100), nullable=True)
    replacement_value = db.Column(db.Float, default=0.0)
    is_chiller = db.Column(db.Boolean, default=False)
    api_chiller_id = db.Column(db.String(50), nullable=True)
    
    # Foreign Keys
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=True) # Optional for now to not break existing data
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    subcategory_id = db.Column(db.Integer, db.ForeignKey('sub_category.id'), nullable=True)
    
    # Relationships
    work_orders = db.relationship('WorkOrder', backref='asset', lazy='dynamic')
    bom_parts = db.relationship('AssetPartBOM', backref='asset', lazy='dynamic', cascade='all, delete-orphan')
    meters = db.relationship('AssetMeter', backref='asset', lazy='dynamic', cascade='all, delete-orphan')
    personnel = db.relationship('AssetPersonnel', backref='asset', lazy='dynamic', cascade='all, delete-orphan')
    warranties = db.relationship('AssetWarranty', backref='asset', lazy='dynamic', cascade='all, delete-orphan')
    businesses = db.relationship('AssetBusiness', backref='asset', lazy='dynamic', cascade='all, delete-orphan')
    files = db.relationship('AssetFile', backref='asset', lazy='dynamic', cascade='all, delete-orphan')
    custom_fields = db.relationship('AssetCustomField', backref='asset', lazy='dynamic', cascade='all, delete-orphan')

class AssetPartBOM(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    quantity = db.Column(db.Float, default=1.0)
    note = db.Column(db.String(255))
    
    part = db.relationship('Part')

class AssetMeter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(50))
    
    # API Integration Fields (Replaces MQTT)
    api_url = db.Column(db.String(500), nullable=True)
    api_method = db.Column(db.String(10), default='GET')
    api_json_key = db.Column(db.String(255), nullable=True)
    api_interval = db.Column(db.Integer, default=5) # In minutes
    
    # Legacy MQTT Integration Fields
    mqtt_broker = db.Column(db.String(255), nullable=True)
    mqtt_port = db.Column(db.Integer, default=1883)
    mqtt_topic = db.Column(db.String(255), nullable=True)
    mqtt_payload_key = db.Column(db.String(255), nullable=True)
    
    readings = db.relationship('AssetMeterReading', backref='meter', lazy='dynamic', cascade='all, delete-orphan')

class AssetMeterReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('asset_meter.id'), nullable=False)
    reading_value = db.Column(db.Float, nullable=False)
    reading_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    user = db.relationship('User')

class AssetPersonnel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notify_on_status_change = db.Column(db.Boolean, default=False)
    notify_on_wo = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User')

class AssetWarranty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    type = db.Column(db.String(50)) 
    provider = db.Column(db.String(100))
    lifespan = db.Column(db.String(100))
    expiry_date = db.Column(db.DateTime)
    cert_number = db.Column(db.String(100))
    description = db.Column(db.Text)

class AssetBusiness(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    supplier_part_number = db.Column(db.String(100))
    catalog = db.Column(db.String(100))
    price = db.Column(db.Float, default=0.0)
    is_preferred = db.Column(db.Boolean, default=False)
    
    vendor = db.relationship('Vendor')

class AssetFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    is_url = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(255))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

class AssetCustomField(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    field_value = db.Column(db.Text)
    expiry_date = db.Column(db.DateTime, nullable=True)

wo_assignees = db.Table('wo_assignees',
    db.Column('work_order_id', db.Integer, db.ForeignKey('work_order.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class WorkOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey('work_order_status.id'), nullable=True) # Replaces string status
    priority = db.Column(db.String(20), default='Medium') # Highest, High, Medium, Low, None
    maintenance_type = db.Column(db.String(50), default='Corrective') # Preventive, Corrective, Inspection, Other
    
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Tracking Fields
    project_code = db.Column(db.String(50), nullable=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    suggested_start_date = db.Column(db.DateTime, nullable=True)
    suggested_completion_date = db.Column(db.DateTime, nullable=True)
    estimated_hours = db.Column(db.Float, nullable=True)
    work_instructions = db.Column(db.Text, nullable=True)
    delay_reason = db.Column(db.Text, nullable=True)
    tasklist_note = db.Column(db.Text, nullable=True)
    
    # Foreign Keys
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # User ID
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    tasklist_id = db.Column(db.Integer, db.ForeignKey('tasklist.id'), nullable=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey('checklist.id'), nullable=True)
    helpdesk_ticket_id = db.Column(db.Integer, db.ForeignKey('helpdesk_ticket.id'), nullable=True)
    
    # Signatures
    customer_name = db.Column(db.String(100), nullable=True)
    customer_title = db.Column(db.String(100), nullable=True)
    customer_signature = db.Column(db.Text, nullable=True)
    technician_signature = db.Column(db.Text, nullable=True)
    
    # Relationships
    team = db.relationship('Team')
    assignees = db.relationship('User', secondary=wo_assignees, lazy='subquery', backref=db.backref('assigned_work_orders', lazy=True))
    tasklist = db.relationship('Tasklist', backref='work_orders')
    checklist = db.relationship('Checklist', backref='work_orders')
    procedures = db.relationship('WorkOrderProcedure', backref='work_order', lazy='dynamic', cascade='all, delete-orphan', order_by='WorkOrderProcedure.id')
    checklist_parameters = db.relationship('WorkOrderChecklistParameter', backref='work_order', lazy='dynamic', cascade='all, delete-orphan', order_by='WorkOrderChecklistParameter.id')

class WorkOrderStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    control_type = db.Column(db.String(20), default='Active') # Draft, Pending, Active, Closed
    
    @property
    def state_type(self):
        return self.control_type
        
    @state_type.setter
    def state_type(self, value):
        self.control_type = value

    def __init__(self, **kwargs):
        if 'state_type' in kwargs and 'control_type' not in kwargs:
            kwargs['control_type'] = kwargs.pop('state_type')
        super().__init__(**kwargs)
    
    # Relationships
    work_orders = db.relationship('WorkOrder', backref='current_status', lazy='dynamic')

class WorkOrderAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    work_order = db.relationship('WorkOrder', backref=db.backref('attachments', lazy='dynamic', cascade='all, delete-orphan'))

class WorkOrderPart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    quantity_used = db.Column(db.Float, default=1.0)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    work_order = db.relationship('WorkOrder', backref=db.backref('used_parts', lazy='dynamic', cascade='all, delete-orphan'))
    part = db.relationship('Part', backref=db.backref('work_orders_used_in', lazy='dynamic'))

class WorkOrderLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    log_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    work_order = db.relationship('WorkOrder', backref=db.backref('logs', lazy='dynamic', order_by='WorkOrderLog.created_at.desc()', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('work_order_logs', lazy='dynamic'))

class Part(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    make = db.Column(db.String(50))
    model_num = db.Column(db.String(50))
    price = db.Column(db.Float, default=0.0)
    unit_cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default='IDR')
    unit = db.Column(db.String(50))
    
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    
    # Relationships
    site = db.relationship('Site', backref=db.backref('parts', lazy='dynamic'))
    category = db.relationship('Category', backref=db.backref('parts', lazy='dynamic'))

class StockLevel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    qty_on_hand = db.Column(db.Integer, default=0)
    min_qty = db.Column(db.Integer, default=0)
    aisle = db.Column(db.String(20))
    bin_number = db.Column(db.String(20))
    row = db.Column(db.String(20))
    
    last_restock_date = db.Column(db.Date, nullable=True)
    pic_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    source_from = db.Column(db.String(100), nullable=True)
    
    # Relationships
    part = db.relationship('Part', backref=db.backref('stock_levels', lazy='dynamic'))
    site = db.relationship('Site', backref=db.backref('stock_levels', lazy='dynamic'))
    pic = db.relationship('User', foreign_keys=[pic_id])

class StockTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_code = db.Column(db.String(50), unique=True, nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(20), nullable=False) # 'ADD' or 'ADJUST'
    qty_before = db.Column(db.Integer, nullable=False)
    qty_after = db.Column(db.Integer, nullable=False)
    qty_change = db.Column(db.Integer, nullable=False)
    source_from = db.Column(db.String(100), nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    part = db.relationship('Part', backref=db.backref('stock_transactions', lazy='dynamic'))
    site = db.relationship('Site', backref=db.backref('stock_transactions', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('stock_transactions', lazy='dynamic'))

class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    trade = db.Column(db.String(100))
    contact_info = db.Column(db.Text)

class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default='Draft') # Draft, Submitted, Approved, Receiving, Closed
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    total_cost = db.Column(db.Float, default=0.0)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    vendor = db.relationship('Vendor', backref=db.backref('purchase_orders', lazy='dynamic'))
    site = db.relationship('Site', backref=db.backref('purchase_orders', lazy='dynamic'))
    requester = db.relationship('User', backref=db.backref('purchase_requests', lazy='dynamic'))

class POItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_order.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    quantity = db.Column(db.Float, default=1.0)
    unit_cost = db.Column(db.Float, default=0.0)
    line_total = db.Column(db.Float, default=0.0)
    
    # Relationships
    purchase_order = db.relationship('PurchaseOrder', backref=db.backref('items', lazy='dynamic'))
    part = db.relationship('Part', backref=db.backref('po_items', lazy='dynamic'))

class MaterialRequisition(db.Model):
    __tablename__ = 'material_requisition'
    id = db.Column(db.Integer, primary_key=True)
    requisition_no = db.Column(db.String(100), unique=True, nullable=False)
    request_date = db.Column(db.Date, default=datetime.utcnow)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    project_code = db.Column(db.String(50), nullable=True)
    category_division = db.Column(db.String(50), default='OT') # OT, Cons, FA, ME, EL, etc.
    delivery_type = db.Column(db.String(50), default='DIRECT_SITE') # DIRECT_SITE, VIA_JTI
    drawing_ref = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default='Submitted') # Draft, Submitted, Approved, Purchasing, Arrived_JTI, Shipped_to_Site, Received_Site, Rejected, Cancelled
    
    # Requester / Technician
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requester_signature = db.Column(db.Text, nullable=True) # Base64 signature
    requester_signed_at = db.Column(db.DateTime, nullable=True)
    
    # Supervisor / Approver
    supervisor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    supervisor_signature = db.Column(db.Text, nullable=True)
    supervisor_signed_at = db.Column(db.DateTime, nullable=True)
    supervisor_notes = db.Column(db.Text, nullable=True)
    
    # JTI Receiver (For VIA_JTI)
    jti_receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    jti_received_at = db.Column(db.DateTime, nullable=True)
    jti_notes = db.Column(db.Text, nullable=True)
    jti_receiver_photo = db.Column(db.String(255), nullable=True)
    
    # Site Receiver
    site_receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    site_receiver_signature = db.Column(db.Text, nullable=True)
    site_received_at = db.Column(db.DateTime, nullable=True)
    site_notes = db.Column(db.Text, nullable=True)
    site_receiver_photo = db.Column(db.String(255), nullable=True)
    
    # Purchasing info
    po_number = db.Column(db.String(100), nullable=True)
    purchasing_notes = db.Column(db.Text, nullable=True)
    
    # Hold Tracking
    previous_status = db.Column(db.String(50), nullable=True)
    hold_reason = db.Column(db.Text, nullable=True)
    held_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    held_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    site = db.relationship('Site', backref=db.backref('material_requisitions', lazy='dynamic'))
    requester = db.relationship('User', foreign_keys=[requester_id], backref=db.backref('requested_ppms', lazy='dynamic'))
    supervisor = db.relationship('User', foreign_keys=[supervisor_id], backref=db.backref('approved_ppms', lazy='dynamic'))
    jti_receiver = db.relationship('User', foreign_keys=[jti_receiver_id])
    site_receiver = db.relationship('User', foreign_keys=[site_receiver_id])
    held_by = db.relationship('User', foreign_keys=[held_by_id])
    items = db.relationship('MaterialRequisitionItem', backref='requisition', lazy='dynamic', cascade='all, delete-orphan')

class MaterialRequisitionItem(db.Model):
    __tablename__ = 'material_requisition_item'
    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('material_requisition.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=True)
    
    item_name = db.Column(db.String(255), nullable=False)
    size_capacity = db.Column(db.String(255), nullable=True)
    spec_brand = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(50), default='Pcs')
    target_date = db.Column(db.Date, nullable=True)
    warehouse_stock = db.Column(db.Integer, default=0)
    purchase_status = db.Column(db.String(100), default='Pending') # Pending, Ordered, Shipped, Received, Out of Stock
    notes = db.Column(db.Text, nullable=True)
    
    qty_received_jti = db.Column(db.Float, default=0.0)
    qty_received_site = db.Column(db.Float, default=0.0)
    
    part = db.relationship('Part')

class MaterialRequisitionLog(db.Model):
    __tablename__ = 'material_requisition_log'
    id = db.Column(db.Integer, primary_key=True)
    requisition_id = db.Column(db.Integer, db.ForeignKey('material_requisition.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    requisition = db.relationship('MaterialRequisition', backref=db.backref('logs', lazy='dynamic', order_by='MaterialRequisitionLog.created_at.desc()', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('ppm_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<MaterialRequisitionLog {self.id} for PPM {self.requisition_id}: {self.action}>'

class ProjectCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))

class Tasklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    project_code = db.Column(db.String(50), nullable=True)
    
    # Relationships
    procedures = db.relationship('TasklistProcedure', backref='tasklist', lazy='dynamic', cascade='all, delete-orphan', order_by='(TasklistProcedure.position, TasklistProcedure.id)')

class TasklistProcedure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tasklist_id = db.Column(db.Integer, db.ForeignKey('tasklist.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    requires_attachment = db.Column(db.Boolean, default=False)
    min_photos = db.Column(db.Integer, default=0)
    estimated_minutes = db.Column(db.Integer, default=0)
    position = db.Column(db.Integer, default=0)
    
class Checklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    project_code = db.Column(db.String(50), nullable=True)
    
class ChecklistParameterTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey('checklist.id'), nullable=False)
    parameter = db.Column(db.String(100), nullable=False)
    standard = db.Column(db.String(100), nullable=False)
    position = db.Column(db.Integer, default=0)
    
    checklist = db.relationship('Checklist', backref=db.backref('parameters', lazy='dynamic', order_by='(ChecklistParameterTemplate.position, ChecklistParameterTemplate.id)'))

class WorkOrderProcedure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    tasklist_name = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    requires_attachment = db.Column(db.Boolean, default=False)
    min_photos = db.Column(db.Integer, default=0)
    estimated_minutes = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50), default='Pending') # Pending, Done, Failed
    notes = db.Column(db.Text, nullable=True)
    attachment_path = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # relationships
    completed_by = db.relationship('User', foreign_keys=[completed_by_id])

class WorkOrderChecklistParameter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    checklist_name = db.Column(db.String(100), nullable=True)
    parameter = db.Column(db.String(100), nullable=False)
    standard = db.Column(db.String(100), nullable=False)
    value = db.Column(db.String(100), nullable=True)
    note = db.Column(db.Text, nullable=True)

# Association table for multiple technicians
helpdesk_ticket_technician = db.Table('helpdesk_ticket_technician',
    db.Column('ticket_id', db.Integer, db.ForeignKey('helpdesk_ticket.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class HelpdeskTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_code = db.Column(db.String(50), unique=True, nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # Information
    company = db.Column(db.String(100), nullable=True)
    is_internal = db.Column(db.Boolean, default=False)
    divisi_tujuan = db.Column(db.String(100), nullable=True)
    modul = db.Column(db.String(100), nullable=True)
    location_subject = db.Column(db.String(255), nullable=True)
    asset = db.Column(db.String(255), nullable=True)
    ticket_type = db.Column(db.String(100), nullable=True)
    complain_type = db.Column(db.String(255), nullable=True)
    damage_photo = db.Column(db.String(255), nullable=True)
    damage_note = db.Column(db.Text, nullable=True)
    
    # Customer
    partner = db.Column(db.String(100), nullable=True)
    person_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    mobile = db.Column(db.String(50), nullable=True)
    
    # Responsible
    team = db.Column(db.String(100), nullable=True)
    team_head = db.Column(db.String(100), nullable=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    priority = db.Column(db.String(50), nullable=True)
    
    # Miscellaneous
    tags = db.Column(db.String(255), nullable=True)
    scheduled_start_date = db.Column(db.DateTime, nullable=True)
    scheduled_end_date = db.Column(db.DateTime, nullable=True)
    actual_end_date = db.Column(db.DateTime, nullable=True)
    
    # Tracking
    status = db.Column(db.String(50), default='New') # New, Action Plan, WIP, Done...
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Tasklist & Checklist Master References
    tasklist_id = db.Column(db.Integer, db.ForeignKey('tasklist.id'), nullable=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey('checklist.id'), nullable=True)
    
    # Relationships
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id], backref=db.backref('primary_assigned_tickets', lazy='dynamic'))
    technicians = db.relationship('User', secondary=helpdesk_ticket_technician, backref=db.backref('assigned_helpdesk_tickets', lazy='dynamic'))
    work_orders = db.relationship('WorkOrder', backref='helpdesk_ticket', lazy='dynamic')
    tasklist = db.relationship('Tasklist', foreign_keys=[tasklist_id])
    checklist = db.relationship('Checklist', foreign_keys=[checklist_id])

class HelpdeskProcedure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('helpdesk_ticket.id'), nullable=False)
    tasklist_name = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    requires_attachment = db.Column(db.Boolean, default=False)
    min_photos = db.Column(db.Integer, default=0)
    estimated_minutes = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50), default='Pending') # Pending, Done, Failed
    notes = db.Column(db.Text, nullable=True)
    attachment_path = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # relationships
    ticket = db.relationship('HelpdeskTicket', backref=db.backref('procedures', lazy='dynamic', cascade='all, delete-orphan'))
    completed_by = db.relationship('User', foreign_keys=[completed_by_id])

class HelpdeskChecklistParameter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('helpdesk_ticket.id'), nullable=False)
    checklist_name = db.Column(db.String(100), nullable=True)
    parameter = db.Column(db.String(100), nullable=False)
    standard = db.Column(db.String(100), nullable=False)
    value = db.Column(db.String(100), nullable=True)
    note = db.Column(db.Text, nullable=True)
    
    # relationships
    ticket = db.relationship('HelpdeskTicket', backref=db.backref('checklists', lazy='dynamic', cascade='all, delete-orphan'))

class HelpdeskProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('helpdesk_ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    ticket = db.relationship('HelpdeskTicket', backref=db.backref('progress_logs', lazy='dynamic', cascade='all, delete-orphan', order_by='HelpdeskProgress.created_at.asc()'))
    user = db.relationship('User')

class HelpdeskProgressFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    progress_id = db.Column(db.Integer, db.ForeignKey('helpdesk_progress.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    progress = db.relationship('HelpdeskProgress', backref=db.backref('files', lazy='dynamic', cascade='all, delete-orphan'))

class HelpdeskTicketLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('helpdesk_ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    log_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    ticket = db.relationship('HelpdeskTicket', backref=db.backref('activity_logs', lazy='dynamic', order_by='HelpdeskTicketLog.created_at.desc()', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('helpdesk_logs', lazy='dynamic'))

class HelpdeskPart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('helpdesk_ticket.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), nullable=False)
    quantity_used = db.Column(db.Float, default=1.0)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    ticket = db.relationship('HelpdeskTicket', backref=db.backref('used_parts', lazy='dynamic', cascade='all, delete-orphan'))
    part = db.relationship('Part', backref=db.backref('helpdesk_tickets_used_in', lazy='dynamic'))

class HelpdeskModule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=True) # Allowed null for global if needed
    
    site = db.relationship('Site', backref=db.backref('hd_modules', lazy='dynamic'))

class HelpdeskLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=True) # Allowed null for global if needed
    
    site = db.relationship('Site', backref=db.backref('hd_locations', lazy='dynamic'))

class ChillerFaultCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chiller_type = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False, default='general')
    fault_code = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)

class UserDashboardWidget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    widget_key = db.Column(db.String(50), nullable=False)
    position = db.Column(db.Integer, default=0)
    col_span = db.Column(db.Integer, default=6)
    is_visible = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('dashboard_widgets', lazy='dynamic'))

class CustomSidebarLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(50), default='bi-link-45deg')
    position = db.Column(db.Integer, default=0)
    
    user = db.relationship('User', backref=db.backref('custom_links', lazy='dynamic'))

class CustomDashboard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), default='bi-speedometer2')
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    widgets = db.relationship('CustomDashboardWidget', backref='dashboard', lazy='dynamic', cascade='all, delete-orphan')
    user = db.relationship('User', backref=db.backref('custom_dashboards', lazy='dynamic'))

class CustomDashboardWidget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dashboard_id = db.Column(db.Integer, db.ForeignKey('custom_dashboard.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    widget_type = db.Column(db.String(50), default='value_card')
    data_source = db.Column(db.String(50), nullable=False)
    data_config = db.Column(db.Text)  # JSON: {"asset_id": 1, "meter_id": 5, ...}
    position = db.Column(db.Integer, default=0)
    col_span = db.Column(db.Integer, default=4)
    color = db.Column(db.String(20), default='primary')

class SavedWorkOrderView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    view_mode = db.Column(db.String(20), default='pivot')
    pivot_row = db.Column(db.String(50))
    pivot_col = db.Column(db.String(50))
    filters = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('saved_views', lazy='dynamic'))


# ============================================
# LOGSHEET MODELS - Separate from Work Orders
# ============================================

class LogsheetTemplate(db.Model):
    """Master Data for Logsheet Checklist Templates"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LogsheetTemplateParameter(db.Model):
    """Parameters predefined in a Logsheet Template"""
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('logsheet_template.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    entry_type = db.Column(db.String(20), default='reading') # reading, task, observation
    unit = db.Column(db.String(20), nullable=True)
    standard_min = db.Column(db.Float, nullable=True)
    standard_max = db.Column(db.Float, nullable=True)
    position = db.Column(db.Integer, default=0)

    template = db.relationship('LogsheetTemplate', backref=db.backref('parameters', lazy='dynamic', order_by='(LogsheetTemplateParameter.position, LogsheetTemplateParameter.id)'))

# Association table for multiple technicians in a schedule
logsheet_schedule_technicians = db.Table('logsheet_schedule_technicians',
    db.Column('schedule_id', db.Integer, db.ForeignKey('logsheet_schedule.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)


class LogsheetSchedule(db.Model):
    """Schedule template for logsheets - created by Admin/Supervisor"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Daily Chiller Check", "Weekly PM Generator"
    code = db.Column(db.String(50), unique=True, nullable=False)  # Format: SCH-YYYYMMDD-XXX

    # Schedule Info
    scheduled_date = db.Column(db.Date, nullable=False)
    scheduled_time = db.Column(db.Time, nullable=True)  # e.g., 08:00, 20:00
    shift = db.Column(db.String(10), nullable=True)  # SHIFT1, SHIFT2, SHIFT3

    # Asset Info
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    asset = db.relationship('Asset', backref=db.backref('logsheet_schedules', lazy='dynamic'))

    # Site Info
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    site = db.relationship('Site', backref=db.backref('logsheet_schedules', lazy='dynamic'))

    # Created by
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_by = db.relationship('User')

    # Team Assigned (Optional)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    team = db.relationship('Team', backref=db.backref('assigned_logsheets', lazy='dynamic'))

    # Status: Scheduled, In Progress, Completed, Cancelled
    status = db.Column(db.String(20), default='Scheduled')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    assigned_technicians = db.relationship('User', secondary=logsheet_schedule_technicians,
                                            backref=db.backref('assigned_logsheets', lazy='dynamic'))
    parameters = db.relationship('LogsheetScheduleParameter', backref='schedule', lazy='dynamic',
                                  cascade='all, delete-orphan', order_by='(LogsheetScheduleParameter.position, LogsheetScheduleParameter.id)')
    # Link to filled logsheet
    logsheet = db.relationship('Logsheet', back_populates='logsheet_schedule', uselist=False)

    def __repr__(self):
        return f'<LogsheetSchedule {self.code}>'


class LogsheetScheduleParameter(db.Model):
    """Predefined parameters for a logsheet schedule"""
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('logsheet_schedule.id'), nullable=False)

    # Parameter info
    name = db.Column(db.String(100), nullable=False)  # e.g., "Temperature Inlet", "Pressure"
    entry_type = db.Column(db.String(20), default='reading')  # reading, task, observation
    unit = db.Column(db.String(20), nullable=True)  # e.g., "°C", "PSI"
    standard_min = db.Column(db.Float, nullable=True)
    standard_max = db.Column(db.Float, nullable=True)

    # Position for ordering
    position = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<Parameter {self.name}>'


class Logsheet(db.Model):
    """Filled Daily Maintenance Log Sheet"""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)  # Format: LS-YYYYMMDD-XXX

    # Link to schedule (optional)
    schedule_id = db.Column(db.Integer, db.ForeignKey('logsheet_schedule.id'), nullable=True)
    logsheet_schedule = db.relationship('LogsheetSchedule', back_populates='logsheet', uselist=False)

    # Date & Time
    date = db.Column(db.Date, nullable=False)
    shift = db.Column(db.String(10), nullable=True)

    # Status: Draft, Submitted, Approved
    status = db.Column(db.String(20), default='Draft')

    # Asset Info
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    asset = db.relationship('Asset', backref=db.backref('logsheets', lazy='dynamic'))

    # Site Info
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    site = db.relationship('Site', backref=db.backref('logsheets', lazy='dynamic'))

    # Operator/User filling the logsheet
    filled_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filled_by = db.relationship('User', foreign_keys=[filled_by_id])

    # Optional: Link to Work Order
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=True)
    work_order = db.relationship('WorkOrder', backref=db.backref('logsheets', lazy='dynamic'))

    # General Notes
    notes = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    entries = db.relationship('LogsheetEntry', backref='logsheet', lazy='dynamic', cascade='all, delete-orphan',
                              order_by='LogsheetEntry.position')
    signatures = db.relationship('LogsheetSignature', backref='logsheet', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Logsheet {self.code}>'

class LogsheetLog(db.Model):
    """Activity Log for Logsheet"""
    id = db.Column(db.Integer, primary_key=True)
    logsheet_id = db.Column(db.Integer, db.ForeignKey('logsheet.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('logsheet_logs', lazy='dynamic'))
    logsheet = db.relationship('Logsheet', backref=db.backref('logs', lazy='dynamic', order_by='LogsheetLog.created_at.desc()', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<LogsheetLog {self.id}: {self.action}>'


class LogsheetEntry(db.Model):
    """Individual entry in a logsheet (parameter readings, tasks, etc.)"""
    id = db.Column(db.Integer, primary_key=True)
    logsheet_id = db.Column(db.Integer, db.ForeignKey('logsheet.id'), nullable=False)

    # Entry type: reading, task, observation, issue
    entry_type = db.Column(db.String(30), nullable=False)

    # For readings
    parameter_name = db.Column(db.String(100), nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    value = db.Column(db.String(100), nullable=True)
    standard_min = db.Column(db.Float, nullable=True)
    standard_max = db.Column(db.Float, nullable=True)

    # For tasks/observations
    description = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)

    # For issues
    issue_severity = db.Column(db.String(20), nullable=True)
    requires_wo = db.Column(db.Boolean, default=False)

    # Position for ordering
    position = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LogsheetEntry {self.id}: {self.parameter_name or self.description}>'


class LogsheetSignature(db.Model):
    """Signatures for logsheet approval"""
    id = db.Column(db.Integer, primary_key=True)
    logsheet_id = db.Column(db.Integer, db.ForeignKey('logsheet.id'), nullable=False)

    signature_type = db.Column(db.String(30), nullable=False)  # operator, supervisor, qc

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User')

    signature_data = db.Column(db.Text, nullable=True)
    signed_name = db.Column(db.String(100), nullable=True)

    signed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<LogsheetSignature {self.signature_type}>'

class BasFrame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    site = db.relationship('Site')

    def __repr__(self):
        return f'<BasFrame {self.name}>'

class Shift(db.Model):
    __tablename__ = 'shift'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.Time, nullable=True) # made nullable for off days
    end_time = db.Column(db.Time, nullable=True)
    is_off_day = db.Column(db.Boolean, default=False)
    
    site = db.relationship('Site', backref=db.backref('shifts', lazy=True))

    def __repr__(self):
        return f'<Shift {self.name} at {self.site_id}>'

class UserShift(db.Model):
    __tablename__ = 'user_shift'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('user_shifts', lazy=True))
    shift = db.relationship('Shift', backref=db.backref('user_shifts', lazy=True))

    def __repr__(self):
        return f'<UserShift {self.user_id} on {self.date}>'

class DigitalSignature(db.Model):
    __tablename__ = 'digital_signature'
    id = db.Column(db.String(36), primary_key=True) # UUID
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    signer_name = db.Column(db.String(100), nullable=False)
    signer_title = db.Column(db.String(100), nullable=True)
    signed_at = db.Column(db.DateTime, default=datetime.utcnow)
    document_hash = db.Column(db.String(64), nullable=False) # SHA-256
    status = db.Column(db.String(20), default='Valid') # Valid, Revoked
    pdf_path = db.Column(db.String(255), nullable=True)
    
    work_order = db.relationship('WorkOrder', backref=db.backref('digital_signatures', lazy=True))

    def __repr__(self):
        return f'<DigitalSignature {self.id} for WO {self.work_order_id}>'

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_record'
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(50), nullable=False, index=True)
    nama = db.Column(db.String(100), nullable=True)
    date = db.Column(db.Date, nullable=False, index=True)
    jam_masuk = db.Column(db.DateTime, nullable=True)
    jam_pulang = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), nullable=True) # Sesuai Jadwal, Terlambat, Tidak Ada Jadwal
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_shift_id = db.Column(db.Integer, db.ForeignKey('user_shift.id'), nullable=True)
    
    user = db.relationship('User', backref=db.backref('attendances', lazy=True))
    user_shift = db.relationship('UserShift', backref=db.backref('attendance_records', lazy=True))

class SystemSetting(db.Model):
    __tablename__ = 'system_setting'
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<SystemSetting {self.setting_key}>'

class EmployeeLeave(db.Model):
    __tablename__ = 'employee_leave'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(50), default='Cuti') # Cuti Tahunan, Cuti Sakit, Cuti Alasan Penting, Izin
    reason = db.Column(db.Text, nullable=True)
    
    # Replacement tracking
    needs_replacement = db.Column(db.Boolean, default=False)
    replacement_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    replacement_status = db.Column(db.String(30), default='not_needed') # not_needed, pending, assigned
    original_shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=True)
    is_shift_swap = db.Column(db.Boolean, default=False) # True = Pindah Shift (bukan lembur)
    replacement_original_shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=True)
    
    # Overall leave status
    status = db.Column(db.String(20), default='Approved') # Approved, Cancelled
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    site = db.relationship('Site', backref=db.backref('employee_leaves', lazy=True))
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('leaves', lazy=True))
    replacement_user = db.relationship('User', foreign_keys=[replacement_user_id], backref=db.backref('replacing_leaves', lazy=True))
    original_shift = db.relationship('Shift', foreign_keys=[original_shift_id])
    replacement_original_shift = db.relationship('Shift', foreign_keys=[replacement_original_shift_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<EmployeeLeave {self.id} user {self.user_id} on {self.start_date} to {self.end_date}>'

class EmployeeOvertime(db.Model):
    __tablename__ = 'employee_overtime'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Approved') # Approved, Cancelled
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    site = db.relationship('Site', backref=db.backref('employee_overtimes', lazy=True))
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('overtimes', lazy=True))
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    @property
    def duration_hours(self):
        if not self.start_date or not self.start_time or not self.end_date or not self.end_time:
            return 0.0
        start_dt = datetime.combine(self.start_date, self.start_time)
        end_dt = datetime.combine(self.end_date, self.end_time)
        diff = (end_dt - start_dt).total_seconds()
        return max(0.0, round(diff / 3600.0, 2))

    def __repr__(self):
        return f'<EmployeeOvertime {self.id} user {self.user_id} from {self.start_date} {self.start_time} to {self.end_date} {self.end_time}>'

