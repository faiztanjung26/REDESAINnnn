import pytest
from unittest.mock import patch, MagicMock
from models import db, User, Site, Asset, Category, SystemSetting

def test_analyze_meters_no_api_key(app, client):
    with app.app_context():
        site = Site(name="Test Site")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin_ai", name="Admin AI", role="Admin", is_approved=True)
        admin.set_password("pass123")
        db.session.add(admin)

        cat = Category(name="HVAC")
        db.session.add(cat)
        db.session.commit()

        asset = Asset(name="Chiller 1", code="AST-CH1", site_id=site.id, category_id=cat.id)
        db.session.add(asset)
        db.session.commit()

        admin_id = admin.id
        asset_id = asset.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    with patch.dict('os.environ', {}, clear=True):
        res = client.post(f"/assets/{asset_id}/meters/analyze", json={'prompt': 'Test prompt'})
        assert res.status_code == 500
        json_data = res.get_json()
        assert json_data['success'] is False
        assert "GROQ_API_KEY" in json_data['message']

def test_analyze_meters_empty_prompt(app, client):
    with app.app_context():
        site = Site(name="Test Site 2")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin_ai2", name="Admin AI 2", role="Admin", is_approved=True)
        admin.set_password("pass123")
        db.session.add(admin)

        cat = Category(name="HVAC")
        db.session.add(cat)

        setting = SystemSetting(setting_key='GROQ_API_KEY', setting_value='test_key_dummy')
        db.session.add(setting)
        db.session.commit()

        asset = Asset(name="Chiller 2", code="AST-CH2", site_id=site.id, category_id=cat.id)
        db.session.add(asset)
        db.session.commit()

        admin_id = admin.id
        asset_id = asset.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    res = client.post(f"/assets/{asset_id}/meters/analyze", json={'prompt': ''})
    assert res.status_code == 400
    json_data = res.get_json()
    assert json_data['success'] is False

def test_analyze_meters_success_with_mock(app, client):
    with app.app_context():
        site = Site(name="Test Site 3")
        db.session.add(site)
        db.session.commit()

        admin = User(nrp="admin_ai3", name="Admin AI 3", role="Admin", is_approved=True)
        admin.set_password("pass123")
        db.session.add(admin)

        cat = Category(name="HVAC")
        db.session.add(cat)

        setting = SystemSetting(setting_key='GROQ_API_KEY', setting_value='gsk_valid_mock_key')
        db.session.add(setting)
        db.session.commit()

        asset = Asset(name="Chiller 3", code="AST-CH3", site_id=site.id, category_id=cat.id)
        db.session.add(asset)
        db.session.commit()

        admin_id = admin.id
        asset_id = asset.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'choices': [
            {'message': {'content': 'Kondisi Chiller saat ini dalam status optimal dan tekanan normal.'}}
        ]
    }

    with patch('requests.post', return_value=mock_resp):
        res = client.post(f"/assets/{asset_id}/meters/analyze", json={'prompt': 'Analisis tekanan Chiller'})
        assert res.status_code == 200
        json_data = res.get_json()
        assert json_data['success'] is True
        assert 'Kondisi Chiller' in json_data['output']
        assert json_data['model_used'] == 'llama-3.3-70b-versatile'
