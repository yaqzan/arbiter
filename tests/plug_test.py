"""Plug and play: a fresh clone runs on the example library, writes wait for `init`,
and nothing personal or machine-specific is a default."""

import importlib

import pytest

from arbiter import config, db, example, media_types
from arbiter.sources import arr


@pytest.fixture
def no_library(tmp_path, monkeypatch):
    """No data/arbiter.db: the state of a fresh clone."""
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(config, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(config, 'POSTER_CACHE', tmp_path / 'cache' / 'posters')
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'arbiter.db')
    db.close()
    monkeypatch.setattr(db, '_example_path', None)
    yield tmp_path
    db.close()


def test_example_library_is_well_formed():
    library = example.load()
    titles = {(i['media_type'], i['title']) for i in library['items']}
    assert all(media_types.is_known(t) for t, _ in titles)
    # Every contest can serve at least one full round of four.
    for key in media_types.TYPES:
        assert sum(1 for t, _ in titles if t == key) >= 4, key
    for round_ in library['rounds']:
        for group in round_['order']:
            for title in group:
                assert (round_['media_type'], title) in titles


def test_reads_fall_back_to_the_example(no_library):
    assert db.using_example()
    count = db.one('SELECT COUNT(*) c FROM items')['c']
    assert count == len(example.load()['items'])
    assert db.one('SELECT COUNT(*) c FROM rank_sets')['c'] == len(example.load()['rounds'])
    assert not (no_library / 'arbiter.db').exists()


def test_api_refuses_writes_until_init(no_library):
    from arbiter.api import create_app
    # A tailnet peer, so the write reaches the example check instead of being
    # refused as a stranger's first (tests/access_test.py covers that).
    client = create_app().test_client()
    client.environ_base['REMOTE_ADDR'] = '100.101.102.103'

    health = client.get('/api/health').get_json()
    assert health['example'] is True and health['items'] > 0
    assert client.get('/api/rank/set?type=movie').get_json()['items']

    response = client.post('/api/rank/set-result', json={'type': 'movie', 'tiers': [[1], [2]]})
    assert response.status_code == 409
    assert 'init' in response.get_json()['error']


def test_cli_writes_refuse_until_init(no_library, capsys):
    from arbiter import cli
    assert cli.main(['refit']) == 1
    assert 'init' in capsys.readouterr().err


def test_init_creates_an_empty_library_and_never_overwrites(no_library):
    from arbiter import cli
    assert cli.main(['init']) == 0
    assert (no_library / 'arbiter.db').exists()
    assert not db.using_example()
    assert db.one('SELECT COUNT(*) c FROM items')['c'] == 0
    assert cli.main(['init']) == 1


def test_init_with_examples_seeds_your_library(no_library):
    from arbiter import cli
    assert cli.main(['init', '--examples']) == 0
    assert db.one('SELECT COUNT(*) c FROM items')['c'] == len(example.load()['items'])


def test_no_personal_defaults(monkeypatch, tmp_path):
    for key in list(__import__('os').environ):
        if key.startswith(('ARBITER_', 'CURATOR_')):
            monkeypatch.delenv(key)
    monkeypatch.setenv('ARBITER_ENV_FILE', str(tmp_path / 'missing.env'))
    fresh = importlib.reload(config)
    try:
        assert fresh.RADARR_URL == '' and fresh.SONARR_URL == ''
        assert fresh.RADARR_KEY == '' and fresh.SONARR_KEY == ''
        assert fresh.OBSIDIAN_VAULT is None
        assert fresh.PUBLIC_ORIGIN == ''
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_legacy_env_names_still_work(monkeypatch, tmp_path):
    monkeypatch.setenv('ARBITER_ENV_FILE', str(tmp_path / 'missing.env'))
    monkeypatch.delenv('ARBITER_PORT', raising=False)
    monkeypatch.setenv('CURATOR_PORT', '5999')
    try:
        assert importlib.reload(config).API_PORT == 5999
        monkeypatch.setenv('ARBITER_PORT', '5998')
        assert importlib.reload(config).API_PORT == 5998
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_env_file_is_read(monkeypatch, tmp_path):
    env = tmp_path / '.env'
    env.write_text('# comment\nARBITER_OBSIDIAN_VAULT="/some/vault"\n', encoding='utf-8')
    monkeypatch.delenv('ARBITER_OBSIDIAN_VAULT', raising=False)
    monkeypatch.delenv('CURATOR_OBSIDIAN_VAULT', raising=False)
    monkeypatch.setenv('ARBITER_ENV_FILE', str(env))
    try:
        assert str(importlib.reload(config).OBSIDIAN_VAULT).replace('\\', '/') == '/some/vault'
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_unconfigured_arrs_are_off_without_probing(monkeypatch):
    monkeypatch.setattr(config, 'RADARR_URL', '')
    monkeypatch.setattr(config, 'SONARR_URL', '')

    def boom(*args, **kwargs):
        raise AssertionError('probed an unconfigured *arr')

    monkeypatch.setattr(arr, '_get', boom)
    assert arr.available(force=True) == {'radarr': False, 'sonarr': False}
    assert arr.annotate([{'tmdb_id': '1'}]) == [{'tmdb_id': '1'}]
