from datetime import date, time, datetime
from models import db, User, Site, Shift, UserShift, EmployeeOvertime, AttendanceRecord, EmployeeLeave

def create_admin_and_site(app):
    with app.app_context():
        site = Site(name="Site Test")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin01", name="Admin Test", role="Admin", site_id=site.id, is_approved=True)
        admin.set_password("pass123")
        db.session.add(admin)

        tech1 = User(nrp="tech01", name="Teknisi 1", role="Technician", site_id=site.id, is_approved=True)
        tech1.set_password("pass123")
        db.session.add(tech1)

        tech2 = User(nrp="tech02", name="Teknisi 2", role="Technician", site_id=site.id, is_approved=True)
        tech2.set_password("pass123")
        db.session.add(tech2)

        shift_pagi = Shift(site_id=site.id, name="Pagi", start_time=time(7, 0), end_time=time(15, 0), is_off_day=False)
        shift_libur = Shift(site_id=site.id, name="Libur", start_time=time(0, 0), end_time=time(0, 0), is_off_day=True)
        db.session.add_all([shift_pagi, shift_libur])
        db.session.commit()

        return site.id, admin.id, tech1.id, tech2.id, shift_pagi.id, shift_libur.id

def test_employee_overtime_model(app):
    site_id, admin_id, tech1_id, _, _, _ = create_admin_and_site(app)
    with app.app_context():
        # Test normal overtime duration
        ot1 = EmployeeOvertime(
            site_id=site_id,
            user_id=tech1_id,
            start_date=date(2026, 9, 10),
            start_time=time(17, 0),
            end_date=date(2026, 9, 10),
            end_time=time(21, 0),
            reason="Lembur genset"
        )
        assert ot1.duration_hours == 4.0

        # Test overnight overtime duration (22:00 to 06:00 next day = 8.0 hours)
        ot2 = EmployeeOvertime(
            site_id=site_id,
            user_id=tech1_id,
            start_date=date(2026, 9, 10),
            start_time=time(22, 0),
            end_date=date(2026, 9, 11),
            end_time=time(6, 0),
            reason="Lembur malam"
        )
        assert ot2.duration_hours == 8.0

def test_overtime_crud_api(app, client):
    site_id, admin_id, tech1_id, tech2_id, _, _ = create_admin_and_site(app)

    # Login as admin
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # 1. Post new overtime
    res = client.post(f'/api/overtime/{site_id}', json={
        'user_id': tech1_id,
        'start_date': '2026-09-12',
        'start_time': '17:00',
        'end_date': '2026-09-12',
        'end_time': '21:00',
        'reason': 'Perbaikan Chiller'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    ot_id = data['id']

    # 2. Validation: End time <= Start time
    res_bad = client.post(f'/api/overtime/{site_id}', json={
        'user_id': tech1_id,
        'start_date': '2026-09-12',
        'start_time': '21:00',
        'end_date': '2026-09-12',
        'end_time': '17:00'
    })
    assert res_bad.status_code == 400
    assert 'lebih besar' in res_bad.get_json()['error']

    # 3. Get overtime list
    res_get = client.get(f'/api/overtime/{site_id}')
    assert res_get.status_code == 200
    ot_list = res_get.get_json()
    assert len(ot_list) == 1
    assert ot_list[0]['id'] == ot_id
    assert ot_list[0]['user_id'] == tech1_id
    assert ot_list[0]['duration_hours'] == 4.0
    assert ot_list[0]['reason'] == 'Perbaikan Chiller'

    # 4. Delete overtime
    res_del = client.delete(f'/api/overtime/{site_id}/{ot_id}')
    assert res_del.status_code == 200
    assert res_del.get_json()['success'] is True

    res_get2 = client.get(f'/api/overtime/{site_id}')
    assert len(res_get2.get_json()) == 0

def test_calendar_label_lembur_strictly_conditioned(app, client):
    site_id, admin_id, tech1_id, tech2_id, shift_pagi_id, shift_libur_id = create_admin_and_site(app)

    with app.app_context():
        # Technician 1 has regular Shift Pagi on 2026-09-15 AND an Overtime record
        us1 = UserShift(user_id=tech1_id, shift_id=shift_pagi_id, date=date(2026, 9, 15))
        ot1 = EmployeeOvertime(
            site_id=site_id,
            user_id=tech1_id,
            start_date=date(2026, 9, 15),
            start_time=time(17, 0),
            end_date=date(2026, 9, 15),
            end_time=time(21, 0),
            reason="Lembur Resmi"
        )
        db.session.add_all([us1, ot1])

        # Technician 2 has Shift Libur on 2026-09-15, clocked in, BUT NO Overtime record
        us2 = UserShift(user_id=tech2_id, shift_id=shift_libur_id, date=date(2026, 9, 15))
        db.session.add(us2)
        db.session.commit()

        # Add attendance tap for tech 2 on off-day
        att2 = AttendanceRecord(
            nrp="tech02",
            nama="Teknisi 2",
            date=date(2026, 9, 15),
            jam_masuk=datetime(2026, 9, 15, 8, 0),
            user_id=tech2_id,
            user_shift_id=us2.id
        )
        db.session.add(att2)
        db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # 1. Check Plan Mode
    res_plan = client.get(f'/api/shift_assignments/{site_id}?mode=plan')
    assert res_plan.status_code == 200
    events_plan = res_plan.get_json()

    ev1_plan = next(e for e in events_plan if e['extendedProps']['user_id'] == tech1_id)
    ev2_plan = next(e for e in events_plan if e['extendedProps']['user_id'] == tech2_id)

    # Technician 1 MUST have [Lembur] because overtime record exists
    assert '[Lembur]' in ev1_plan['title']
    assert ev1_plan['extendedProps']['is_overtime'] is True

    # Technician 2 MUST NOT have [Lembur] because NO overtime record was created
    assert '[Lembur]' not in ev2_plan['title']
    assert ev2_plan['extendedProps']['is_overtime'] is False

    # 2. Check Realisasi Mode
    res_real = client.get(f'/api/shift_assignments/{site_id}?mode=realisasi')
    assert res_real.status_code == 200
    events_real = res_real.get_json()

    ev1_real = next(e for e in events_real if e['extendedProps']['user_id'] == tech1_id)
    ev2_real = next(e for e in events_real if e['extendedProps']['user_id'] == tech2_id)

    # In Realisasi: tech 1 still has [Lembur]
    assert '[Lembur]' in ev1_real['title']
    assert ev1_real['extendedProps']['is_overtime'] is True

    # In Realisasi: tech 2 with clock-in on off-day but without overtime form MUST NOT have [Lembur]
    # Instead, the status MUST be 'Hadir dalam Waktu Libur'
    assert '[Lembur]' not in ev2_real['title']
    assert '[Hadir dalam Waktu Libur]' in ev2_real['title']
    assert ev2_real['extendedProps']['is_overtime'] is False
    assert ev2_real['extendedProps']['status'] == 'Hadir dalam Waktu Libur'
    assert ev1_real['extendedProps']['status'] == 'Belum Hadir'
    
    # In Plan: props.status for tech 2 is also 'Hadir dalam Waktu Libur'
    assert ev2_plan['extendedProps']['status'] == 'Hadir dalam Waktu Libur'
    assert ev2_plan['extendedProps']['is_overtime'] is False


def test_cuti_and_lembur_calendar_modes(app, client):
    site_id, admin_id, tech1_id, tech2_id, shift_pagi_id, _ = create_admin_and_site(app)

    with app.app_context():
        # 1. Tech 1 is on Approved Cuti with Tech 2 assigned as replacement
        leave = EmployeeLeave(
            site_id=site_id,
            user_id=tech1_id,
            leave_type="Cuti Tahunan",
            start_date=date(2026, 9, 20),
            end_date=date(2026, 9, 21),
            reason="Keperluan Keluarga",
            original_shift_id=shift_pagi_id,
            replacement_user_id=tech2_id,
            replacement_status="assigned",
            status="Approved"
        )
        
        # 2. Tech 2 has an Approved Overtime
        ot = EmployeeOvertime(
            site_id=site_id,
            user_id=tech2_id,
            start_date=date(2026, 9, 22),
            start_time=time(18, 0),
            end_date=date(2026, 9, 22),
            end_time=time(22, 0),
            reason="Standby Maintenance",
            status="Approved"
        )
        db.session.add_all([leave, ot])
        db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # Test mode=cuti
    res_cuti = client.get(f'/api/shift_assignments/{site_id}?mode=cuti')
    assert res_cuti.status_code == 200
    cuti_events = res_cuti.get_json()
    # 2 days of leave, each day has 1 off-day cuti event and 1 replacement event = 4 events
    assert len(cuti_events) == 4
    cuti_evs = [e for e in cuti_events if e['extendedProps']['is_cuti'] is True]
    rep_evs = [e for e in cuti_events if e['extendedProps']['is_replacement'] is True]
    assert len(cuti_evs) == 2
    assert len(rep_evs) == 2
    assert 'Teknisi 1 - Cuti Tahunan' in cuti_evs[0]['title']
    assert cuti_evs[0]['extendedProps']['is_off_day'] is True
    assert 'Teknisi 2 - Masuk Ganti Teknisi 1' in rep_evs[0]['title']
    assert rep_evs[0]['extendedProps']['is_off_day'] is False

    # Test mode=lembur
    res_lembur = client.get(f'/api/shift_assignments/{site_id}?mode=lembur')
    assert res_lembur.status_code == 200
    lembur_events = res_lembur.get_json()
    assert len(lembur_events) == 1
    assert 'Teknisi 2 - Lembur (18:00 - 22:00) [4.0 Jam]' in lembur_events[0]['title']
    assert lembur_events[0]['extendedProps']['is_overtime'] is True
    assert lembur_events[0]['extendedProps']['overtime_reason'] == 'Standby Maintenance'

def test_export_raw_odoo_attendance(app, client, monkeypatch):
    from models import SystemSetting
    site_id, admin_id, tech1_id, _, _, _ = create_admin_and_site(app)

    with app.app_context():
        s = SystemSetting(setting_key='ATTENDANCE_API_URL', setting_value='https://dummy-odoo.test/api')
        db.session.add(s)
        db.session.commit()

    # Mock requests.get
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                'results': [
                    {
                        'nrp': 'tech01',
                        'nama_karyawan': 'Teknisi 1',
                        'date': '2026-09-10',
                        'check_in': '2026-09-10 08:00:00',
                        'check_out': '2026-09-10 17:00:00',
                        'department': 'Engineering'
                    }
                ]
            }

    import requests
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: MockResponse())

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    res = client.get('/api/attendance/export_raw_odoo?date_from=2026-09-10&date_to=2026-09-10')
    assert res.status_code == 200
    assert res.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert 'Data_Mentah_Absensi_Odoo' in res.headers.get('Content-Disposition', '')

def test_unassigned_attendance_not_in_schedule_plan(app, client):
    site_id, admin_id, tech1_id, tech2_id, _, _ = create_admin_and_site(app)

    with app.app_context():
        # Technician 1 has attendance record on 2026-09-18 BUT NO UserShift scheduled
        att = AttendanceRecord(
            nrp="tech01",
            nama="Teknisi 1",
            date=date(2026, 9, 18),
            jam_masuk=datetime(2026, 9, 18, 8, 30),
            jam_pulang=datetime(2026, 9, 18, 17, 0),
            user_id=tech1_id
        )
        db.session.add(att)
        db.session.commit()
        att_id = att.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # In Schedule Plan (mode=plan): Should NOT display because no shift was entered/scheduled
    res_plan = client.get(f'/api/shift_assignments/{site_id}?mode=plan')
    assert res_plan.status_code == 200
    events_plan = res_plan.get_json()
    assert len(events_plan) == 0

    # In Realisasi (mode=realisasi): SHOULD display as standalone attendance
    res_real = client.get(f'/api/shift_assignments/{site_id}?mode=realisasi')
    assert res_real.status_code == 200
    events_real = res_real.get_json()
    assert len(events_real) == 1
    assert events_real[0]['id'] == f"att-only-{att_id}"
    assert 'Teknisi 1 - Hadir (08:30 - 17:00)' in events_real[0]['title']
    assert events_real[0]['extendedProps']['shift_name'] == 'Tanpa Jadwal'



