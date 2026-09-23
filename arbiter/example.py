"""Seed the active database from `examples/library.json`.

Used two ways: `db` calls `seed()` to build the throwaway read-only example a
fresh clone serves before `init`, and `init --examples` calls it to start YOUR
library from the example titles instead of from nothing.
"""

from __future__ import annotations

import json

from . import catalog, config, db, media_types, ranking


def load(path=None):
    return json.loads((path or config.EXAMPLE_LIBRARY).read_text(encoding='utf-8'))


def seed(path=None):
    """Insert the example titles and rounds into whatever `db.connect()` opens."""
    db.ensure_schema()
    library = load(path)
    ids = {}
    for entry in library.get('items', []):
        fields = dict(entry)
        fields['media_type'] = media_types.get(fields.get('media_type')).key
        if isinstance(fields.get('genres'), list):
            fields['genres'] = json.dumps(fields['genres'])
        item_id, _ = catalog.upsert(fields, source='example')
        ids[(fields['media_type'], fields['title'].lower())] = item_id
    for round_ in library.get('rounds', []):
        media_type = media_types.get(round_.get('media_type')).key
        tiers = [[ids[(media_type, title.lower())] for title in group]
                 for group in round_.get('order', [])]
        ranking.record_ranking(media_type, tiers)
    ranking.refit_everything()
    return len(ids)
