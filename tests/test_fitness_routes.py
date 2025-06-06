import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import create_app

@pytest.fixture
def app():
    os.environ['DATABASE_URL'] = 'sqlite://'
    app = create_app()
    app.config['TESTING'] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_auth_garmin(client):
    with patch('app.routes.fitness_routes.get_garmin_authorization_url') as mock_get:
        mock_get.return_value = {'authorization_url': 'http://example.com'}
        resp = client.get('/auth/garmin')
        assert resp.status_code == 200

def test_garmin_activities(client):
    with patch('app.routes.fitness_routes.fetch_garmin_activities') as mock_fetch:
        mock_fetch.return_value = []
        resp = client.post('/garmin/activities', json={'token': 't', 'token_secret': 's'})
        assert resp.status_code == 200
