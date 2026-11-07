import os
import json
import pytest
from datetime import datetime, timezone
from models import db, User, WorkOrder, WorkOrderStatus, WorkOrderProcedure, Asset, Site, Category

def test_delete_procedure_photo_web(app, client):
    """Test deleting photo from procedure via Web route."""
    with app.app_context():
        # Setup site, status, user
        site = Site(name="Site Test Photo")
        db.session.add(site)
        db.session.commit()

        status_active = WorkOrderStatus(name="In Progress", control_type="Active")
        status_closed = WorkOrderStatus(name="Closed", control_type="Closed")
        db.session.add_all([status_active, status_closed])
        db.session.commit()

        admin = User(nrp="adm_photo", name="Admin Photo", role="Admin", site_id=site.id, is_approved=True)
        admin.set_password("pass")
        db.session.add(admin)

        cat = Category(name="General Equipment")
        db.session.add(cat)
        db.session.commit()

        asset = Asset(code="AST-001", name="Test Asset", site_id=site.id, category_id=cat.id)
        db.session.add(asset)
        db.session.commit()

        # Create Work Order
        wo = WorkOrder(
            code="WO-TEST-001",
            description="Test WO for Photo Deletion",
            status_id=status_active.id,
            asset_id=asset.id
        )
        db.session.add(wo)
        db.session.commit()

        # Create dummy file
        uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        dummy_file1 = 'uploads/dummy_test_photo_1.jpg'
        dummy_file2 = 'uploads/dummy_test_photo_2.jpg'
        with open(os.path.join(app.root_path, 'static', dummy_file1), 'w') as f:
            f.write("dummy1")
        with open(os.path.join(app.root_path, 'static', dummy_file2), 'w') as f:
            f.write("dummy2")

        # Create Procedure requiring 2 photos, currently with 2 photos
        proc = WorkOrderProcedure(
            work_order_id=wo.id,
            tasklist_name="General Tasks",
            name="Check Oil Level",
            min_photos=2,
            requires_attachment=True,
            attachment_path=f"{dummy_file1}|{dummy_file2}",
            is_completed=True,
            status="Done"
        )
        db.session.add(proc)
        db.session.commit()

        admin_id = admin.id
        wo_id = wo.id
        proc_id = proc.id

    # 1. Login session
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    # 2. Delete first photo via AJAX
    res = client.post(
        f'/work-orders/{wo_id}/procedure/{proc_id}/photo/delete',
        data={'photo_path': dummy_file1},
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['remaining_count'] == 1
    # Because min_photos is 2 and remaining is 1, is_completed should revert to False
    assert data['is_completed'] is False
    assert data['status'] == 'Pending'

    # Check physical file dummy1 was deleted
    assert not os.path.exists(os.path.join(app.root_path, 'static', dummy_file1))
    # dummy2 should still exist
    assert os.path.exists(os.path.join(app.root_path, 'static', dummy_file2))

    # Check database state
    with app.app_context():
        p = WorkOrderProcedure.query.get(proc_id)
        assert p.attachment_path == dummy_file2
        assert p.is_completed is False
        assert p.status == 'Pending'

    # 3. Clean up remaining dummy file
    dummy2_path = os.path.join(app.root_path, 'static', dummy_file2)
    if os.path.exists(dummy2_path):
        os.remove(dummy2_path)


def test_delete_procedure_photo_mobile_api(app, client):
    """Test deleting photo from procedure via Mobile API."""
    with app.app_context():
        site = Site(name="Site Mobile")
        db.session.add(site)
        db.session.commit()

        status_active = WorkOrderStatus(name="In Progress", control_type="Active")
        db.session.add(status_active)
        db.session.commit()

        tech = User(nrp="tech_photo", name="Tech Photo", role="Technician", site_id=site.id, is_approved=True)
        tech.set_password("pass123")
        db.session.add(tech)

        cat = Category(name="Electrical")
        db.session.add(cat)
        db.session.commit()

        asset = Asset(code="AST-MOB-001", name="Mobile Asset", site_id=site.id, category_id=cat.id)
        db.session.add(asset)
        db.session.commit()

        wo = WorkOrder(
            code="WO-MOB-001",
            description="Test Mobile WO",
            status_id=status_active.id,
            asset_id=asset.id
        )
        wo.assignees.append(tech)
        db.session.add(wo)
        db.session.commit()

        dummy_file = 'uploads/dummy_mob_photo.jpg'
        full_path = os.path.join(app.root_path, 'static', dummy_file)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write("dummy mobile photo")

        proc = WorkOrderProcedure(
            work_order_id=wo.id,
            tasklist_name="Motor Tasks",
            name="Inspect Motor",
            min_photos=1,
            requires_attachment=True,
            attachment_path=dummy_file,
            is_completed=True,
            status="Done"
        )
        db.session.add(proc)
        db.session.commit()

        wo_id = wo.id
        proc_id = proc.id

    # Mobile login
    login_res = client.post('/api/mobile/login', json={'nrp': 'tech_photo', 'password': 'pass123'})
    assert login_res.status_code == 200
    token = login_res.get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    # Delete photo via mobile endpoint
    res = client.post(
        f'/api/mobile/work-orders/{wo_id}/procedures/{proc_id}/photos/delete',
        headers=headers,
        json={'photo_path': dummy_file}
    )
    assert res.status_code == 200
    resp_data = res.get_json()
    assert resp_data['status'] == 'success'
    assert resp_data['procedure']['photos'] == []
    assert resp_data['procedure']['is_completed'] is False

    # Check physical file deleted
    assert not os.path.exists(full_path)
