"""Temporary ingress diagnostics expose data only to the existing demo credential."""
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from app import fish_audio, main
import ip_verification_app as probe


TOKEN = 'test-demo-credential-for-health-only-32-chars'


@pytest.fixture(autouse=True)
def prohibit_paid_operations(monkeypatch):
    monkeypatch.setenv('DEMO_ACCESS_TOKEN', TOKEN)
    forbidden = AsyncMock(side_effect=AssertionError('Health diagnostics must not call Fish.'))
    for name in ('generate', 'transcribe', 'create_voice'):
        monkeypatch.setattr(fish_audio, name, forbidden)
    yield
    forbidden.assert_not_called()


@pytest.mark.parametrize('credential', [None, 'Bearer invalid', 'Basic ' + TOKEN])
def test_unauthenticated_health_has_no_diagnostics(credential):
    headers = {'Authorization': credential} if credential else {}
    with TestClient(probe.app) as client:
        response = client.get('/api/health', headers=headers)
        assert response.status_code == 200
        assert 'x-tweeq-ip-check' not in response.headers


def test_authorized_diagnostics_preserve_health_body_and_hide_ips(monkeypatch):
    monkeypatch.setenv('PUBLIC_AI_ENABLED', 'false')
    monkeypatch.setenv('PUBLIC_GENERATIONS_ENABLED', 'false')
    with TestClient(probe.app) as client:
        response = client.get('/api/health', headers={'Authorization': 'Bearer ' + TOKEN,
                                                     'CF-Connecting-IP': '198.51.100.15'})
        assert response.json() == main.health()
        result = json.loads(response.headers['x-tweeq-ip-check'])
        assert result['cf_single_valid'] is True
        assert result['cf_is_spoof_test_address'] is False
        assert result['public_switches_disabled'] is True
        assert len(result['network_fingerprint']) == 64
        assert '198.51.100.15' not in response.headers['x-tweeq-ip-check']
        assert TOKEN not in response.headers['x-tweeq-ip-check']
        assert response.headers['cache-control'] == 'no-store'


def test_fake_or_ambiguous_header_is_visible_only_as_safe_flags():
    with TestClient(probe.app, headers={'Authorization': 'Bearer ' + TOKEN}) as client:
        result = json.loads(client.get('/api/health', headers={'CF-Connecting-IP': '203.0.113.31'}).headers['x-tweeq-ip-check'])
        assert result['cf_is_spoof_test_address'] is True
        response = client.get('/api/health', headers=[('CF-Connecting-IP', '198.51.100.15'),
                                                    ('CF-Connecting-IP', '203.0.113.31')])
        result = json.loads(response.headers['x-tweeq-ip-check'])
        assert result['cf_single_valid'] is False and result['network_fingerprint'] is None


def test_normal_application_has_no_temporary_diagnostics():
    with TestClient(main.app) as client:
        response = client.get('/api/health', headers={'Authorization': 'Bearer ' + TOKEN})
        assert 'x-tweeq-ip-check' not in response.headers
