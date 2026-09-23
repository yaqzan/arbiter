# Arbiter

I built Arbiter to rank everything I've watched. Films, TV, anime, anime films and
documentaries each get their own contest. It shows me six titles at a time, I put
them in order (ties allowed), and a Bradley-Terry fit turns all those orderings into
a score for every title.

It runs on your machine with your own library. A fresh clone comes with a small
example library so you can click around before you plug in yours.

## Why I compare titles

Star ratings drift. Give three films an 8 over three years and you stop knowing
which one you liked most. Putting a handful in order is easy, so that's the only
question Arbiter asks, and it works the scores out from the answers.

Ordering six titles carries about **7 times the information** of picking a winner
from two (Fisher information 3.55 against 0.50). In practice that's around 110
rounds to reach the accuracy that head-to-head duels need 700 for.

Ties count. "These three are the same to me" is a real answer and the fit uses it.

## Quick start

You need Python 3.11+ and Node 18+.

```powershell
git clone https://github.com/yaqzan/arbiter
cd arbiter
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build

python -m arbiter serve          # http://127.0.0.1:5002
```

Open http://127.0.0.1:5002 and you'll see the example library: 28 well-known
titles and a few rounds already ranked. It's read only.

Anyone can look at Arbiter, but only a device on your Tailscale network can change
anything (see [Who can change things](#who-can-change-things)). On a machine
without Tailscale, start it like this to rank and edit locally:

```powershell
$env:ARBITER_OPEN = '1'; python -m arbiter serve    # PowerShell
ARBITER_OPEN=1 python -m arbiter serve              # bash
```

With that on, recording a round tells you to create your own library first.

## Plug in your own library

Create your library. This makes `data/arbiter.db`, which is yours and never gets
committed:

```powershell
python -m arbiter init                # start empty
python -m arbiter init --examples     # or start with the example titles in it
```

Restart `serve` after `init`. Then fill it from any mix of the three sources
below. Every import can be re-run safely: it fills in what's missing and never
overwrites a tier, a contest or a note you set yourself.

### 1. Plex

If you watch through Plex, this is the quickest way in:

```powershell
python -m arbiter import-plex --dry-run    # see what it would add
python -m arbiter import-plex
```

It reads the watch history straight out of Plex Media Server's own database, so it
works even if a library was deleted or you moved machines. Watched episodes roll
up into their show. Titles, posters and ids come from Plex's metadata service, so
there's no TMDB key to set up.

What it needs:

- **The Plex database.** Arbiter looks where Plex keeps it by default on Windows,
  macOS and Linux. If yours is elsewhere, set `ARBITER_PLEX_DB`.
- **A Plex token.** On Windows it's read from the registry once you're signed in
  to Plex Media Server. Anywhere else, set `ARBITER_PLEX_TOKEN`.

The Add page in the app can also run the import and shows whether it found both.

### 2. Obsidian (or any folder of notes)

I keep a media log in Obsidian with one note per thing I've watched and a star
rating in the frontmatter. Those star ratings become Arbiter's starting tiers,
which makes the early rounds much sharper. The importer expects notes like this,
where the file name is the title:

```yaml
---
Type: "Film"            # Film, TV, Anime, Anime Movie or Documentary
Status: "Finished"      # anything else is skipped
Score /5: "⭐️⭐️⭐️⭐️"   # the number of stars becomes the tier
Finished: 2025-03-29    # optional, helps tell remakes apart
---
```

Point Arbiter at the folder and try it:

```powershell
python -m arbiter import-obsidian --path "D:\Notes\Media" --dry-run
python -m arbiter import-obsidian --path "D:\Notes\Media"
```

Or set `ARBITER_OBSIDIAN_VAULT` in `.env` and leave off `--path`. Each note is
matched against Plex's catalog by title, and it only goes in when exactly one title
matches. When a note can't be pinned down, the dry run lists what Plex offered, and
you write the answer into `data/obsidian-overrides.json`:

```json
{
  "Solaris": {"year": 1972},
  "The Seventh Seal": {"query": "Det sjunde inseglet", "title": "The Seventh Seal", "year": 1957},
  "Some Short Film": {"manual": true, "year": 2019}
}
```

`examples/obsidian-overrides.example.json` shows every key the file understands.
TV and anime notes logged per season (`Show S01`, `Show S02`) are grouped into one
show, and its tier is the average of the seasons.

### 3. Add titles by hand

Anything you watched somewhere else goes in from the **Add** page: search, pick the
right one, optionally give it a tier. The same thing from the command line:

```powershell
python -m arbiter search "the wire"
python -m arbiter add plex://show/<rating-key> --type tv --tier 5
```

Search uses Plex's catalog too, so it needs the Plex token. You don't need to have
the title in a Plex library.

## Settings

Everything machine-specific is a setting. Copy `.env.example` to `.env` (it's
gitignored) and fill in what applies to you, or set the same names as environment
variables. With nothing set, Arbiter runs on 127.0.0.1:5002 with its data in
`data/` and every optional source switched off.

| Setting | What it does |
|---|---|
| `ARBITER_HOST`, `ARBITER_PORT` | Where the server listens (127.0.0.1:5002) |
| `ARBITER_DATA_DIR`, `ARBITER_DB` | Where your library lives (`data/arbiter.db`) |
| `ARBITER_PLEX_DB`, `ARBITER_PLEX_TOKEN` | Plex database and token, when the defaults don't find them |
| `ARBITER_OBSIDIAN_VAULT` | Your media notes folder |
| `ARBITER_OBSIDIAN_OVERRIDES` | Your hand-resolved titles (`data/obsidian-overrides.json`) |
| `ARBITER_RADARR_URL`, `ARBITER_RADARR_KEY`, `ARBITER_SONARR_URL`, `ARBITER_SONARR_KEY` | Optional "on disk" badge |
| `ARBITER_PUBLIC_ORIGIN` | Your public address, if you publish it |
| `ARBITER_TRUST_TAILNET` | `1` (default) lets Tailscale peers make changes; `0` makes everything read only |
| `ARBITER_OPEN` | `1` lets every caller make changes. For local development only, and only read from the real environment, never `.env` |

Radarr and Sonarr are optional. With them set, library cards get an "on disk"
badge. They don't have to run on the same computer as Arbiter: I keep mine on a
different machine and point the URLs at it. If they're unset or unreachable,
nothing else changes.

## Using it

| Page | What it's for |
|---|---|
| **Rank** | Order six. Click to place, `Shift`/`Ctrl`+click to tie, drag to put a card exactly where you want it, `⌫` takes one back, `S` skips, `Z` undoes the round. It submits when the last card lands. |
| **Leaderboard** | Standings for one contest, with each score's uncertainty and round count. |
| **Review** | Titles whose score has moved out of the tier you gave them. Worth a look; nothing changes on its own. |
| **History** | Every round, in the order you gave it. Fix a mis-click here and the scores update. |
| **Library** | Browse, filter, set tiers, move a title to another contest, archive. |
| **Add** | Import from Plex, or search for anything else. |

The 1 to 5 **tier** is your starting guess and seeds the fit. Leaving it blank is
fine: the title starts in the middle and the rounds decide where it ends up.

Other commands:

```powershell
python -m arbiter stats                       # progress per contest
python -m arbiter top anime --limit 20        # a leaderboard in the terminal
python -m arbiter refit                       # recompute every score
python -m arbiter purge-history <id>          # dry run; add --apply to wipe one title's rounds
```

## Who can change things

I publish my Arbiter so people can see what I've ranked. For a long time anyone who
found it could also rank, re-tier and delete. Now the rule is simple:

> A request from my Tailscale network (100.64.0.0/10) is me. Everyone else can look.

| Anyone can see | Only a Tailscale peer can |
|---|---|
| the leaderboards, library, review queue and round history | rank, re-tier, move, archive, delete, fix a round |
| each title's scores, rounds and comparison history | add titles, search Plex, run an import, see import status |

- **The check is the network address the connection came from.** Headers like
  `X-Forwarded-For` are ignored, because anyone can type them. A Cloudflare tunnel
  running on the same machine connects over 127.0.0.1, so everything that comes
  through the public address is a visitor.
- **`serve` listens on 127.0.0.1 and on the machine's Tailscale address**, and it
  prints the address to use for changes, e.g. `http://mybox.tail1234.ts.net:5002`.
  It never listens on every interface, so nothing on your LAN can connect. Opening
  the public hostname from a phone on your tailnet still counts as a visitor,
  because that traffic goes through Cloudflare.
- **The page adapts.** A visitor gets no Rank or Add page and no edit buttons.
  There's no login screen.
- **No Tailscale on the machine?** Then nobody can change anything through the site,
  you included. Use `ARBITER_OPEN=1` for local work, and never set it on a server
  with a public tunnel: that tunnel arrives on 127.0.0.1 too.
- **Any API route is private until it's added to the public list** in
  `arbiter/api.py`, and every write needs a Tailscale peer whatever the route.

## Your data

Everything personal stays out of git:

- `data/`: your library (`arbiter.db`, a single SQLite file you can back up by
  copying), the metadata cache, purge backups and your Obsidian overrides
- `.env`: your paths, tokens and keys
- `ops/cloudflared-config.yml`: your tunnel, if you have one

Until `data/arbiter.db` exists, reads come from `examples/library.json` and writes
are refused.

## Running it all the time (Windows, optional)

```powershell
ops\windows\install-tasks.ps1
```

That registers an "Arbiter Watchdog" task that checks every 5 minutes and starts
the server if it's down. If you run a Cloudflare tunnel, copy
`ops/cloudflared-config.example.yml` to `ops/cloudflared-config.yml`, fill in your
tunnel, and the watchdog looks after that too. The public hostname is read only;
make your changes at the Tailscale address `serve` prints.

## Layout

```
arbiter/            the backend (Flask + SQLite)
  media_types.py      the contests and their wording
  scorer.py           the Bradley-Terry / Plackett-Luce fit
  ranking.py          history, refit, undo, purge, choosing the next six
  catalog.py          adding titles; imports never overwrite your choices
  sources/            Plex watch history, Plex metadata and search, Obsidian, Radarr/Sonarr
frontend/           Vite + React + TypeScript
examples/           the example library and an example overrides file
ops/                tunnel example and the Windows watchdog
tests/              pytest, no database or network needed
```

Tests: `python -m pytest tests -q`.

## License

MIT. See `LICENSE`.
