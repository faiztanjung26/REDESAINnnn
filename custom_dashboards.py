"""
Custom Dashboard Builder Blueprint
Allows users to create custom dashboard pages with dynamic data widgets.
Supports 15+ data sources across 5 categories.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import (db, CustomDashboard, CustomDashboardWidget, Asset, AssetMeter,
                    AssetMeterReading, WorkOrder, Site, Category, Part, StockLevel,
                    HelpdeskTicket, PurchaseOrder, Vendor, WorkOrderPart,
                    AssetCustomField, WorkOrderStatus)
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
import json
import os
import traceback

custom_dashboards_bp = Blueprint('custom_dashboards', __name__, url_prefix='/custom-dashboard')

# ============================================
# IOT EXTERNAL DATABASE CONNECTION
# ============================================
def get_iot_db_connection():
    """Get connection to the external IoT/Chiller MySQL database."""
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=os.environ.get('IOT_MYSQL_HOST', '127.0.0.1'),
            user=os.environ.get('IOT_MYSQL_USER', 'root'),
            password=os.environ.get('IOT_MYSQL_PASSWORD', ''),
            database=os.environ.get('IOT_MYSQL_DB', 'jti-new2'),
            port=int(os.environ.get('IOT_MYSQL_PORT', '3306')),
            connect_timeout=5
        )
        return conn
    except Exception as e:
        print(f"[Custom Dashboard] IoT DB connection error: {e}")
        return None


# ============================================
# DATA SOURCE REGISTRY (Categorized)
# ============================================
DATA_SOURCES = {
    # ── Asset Data ──────────────────────────────
    'meter_latest': {
        'label': 'Asset Meter (Nilai Terakhir)',
        'icon': 'bi-speedometer2',
        'category': 'asset',
        'widget_type': 'value_card',
        'description': 'Ambil nilai terbaru dari meter aset (suhu, tekanan, kW, dll)',
        'config_fields': [
            {'name': 'asset_id', 'label': 'Pilih Asset', 'type': 'select_asset'},
            {'name': 'meter_id', 'label': 'Pilih Meter', 'type': 'select_meter'},
        ]
    },
    'meter_history': {
        'label': 'Meter Trend & Statistik',
        'icon': 'bi-graph-up',
        'category': 'asset',
        'widget_type': 'line_chart',
        'description': 'Trend line chart + Min/Max/Avg dari meter reading dalam periode waktu',
        'config_fields': [
            {'name': 'asset_id', 'label': 'Pilih Asset', 'type': 'select_asset'},
            {'name': 'meter_id', 'label': 'Pilih Meter', 'type': 'select_meter'},
            {'name': 'period', 'label': 'Periode', 'type': 'select', 'options': ['7 Hari', '30 Hari', '90 Hari', '1 Tahun']},
        ]
    },
    'asset_count': {
        'label': 'Jumlah Asset',
        'icon': 'bi-box',
        'category': 'asset',
        'widget_type': 'value_card',
        'description': 'Hitung jumlah asset berdasarkan filter status/site',
        'config_fields': [
            {'name': 'status', 'label': 'Status', 'type': 'select', 'options': ['All', 'Online', 'Offline', 'Under Repair', 'Decommissioned']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'asset_detail': {
        'label': 'Detail Info Asset',
        'icon': 'bi-info-circle',
        'category': 'asset',
        'widget_type': 'info_card',
        'description': 'Tampilkan info lengkap asset: status, site, lokasi, serial number, make/model',
        'config_fields': [
            {'name': 'asset_id', 'label': 'Pilih Asset', 'type': 'select_asset'},
        ]
    },
    'asset_custom_field': {
        'label': 'Asset Custom Field',
        'icon': 'bi-input-cursor-text',
        'category': 'asset',
        'widget_type': 'value_card',
        'description': 'Ambil nilai dari custom field asset tertentu',
        'config_fields': [
            {'name': 'asset_id', 'label': 'Pilih Asset', 'type': 'select_asset'},
            {'name': 'field_name', 'label': 'Nama Field', 'type': 'select_custom_field'},
        ]
    },
    'asset_uptime': {
        'label': 'Asset Downtime (Jam)',
        'icon': 'bi-clock-history',
        'category': 'asset',
        'widget_type': 'value_card',
        'description': 'Hitung total jam downtime asset berdasarkan WO Corrective dalam periode',
        'config_fields': [
            {'name': 'asset_id', 'label': 'Pilih Asset', 'type': 'select_asset'},
            {'name': 'period', 'label': 'Periode', 'type': 'select', 'options': ['30 Hari', '90 Hari', '1 Tahun', 'All Time']},
        ]
    },

    # ── Operational Data ────────────────────────
    'wo_count': {
        'label': 'Jumlah Work Order',
        'icon': 'bi-clipboard-data',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Hitung jumlah work order berdasarkan filter',
        'config_fields': [
            {'name': 'status_type', 'label': 'Status', 'type': 'select', 'options': ['All', 'Active', 'Closed', 'Pending', 'Draft']},
            {'name': 'maint_type', 'label': 'Tipe Maintenance', 'type': 'select', 'options': ['All', 'Preventive', 'Corrective', 'Predictive']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'wo_cost': {
        'label': 'Total Biaya Work Order',
        'icon': 'bi-currency-dollar',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Hitung total biaya parts yang terpakai di work orders',
        'config_fields': [
            {'name': 'status_type', 'label': 'Status', 'type': 'select', 'options': ['All', 'Active', 'Closed']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'helpdesk_count': {
        'label': 'Jumlah Tiket Helpdesk',
        'icon': 'bi-headset',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Hitung jumlah tiket helpdesk',
        'config_fields': [
            {'name': 'status', 'label': 'Status', 'type': 'select', 'options': ['All', 'New', 'Action Plan', 'WIP', 'Done', 'Open', 'In Progress', 'Resolved', 'Closed']},
        ]
    },
    'stock_level': {
        'label': 'Stock Level (Part)',
        'icon': 'bi-nut',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Tampilkan jumlah stok part tertentu',
        'config_fields': [
            {'name': 'part_id', 'label': 'Pilih Part', 'type': 'select_part'},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'kpi_value': {
        'label': 'KPI Metric',
        'icon': 'bi-activity',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Tampilkan KPI: MTBF, MTTR, PM Compliance, Asset Availability',
        'config_fields': [
            {'name': 'kpi_type', 'label': 'Jenis KPI', 'type': 'select', 'options': ['MTBF (Hours)', 'MTTR (Hours)', 'PM Compliance (%)', 'Asset Availability (%)']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'po_count': {
        'label': 'Jumlah Purchase Order',
        'icon': 'bi-cart',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Hitung jumlah PO berdasarkan status',
        'config_fields': [
            {'name': 'status', 'label': 'Status', 'type': 'select', 'options': ['All', 'Draft', 'Submitted', 'Approved', 'Receiving', 'Closed']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'po_total_cost': {
        'label': 'Total Biaya PO',
        'icon': 'bi-cash-stack',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Hitung total biaya purchase order',
        'config_fields': [
            {'name': 'status', 'label': 'Status', 'type': 'select', 'options': ['All', 'Draft', 'Submitted', 'Approved', 'Receiving', 'Closed']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'vendor_count': {
        'label': 'Jumlah Vendor',
        'icon': 'bi-building',
        'category': 'operational',
        'widget_type': 'value_card',
        'description': 'Hitung total vendor yang terdaftar',
        'config_fields': []
    },

    # ── IoT / Sensor ───────────────────────────
    'iot_chiller_param': {
        'label': 'IoT Chiller Parameter',
        'icon': 'bi-broadcast',
        'category': 'iot',
        'widget_type': 'value_card',
        'description': 'Ambil parameter real-time dari chiller (suhu, tekanan, kW, FLA, dll) via IoT Database',
        'config_fields': [
            {'name': 'iot_site_id', 'label': 'Pilih Site IoT', 'type': 'select_iot_site'},
            {'name': 'iot_chiller_id', 'label': 'Pilih Chiller', 'type': 'select_iot_chiller'},
            {'name': 'iot_param', 'label': 'Parameter', 'type': 'select_iot_param'},
        ]
    },

    # ── Analysis ────────────────────────────────
    'analysis_trend': {
        'label': 'Trend Analysis (Line Chart)',
        'icon': 'bi-graph-up-arrow',
        'category': 'analysis',
        'widget_type': 'line_chart',
        'description': 'Trend WO count atau meter value per bulan dalam line chart',
        'config_fields': [
            {'name': 'trend_type', 'label': 'Data yang di-trend', 'type': 'select', 'options': ['WO Count per Bulan', 'Helpdesk per Bulan', 'Meter Reading']},
            {'name': 'maint_type', 'label': 'Tipe WO (jika WO)', 'type': 'select', 'options': ['All', 'Preventive', 'Corrective']},
            {'name': 'asset_id', 'label': 'Asset (jika Meter)', 'type': 'select_asset'},
            {'name': 'meter_id', 'label': 'Meter (jika Meter)', 'type': 'select_meter'},
            {'name': 'period', 'label': 'Periode', 'type': 'select', 'options': ['6 Bulan', '12 Bulan']},
        ]
    },
    'analysis_distribution': {
        'label': 'Distribusi Status (Pie Chart)',
        'icon': 'bi-pie-chart',
        'category': 'analysis',
        'widget_type': 'pie_chart',
        'description': 'Pie/Donut chart distribusi WO status, asset status, atau helpdesk status',
        'config_fields': [
            {'name': 'dist_type', 'label': 'Distribusi', 'type': 'select', 'options': ['WO by Status', 'WO by Type', 'Asset by Status', 'Helpdesk by Status']},
            {'name': 'site_id', 'label': 'Site (opsional)', 'type': 'select_site'},
        ]
    },
    'analysis_top_n': {
        'label': 'Top N Ranking (Bar Chart)',
        'icon': 'bi-bar-chart',
        'category': 'analysis',
        'widget_type': 'bar_chart',
        'description': 'Ranking: top asset by downtime, top part by usage, top technician by WO',
        'config_fields': [
            {'name': 'ranking_type', 'label': 'Ranking', 'type': 'select', 'options': ['Top Downtime Asset', 'Top Part Usage', 'Top Technician WO']},
            {'name': 'top_n', 'label': 'Jumlah (N)', 'type': 'select', 'options': ['5', '10']},
        ]
    },

    # ── Advanced ────────────────────────────────
    'custom_sql': {
        'label': 'Custom SQL Query',
        'icon': 'bi-database-gear',
        'category': 'advanced',
        'widget_type': 'table_card',
        'description': 'Tulis query SQL SELECT sendiri untuk mengambil data apapun (Admin only)',
        'config_fields': [
            {'name': 'sql_query', 'label': 'SQL Query (SELECT only)', 'type': 'textarea'},
            {'name': 'display_mode', 'label': 'Tampilan', 'type': 'select', 'options': ['Single Value', 'Table']},
        ]
    },
}

DATA_SOURCE_CATEGORIES = {
    'asset': {'label': 'Data Asset', 'icon': 'bi-box-seam', 'color': '#6366f1'},
    'operational': {'label': 'Data Operasional', 'icon': 'bi-clipboard-data', 'color': '#10b981'},
    'iot': {'label': 'IoT / Sensor', 'icon': 'bi-broadcast', 'color': '#f59e0b'},
    'analysis': {'label': 'Analisis Data', 'icon': 'bi-graph-up-arrow', 'color': '#ec4899'},
    'advanced': {'label': 'Advanced', 'icon': 'bi-database-gear', 'color': '#64748b'},
}

# IoT Parameter definitions
IOT_PARAMS = [
    {'key': 'evap_lwt', 'label': 'Evap LWT', 'unit': '°C'},
    {'key': 'evap_rwt', 'label': 'Evap RWT', 'unit': '°C'},
    {'key': 'evap_satur_temp', 'label': 'Evap Saturated Temp', 'unit': '°C'},
    {'key': 'cond_lwt', 'label': 'Cond LWT', 'unit': '°C'},
    {'key': 'cond_rwt', 'label': 'Cond RWT', 'unit': '°C'},
    {'key': 'cond_satur_temp', 'label': 'Cond Saturated Temp', 'unit': '°C'},
    {'key': 'fla', 'label': 'FLA (%)', 'unit': '%'},
    {'key': 'Sys1_Evap_Press', 'label': 'Evap Pressure', 'unit': 'psi'},
    {'key': 'Sys1_Cond_Press', 'label': 'Cond Pressure', 'unit': 'psi'},
    {'key': 'Sys1_Disch_Temp', 'label': 'Discharge Temp', 'unit': '°C'},
    {'key': 'Sys1_Oil_Press', 'label': 'Oil Pressure', 'unit': 'psi'},
    {'key': 'Output_Voltage', 'label': 'Output Voltage', 'unit': 'V'},
    {'key': 'Output_Current', 'label': 'Output Current', 'unit': 'A'},
    {'key': 'Output_Power', 'label': 'Output Power', 'unit': 'kW'},
    {'key': 'Sys1_Run_Hour', 'label': 'Run Hours', 'unit': 'hrs'},
    {'key': 'Disch_Superheat', 'label': 'Discharge Superheat', 'unit': '°C'},
    {'key': 'Sys1_Comp_FLA', 'label': 'Compressor FLA', 'unit': '%'},
    {'key': 'safety_fault', 'label': 'Safety Fault Code', 'unit': ''},
    {'key': 'warning_fault', 'label': 'Warning Fault Code', 'unit': ''},
    {'key': 'cycling_fault', 'label': 'Cycling Fault Code', 'unit': ''},
]


def _get_period_days(period_str):
    """Convert period string to days."""
    mapping = {
        '7 Hari': 7, '30 Hari': 30, '90 Hari': 90, '1 Tahun': 365,
        '6 Bulan': 180, '12 Bulan': 365, 'All Time': 99999
    }
    return mapping.get(period_str, 30)


# ============================================
# FETCH WIDGET VALUE
# ============================================
def fetch_widget_value(widget):
    """Fetch live data value for a single widget based on its data_source and config."""
    try:
        config = json.loads(widget.data_config) if widget.data_config else {}
    except:
        config = {}

    source = widget.data_source

    try:
        # ── meter_latest ──
        if source == 'meter_latest':
            meter_id = config.get('meter_id')
            if meter_id:
                reading = AssetMeterReading.query.filter_by(meter_id=meter_id)\
                    .order_by(AssetMeterReading.reading_date.desc()).first()
                if reading:
                    meter = db.session.get(AssetMeter, meter_id)
                    unit = meter.unit if meter else ''
                    return {'value': reading.reading_value, 'unit': unit,
                            'updated': reading.reading_date.strftime('%d %b %Y %H:%M'),
                            'type': 'value_card'}
            return {'value': '-', 'unit': '', 'updated': 'No data', 'type': 'value_card'}

        # ── meter_history ──
        elif source == 'meter_history':
            meter_id = config.get('meter_id')
            period = config.get('period', '30 Hari')
            days = _get_period_days(period)
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

            if meter_id:
                readings = AssetMeterReading.query.filter(
                    AssetMeterReading.meter_id == int(meter_id),
                    AssetMeterReading.reading_date >= cutoff
                ).order_by(AssetMeterReading.reading_date.asc()).all()

                meter = db.session.get(AssetMeter, int(meter_id))
                unit = meter.unit if meter else ''

                if readings:
                    values = [r.reading_value for r in readings]
                    labels = [r.reading_date.strftime('%d/%m') for r in readings]
                    return {
                        'type': 'line_chart',
                        'labels': labels,
                        'values': values,
                        'unit': unit,
                        'stats': {
                            'min': round(min(values), 2),
                            'max': round(max(values), 2),
                            'avg': round(sum(values) / len(values), 2),
                            'count': len(values)
                        }
                    }
            return {'type': 'line_chart', 'labels': [], 'values': [], 'unit': '', 'stats': {'min': '-', 'max': '-', 'avg': '-', 'count': 0}}

        # ── asset_count ──
        elif source == 'asset_count':
            query = Asset.query
            status = config.get('status', 'All')
            site_id = config.get('site_id')
            if site_id and str(site_id) != '0':
                query = query.filter(Asset.site_id == int(site_id))
            if status != 'All':
                query = query.filter(Asset.status == status)
            return {'value': query.count(), 'unit': 'Assets', 'type': 'value_card'}

        # ── asset_detail ──
        elif source == 'asset_detail':
            asset_id = config.get('asset_id')
            if asset_id:
                asset = db.session.get(Asset, int(asset_id))
                if asset:
                    site_name = asset.site.name if asset.site else '-'
                    loc_name = asset.location.name if asset.location else '-'
                    cat_name = asset.category.name if asset.category else '-'
                    return {
                        'type': 'info_card',
                        'fields': [
                            {'label': 'Status', 'value': asset.status or '-'},
                            {'label': 'Site', 'value': site_name},
                            {'label': 'Location', 'value': loc_name},
                            {'label': 'Category', 'value': cat_name},
                            {'label': 'Criticality', 'value': asset.criticality or '-'},
                            {'label': 'Make', 'value': asset.make or '-'},
                            {'label': 'Model', 'value': asset.model or '-'},
                            {'label': 'Serial No.', 'value': asset.serial_number or '-'},
                            {'label': 'Code', 'value': asset.code or '-'},
                        ]
                    }
            return {'type': 'info_card', 'fields': [{'label': 'Error', 'value': 'Asset not found'}]}

        # ── asset_custom_field ──
        elif source == 'asset_custom_field':
            asset_id = config.get('asset_id')
            field_name = config.get('field_name')
            if asset_id and field_name:
                cf = AssetCustomField.query.filter_by(
                    asset_id=int(asset_id), field_name=field_name
                ).first()
                if cf:
                    return {'value': cf.field_value or '-', 'unit': '', 'type': 'value_card',
                            'updated': cf.expiry_date.strftime('%d %b %Y') if cf.expiry_date else ''}
            return {'value': '-', 'unit': '', 'type': 'value_card'}

        # ── asset_uptime ──
        elif source == 'asset_uptime':
            asset_id = config.get('asset_id')
            period = config.get('period', '30 Hari')
            days = _get_period_days(period)

            if asset_id:
                cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days) if days < 99999 else datetime(2000, 1, 1)
                wos = WorkOrder.query.filter(
                    WorkOrder.asset_id == int(asset_id),
                    WorkOrder.maintenance_type == 'Corrective',
                    WorkOrder.date_created >= cutoff
                ).all()
                total_hours = 0
                for wo in wos:
                    if wo.start_date and wo.end_date and wo.end_date > wo.start_date:
                        total_hours += (wo.end_date - wo.start_date).total_seconds() / 3600
                return {'value': round(total_hours, 1), 'unit': 'Jam', 'type': 'value_card'}
            return {'value': '-', 'unit': '', 'type': 'value_card'}

        # ── wo_count ──
        elif source == 'wo_count':
            from sqlalchemy.orm import selectinload
            query = WorkOrder.query.options(selectinload(WorkOrder.current_status))
            status_type = config.get('status_type', 'All')
            maint_type = config.get('maint_type', 'All')
            site_id = config.get('site_id')

            if site_id and str(site_id) != '0':
                query = query.join(Asset).filter(Asset.site_id == int(site_id))
            if maint_type != 'All':
                query = query.filter(WorkOrder.maintenance_type == maint_type)
            if status_type != 'All':
                all_wos = query.all()
                count = sum(1 for wo in all_wos if wo.current_status and wo.current_status.control_type == status_type)
                return {'value': count, 'unit': 'WO', 'type': 'value_card'}
            return {'value': query.count(), 'unit': 'WO', 'type': 'value_card'}

        # ── wo_cost ──
        elif source == 'wo_cost':
            status_type = config.get('status_type', 'All')
            site_id = config.get('site_id')
            query = db.session.query(
                func.sum(WorkOrderPart.quantity_used * Part.unit_cost)
            ).join(Part, WorkOrderPart.part_id == Part.id)\
             .join(WorkOrder, WorkOrderPart.work_order_id == WorkOrder.id)

            if site_id and str(site_id) != '0':
                query = query.join(Asset, WorkOrder.asset_id == Asset.id).filter(Asset.site_id == int(site_id))

            total = query.scalar() or 0
            return {'value': f'{total:,.0f}', 'unit': 'IDR', 'type': 'value_card'}

        # ── helpdesk_count ──
        elif source == 'helpdesk_count':
            query = HelpdeskTicket.query
            status = config.get('status', 'All')
            if status != 'All':
                query = query.filter(HelpdeskTicket.status == status)
            return {'value': query.count(), 'unit': 'Tickets', 'type': 'value_card'}

        # ── stock_level ──
        elif source == 'stock_level':
            part_id = config.get('part_id')
            site_id = config.get('site_id')
            if part_id:
                query = StockLevel.query.filter_by(part_id=int(part_id))
                if site_id and str(site_id) != '0':
                    query = query.filter_by(site_id=int(site_id))
                stock = query.first()
                if stock:
                    return {'value': stock.qty_on_hand, 'unit': 'pcs', 'min_qty': stock.min_qty, 'type': 'value_card'}
            return {'value': '-', 'unit': '', 'type': 'value_card'}

        # ── kpi_value ──
        elif source == 'kpi_value':
            kpi_type = config.get('kpi_type', 'MTBF (Hours)')
            site_id = config.get('site_id')
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            if site_id and str(site_id) != '0':
                all_wos = WorkOrder.query.join(Asset).filter(Asset.site_id == int(site_id)).all()
                online_count = Asset.query.filter_by(status='Online', site_id=int(site_id)).count()
                total_assets = Asset.query.filter_by(site_id=int(site_id)).count()
            else:
                all_wos = WorkOrder.query.all()
                online_count = Asset.query.filter_by(status='Online').count()
                total_assets = Asset.query.count()

            completed_wos = [w for w in all_wos if w.current_status and w.current_status.control_type == 'Closed']

            if 'MTTR' in kpi_type:
                total_repair = sum(
                    (wo.end_date - wo.start_date).total_seconds() / 3600
                    for wo in completed_wos
                    if wo.start_date and wo.end_date and wo.end_date > wo.start_date
                )
                val = round(total_repair / len(completed_wos), 1) if completed_wos else 0
                return {'value': val, 'unit': 'Hours', 'type': 'value_card'}
            elif 'MTBF' in kpi_type:
                corrective = [w for w in all_wos if w.maintenance_type == 'Corrective']
                uptime = online_count * 30 * 24
                val = round(uptime / len(corrective), 1) if corrective else 0
                return {'value': val, 'unit': 'Hours', 'type': 'value_card'}
            elif 'PM Compliance' in kpi_type:
                pm_wos = [w for w in all_wos if w.maintenance_type == 'Preventive' and w.suggested_completion_date]
                compliant = 0
                for wo in pm_wos:
                    if wo.current_status and wo.current_status.control_type == 'Closed':
                        if wo.end_date and wo.end_date <= wo.suggested_completion_date:
                            compliant += 1
                    else:
                        if now <= wo.suggested_completion_date:
                            compliant += 1
                val = round((compliant / len(pm_wos)) * 100, 1) if pm_wos else 100
                return {'value': val, 'unit': '%', 'type': 'value_card'}
            elif 'Availability' in kpi_type:
                val = round((online_count / total_assets) * 100, 1) if total_assets > 0 else 0
                return {'value': val, 'unit': '%', 'type': 'value_card'}

        # ── po_count ──
        elif source == 'po_count':
            query = PurchaseOrder.query
            status = config.get('status', 'All')
            site_id = config.get('site_id')
            if site_id and str(site_id) != '0':
                query = query.filter(PurchaseOrder.site_id == int(site_id))
            if status != 'All':
                query = query.filter(PurchaseOrder.status == status)
            return {'value': query.count(), 'unit': 'PO', 'type': 'value_card'}

        # ── po_total_cost ──
        elif source == 'po_total_cost':
            query = db.session.query(func.sum(PurchaseOrder.total_cost))
            status = config.get('status', 'All')
            site_id = config.get('site_id')
            if site_id and str(site_id) != '0':
                query = query.filter(PurchaseOrder.site_id == int(site_id))
            if status != 'All':
                query = query.filter(PurchaseOrder.status == status)
            total = query.scalar() or 0
            return {'value': f'{total:,.0f}', 'unit': 'IDR', 'type': 'value_card'}

        # ── vendor_count ──
        elif source == 'vendor_count':
            return {'value': Vendor.query.count(), 'unit': 'Vendors', 'type': 'value_card'}

        # ── iot_chiller_param ──
        elif source == 'iot_chiller_param':
            chiller_id = config.get('iot_chiller_id')
            param_key = config.get('iot_param')
            if chiller_id and param_key:
                conn = get_iot_db_connection()
                if conn:
                    try:
                        cursor = conn.cursor(dictionary=True)
                        # Get chiller name
                        cursor.execute("SELECT chiller_num FROM chillers WHERE id = %s", (chiller_id,))
                        chiller_info = cursor.fetchone()
                        chiller_name = chiller_info['chiller_num'] if chiller_info else chiller_id

                        # Get latest data
                        cursor.execute(f"""
                            SELECT `{param_key}`, timestamp
                            FROM chiller_datas
                            WHERE chiller_id = %s
                            ORDER BY timestamp DESC
                            LIMIT 1
                        """, (chiller_id,))
                        row = cursor.fetchone()
                        if row and row.get(param_key) is not None:
                            # Find unit from IOT_PARAMS
                            unit = ''
                            for p in IOT_PARAMS:
                                if p['key'] == param_key:
                                    unit = p['unit']
                                    break
                            ts = row.get('timestamp')
                            updated = ts.strftime('%d %b %Y %H:%M') if ts else '-'
                            val = row[param_key]
                            if isinstance(val, float):
                                val = round(val, 2)
                            return {'value': val, 'unit': unit, 'updated': updated,
                                    'subtitle': f'Chiller: {chiller_name}', 'type': 'value_card'}
                    except Exception as e:
                        print(f"[IoT Widget] Error: {e}")
                    finally:
                        conn.close()
            return {'value': '-', 'unit': '', 'updated': 'DB Error / Not Connected', 'type': 'value_card'}

        # ── analysis_trend ──
        elif source == 'analysis_trend':
            trend_type = config.get('trend_type', 'WO Count per Bulan')
            period = config.get('period', '12 Bulan')
            months = 6 if '6' in period else 12
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            labels = []
            values = []

            if 'WO' in trend_type:
                maint_type = config.get('maint_type', 'All')
                for i in range(months - 1, -1, -1):
                    dt = now - timedelta(days=i * 30)
                    start = dt.replace(day=1, hour=0, minute=0, second=0)
                    if i > 0:
                        end = (now - timedelta(days=(i - 1) * 30)).replace(day=1, hour=0, minute=0, second=0)
                    else:
                        end = now
                    q = WorkOrder.query.filter(WorkOrder.date_created >= start, WorkOrder.date_created < end)
                    if maint_type != 'All':
                        q = q.filter(WorkOrder.maintenance_type == maint_type)
                    labels.append(start.strftime('%b %Y'))
                    values.append(q.count())

            elif 'Helpdesk' in trend_type:
                for i in range(months - 1, -1, -1):
                    dt = now - timedelta(days=i * 30)
                    start = dt.replace(day=1, hour=0, minute=0, second=0)
                    if i > 0:
                        end = (now - timedelta(days=(i - 1) * 30)).replace(day=1, hour=0, minute=0, second=0)
                    else:
                        end = now
                    q = HelpdeskTicket.query.filter(HelpdeskTicket.created_at >= start, HelpdeskTicket.created_at < end)
                    labels.append(start.strftime('%b %Y'))
                    values.append(q.count())

            elif 'Meter' in trend_type:
                meter_id = config.get('meter_id')
                if meter_id:
                    cutoff = now - timedelta(days=months * 30)
                    readings = AssetMeterReading.query.filter(
                        AssetMeterReading.meter_id == int(meter_id),
                        AssetMeterReading.reading_date >= cutoff
                    ).order_by(AssetMeterReading.reading_date.asc()).all()
                    labels = [r.reading_date.strftime('%d/%m') for r in readings]
                    values = [r.reading_value for r in readings]

            return {'type': 'line_chart', 'labels': labels, 'values': values, 'unit': ''}

        # ── analysis_distribution ──
        elif source == 'analysis_distribution':
            dist_type = config.get('dist_type', 'WO by Status')
            site_id = config.get('site_id')
            labels = []
            values = []
            colors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#64748b', '#ef4444', '#8b5cf6', '#06b6d4']

            if dist_type == 'WO by Status':
                statuses = WorkOrderStatus.query.all()
                for st in statuses:
                    q = WorkOrder.query.filter_by(status_id=st.id)
                    if site_id and str(site_id) != '0':
                        q = q.join(Asset).filter(Asset.site_id == int(site_id))
                    c = q.count()
                    if c > 0:
                        labels.append(st.name)
                        values.append(c)

            elif dist_type == 'WO by Type':
                for mt in ['Preventive', 'Corrective', 'Predictive', 'Inspection']:
                    q = WorkOrder.query.filter_by(maintenance_type=mt)
                    if site_id and str(site_id) != '0':
                        q = q.join(Asset).filter(Asset.site_id == int(site_id))
                    c = q.count()
                    if c > 0:
                        labels.append(mt)
                        values.append(c)

            elif dist_type == 'Asset by Status':
                for st in ['Online', 'Offline', 'Under Repair', 'Decommissioned']:
                    q = Asset.query.filter_by(status=st)
                    if site_id and str(site_id) != '0':
                        q = q.filter(Asset.site_id == int(site_id))
                    c = q.count()
                    if c > 0:
                        labels.append(st)
                        values.append(c)

            elif dist_type == 'Helpdesk by Status':
                for st in ['New', 'Action Plan', 'WIP', 'Done', 'Closed']:
                    c = HelpdeskTicket.query.filter_by(status=st).count()
                    if c > 0:
                        labels.append(st)
                        values.append(c)

            return {'type': 'pie_chart', 'labels': labels, 'values': values, 'colors': colors[:len(labels)]}

        # ── analysis_top_n ──
        elif source == 'analysis_top_n':
            ranking_type = config.get('ranking_type', 'Top Downtime Asset')
            top_n = int(config.get('top_n', '5'))
            labels = []
            values = []

            if ranking_type == 'Top Downtime Asset':
                all_wos = WorkOrder.query.all()
                completed = [w for w in all_wos if w.current_status and w.current_status.control_type == 'Closed']
                asset_downtime = {}
                for wo in completed:
                    if wo.asset_id and wo.start_date and wo.end_date and wo.end_date > wo.start_date:
                        hrs = (wo.end_date - wo.start_date).total_seconds() / 3600
                        asset_downtime[wo.asset_id] = asset_downtime.get(wo.asset_id, 0) + hrs
                sorted_ids = sorted(asset_downtime, key=asset_downtime.get, reverse=True)[:top_n]
                for aid in sorted_ids:
                    ast = db.session.get(Asset, aid)
                    if ast:
                        labels.append(ast.name[:25])
                        values.append(round(asset_downtime[aid], 1))

            elif ranking_type == 'Top Part Usage':
                results = db.session.query(
                    Part.name, func.sum(WorkOrderPart.quantity_used).label('total')
                ).join(Part, WorkOrderPart.part_id == Part.id)\
                 .group_by(Part.name)\
                 .order_by(func.sum(WorkOrderPart.quantity_used).desc())\
                 .limit(top_n).all()
                for r in results:
                    labels.append(r[0][:25])
                    values.append(float(r[1] or 0))

            elif ranking_type == 'Top Technician WO':
                from models import User
                results = db.session.query(
                    User.name, func.count(WorkOrder.id).label('total')
                ).join(WorkOrder, WorkOrder.assigned_to == User.id)\
                 .group_by(User.name)\
                 .order_by(func.count(WorkOrder.id).desc())\
                 .limit(top_n).all()
                for r in results:
                    labels.append(r[0][:25])
                    values.append(int(r[1] or 0))

            return {'type': 'bar_chart', 'labels': labels, 'values': values}

        # ── custom_sql ──
        elif source == 'custom_sql':
            sql_query = config.get('sql_query', '')
            display_mode = config.get('display_mode', 'Single Value')

            if not sql_query or not sql_query.strip().upper().startswith('SELECT'):
                return {'type': 'table_card', 'error': 'Query harus dimulai dengan SELECT', 'rows': [], 'columns': []}

            # Block dangerous keywords
            upper_q = sql_query.upper()
            blocked = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', '--', ';']
            for b in blocked:
                if b in upper_q:
                    return {'type': 'table_card', 'error': f'Keyword "{b}" tidak diizinkan', 'rows': [], 'columns': []}

            try:
                result = db.session.execute(db.text(sql_query))
                columns = list(result.keys()) if result.returns_rows else []
                rows = [list(r) for r in result.fetchall()] if result.returns_rows else []

                if display_mode == 'Single Value' and rows:
                    val = rows[0][0] if rows[0] else '-'
                    if isinstance(val, float):
                        val = round(val, 2)
                    return {'type': 'value_card', 'value': val, 'unit': ''}

                # Limit rows to 20
                return {'type': 'table_card', 'columns': columns, 'rows': rows[:20]}
            except Exception as e:
                return {'type': 'table_card', 'error': str(e)[:200], 'rows': [], 'columns': []}

    except Exception as e:
        traceback.print_exc()
        return {'value': 'Error', 'unit': '', 'type': 'value_card', 'error': str(e)[:100]}

    return {'value': '-', 'unit': '', 'type': 'value_card'}


# ============================================
# VIEWS
# ============================================

@custom_dashboards_bp.route('/<int:id>')
@login_required
def view(id):
    dashboard = CustomDashboard.query.get_or_404(id)
    if dashboard.user_id != current_user.id:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('dashboard'))

    widgets = dashboard.widgets.order_by(CustomDashboardWidget.position).all()

    # Fetch live values for all widgets
    widget_data = []
    for w in widgets:
        result = fetch_widget_value(w)
        widget_data.append({
            'widget': w,
            'data': result
        })

    # Get assets, meters, parts, sites for the "Add Widget" form (as plain dicts for tojson)
    assets = [{'id': a.id, 'name': a.name, 'code': a.code or '', 'site_name': (a.site.name if a.site else '')} for a in Asset.query.order_by(Asset.name).all()]
    sites = [{'id': s.id, 'name': s.name} for s in Site.query.order_by(Site.name).all()]
    parts = [{'id': p.id, 'name': p.name} for p in Part.query.order_by(Part.name).all()]

    return render_template('custom_dashboard/view.html',
                           dashboard=dashboard,
                           widget_data=widget_data,
                           data_sources=DATA_SOURCES,
                           data_source_categories=DATA_SOURCE_CATEGORIES,
                           iot_params=IOT_PARAMS,
                           assets=assets,
                           sites=sites,
                           parts=parts,
                           is_admin=(current_user.role == 'Admin'))


# ============================================
# API ENDPOINTS
# ============================================

@custom_dashboards_bp.route('/api/create', methods=['POST'])
@login_required
def create_dashboard():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Nama dashboard harus diisi'}), 400

    max_pos = db.session.query(db.func.max(CustomDashboard.position)).filter_by(user_id=current_user.id).scalar() or 0

    dash = CustomDashboard(
        user_id=current_user.id,
        name=data['name'],
        icon=data.get('icon', 'bi-speedometer2'),
        position=max_pos + 1
    )
    db.session.add(dash)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'id': dash.id,
        'name': dash.name,
        'url': url_for('custom_dashboards.view', id=dash.id)
    })


@custom_dashboards_bp.route('/api/<int:id>/delete', methods=['POST'])
@login_required
def delete_dashboard(id):
    dash = CustomDashboard.query.filter_by(id=id, user_id=current_user.id).first()
    if not dash:
        return jsonify({'error': 'Dashboard not found'}), 404
    db.session.delete(dash)
    db.session.commit()
    return jsonify({'status': 'ok'})


@custom_dashboards_bp.route('/api/<int:id>/rename', methods=['POST'])
@login_required
def rename_dashboard(id):
    data = request.get_json()
    dash = CustomDashboard.query.filter_by(id=id, user_id=current_user.id).first()
    if not dash:
        return jsonify({'error': 'Dashboard not found'}), 404
    dash.name = data.get('name', dash.name)
    dash.icon = data.get('icon', dash.icon)
    db.session.commit()
    return jsonify({'status': 'ok'})


@custom_dashboards_bp.route('/api/<int:dashboard_id>/widget/add', methods=['POST'])
@login_required
def add_widget(dashboard_id):
    dash = CustomDashboard.query.filter_by(id=dashboard_id, user_id=current_user.id).first()
    if not dash:
        return jsonify({'error': 'Dashboard not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid data'}), 400

    # Block custom_sql for non-admins
    if data.get('data_source') == 'custom_sql' and current_user.role != 'Admin':
        return jsonify({'error': 'Custom SQL hanya untuk Admin'}), 403

    max_pos = db.session.query(db.func.max(CustomDashboardWidget.position)).filter_by(dashboard_id=dashboard_id).scalar() or 0

    # Auto-detect widget_type from source definition
    source_key = data.get('data_source', '')
    source_def = DATA_SOURCES.get(source_key, {})
    widget_type = data.get('widget_type', source_def.get('widget_type', 'value_card'))

    widget = CustomDashboardWidget(
        dashboard_id=dashboard_id,
        title=data.get('title', 'Untitled'),
        widget_type=widget_type,
        data_source=data['data_source'],
        data_config=json.dumps(data.get('data_config', {})),
        position=max_pos + 1,
        col_span=data.get('col_span', 4),
        color=data.get('color', 'primary')
    )
    db.session.add(widget)
    db.session.commit()

    return jsonify({'status': 'ok', 'id': widget.id, 'message': 'Widget added'})


@custom_dashboards_bp.route('/api/widget/<int:widget_id>/delete', methods=['POST'])
@login_required
def delete_widget(widget_id):
    widget = CustomDashboardWidget.query.get_or_404(widget_id)
    dash = db.session.get(CustomDashboard, widget.dashboard_id)
    if not dash or dash.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    db.session.delete(widget)
    db.session.commit()
    return jsonify({'status': 'ok'})


@custom_dashboards_bp.route('/api/<int:dashboard_id>/layout', methods=['POST'])
@login_required
def save_layout(dashboard_id):
    """Save widget positions and col_span in bulk (for drag-and-drop reorder + resize)."""
    dash = CustomDashboard.query.filter_by(id=dashboard_id, user_id=current_user.id).first()
    if not dash:
        return jsonify({'error': 'Dashboard not found'}), 404

    data = request.get_json()
    layout = data.get('layout', [])  # [{id, position, col_span}, ...]

    for item in layout:
        widget = db.session.get(CustomDashboardWidget, item.get('id'))
        if widget and widget.dashboard_id == dashboard_id:
            widget.position = item.get('position', widget.position)
            if 'col_span' in item:
                widget.col_span = item['col_span']

    db.session.commit()
    return jsonify({'status': 'ok'})


@custom_dashboards_bp.route('/api/widget/<int:widget_id>/update', methods=['POST'])
@login_required
def update_widget(widget_id):
    """Update full widget properties."""
    widget = CustomDashboardWidget.query.get_or_404(widget_id)
    dash = db.session.get(CustomDashboard, widget.dashboard_id)
    if not dash or dash.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()
    if 'title' in data:
        widget.title = data['title']
    if 'color' in data:
        widget.color = data['color']
    if 'col_span' in data:
        widget.col_span = int(data['col_span'])

    if 'data_source' in data:
        widget.data_source = data['data_source']
        widget.widget_type = data.get('widget_type', DATA_SOURCES.get(data['data_source'], {}).get('widget_type', 'value_card'))

    if 'data_config' in data:
        widget.data_config = json.dumps(data['data_config'])
    else:
        # Fallback for old partial updates (if any leftover)
        try:
            config = json.loads(widget.data_config) if widget.data_config else {}
        except:
            config = {}
        if 'widget_height' in data:
            config['widget_height'] = data['widget_height']
        if 'font_size' in data:
            config['font_size'] = data['font_size']
        widget.data_config = json.dumps(config)

    db.session.commit()
    return jsonify({'status': 'ok'})


@custom_dashboards_bp.route('/api/<int:dashboard_id>/data', methods=['GET'])
@login_required
def get_dashboard_data(dashboard_id):
    """Fetch live data for all widgets on a dashboard (for auto-refresh)."""
    dash = CustomDashboard.query.filter_by(id=dashboard_id, user_id=current_user.id).first()
    if not dash:
        return jsonify({'error': 'Not found'}), 404

    widgets = dash.widgets.order_by(CustomDashboardWidget.position).all()
    result = {}
    for w in widgets:
        result[w.id] = fetch_widget_value(w)

    return jsonify({'data': result})


@custom_dashboards_bp.route('/api/list', methods=['GET'])
@login_required
def list_dashboards():
    """Return list of user's custom dashboards for sidebar rendering."""
    dashboards = CustomDashboard.query.filter_by(user_id=current_user.id)\
        .order_by(CustomDashboard.position).all()
    return jsonify({
        'dashboards': [{
            'id': d.id,
            'name': d.name,
            'icon': d.icon,
            'url': url_for('custom_dashboards.view', id=d.id)
        } for d in dashboards]
    })


@custom_dashboards_bp.route('/api/meters/<int:asset_id>', methods=['GET'])
@login_required
def get_asset_meters(asset_id):
    """Return meters for a specific asset."""
    meters = AssetMeter.query.filter_by(asset_id=asset_id).order_by(AssetMeter.name).all()
    return jsonify({
        'meters': [{'id': m.id, 'name': m.name, 'unit': m.unit} for m in meters]
    })


@custom_dashboards_bp.route('/api/custom-fields/<int:asset_id>', methods=['GET'])
@login_required
def get_asset_custom_fields(asset_id):
    """Return custom fields for a specific asset."""
    fields = AssetCustomField.query.filter_by(asset_id=asset_id).all()
    return jsonify({
        'fields': [{'name': f.field_name, 'value': f.field_value} for f in fields]
    })


# ── IoT API Endpoints ──
@custom_dashboards_bp.route('/api/iot/sites', methods=['GET'])
@login_required
def get_iot_sites():
    """Return list of IoT sites from external MySQL."""
    conn = get_iot_db_connection()
    if not conn:
        return jsonify({'sites': [], 'error': 'Cannot connect to IoT DB'})
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM sites ORDER BY name")
        sites = cursor.fetchall()
        return jsonify({'sites': sites})
    except Exception as e:
        return jsonify({'sites': [], 'error': str(e)})
    finally:
        conn.close()


@custom_dashboards_bp.route('/api/iot/chillers/<int:site_id>', methods=['GET'])
@login_required
def get_iot_chillers(site_id):
    """Return chillers for a specific IoT site."""
    conn = get_iot_db_connection()
    if not conn:
        return jsonify({'chillers': []})
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, chiller_num, model_number FROM chillers WHERE site_id = %s ORDER BY chiller_num", (site_id,))
        chillers = cursor.fetchall()
        return jsonify({'chillers': chillers})
    except Exception as e:
        return jsonify({'chillers': [], 'error': str(e)})
    finally:
        conn.close()


# ── SQL Preview Endpoint (Admin only) ──
@custom_dashboards_bp.route('/api/sql/preview', methods=['POST'])
@login_required
def preview_sql():
    """Preview a custom SQL query result (Admin only)."""
    if current_user.role != 'Admin':
        return jsonify({'error': 'Admin only'}), 403

    data = request.get_json()
    sql = data.get('sql', '').strip()

    if not sql.upper().startswith('SELECT'):
        return jsonify({'error': 'Query harus dimulai dengan SELECT'}), 400

    upper_q = sql.upper()
    blocked = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', '--']
    for b in blocked:
        if b in upper_q:
            return jsonify({'error': f'Keyword "{b}" tidak diizinkan'}), 400

    try:
        result = db.session.execute(db.text(sql))
        columns = list(result.keys()) if result.returns_rows else []
        rows = [list(r) for r in result.fetchmany(5)] if result.returns_rows else []

        # Convert non-serializable types
        clean_rows = []
        for row in rows:
            clean_row = []
            for v in row:
                if isinstance(v, datetime):
                    clean_row.append(v.strftime('%Y-%m-%d %H:%M'))
                elif isinstance(v, float):
                    clean_row.append(round(v, 2))
                else:
                    clean_row.append(v)
            clean_rows.append(clean_row)

        return jsonify({'columns': columns, 'rows': clean_rows, 'total': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 400
