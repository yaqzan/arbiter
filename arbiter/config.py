"""Paths, ports and credential lookup. Nothing personal is written down here.

Every setting resolves in this order, first hit wins:

  1. an `ARBITER_<NAME>` environment variable
  2. the legacy `CURATOR_<NAME>` variable (the project's old name; still read so
     an existing install keeps working)
  3. the same `ARBITER_<NAME>` line in `.env` at the repo root (gitignored; copy
     `.env.example`), or in the file `ARBITER_ENV_FILE` points at
  4. a neutral default. Defaults never point at a particular machine, another
     repo or a particular domain: an unset Obsidian vault means the Obsidian
     import asks for `--path`, unset Radarr/Sonarr means the "on disk" badge is
     simply off.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / 'examples'
EXAMPLE_LIBRARY = EXAMPLES_DIR / 'library.json'


def _load_env_file():
    """`KEY=value` lines from .env. Blank lines and `#` comments are skipped;
    surrounding quotes are stripped. No interpolation, no export keyword."""
    path = os.environ.get('ARBITER_ENV_FILE') or os.environ.get('CURATOR_ENV_FILE')
    file = Path(path) if path else ROOT / '.env'
    if not file.is_file():
        return {}
    values = {}
    for line in file.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        values[key.strip()] = value
    return values


_FILE = _load_env_file()


def setting(name, default=None):
    """One setting by its short name (`plex_db` -> ARBITER_PLEX_DB)."""
    for prefix in ('ARBITER_', 'CURATOR_'):
        value = os.environ.get(prefix + name.upper())
        if value not in (None, ''):
            return value
    for prefix in ('ARBITER_', 'CURATOR_'):
        value = _FILE.get(prefix + name.upper())
        if value not in (None, ''):
            return value
    return default


# ── serving ──────────────────────────────────────────────────────────────────
# One port serves both /api and the built SPA, so a tunnel or reverse proxy needs
# exactly one hostname.
API_HOST = str(setting('host', '127.0.0.1'))
API_PORT = int(setting('port', 5002))
# Only used for display. Empty unless you publish it somewhere.
PUBLIC_ORIGIN = str(setting('public_origin', '')).rstrip('/')

# ── who can change things ────────────────────────────────────────────────────
# Anyone can read. Only a tailnet peer can write (see arbiter/auth.py), so the
# server listens on loopback AND on this machine's Tailscale address. That second
# bind is the lock. There is no passphrase to fall back on.
#
# Deliberately never 0.0.0.0. Binding every interface would let the LAN reach the
# port too, and the whole guarantee is that the SOCKET proves where a request
# came from. Two named binds keep that true: nothing but loopback and the tailnet
# can connect at all. With no Tailscale on the box the second bind is skipped and
# everyone, me included, gets the read-only site.
TAILSCALE_EXE = str(setting('tailscale') or shutil.which('tailscale') or (
    'C:/Program Files/Tailscale/tailscale.exe' if sys.platform == 'win32'
    else 'tailscale'))
TRUST_TAILNET = str(setting('trust_tailnet', '1')) != '0'

# Development only, off unless set. The Vite dev server talks to a loopback API,
# which by the rule above is a stranger, so without this nothing that writes can
# be tried locally. Read from the real environment ONLY (ARBITER_OPEN, or the
# legacy CURATOR_OPEN), never from .env: the service wrapper reads .env too, and
# loopback is also where the public tunnel arrives, so this flag in the wrong
# place opens every write to the internet. Never set it in server.ps1.
OPEN_ACCESS = (os.environ.get('ARBITER_OPEN')
               or os.environ.get('CURATOR_OPEN') or '') == '1'

_TAILSCALE_IP_CACHE = []


def tailscale_ip():
    """This machine's tailnet IPv4, or '' if Tailscale isn't running.

    Returns empty rather than raising, so the app still boots on a box without
    Tailscale and simply skips the second bind.
    """
    if _TAILSCALE_IP_CACHE:
        return _TAILSCALE_IP_CACHE[0]
    address = str(setting('tailscale_ip', '')).strip()
    if not address:
        try:
            out = subprocess.run([TAILSCALE_EXE, 'ip', '-4'],
                                 capture_output=True, text=True, timeout=10)
            address = (out.stdout or '').strip().splitlines()[0].strip()
        except (OSError, subprocess.SubprocessError, IndexError):
            address = ''
    _TAILSCALE_IP_CACHE.append(address)
    return address


_TAILNET_URL_CACHE = []


def tailnet_url():
    """The address to open from a tailnet device, or '' without Tailscale.

    Prefers the MagicDNS name over the raw 100.x address. The public hostname
    can't do this job: it points at the Cloudflare tunnel, so a phone on the
    tailnet still arrives through Cloudflare and the app sees loopback. Printed
    by `serve` and nowhere else, so it stays off the public surface.
    """
    if _TAILNET_URL_CACHE:
        return _TAILNET_URL_CACHE[0]
    host = ''
    try:
        out = subprocess.run([TAILSCALE_EXE, 'status', '--json'],
                             capture_output=True, text=True, timeout=10)
        host = (json.loads(out.stdout or '{}')
                .get('Self', {}).get('DNSName', '') or '').rstrip('.')
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        host = ''
    host = host or tailscale_ip()
    url = f'http://{host}:{API_PORT}' if host else ''
    _TAILNET_URL_CACHE.append(url)
    return url


# ── storage ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(setting('data_dir', ROOT / 'data'))


def _default_db():
    # `curator.db` is the pre-rename file name; an existing install keeps using
    # it until it is renamed to arbiter.db.
    preferred = DATA_DIR / 'arbiter.db'
    legacy = DATA_DIR / 'curator.db'
    return legacy if (not preferred.exists() and legacy.exists()) else preferred


DB_PATH = Path(setting('db') or _default_db())
CACHE_DIR = DATA_DIR / 'cache'
POSTER_CACHE = CACHE_DIR / 'posters'
FRONTEND_DIST = ROOT / 'frontend' / 'dist'

# ── Plex ─────────────────────────────────────────────────────────────────────
PLEX_METADATA_BASE = 'https://metadata.provider.plex.tv'
PLEX_DISCOVER_BASE = 'https://discover.provider.plex.tv'


def _default_plex_db():
    """Where Plex Media Server keeps its library database on this OS."""
    tail = Path('Plex Media Server') / 'Plug-in Support' / 'Databases' / \
        'com.plexapp.plugins.library.db'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', '')) / tail
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / tail
    return Path('/var/lib/plexmediaserver/Library/Application Support') / tail


# Plex's own library database. Its `metadata_item_settings` table is the watch
# ledger, keyed by the global `plex://` GUID, so it survives a library being
# removed or a machine migration. That is why the importer reads it directly
# instead of asking the HTTP API for a library that may not exist any more.
PLEX_DB = Path(setting('plex_db') or _default_plex_db())

# ── Obsidian (optional: a folder of one-note-per-title with star ratings) ─────
_vault = setting('obsidian_vault')
OBSIDIAN_VAULT = Path(_vault) if _vault else None
OBSIDIAN_OVERRIDES = Path(setting('obsidian_overrides',
                                  DATA_DIR / 'obsidian-overrides.json'))

# ── Radarr / Sonarr (optional "on disk" badge) ───────────────────────────────
# **Every local service is addressed as 127.0.0.1, never `localhost`.** On
# Windows `localhost` resolves to `::1` first; against an IPv4-only bind a dead
# service then burns the full timeout twice (measured 3.0s vs 1.5s per probe).
# The *arrs can live on another machine entirely: set the URL to wherever they
# are. Unset URL or key = enrichment off, nothing is probed.
RADARR_URL = str(setting('radarr_url', '')).rstrip('/')
SONARR_URL = str(setting('sonarr_url', '')).rstrip('/')


def _arr_key(service):
    """Key from `<service>_key`, else from an optional secrets JSON file shaped
    `{"radarr": {"api_key": "..."}, "sonarr": {...}}` named by `arr_secrets`."""
    key = setting(f'{service}_key')
    if key:
        return str(key)
    path = setting('arr_secrets')
    if not path:
        return ''
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))[service]['api_key']
    except Exception:
        return ''


RADARR_KEY = _arr_key('radarr')
SONARR_KEY = _arr_key('sonarr')

_PLEX_TOKEN_CACHE = None


def plex_token():
    """The Plex auth token: config/env, else (Windows) the registry value Plex
    Media Server writes when you sign in.

    Cached for the process lifetime: the registry read spawns PowerShell and the
    token does not change while the server is up.
    """
    global _PLEX_TOKEN_CACHE
    if _PLEX_TOKEN_CACHE is not None:
        return _PLEX_TOKEN_CACHE

    token = setting('plex_token') or os.environ.get('PLEX_TOKEN')
    if not token and sys.platform == 'win32':
        try:
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "(Get-ItemProperty 'HKCU:\\Software\\Plex, Inc.\\Plex Media Server' "
                 "-Name PlexOnlineToken -ErrorAction SilentlyContinue).PlexOnlineToken"],
                capture_output=True, text=True, timeout=20)
            token = (out.stdout or '').strip()
        except Exception:
            token = ''
    _PLEX_TOKEN_CACHE = str(token or '')
    return _PLEX_TOKEN_CACHE


def ensure_dirs():
    for path in (DATA_DIR, CACHE_DIR, POSTER_CACHE):
        path.mkdir(parents=True, exist_ok=True)
