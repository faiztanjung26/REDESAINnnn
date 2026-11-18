"""Pembantu tampilan baca-saja untuk dashboard dan daftar Work Order.

Modul ini hanya membaca data dan menghitung ringkasan untuk templat. Tidak ada yang ditulis ke
database. Model, status WO, rumus KPI, hak akses per peran, login dan CSRF tidak disentuh.
Pemanggil membungkus tiap fungsi dengan try/except: bila kueri gagal, halaman tetap tampil tanpa
bagian tambahan itu.
"""
from datetime import datetime, timedelta, timezone

WIB = timedelta(hours=7)
MONTHS_ID = ('Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des')
# urutan tab status; status lain menyusul menurut abjad
STATUS_ORDER = ('Draft', 'Assigned', 'Confirmed', 'Pending', 'Hold', 'In Progress', 'Active',
                'Solved', 'Completed', 'Incompleted', 'Closed', 'Cancelled')


def now_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + WIB


def greeting(now=None):
    hour = (now or now_wib()).hour
    if hour < 11:
        return 'Selamat pagi'
    if hour < 15:
        return 'Selamat siang'
    if hour < 18:
        return 'Selamat sore'
    return 'Selamat malam'


def due_chip(due, today):
    """(teks, rona) untuk tenggat. Rona: bad = terlambat, warn = hari ini atau besok, mute = lainnya."""
    if not due:
        return 'Tanpa tenggat', 'mute'
    days = (due.date() - today).days
    if days < 0:
        return 'Terlambat %d hari' % -days, 'bad'
    if days == 0:
        return 'Hari ini', 'warn'
    if days == 1:
        return 'Besok', 'warn'
    return '%d hari lagi' % days, 'mute'


def month_keys(now=None, months=6):
    """Daftar (tahun, bulan) dari yang tertua sampai bulan ini."""
    now = now or now_wib()
    year, month, keys = now.year, now.month, []
    for _ in range(months):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    return keys


def my_tasks(user, site_id=None, limit=6):
    """WO aktif atau tertunda yang ditugaskan ke pengguna, tenggat terdekat dulu."""
    from sqlalchemy.orm import selectinload
    from models import Asset, WorkOrder, WorkOrderStatus

    today = now_wib().date()
    query = (WorkOrder.query
             .join(WorkOrderStatus, WorkOrder.status_id == WorkOrderStatus.id)
             .filter(WorkOrder.assignees.any(id=user.id),
                     WorkOrderStatus.control_type.in_(('Active', 'Pending'))))
    if site_id:
        query = query.join(Asset, WorkOrder.asset_id == Asset.id).filter(Asset.site_id == site_id)
    total = query.count()
    start_today = datetime(today.year, today.month, today.day)
    overdue = query.filter(WorkOrder.suggested_completion_date < start_today).count()
    rows = (query.options(selectinload(WorkOrder.asset), selectinload(WorkOrder.current_status))
            .order_by(WorkOrder.suggested_completion_date.is_(None),
                      WorkOrder.suggested_completion_date, WorkOrder.id)
            .limit(limit).all())
    items = []
    for wo in rows:
        text, tone = due_chip(wo.suggested_completion_date, today)
        items.append({'wo': wo, 'due_text': text, 'due_tone': tone})
    return {'items': items, 'total': total, 'overdue': overdue}


def wo_trend(site_id=None, technician_id=None, months=6):
    """WO dibuat dan selesai per bulan untuk grafik tren. Selesai = status bernama Completed."""
    from models import Asset, WorkOrder, WorkOrderStatus, db

    keys = month_keys(months=months)
    start = datetime(keys[0][0], keys[0][1], 1)
    query = (db.session.query(WorkOrder.date_created, WorkOrder.end_date, WorkOrderStatus.name)
             .select_from(WorkOrder)
             .outerjoin(WorkOrderStatus, WorkOrder.status_id == WorkOrderStatus.id)
             .filter(db.or_(WorkOrder.date_created >= start, WorkOrder.end_date >= start)))
    if site_id:
        query = query.join(Asset, WorkOrder.asset_id == Asset.id).filter(Asset.site_id == site_id)
    if technician_id:
        query = query.filter(WorkOrder.assignees.any(id=technician_id))
    created = {k: 0 for k in keys}
    completed = {k: 0 for k in keys}
    for date_created, end_date, status_name in query.all():
        if date_created and (date_created.year, date_created.month) in created:
            created[(date_created.year, date_created.month)] += 1
        done_at = end_date or date_created
        if status_name == 'Completed' and done_at and (done_at.year, done_at.month) in completed:
            completed[(done_at.year, done_at.month)] += 1
    return {
        'labels': [MONTHS_ID[m - 1] for _, m in keys],
        'keys': ['%d-%02d' % k for k in keys],
        'created': [created[k] for k in keys],
        'completed': [completed[k] for k in keys],
    }


def status_tabs(query, statuses, args, selected):
    """Hitungan WO per status untuk tab di daftar. `query` = kueri daftar tanpa filter status."""
    from flask import url_for
    from sqlalchemy import func
    from models import WorkOrder, WorkOrderStatus, db

    ids = query.with_entities(WorkOrder.id).statement
    rows = (db.session.query(WorkOrderStatus.name, func.count(WorkOrder.id))
            .select_from(WorkOrder)
            .outerjoin(WorkOrderStatus, WorkOrder.status_id == WorkOrderStatus.id)
            .filter(WorkOrder.id.in_(ids))
            .group_by(WorkOrderStatus.name).all())
    counts = {name: n for name, n in rows if name}
    total = sum(n for _, n in rows)

    base = args.to_dict(flat=True)
    base.pop('status', None)

    def link(status=None):
        params = dict(base)
        if status:
            params['status'] = status
        return url_for('work_orders.index', **params)

    rank = {name: i for i, name in enumerate(STATUS_ORDER)}
    tabs = []
    for st in sorted(statuses, key=lambda s: (rank.get(s.name, 99), s.name)):
        n = counts.get(st.name, 0)
        if n or st.name == selected:
            tabs.append({'name': st.name, 'count': n, 'url': link(st.name),
                         'active': st.name == selected, 'control_type': st.control_type})
    return {
        'all': {'count': total, 'url': link(), 'active': not selected},
        'tabs': tabs,
        'unlisted': bool(selected) and selected not in {s.name for s in statuses},
    }


if __name__ == '__main__':
    # pemeriksaan mandiri untuk fungsi murni (tanpa database): python3 ui_extras.py
    day = datetime(2026, 11, 17).date()
    assert due_chip(datetime(2026, 11, 15), day) == ('Terlambat 2 hari', 'bad')
    assert due_chip(datetime(2026, 11, 17, 23), day) == ('Hari ini', 'warn')
    assert due_chip(datetime(2026, 11, 18), day) == ('Besok', 'warn')
    assert due_chip(datetime(2026, 11, 25), day) == ('8 hari lagi', 'mute')
    assert due_chip(None, day) == ('Tanpa tenggat', 'mute')
    assert month_keys(datetime(2026, 2, 10)) == [(2025, 9), (2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2)]
    assert greeting(datetime(2026, 1, 1, 9)) == 'Selamat pagi' and greeting(datetime(2026, 1, 1, 19)) == 'Selamat malam'
    print('ui_extras: ok')
