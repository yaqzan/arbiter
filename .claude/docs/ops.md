# Ops: the live service and the Arbiter cutover

## Live service (this machine)

- Registered in `C:\Development\server.ps1` as `curator` = `curator-api` +
  `curator-tunnel`. The api entry runs `python -u -m curator serve` from this folder;
  its process matcher keys on `-m curator` **plus `serve`**, so import/stats/top
  runs aren't mistaken for a stale server.
- Own locally-managed cloudflared tunnel named `curator`, config at
  `ops/cloudflared-config.yml` (gitignored; the public copy is
  `cloudflared-config.example.yml`), `curator.yaqzan.dev` -> `http://127.0.0.1:5002`.
  Own tunnel because `trading-api` is dashboard-managed and cannot be extended from
  config. Global rule: `--config` + tunnel UUID, `--overwrite-dns` to fix a bad
  record; ~30s of edge 502s after a connector restart is normal.
- "Curator Watchdog" scheduled task, every 5 min, runs `ops/windows/watchdog.ps1`
  with NO arguments (via Trader's `hidden_run.vbs`; re-registering needs an
  elevated shell). The gitignored `ops/windows/watchdog.local.psd1` supplies
  `Name='curator'` + `Controller=server.ps1` so it keeps probing `run curator` and
  calling `server.ps1 start -Service curator-*`.
- Storage: `data/curator.db` (SQLite, WAL). `config._default_db` uses it while
  `data/arbiter.db` doesn't exist. Backup = copy the file (with `-wal`/`-shm` while
  the server runs). Cache under `data/cache/`, purge backups under `data/purges/`.
- **Access (see [`access.md`](access.md)).** `serve` binds 127.0.0.1:5002 (where
  the tunnel lands, read only) and the Tailscale IP on the same port (writes). I
  edit at `http://<machine>.<tailnet>.ts.net:5002`; `serve` prints the real one.
  server.ps1 needs no `--host`: the launch line stays as it is. Never add
  `ARBITER_OPEN` to it. If Tailscale is not up when the service starts, the tailnet
  bind is skipped until the next restart.
- **The process running since before 2026-09-23 predates the guard**, so the live
  site stays writable by anyone until it restarts. Restart and rebuild the SPA
  together (step 5 below, or earlier on its own): the new SPA against the old
  server shows everyone the read-only view, and the old SPA against the new server
  shows strangers buttons that 403.
- Settings in the gitignored root `.env` (public origin, Obsidian vault path).
  Plex token from the registry. Radarr/Sonarr run on another machine and are not configured
  here, so the badge is off.

## Pre-cutover scaffolding (delete at cutover)

- `curator/` (local only, in `.git/info/exclude`): a shim so `python -m curator
  serve` still starts Arbiter, plus `curator/sources/*` aliases for the lazy imports
  of the process that was already running at the rename.
- `watchdog.local.psd1` (above) and the `curator.db` fallback.
- `frontend/dist` still holds the pre-rename build; the running server serves it
  from disk, so rebuild only at cutover.

## Cutover checklist (owner-run, in order)

1. Stop the service: `server.ps1 -Action stop -Service curator`.
2. Rename the folder `C:\Development\Curator` -> `C:\Development\Arbiter`; in it,
   rename `data\curator.db` (+ `-wal`/`-shm` if present) to `arbiter.db`, delete
   the `curator\` shim folder and the `/curator/` line in `.git\info\exclude`.
3. `server.ps1`: `$CuratorDir` -> Arbiter folder, services `arbiter`,
   `arbiter-api`, `arbiter-tunnel` (ValidateSet, `$ServiceOrder`, group map, dir
   map, matcher `-m\s+arbiter` + `serve`, launch line `-m arbiter serve`, tunnel
   `run arbiter`, health URLs). Keep `curator*` aliases for a while if anything else
   calls them.
4. Tunnel: create `arbiter` tunnel (or keep the `curator` UUID and just rename it in
   config), route `arbiter.yaqzan.dev`, keep `curator.yaqzan.dev` as a redirect
   (Cloudflare redirect rule to `https://arbiter.yaqzan.dev/$1`). Update
   `ops/cloudflared-config.yml`; set `ARBITER_PUBLIC_ORIGIN` in `.env`.
5. `npm --prefix frontend run build`, then `server.ps1 -Action start -Service arbiter`
   and check `/api/health` locally and publicly: `authed` is false on
   `http://127.0.0.1:5002` and on the public hostname, true on the tailnet address.
   A PATCH through the public hostname must 403.
6. Watchdog (elevated): `Unregister-ScheduledTask 'Curator Watchdog'`, delete
   `watchdog.local.psd1`, run
   `ops\windows\install-tasks.ps1 -Controller C:\Development\server.ps1`.
7. GitHub: bundle the local history (it holds the old tunnel config and overrides),
   rename `yaqzan/curator` -> `yaqzan/arbiter`; orphan commit of the
   tracked tree, force-push over the snapshot `main`, per the Foyer pilot note.
8. Pharos `config.json` apps key `curator` -> `arbiter`, rename the Pushover app.
9. claude-rc `$Projects` entry, Foyer projects page, `~/.claude.json`
   `githubRepoPaths`, memory, kanban board folder name.
