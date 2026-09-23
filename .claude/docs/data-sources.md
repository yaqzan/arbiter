# Data Sources — why these, and the traps

## Watch ledger: Plex's SQLite, not its HTTP API

`metadata_item_settings` keys by the global `plex://` GUID, not a local library
id, so it survives a library removal or machine migration. Current state:
`/library/sections` -> 0 sections; `metadata_item_settings` -> 631 rows, 630 with
views. Libraries were lost in the 2026-08 migration; history wasn't. First import:
**107 watched films + 523 episodes -> 41 shows = 148 titles** (95 movie / 22 anime
/ 18 tv / 11 anime_movie / 2 documentary).

**Copy the WAL, not just the .db.** The main file reports 0 rows alone — recent
data lives in the 1.4 MB write-ahead log. Copying `.db` alone silently reads an
empty database. `plex_watch._snapshot` copies `-wal` and `-shm` too and opens the
copy read-only. This module never writes to Plex's data.

## Tiers: the Obsidian media log, not Plex

The folder named by `ARBITER_OBSIDIAN_VAULT` — one note per thing consumed
(the owner's was exported from Notion), `Type`/`Status`/`Score /5` in frontmatter. 802
notes, almost all carrying a star rating. Plex's own ratings could seed 6 tiers
across 148 titles; this log seeded 367 across 388 — without it the audit runs on
an unseeded prior. Games/books/audiobooks/manga/decks have no contest and are
skipped (`obsidian.TYPE_MAP` is the whole mapping).

**TV and anime are logged per SEASON; the contest ranks the show.** `obsidian.series_title`
strips a trailing marker (`S04`, `Season 3`, `Final Season Part 2`, `(rewatch)`, a
dangling `-`) and groups notes. Tier = mean of seasons, rounded up at the half (the
best season alone would rank on its peak). Only a *trailing* marker counts, or
titles like `2 Fast 2 Furious` / `Apollo 13` lose their tails. 93 of 460 notes
merge this way. The override lookup runs before grouping, so an override's
`title` is also the grouping key — the only way to know a `Show - Some Arc` note
is a season of `Show`.

**The note has no title field — the filename IS the title**, no year/GUID/external
id. Resolved against Discover by name; a match is accepted only on an exact
normalized title exactly one film answers to — never on Discover's ranking (for
titles shared by several films the top hit is often an obscure namesake). A
wrong match is worse than a gap: a real star rating gets filed against the wrong
title with nothing downstream able to tell. Taking the top hit would have
mis-filed ~10 of 75.

Narrowing, in order: a `(1982)` the user put in the note's own name (must be
stripped before searching — Discover ranks the parenthesised form below a newer
film of the same name); the watched year (a release after the watch is
impossible); `catalog._distinct_films` (Discover's index carries
duplicate/year-less shadow records that read as ambiguity but aren't).

**What still won't resolve goes in `data/obsidian-overrides.json` (gitignored,
`ARBITER_OBSIDIAN_OVERRIDES`), not the heuristic.** 153 of 460 needed a human:
typos in note names, export damage (a leftover `Media - ` prefix, a dangling
`S05 -`), Plex spelling a title differently (digits for letters, `x` for `and`,
run-together words), Plex putting the year inside the title (`Title (2021)`), and
real ambiguity (a remake watched in the remake's year). `query` may search under
one name and match another — the only way to reach a film Discover indexes under
its original-language title only.

`manual` builds a row with no Plex record behind it, not a workaround — Discover's
index genuinely lacks some well-known films. Such a row has no poster/external
ids, so `find_existing` matches on title+year only — keep the year right or the
next import files a duplicate.

The vault's own bucket wins over Plex's classifier (vault files anime films and
documentaries separately; disagreements print, not obey — re-file from the
library page). `_EXPECTED_KIND` fences a Film note off a series and vice versa,
but lists no kind for documentaries (a nature series and a feature documentary
are both valid answers there).

## Metadata: Plex's metadata provider, no TMDB key needed

`metadata.provider.plex.tv/library/metadata/<ratingKey>` resolves a `plex://` GUID
to full metadata and external ids (imdb/tmdb/tvdb) without a lookup table.

**The comma-batch endpoint caps at 20 results, silently.** Asking for 40 returns
20 with a 200 and no marker. Silently dropped 60 of 140 titles and ~260 of 523
episodes on first import. `BATCH_SIZE = 20`, and `fetch_many` re-requests any gap
individually so a future cap change degrades to slow, not lossy.

## Classification: Animation + Japan, a heuristic

Plex has no native "Anime" genre on most records; anime = Animation + Japanese
origin country. Re-filable from the library page; a re-import never recomputes it.

**Search results carry no `Country` — re-classify from full metadata, not the
search payload.** A Studio Ghibli film returns from Discover as plain `movie`; full
record is `Genre=[Animation,...,Anime]`, `Country=[Japan]` -> `anime_movie`. The
frontend sends the previewed contest back, so a wrong preview files it wrong.
`_reclassify_from_full_metadata` costs one extra batched request per search, fails
soft.

## Radarr/Sonarr: enrichment, never a dependency

Pure config: `ARBITER_RADARR_URL`/`_KEY`, `ARBITER_SONARR_URL`/`_KEY` (or an
`ARBITER_ARR_SECRETS` JSON file). No default URL or key: the owner's *arrs run on
a different machine, so a localhost default would only ever probe a dead port.
Unconfigured = reported down with no probe (`arr.available`). When configured
they are still often unreachable. `arr.available()` is
cached 60s, probes both halves in parallel at a 1.5s timeout;
`ownership_index()` skips the full fetch when nothing is listening. Use
`127.0.0.1`, never `localhost` (global rule) — measured here at 3.0s/dead-service
via `localhost` vs 1.5s via `127.0.0.1`; `/api/import/status` took 8.2s before this
fix.
