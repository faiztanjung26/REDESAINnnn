import pytest
from models import db, User, Site, Location, Category, SubCategory, Asset

def setup_test_assets_data(app):
    with app.app_context():
        # Create Site
        site1 = Site(name="Bintaro Xchange 1")
        site2 = Site(name="Pondok Indah Mall")
        db.session.add_all([site1, site2])
        db.session.commit()

        # Create Admin User
        admin = User(nrp="admin_test", name="Admin Test", role="Admin", is_approved=True)
        admin.set_password("password123")
        db.session.add(admin)
        db.session.commit()

        # Create Categories
        cat_hvac = Category(name="HVAC")
        cat_elec = Category(name="Electrical")
        db.session.add_all([cat_hvac, cat_elec])
        db.session.commit()

        # Create Subcategories
        sub_chiller = SubCategory(name="Chiller", category_id=cat_hvac.id)
        sub_panel = SubCategory(name="Panel", category_id=cat_elec.id)
        db.session.add_all([sub_chiller, sub_panel])
        db.session.commit()

        # Create Locations
        loc_rooftop = Location(name="Roof Top", site_id=site1.id, description="Area lantai atas")
        loc_basement = Location(name="Basement", site_id=site1.id, description="Area parkir bawah")
        db.session.add_all([loc_rooftop, loc_basement])
        db.session.commit()

        # Create Assets
        asset1 = Asset(
            name="Chiller BXC 1 No. 1",
            code="AST-EC3841",
            status="Online",
            criticality="High",
            site_id=site1.id,
            location_id=loc_rooftop.id,
            category_id=cat_hvac.id,
            subcategory_id=sub_chiller.id,
            serial_number="SN-CHILLER-01",
            model="Carrier 30XA",
            make="Carrier"
        )
        asset2 = Asset(
            name="Chiller BXC 1 No. 2",
            code="AST-26D4E8",
            status="Offline",
            criticality="High",
            site_id=site1.id,
            location_id=loc_rooftop.id,
            category_id=cat_hvac.id,
            subcategory_id=sub_chiller.id,
            serial_number="SN-CHILLER-02",
            model="Carrier 30XA",
            make="Carrier"
        )
        asset3 = Asset(
            name="Main Distribution Panel",
            code="AST-MDP-01",
            status="Online",
            criticality="Critical",
            site_id=site1.id,
            location_id=loc_basement.id,
            category_id=cat_elec.id,
            subcategory_id=sub_panel.id,
            serial_number="SN-MDP-99",
            model="Schneider Prisma",
            make="Schneider"
        )
        db.session.add_all([asset1, asset2, asset3])
        db.session.commit()

        return {
            'admin_id': admin.id,
            'site1_id': site1.id,
            'site2_id': site2.id,
            'cat_hvac_id': cat_hvac.id,
            'cat_elec_id': cat_elec.id,
            'loc_rooftop_id': loc_rooftop.id,
            'loc_basement_id': loc_basement.id,
            'asset1_id': asset1.id,
            'asset2_id': asset2.id,
            'asset3_id': asset3.id,
        }

def test_assets_search_by_name_and_code(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Search by asset code
    res = client.get(f"/assets/?site_id={data['site1_id']}&tab=assets&q=AST-EC3841")
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Chiller BXC 1 No. 1" in html
    assert "Main Distribution Panel" not in html

    # Search by keyword "Chiller"
    res2 = client.get(f"/assets/?site_id={data['site1_id']}&tab=assets&q=Chiller")
    assert res2.status_code == 200
    html2 = res2.data.decode('utf-8')
    assert "Chiller BXC 1 No. 1" in html2
    assert "Chiller BXC 1 No. 2" in html2
    assert "Main Distribution Panel" not in html2

def test_assets_filter_by_status(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Filter by status "Offline"
    res = client.get(f"/assets/?site_id={data['site1_id']}&tab=assets&status=Offline")
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Chiller BXC 1 No. 2" in html
    assert "Chiller BXC 1 No. 1" not in html
    assert "Main Distribution Panel" not in html

def test_assets_filter_by_category_and_location(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Filter by category Electrical
    res = client.get(f"/assets/?site_id={data['site1_id']}&tab=assets&category_id={data['cat_elec_id']}")
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Main Distribution Panel" in html
    assert "Chiller BXC 1 No. 1" not in html

    # Filter by location Basement
    res2 = client.get(f"/assets/?site_id={data['site1_id']}&tab=assets&location_id={data['loc_basement_id']}")
    assert res2.status_code == 200
    html2 = res2.data.decode('utf-8')
    assert "Main Distribution Panel" in html2
    assert "Chiller BXC 1 No. 1" not in html2

def test_locations_tab_search(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Search in locations tab
    res = client.get(f"/assets/?site_id={data['site1_id']}&tab=locations&q=Roof")
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Roof Top" in html
    assert "Basement" not in html

def test_tree_tab_search(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Tree search with keyword "Panel"
    res = client.get(f"/assets/?site_id={data['site1_id']}&tab=tree&q=Panel")
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Main Distribution Panel" in html
    assert "Chiller BXC 1 No. 1" not in html

def test_facility_grid_search(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Search on Facility overview
    res = client.get("/assets/?q=Bintaro")
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Bintaro Xchange 1" in html
    assert "Pondok Indah Mall" not in html

def test_assets_search_route_fallback(app, client):
    data = setup_test_assets_data(app)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(data['admin_id'])

    # Exact code search redirects to view
    res = client.get("/assets/search?q=AST-EC3841")
    assert res.status_code == 302
    assert f"/assets/{data['asset1_id']}" in res.headers['Location']

    # Multiple matching search redirects to index with q
    res2 = client.get("/assets/search?q=Chiller")
    assert res2.status_code == 302
    assert "tab=assets" in res2.headers['Location']
    assert "q=Chiller" in res2.headers['Location']
