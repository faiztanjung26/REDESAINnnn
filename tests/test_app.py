def test_home_redirect_to_login(client):
    """Test that the root URL redirects to login if not authenticated."""
    response = client.get('/')
    # Because there are decorators like @login_required, 
    # it should redirect (status code 302) to the login page
    assert response.status_code == 302
    assert b'/login' in response.data or response.headers['Location'].endswith('/login')

def test_login_page_loads(client):
    """Test that the login page renders successfully."""
    response = client.get('/login')
    # If the login blueprint is mounted correctly, this should return 200
    assert response.status_code == 200
    # Check if the login form or related text is in the response
    assert b'Login' in response.data or b'login' in response.data.lower()

def test_nonexistent_route_404(client):
    """Test that a non-existent route returns 404."""
    response = client.get('/this-route-does-not-exist')
    assert response.status_code == 404

def test_logsheet_management_excludes_day_off_shifts(app, client):
    """Test that logsheet management does not show day off shifts (Cuti, Libur, is_off_day=True)."""
    from datetime import time
    from models import db, User, Site, Shift

    with app.app_context():
        site = Site(name="Site Jakarta")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin99", name="Admin Jakarta", role="Admin", site_id=site.id, is_approved=True)
        admin.set_password("secret")
        db.session.add(admin)

        s_pagi = Shift(site_id=site.id, name="Shift Pagi", start_time=time(7, 0), end_time=time(15, 0), is_off_day=False)
        s_cuti = Shift(site_id=site.id, name="Cuti", start_time=time(0, 0), end_time=time(0, 0), is_off_day=True)
        s_libur = Shift(site_id=site.id, name="Libur", start_time=time(0, 0), end_time=time(0, 0), is_off_day=True)
        db.session.add_all([s_pagi, s_cuti, s_libur])
        db.session.commit()

        admin_id = admin.id
        site_id = site.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    response = client.get(f'/dashboard/logsheet_management?site_id={site_id}&tab=schedules')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert "Cuti" not in html
    assert "Libur" not in html

def test_logsheet_management_grid_and_list_views(app, client):
    """Test that logsheet management renders both Grid and List view containers and handles view_mode parameter."""
    from datetime import date, time
    from models import db, User, Site, Shift, Asset, LogsheetSchedule

    with app.app_context():
        site = Site(name="Site Bali")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin88", name="Admin Bali", role="Admin", site_id=site.id, is_approved=True)
        admin.set_password("secret")
        db.session.add(admin)

        from models import Category
        cat = Category(name="HVAC")
        db.session.add(cat)
        db.session.commit()

        asset = Asset(name="Chiller No. 3 (600TR)", code="AST-585ED9", site_id=site.id, category_id=cat.id)
        db.session.add(asset)
        db.session.commit()

        sched = LogsheetSchedule(
            code="SCH-20260821-001",
            name="Chiller No. 3 (600TR)",
            asset_id=asset.id,
            site_id=site.id,
            scheduled_date=date(2026, 8, 21),
            scheduled_time=time(14, 0),
            status="Scheduled",
            created_by_id=admin.id
        )
        db.session.add(sched)
        db.session.commit()

        admin_id = admin.id
        site_id = site.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # Test default grid view
    res_grid = client.get(f'/dashboard/logsheet_management?site_id={site_id}&tab=schedules&date_from=2026-08-21&date_to=2026-08-21')
    assert res_grid.status_code == 200
    html_grid = res_grid.data.decode('utf-8')
    assert 'id="gridViewContainer"' in html_grid
    assert 'id="listViewContainer"' in html_grid
    assert 'SCH-20260821-001' in html_grid
    assert 'Chiller No. 3 (600TR)' in html_grid

    # Test list view mode
    res_list = client.get(f'/dashboard/logsheet_management?site_id={site_id}&tab=schedules&date_from=2026-08-21&date_to=2026-08-21&view_mode=list')
    assert res_list.status_code == 200
    html_list = res_list.data.decode('utf-8')
    assert 'SCH-20260821-001' in html_list
    assert 'Isi' in html_list

def test_bulk_add_asset_logsheet_with_technicians(app, client):
    """Test bulk adding multiple assets with custom date and max 2 technicians per asset."""
    from datetime import date
    from models import db, User, Site, Asset, Category, LogsheetSchedule, AssetCustomField

    with app.app_context():
        site = Site(name="Site Surabaya")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin77", name="Admin SBY", role="Admin", site_id=site.id, is_approved=True)
        tech1 = User(nrp="tech71", name="Teknisi 1", role="Technician", site_id=site.id, is_approved=True)
        tech2 = User(nrp="tech72", name="Teknisi 2", role="Technician", site_id=site.id, is_approved=True)
        tech3 = User(nrp="tech73", name="Teknisi 3", role="Technician", site_id=site.id, is_approved=True)
        admin.set_password("secret")
        tech1.set_password("secret")
        tech2.set_password("secret")
        tech3.set_password("secret")
        db.session.add_all([admin, tech1, tech2, tech3])

        cat = Category(name="Pumps")
        db.session.add(cat)
        db.session.commit()

        a1 = Asset(name="Pump 01", code="PMP-01", site_id=site.id, category_id=cat.id)
        a2 = Asset(name="Pump 02", code="PMP-02", site_id=site.id, category_id=cat.id)
        db.session.add_all([a1, a2])
        db.session.commit()

        admin_id = admin.id
        site_id = site.id
        t1_id = tech1.id
        t2_id = tech2.id
        t3_id = tech3.id
        a1_id = a1.id
        a2_id = a2.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # Post multi-asset creation
    post_data = {
        'scheduled_date': '2026-09-20',
        'scheduled_time': '09:30',
        'site_id': str(site_id),
        'asset_ids': [str(a1_id), str(a2_id)],
        f'tech_ids_{a1_id}': [str(t1_id), str(t2_id), str(t3_id)], # tech3 should be ignored because max 2
        f'tech_ids_{a2_id}': [str(t1_id)]
    }

    res = client.post('/dashboard/logsheet/api/add_asset', data=post_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        # Verify both assets marked as logsheet assets
        cf1 = AssetCustomField.query.filter_by(asset_id=a1_id, field_name='is_logsheet_asset').first()
        cf2 = AssetCustomField.query.filter_by(asset_id=a2_id, field_name='is_logsheet_asset').first()
        assert cf1 is not None and cf1.field_value == 'true'
        assert cf2 is not None and cf2.field_value == 'true'

        # Verify schedules created
        scheds = LogsheetSchedule.query.filter_by(scheduled_date=date(2026, 9, 20)).all()
        assert len(scheds) == 2

        s1 = next(s for s in scheds if s.asset_id == a1_id)
        s2 = next(s for s in scheds if s.asset_id == a2_id)

        # Asset 1 must have exactly 2 technicians (t1 and t2)
        assert len(s1.assigned_technicians) == 2
        tech_ids_s1 = [t.id for t in s1.assigned_technicians]
        assert t1_id in tech_ids_s1
        assert t2_id in tech_ids_s1
        assert t3_id not in tech_ids_s1

        # Asset 2 must have 1 technician (t1)
        assert len(s2.assigned_technicians) == 1
        assert s2.assigned_technicians[0].id == t1_id


def test_bulk_add_asset_date_range_and_multiple_times(app, client):
    """Test generating schedules across a date range and with multiple inspection times per asset."""
    from datetime import date, time
    from models import db, User, Site, Asset, Category, LogsheetSchedule

    with app.app_context():
        site = Site(name="Site Medan")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin55", name="Admin Medan", role="Admin", site_id=site.id, is_approved=True)
        tech1 = User(nrp="tech51", name="Teknisi Mdn 1", role="Technician", site_id=site.id, is_approved=True)
        tech2 = User(nrp="tech52", name="Teknisi Mdn 2", role="Technician", site_id=site.id, is_approved=True)
        admin.set_password("secret")
        tech1.set_password("secret")
        tech2.set_password("secret")
        db.session.add_all([admin, tech1, tech2])

        cat = Category(name="Generators")
        db.session.add(cat)
        db.session.commit()

        gen1 = Asset(name="Genset 01", code="GEN-01", site_id=site.id, category_id=cat.id)
        gen2 = Asset(name="Genset 02", code="GEN-02", site_id=site.id, category_id=cat.id)
        db.session.add_all([gen1, gen2])
        db.session.commit()

        admin_id = admin.id
        site_id = site.id
        t1_id = tech1.id
        t2_id = tech2.id
        g1_id = gen1.id
        g2_id = gen2.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # Schedule for 3 days (2026-10-01 to 2026-10-03)
    # gen1: 3 times per day (08:00, 14:00, 20:00) with 2 technicians (t1, t2)
    # gen2: 2 times per day (09:00, 17:00) with 1 technician (t2)
    post_data = {
        'scheduled_date': '2026-10-01',
        'scheduled_end_date': '2026-10-03',
        'site_id': str(site_id),
        'asset_ids': [str(g1_id), str(g2_id)],
        f'times_{g1_id}': ['08:00', '14:00', '20:00'],
        f'tech_ids_{g1_id}': [str(t1_id), str(t2_id)],
        f'times_{g2_id}': ['09:00', '17:00'],
        f'tech_ids_{g2_id}': [str(t2_id)]
    }

    res = client.post('/dashboard/logsheet/api/add_asset', data=post_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        # Total expected schedules = 3 days * 3 times (gen1) + 3 days * 2 times (gen2) = 9 + 6 = 15 schedules
        scheds_all = LogsheetSchedule.query.filter(
            LogsheetSchedule.scheduled_date >= date(2026, 10, 1),
            LogsheetSchedule.scheduled_date <= date(2026, 10, 3)
        ).all()
        assert len(scheds_all) == 15

        for d in [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]:
            day_scheds_g1 = [s for s in scheds_all if s.scheduled_date == d and s.asset_id == g1_id]
            day_scheds_g2 = [s for s in scheds_all if s.scheduled_date == d and s.asset_id == g2_id]

            # Gen 1 check
            assert len(day_scheds_g1) == 3
            g1_times = sorted([s.scheduled_time for s in day_scheds_g1])
            assert g1_times == [time(8, 0), time(14, 0), time(20, 0)]
            for s in day_scheds_g1:
                assert len(s.assigned_technicians) == 2
                assigned_ids = [t.id for t in s.assigned_technicians]
                assert t1_id in assigned_ids and t2_id in assigned_ids

            # Gen 2 check
            assert len(day_scheds_g2) == 2
            g2_times = sorted([s.scheduled_time for s in day_scheds_g2])
            assert g2_times == [time(9, 0), time(17, 0)]
            for s in day_scheds_g2:
                assert len(s.assigned_technicians) == 1
                assert s.assigned_technicians[0].id == t2_id


def test_bulk_add_asset_repeat_days_of_week(app, client):
    """Test generating schedules only on specified weekdays (e.g., Senin, Rabu, Kamis)."""
    from datetime import date, time
    from models import db, User, Site, Asset, Category, LogsheetSchedule

    with app.app_context():
        site = Site(name="Site Semarang")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin44", name="Admin Semarang", role="Admin", site_id=site.id, is_approved=True)
        admin.set_password("secret")
        db.session.add(admin)

        cat = Category(name="Transformers")
        db.session.add(cat)
        db.session.commit()

        trafo = Asset(name="Trafo 01", code="TRF-01", site_id=site.id, category_id=cat.id)
        db.session.add(trafo)
        db.session.commit()

        admin_id = admin.id
        site_id = site.id
        trafo_id = trafo.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # Oct 1 2026 is Thu (weekday 3), Oct 8 2026 is Thu (weekday 3) - total 8 days:
    # 2026-10-01 (Thu - 3)
    # 2026-10-02 (Fri - 4)
    # 2026-10-03 (Sat - 5)
    # 2026-10-04 (Sun - 6)
    # 2026-10-05 (Mon - 0)
    # 2026-10-06 (Tue - 1)
    # 2026-10-07 (Wed - 2)
    # 2026-10-08 (Thu - 3)
    # If we filter by repeat_days = ['0', '2', '3'] (Senin, Rabu, Kamis):
    # Expected matching dates: Oct 1 (Thu), Oct 5 (Mon), Oct 7 (Wed), Oct 8 (Thu) -> 4 days total!
    post_data = {
        'scheduled_date': '2026-10-01',
        'scheduled_end_date': '2026-10-08',
        'site_id': str(site_id),
        'asset_ids': [str(trafo_id)],
        'repeat_days': ['0', '2', '3'], # Mon, Wed, Thu
        f'times_{trafo_id}': ['10:00']
    }

    res = client.post('/dashboard/logsheet/api/add_asset', data=post_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        scheds = LogsheetSchedule.query.filter(
            LogsheetSchedule.asset_id == trafo_id,
            LogsheetSchedule.scheduled_date >= date(2026, 10, 1),
            LogsheetSchedule.scheduled_date <= date(2026, 10, 8)
        ).all()

        assert len(scheds) == 4
        sched_dates = sorted([s.scheduled_date for s in scheds])
        assert sched_dates == [
            date(2026, 10, 1), # Thu
            date(2026, 10, 5), # Mon
            date(2026, 10, 7), # Wed
            date(2026, 10, 8)  # Thu
        ]


