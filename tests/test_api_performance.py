import pytest
from datetime import date, time, datetime
from models import db, User, Site, Shift, UserShift, WorkOrderStatus

def test_api_performance_success(app, client):
    with app.app_context():
        site = Site(name="Site Jakarta Performance")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="adm_perf", name="Admin Perf", role="Admin", site_id=site.id, is_approved=True)
        admin.set_password("pass")
        db.session.add(admin)

        tech = User(nrp="tech_perf", name="Tech Perf", role="Technician", site_id=site.id, is_approved=True)
        tech.set_password("pass")
        db.session.add(tech)

        shift = Shift(site_id=site.id, name="Pagi", start_time=time(8, 0), end_time=time(17, 0), is_off_day=False)
        db.session.add(shift)
        db.session.commit()

        user_shift = UserShift(user_id=tech.id, shift_id=shift.id, date=date(2026, 11, 2))
        db.session.add(user_shift)
        db.session.commit()

        admin_id = admin.id
        site_id = site.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    res = client.get(f'/api/performance/{site_id}?year=2026&month=11')
    print("Status code:", res.status_code)
    print("Data:", res.get_json())
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]['name'] == 'Tech Perf'
    assert 'attendance_rate' in data[0]
