"""The Obsidian media log: parsing it, and resolving its titles against Plex.

The thing being defended here is that **a note only ever becomes a catalog row
when the film is actually pinned down**. A vault note carries a real star rating,
so a wrong match does not just add a wrong title — it files a human judgement
against it, and nothing downstream can tell that the judgement is about a
different film.
"""

from arbiter import catalog
from arbiter.sources import obsidian


def write_note(folder, name, **fields):
    lines = ['---'] + [f'{k.replace("_", " ")}: "{v}"' for k, v in fields.items()] + ['---']
    (folder / f'{name}.md').write_text('\n'.join(lines), encoding='utf-8')


def hit(title, year, kind='movie'):
    return {'title': title, 'year': year, 'type': kind,
            'guid': f'plex://movie/{title}-{year}', 'rating_key': str(year)}


# ── reading the vault ────────────────────────────────────────────────────────

def test_stars_become_tiers():
    # The exporter writes each star with a U+FE0F variation selector after it,
    # so the string is twice as long as it looks.
    assert obsidian.tier_from_stars('⭐️⭐️⭐️⭐️') == 4
    assert obsidian.tier_from_stars('⭐️') == 1
    assert obsidian.tier_from_stars('') is None


def test_only_watchable_types_and_finished_entries_are_imported(tmp_path):
    write_note(tmp_path, 'Rashomon', Type='Film', Status='Finished')
    write_note(tmp_path, 'Tetris', Type='Xbox Series X', Status='Finished')
    write_note(tmp_path, 'Middlemarch', Type='Book', Status='Finished')
    write_note(tmp_path, 'Half Watched', Type='Film', Status='Watching')

    entries, report = obsidian.read_vault(tmp_path)

    assert [e['title'] for e in entries] == ['Rashomon']
    assert report['unmapped_type'] == 2      # the game and the book
    assert report['wrong_status'] == 1


def test_a_year_in_the_note_name_is_an_assertion_not_part_of_the_title(tmp_path):
    # `Solaris (1972)` must be SEARCHED as "Solaris" — Discover ranks the
    # parenthesised form below a newer film of that name — then pinned to 1972.
    write_note(tmp_path, 'Solaris (1972)', Type='Film', Status='Finished')
    entries, _ = obsidian.read_vault(tmp_path)
    assert entries[0]['title'] == 'Solaris'
    assert entries[0]['asserted_year'] == 1972


def test_the_epoch_dates_an_entry_that_has_no_watch_dates(tmp_path):
    write_note(tmp_path, 'Ikiru', Type='Film', Status='Finished', Epoch='Summer 2019')
    entries, _ = obsidian.read_vault(tmp_path)
    assert entries[0]['watch_year'] == 2019


def test_normalize_folds_the_punctuation_the_export_mangled():
    # The Notion export dropped colons and swapped hyphens for en-dashes.
    assert (obsidian.normalize_title('Dr Strangelove – Or How I Learned to Stop Worrying')
            == obsidian.normalize_title('Dr. Strangelove: Or How I Learned to Stop Worrying'))
    assert obsidian.normalize_title('La Strada') == obsidian.normalize_title('La strada')


# ── seasons collapse into one series ─────────────────────────────────────────

def test_season_notes_become_one_entry_scored_by_their_mean(tmp_path):
    """The TV contest judges "the show as a whole, not one season", so six
    `Fawlty Towers S0n` notes are six ratings of ONE thing to rank. The mean is
    used rather than the best season, which would rank a show on its peak."""
    for season, stars in (('S01', 3), ('S02', 4), ('S03', 5)):
        write_note(tmp_path, f'Fawlty Towers {season}', Type='TV', Status='Finished',
                   Epoch='Fall 2020', **{'Score /5': '⭐️' * stars})
    write_note(tmp_path, 'Fawlty Towers S01 (rewatch)', Type='TV', Status='Finished',
               Epoch='Fall 2021', **{'Score /5': '⭐️⭐️⭐️⭐️'})

    entries, report = obsidian.read_vault(tmp_path)

    assert len(entries) == 1
    assert entries[0]['title'] == 'Fawlty Towers'
    assert entries[0]['tier'] == 4          # (3+4+5+4)/4 = 4.0
    assert entries[0]['watch_year'] == 2021  # the latest watch of any season
    assert report['merged'] == 3


def test_a_number_in_a_title_is_not_a_season_marker():
    # Only a trailing marker counts, or `2 Fast 2 Furious` and `Apollo 13`
    # would both lose their tails.
    assert obsidian.series_title('2 Fast 2 Furious') == '2 Fast 2 Furious'
    assert obsidian.series_title('Apollo 13') == 'Apollo 13'
    assert (obsidian.series_title('Legend of the Galactic Heroes The Final Season Part 3')
            == 'Legend of the Galactic Heroes')
    assert obsidian.series_title('The Wire S05 -') == 'The Wire'


def test_films_are_never_collapsed_into_each_other(tmp_path):
    # Three films of one arc, not three seasons of one show.
    for numeral in ('I - Blue', 'II - White', 'III - Red'):
        write_note(tmp_path, f'Three Colours {numeral}',
                   Type='Anime Movie', Status='Finished', **{'Score /5': '⭐️⭐️⭐️⭐️'})
    entries, _ = obsidian.read_vault(tmp_path)
    assert len(entries) == 3


def test_an_override_title_is_what_the_grouping_keys_on(tmp_path):
    """`Rurouni Kenshin - Kyoto Arc` is a season of the series, and no
    rule can know that — but the override that names the series must then fold
    the two notes together rather than filing the arc as a second anime."""
    write_note(tmp_path, 'Rurouni Kenshin', Type='Anime', Status='Finished',
               **{'Score /5': '⭐️⭐️⭐️'})
    write_note(tmp_path, 'Rurouni Kenshin - Kyoto Arc', Type='Anime',
               Status='Finished', **{'Score /5': '⭐️⭐️⭐️⭐️⭐️'})

    entries, _ = obsidian.read_vault(tmp_path, overrides={
        'Rurouni Kenshin': {'title': 'Rurouni Kenshin: Meiji Swordsman', 'year': 1996},
        'Rurouni Kenshin - Kyoto Arc': {'title': 'Rurouni Kenshin: Meiji Swordsman',
                                        'year': 1996},
    })

    assert len(entries) == 1
    assert entries[0]['title'] == 'Rurouni Kenshin: Meiji Swordsman'
    assert entries[0]['tier'] == 4          # (3+5)/2


def test_a_manual_override_builds_a_row_with_no_plex_record_behind_it(temp_db):
    """Some films are missing from Discover's index; no query reaches them. A watched,
    rated film belongs in its contest whether or not a provider agrees it
    exists — and title+year is all such a row has to match on next time."""
    result = catalog.import_obsidian([{
        'title': 'Some Short Film', 'note': 'Some Short Film', 'match': 'Some Short Film',
        'query': 'Some Short Film', 'notes': ['Some Short Film'],
        'manual': True, 'guid': None, 'asserted_year': 2013, 'media_type': 'movie',
        'tier': 3, 'watch_year': 2024, 'watched_at': None, 'epoch': 'Winter 2024',
    }])

    assert result['created'] == 1 and result['manual'] == ['Some Short Film (2013)']
    row = temp_db.one('SELECT * FROM items WHERE title = ?', ('Some Short Film',))
    assert (row['year'], row['tier'], row['watched']) == (2013, 3, 1)
    assert row['plex_guid'] is None


def test_an_override_can_move_a_note_to_the_contest_it_belongs_in(tmp_path):
    write_note(tmp_path, 'The Prisoner', Type='Film', Status='Finished',
               **{'Score /5': '⭐️⭐️⭐️⭐️'})
    entries, _ = obsidian.read_vault(tmp_path, overrides={
        'The Prisoner': {'type': 'tv'}})
    assert entries[0]['media_type'] == 'tv'


# ── resolving a title against Plex ───────────────────────────────────────────

def entry(title, **kwargs):
    base = {'title': title, 'note': title, 'query': title, 'match': title,
            'media_type': 'movie', 'tier': 4, 'asserted_year': None,
            'watch_year': None, 'guid': None}
    base.update(kwargs)
    return base


def test_one_film_of_that_name_resolves():
    found, why, _ = catalog.resolve_obsidian_entry(
        entry('Rashomon'), search=lambda q, limit: [hit('Rashomon', 1950)])
    assert found['year'] == 1950 and why == 'matched'


def test_two_films_of_that_name_resolve_to_NOTHING():
    """The whole point. `Solaris` names two films; Discover's top hit need not
    be the one you saw, and a plausible wrong answer here is worse than none."""
    found, why, candidates = catalog.resolve_obsidian_entry(
        entry('Solaris'), search=lambda q, limit: [hit('Solaris', 2002), hit('Solaris', 1972)])
    assert found is None and why == 'ambiguous'
    assert len(candidates) == 2          # both handed back for a human


def test_a_duplicate_record_is_not_an_ambiguity():
    # Discover's index carries the same film twice, and a year-less shadow of
    # half of everything. Neither is a second film.
    found, why, _ = catalog.resolve_obsidian_entry(
        entry('The Third Man'),
        search=lambda q, limit: [hit('The Third Man', 1949), hit('The Third Man', 1949),
                                 hit('The Third Man', None)])
    assert found['year'] == 1949 and why == 'matched'


def test_the_watch_date_fences_out_a_release_that_did_not_exist_yet():
    found, why, _ = catalog.resolve_obsidian_entry(
        entry('Suspiria', watch_year=1990),
        search=lambda q, limit: [hit('Suspiria', 2018), hit('Suspiria', 1977)])
    assert found['year'] == 1977 and why == 'matched'


def test_an_asserted_year_settles_it_outright():
    found, why, _ = catalog.resolve_obsidian_entry(
        entry('The Thing', asserted_year=1982, watch_year=2024),
        search=lambda q, limit: [hit('The Thing', 2011), hit('The Thing', 1982)])
    assert found['year'] == 1982 and why == 'matched-year'


def test_a_series_is_never_accepted_for_a_film_note():
    found, why, _ = catalog.resolve_obsidian_entry(
        entry('The Prisoner'),
        search=lambda q, limit: [hit('The Prisoner', 2017, 'show')])
    assert found is None and why == 'wrong-kind'


def test_an_override_can_search_under_one_name_and_match_another():
    # Discover can find a film only under its original title and still return
    # the English one.
    found, why, _ = catalog.resolve_obsidian_entry(
        entry('The Seventh Seal', query='Det sjunde inseglet', match='The Seventh Seal',
              asserted_year=1957),
        search=lambda q, limit: ([hit('The Seventh Seal', 1957)]
                                 if q == 'Det sjunde inseglet' else []))
    assert found['year'] == 1957 and why == 'matched-year'


# ── what an import is allowed to change ──────────────────────────────────────

def test_a_star_rating_fills_a_blank_tier_but_never_replaces_a_filed_one(temp_db):
    """`_REFRESHABLE` keeps `tier` out of an import's reach; the one exception is
    a tier that is NULL, which is a gap rather than a judgement. This is what
    lets a vault full of ratings seed a catalog that had almost no tiers filed."""
    blank, _ = catalog.upsert({'title': 'Rashomon', 'year': 1950, 'media_type': 'movie',
                               'tmdb_id': '1064213'})
    filed, _ = catalog.upsert({'title': 'Rear Window', 'year': 1954, 'media_type': 'movie',
                               'tmdb_id': '77', 'tier': 2})

    catalog.upsert({'title': 'Rashomon', 'year': 1950, 'media_type': 'movie',
                    'tmdb_id': '1064213', 'tier': 5}, source='obsidian')
    catalog.upsert({'title': 'Rear Window', 'year': 1954, 'media_type': 'movie',
                    'tmdb_id': '77', 'tier': 5}, source='obsidian')

    assert temp_db.one('SELECT tier FROM items WHERE id = ?', (blank,))['tier'] == 5
    assert temp_db.one('SELECT tier FROM items WHERE id = ?', (filed,))['tier'] == 2


def test_a_vault_entry_updates_the_plex_row_rather_than_duplicating_it(temp_db):
    """Both sources describe the same film. Two rows would split its comparison
    history in half — `find_existing` matching on the external id prevents it."""
    plex_row, _ = catalog.upsert({'title': 'Rashomon', 'year': 1950, 'media_type': 'movie',
                                  'tmdb_id': '1064213'}, source='plex-watch')
    same, action = catalog.upsert({'title': 'Rashomon', 'year': 1950, 'media_type': 'movie',
                                   'tmdb_id': '1064213', 'tier': 5}, source='obsidian')
    assert (same, action) == (plex_row, 'updated')
    assert temp_db.one('SELECT COUNT(*) n FROM items')['n'] == 1
