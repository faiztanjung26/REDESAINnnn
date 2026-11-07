"""
Widget Catalog Registry for Customizable Dashboard
Each widget defines its key, display label, icon, default column span, and allowed roles.
"""

WIDGET_CATALOG = [
    {
        'key': 'kpi_cards',
        'label': 'KPI Cards (MTBF / MTTR / PM / Availability)',
        'icon': 'bi-activity',
        'default_col': 12,
        'roles': ['Admin', 'Supervisor', 'Technician'],
    },
    {
        'key': 'wo_status_chart',
        'label': 'Work Order Status Chart',
        'icon': 'bi-pie-chart',
        'default_col': 4,
        'roles': ['Admin', 'Supervisor'],
    },
    {
        'key': 'overdue_wos',
        'label': 'Overdue Work Orders',
        'icon': 'bi-exclamation-circle',
        'default_col': 4,
        'roles': ['Admin', 'Supervisor', 'Technician'],
    },
    {
        'key': 'wo_today',
        'label': 'Work Order Today',
        'icon': 'bi-calendar-day',
        'default_col': 4,
        'roles': ['Admin', 'Supervisor', 'Technician'],
    },
    {
        'key': 'calendar',
        'label': 'Maintenance Calendar',
        'icon': 'bi-calendar-event',
        'default_col': 12,
        'roles': ['Admin', 'Supervisor', 'Technician'],
    },
    {
        'key': 'top_downtime',
        'label': 'Top 5 Downtime Assets',
        'icon': 'bi-shield-exclamation',
        'default_col': 8,
        'roles': ['Admin', 'Supervisor'],
    },
    {
        'key': 'upcoming_wos',
        'label': 'Upcoming WOs (7 Days)',
        'icon': 'bi-clock-history',
        'default_col': 4,
        'roles': ['Admin', 'Supervisor', 'Technician'],
    },
    {
        'key': 'expiring_assets',
        'label': 'Expiring Assets',
        'icon': 'bi-hourglass-split',
        'default_col': 4,
        'roles': ['Admin', 'Supervisor', 'Technician'],
    },
    {
        'key': 'low_stock',
        'label': 'Low Stock Alerts',
        'icon': 'bi-exclamation-octagon',
        'default_col': 6,
        'roles': ['Admin', 'Supervisor'],
    },
    {
        'key': 'pending_prs',
        'label': 'Pending Purchase Requests',
        'icon': 'bi-cart',
        'default_col': 6,
        'roles': ['Admin', 'Supervisor'],
    },
    {
        'key': 'cpi_table',
        'label': 'Asset Performance Index (CPI)',
        'icon': 'bi-speedometer',
        'default_col': 12,
        'roles': ['Admin', 'Supervisor'],
    },
]

def get_catalog_for_role(role):
    """Return only widgets available for the given role."""
    return [w for w in WIDGET_CATALOG if role in w['roles']]

def get_default_layout(role):
    """Return the default widget layout for a given role."""
    widgets = get_catalog_for_role(role)
    return [
        {'widget_key': w['key'], 'position': i, 'col_span': w['default_col'], 'is_visible': True}
        for i, w in enumerate(widgets)
    ]

def get_widget_info(key):
    """Get catalog info for a single widget key."""
    for w in WIDGET_CATALOG:
        if w['key'] == key:
            return w
    return None
