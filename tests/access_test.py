"""The network is the only credential: anyone can read, only a tailnet peer writes.

A stranger here is anything that isn't 100.64.0.0/10, and that includes loopback,
because the public Cloudflare tunnel arrives on loopback.
"""

import importlib
import re

import pytest

from arbiter import api, auth, config

STRANGER = '127.0.0.1'
PEER = '100.101.102.103'
MUTATING = {'POST', 'PUT', 'PATCH', 'DELETE'}


@pytest.fixture
def app(make_item, monkeypatch):
    monkeypatch.setattr(config, 'TRUST_TAILNET', True)
    monkeypatch.setattr(config, 'OPEN_ACCESS', False)
    first = make_item('movie', 'Heat', tier=5)
    make_item('movie', 'Ronin', tier=4)
    make_item('movie', 'Thief', tier=4)
    from arbiter import db
    db.execute("UPDATE items SET notes = 'my private note' WHERE id = ?", (first,))
    application = api.create_app()
    application.config['first_id'] = first
    return application


def client_from(app, address):
    client = app.test_client()
    client.environ_base['REMOTE_ADDR'] = address
    return client


def concrete(rule, item_id):
    """A real URL for a Flask rule: every `<int:x>` becomes an existing id."""
    return re.sub(r'<[^>]+>', str(item_id), rule)


def mutation_routes(app):
    out = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/api/'):
            continue
        for method in sorted(rule.methods & MUTATING):
            out.append((method, rule.rule))
    return out


def test_every_mutation_is_refused_to_a_stranger(app):
    routes = mutation_routes(app)
    # Guard against the enumeration silently finding nothing.
    assert len(routes) >= 9, routes
    client = client_from(app, STRANGER)
    for method, rule in routes:
        url = concrete(rule, app.config['first_id'])
        response = client.open(url, method=method, json={'type': 'movie'})
        assert response.status_code == 403, (method, url, response.status_code)


def test_nothing_changed_after_the_stranger_tried(app):
    client = client_from(app, STRANGER)
    first = app.config['first_id']
    client.patch(f'/api/items/{first}', json={'tier': 1})
    client.delete(f'/api/items/{first}')
    item = client_from(app, PEER).get(f'/api/items/{first}').get_json()
    assert item['tier'] == 5


@pytest.mark.parametrize('path', [
    '/api/rank/set?type=movie',
    '/api/search?q=heat',
    '/api/import/status',
    '/api/items/1/purge-history',       # nested under a public prefix
    '/api/no-such-route',               # unknown means private, not 404-then-open
])
def test_private_reads_are_refused_to_a_stranger(app, path):
    assert client_from(app, STRANGER).get(path).status_code == 403


@pytest.mark.parametrize('path', [
    '/api/health',
    '/api/types',
    '/api/items?type=movie',
    '/api/items/{id}',
    '/api/rank/stats?type=movie',
    '/api/rank/leaderboard?type=movie',
    '/api/rank/review?type=movie',
    '/api/rank/history?type=movie',
])
def test_the_library_and_rankings_are_public(app, path):
    url = path.format(id=app.config['first_id'])
    assert client_from(app, STRANGER).get(url).status_code == 200


def test_a_stranger_never_sees_my_notes(app):
    first = app.config['first_id']
    stranger = client_from(app, STRANGER)
    assert 'notes' not in stranger.get(f'/api/items/{first}').get_json()
    listed = stranger.get('/api/items?type=movie').get_json()['items']
    assert listed and all('notes' not in i for i in listed)
    board = stranger.get('/api/rank/leaderboard?type=movie').get_json()['items']
    assert all('notes' not in i for i in board)
    mine = client_from(app, PEER).get(f'/api/items/{first}').get_json()
    assert mine['notes'] == 'my private note'


def test_health_says_who_is_asking(app):
    stranger = client_from(app, STRANGER).get('/api/health').get_json()
    assert stranger['authed'] is False and stranger['via_tailnet'] is False
    peer = client_from(app, PEER).get('/api/health').get_json()
    assert peer['authed'] is True and peer['via_tailnet'] is True


def test_a_tailnet_peer_can_change_things(app):
    peer = client_from(app, PEER)
    first = app.config['first_id']
    response = peer.patch(f'/api/items/{first}', json={'tier': 3})
    assert response.status_code == 200 and response.get_json()['tier'] == 3
    ids = [i['id'] for i in peer.get('/api/items?type=movie').get_json()['items']]
    round_ = peer.post('/api/rank/set-result', json={'type': 'movie',
                                                    'tiers': [[ids[0]], [ids[1]]]})
    assert round_.status_code == 200
    assert peer.get('/api/rank/set?type=movie').status_code == 200
    assert peer.post('/api/rank/undo', json={'type': 'movie'}).status_code == 200


@pytest.mark.parametrize('header', ['X-Forwarded-For', 'X-Real-IP',
                                    'CF-Connecting-IP', 'Forwarded'])
def test_a_forged_header_from_loopback_is_still_a_stranger(app, header):
    value = f'for={PEER}' if header == 'Forwarded' else PEER
    client = client_from(app, STRANGER)
    first = app.config['first_id']
    response = client.patch(f'/api/items/{first}', json={'tier': 1},
                            headers={header: value})
    assert response.status_code == 403
    health = client.get('/api/health', headers={header: value}).get_json()
    assert health['authed'] is False


def test_near_miss_paths_are_not_public_writes(app):
    client = client_from(app, STRANGER)
    for path in ('/API/items', '/api/items/', '/api//items'):
        assert client.post(path, json={'guid': 'x'}).status_code in (403, 404, 405)
        assert client.post(path, json={'guid': 'x'}).status_code != 200


def test_only_the_tailnet_block_counts():
    assert auth.from_tailnet('100.64.0.1')
    assert auth.from_tailnet('100.127.255.254')
    for outside in ('100.63.255.255', '100.128.0.0', '127.0.0.1', '192.168.1.20',
                    '10.0.0.5', '::1', '', 'not-an-ip'):
        assert not auth.from_tailnet(outside), outside


def test_trust_tailnet_off_refuses_peers_too(app, monkeypatch):
    monkeypatch.setattr(config, 'TRUST_TAILNET', False)
    first = app.config['first_id']
    response = client_from(app, PEER).patch(f'/api/items/{first}', json={'tier': 2})
    assert response.status_code == 403


def test_arbiter_open_lets_loopback_write(app, monkeypatch):
    monkeypatch.setattr(config, 'OPEN_ACCESS', True)
    client = client_from(app, STRANGER)
    first = app.config['first_id']
    response = client.patch(f'/api/items/{first}', json={'tier': 2})
    assert response.status_code == 200
    health = client.get('/api/health').get_json()
    assert health['authed'] is True and health['via_tailnet'] is False


def test_open_and_trust_come_from_the_environment(monkeypatch, tmp_path):
    env = tmp_path / '.env'
    # ARBITER_OPEN in .env must NOT open anything: the service reads .env too.
    env.write_text('ARBITER_OPEN=1\n', encoding='utf-8')
    for key in ('ARBITER_OPEN', 'CURATOR_OPEN', 'ARBITER_TRUST_TAILNET',
                'CURATOR_TRUST_TAILNET'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('ARBITER_ENV_FILE', str(env))
    try:
        fresh = importlib.reload(config)
        assert fresh.OPEN_ACCESS is False
        assert fresh.TRUST_TAILNET is True
        monkeypatch.setenv('ARBITER_OPEN', '1')
        monkeypatch.setenv('ARBITER_TRUST_TAILNET', '0')
        fresh = importlib.reload(config)
        assert fresh.OPEN_ACCESS is True and fresh.TRUST_TAILNET is False
        monkeypatch.delenv('ARBITER_OPEN')
        monkeypatch.setenv('CURATOR_OPEN', '1')
        assert importlib.reload(config).OPEN_ACCESS is True
    finally:
        monkeypatch.undo()
        importlib.reload(config)
