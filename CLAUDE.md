# CLAUDE.md

Guidance for Claude Code when working in this repository. Global single-developer
policy applies (`~/.claude/CLAUDE.md`): work on `main`, dirty worktree is normal,
commits are checkpoints.

## What this is

**Arbiter** (formerly Curator) ranks what we've watched. Films, TV, anime, anime
films and documentaries each get their own comparison contest; elicitation is
"order these six, ties allowed"; score is a batch Bradley-Terry / Plackett-Luce MAP
fit over the whole comparison history, refit after every round. The scorer is a
port of a ranking engine measured against a real corpus in another project; only
the domain changed.

**Public repo, plug and play.** The owner's library is gitignored local state:
`data/` (the SQLite library, cache, purge backups, `obsidian-overrides.json`),
`.env` (paths, tokens, keys), `ops/cloudflared-config.yml`,
`ops/windows/watchdog.local.psd1`. With no library DB, reads fall back to a temp
copy of `examples/library.json` and every write refuses until `init`. Never commit
those files or hardcode a machine path, domain, other repo's path or personal title
into tracked code. Settings: `arbiter/config.py` (env `ARBITER_*`, then legacy
`CURATOR_*`, then `.env`, then neutral defaults).

**Anyone can read, only a tailnet peer can change anything.** The public site shows
my real library and rankings read only; every write (and rating itself) needs a
request from `100.64.0.0/10`. See [`access.md`](.claude/docs/access.md).

Live at https://curator.yaqzan.dev, mid-rename: see
[`ops.md`](.claude/docs/ops.md) for the live service and the pending cutover.

## Commands

```powershell
py -3.11 -m arbiter init [--examples]      # create YOUR library; refuses if one exists
py -3.11 -m arbiter serve                  # API + built SPA on :5002, loopback + tailnet IP
$env:ARBITER_OPEN='1'; py -3.11 -m arbiter serve   # dev ONLY: every caller can write
py -3.11 -m arbiter import-plex [--dry-run]
py -3.11 -m arbiter import-obsidian [--path DIR] [--type movie] [--dry-run] [--overrides FILE]
py -3.11 -m arbiter search "the wire" ; py -3.11 -m arbiter add plex://show/<key> --type tv --tier 5
py -3.11 -m arbiter stats ; py -3.11 -m arbiter top anime --limit 20
py -3.11 -m arbiter refit [--type movie]   # after a bulk tier edit
py -3.11 -m arbiter purge-history <item_id> [--apply]   # dry-run default, --apply backs up first
py -3.11 -m pytest tests -q                # no DB or network needed
npm --prefix frontend run build            # tsc --noEmit && vite build -> frontend/dist
npm --prefix frontend run dev              # :5180, proxies /api to :5002
```

## Architecture

```
Plex library DB (watch ledger) ─┐
Obsidian media log (tiers) ─────┤
Plex metadata provider ─────────┼→ catalog.py → items (SQLite)
Plex Discover search ───────────┘                  │
                                                   ├→ ranking.py ─┐
Radarr/Sonarr (optional badge) ────────────────────┘              │
                                                        scorer.py ─┴→ elo_score / elo_sigma
```

| Module | Owns |
|---|---|
| `media_types.py` | **The contest registry.** The only place a type key, label or piece of surface copy is written down. |
| `scorer.py` | Pure maths. The batch fit, the ranking decomposition, set selection, the tier/boundary arithmetic. Knows nothing about media. |
| `ranking.py` | **The one definition** of "read the history and refit everyone", plus recording, undo, correction, purge and the audit pool. |
| `catalog.py` | Adding and refreshing titles, and the rule that an import never overwrites a human judgement. |
| `db.py` | SQLite schema, thread-local connections, the example fallback, `require_own_data`, `init_database`. |
| `example.py` | Seeds a DB from `examples/library.json` (the fallback, and `init --examples`). |
| `config.py` | Every setting and its lookup order. No personal defaults. |
| `auth.py` | The one access question: is the TCP peer in the tailnet block (or is `ARBITER_OPEN` on)? |
| `api.py` | Flask: `/api/*` plus the built SPA on one port. `PUBLIC_ENDPOINTS` guard; `serve()` binds loopback + tailnet. Mutating `/api` calls 409 in example mode. |
| `sources/plex_watch.py` | The watch ledger, read out of Plex's own SQLite. |
| `sources/plex_meta.py` | Metadata resolution, classification and search. |
| `sources/obsidian.py` | An Obsidian media log: the main source of *tiers*. |
| `sources/arr.py` | Optional "on disk" badge from Radarr/Sonarr. Off unless configured; fails soft. |

## Access (don't silently revert)

Full detail: [`access.md`](.claude/docs/access.md).

- **A tailnet peer address is the only credential, judged on the TCP socket and
  never a header.** cloudflared runs on this machine, so tunnel traffic arrives on
  loopback as a stranger; trusting `X-Forwarded-For` would let the internet claim a
  100.x address. Bind loopback + the tailnet IP, never `0.0.0.0`. Don't add a
  shared code or a login.
- **Default-deny**: `PUBLIC_ENDPOINTS` in `api.py` lists the public GETs. Anything
  else, and every POST/PUT/PATCH/DELETE, needs a peer. `/api/search`,
  `/api/import/status` and `/api/rank/set` stay private. Strangers never get `notes`.
- **`ARBITER_OPEN=1` is for development only**, read from the real environment and
  never from `.env`. Never set it in server.ps1: loopback is where the tunnel lands.
- The frontend hides edit controls unless `/api/health` says `authed: true`. No
  lock screen. The server is what enforces it.

## Load-bearing decisions (don't silently revert)

Full detail: [`ranking-scoring-design.md`](.claude/docs/ranking-scoring-design.md).

- **Every media type is a separate contest, every scoring read filters on it** —
  same 800-1200 scale across contests means a missing filter fails *silently*.
  `ranking.record_ranking` rejects a mixed-type round; re-filing a title drops its
  history.
- **Scorer is a batch fit, not online ELO** — for order independence, transitive
  propagation, and a real posterior SD, not accuracy (algorithm choice is within
  0.01 Spearman regardless).
- **A round stores every pair (C(n,2), one `set_id`) but is never scored as
  independent duels** — that inflates one judgement 1.5x-2.7x (n=4..9) and breaks
  `elo_sigma`, which the calibration gate runs on.
- **Ordering six beats picking a winner from two** — Fisher information 3.550 vs
  0.500 at equal scores (7.1x); ties are signal. Grouping applies to the clicks
  made, not the previously placed title.
- **Two ways to place, both must work**: click appends; drag places at a chosen
  position (middle of a row = tie, edge = rank above/below). Drop indicator is
  drawn ON the row, never a list placeholder. Drag is mouse/pen only — touch stays
  on tap-to-place.
- **Submission is an event consequence, never a `useEffect`** — a synchronous
  `submitLock` ref (StrictMode-safe) guards `commit()`; an effect-driven version
  double-recorded every round.
- **`PRIOR_SD = 0.45`** — don't tighten it (detection of a mis-tiered title over 4
  rounds: 19% at 0.30, 51% at 0.45, 53% at 0.60).
- **Three progress signals, don't collapse them**: `covered` (>=4 rounds,
  coverage only), `contested`/`contested_confident` (the actual finding),
  `settled` (never drive a progress bar with this — unreachable for boundary-far
  titles).
- **`scorer.select_set` deliberately crosses tier boundaries** (`boundary_bias`
  0.65, fenced +/-1 tier) — nearest-score sorting alone made 86.8% of matches
  intra-tier. `audit_pool` must pass `priority` or thin-corpus sigma lets
  already-audited titles dominate.
- **Import fills blanks, never overwrites a judgement** — `catalog._REFRESHABLE`
  excludes `tier`/`media_type`/`notes`/`archived`; the one exception is setting a
  NULL tier. Matching: GUID -> external id -> title+year.
- **Writes need a real library** — CLI write commands call `db.require_own_data()`,
  the API's `before_request` 409s mutating calls in example mode. The example DB is
  rebuilt per process in the temp dir and must never receive user rounds.

## Data sources — why these

Full detail: [`data-sources.md`](.claude/docs/data-sources.md).

- **Watch ledger from Plex's SQLite, not HTTP** — `metadata_item_settings` keys on
  the global `plex://` GUID, survives migration. **Copy the WAL** (`-wal`/`-shm`),
  not just `.db` — the main file alone reports 0 rows.
- **Tiers from an Obsidian media log** (`ARBITER_OBSIDIAN_VAULT`), not Plex.
  TV/anime logged per season; `obsidian.series_title` groups them, tier = mean
  rounded up at the half. Title resolved against Discover only on an exact
  unambiguous normalized match (never top-hit) — a wrong match is worse than a gap.
  Unresolvable entries go in `data/obsidian-overrides.json`
  (`ARBITER_OBSIDIAN_OVERRIDES`).
- **Metadata from Plex's metadata provider** — no TMDB key needed. Batch endpoint
  silently caps at 20 (`BATCH_SIZE = 20`, `fetch_many` re-requests gaps).
- **Classification is Animation + Japan**, a heuristic, re-classified from full
  metadata (not the search payload, which carries no `Country`).
- **Radarr/Sonarr are enrichment, never a dependency** — pure config, no default
  URL or key; the owner's run on another machine. Fails soft, cached 60s. Local
  addresses are `127.0.0.1`, never `localhost`.

Ops (live service, tunnel, watchdog, cutover checklist) →
[`ops.md`](.claude/docs/ops.md) · kanban → vault `Engineering Wiki/Projects/Curator/`.
