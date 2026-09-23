"""Arbiter — rank what you've watched.

A comparison-driven rating system for films, TV, anime and documentaries, built
on a batch Bradley-Terry scorer ported from an earlier ranking project. Each media
type is its own contest (see `media_types.py`); the elicitation is "order these
six, ties allowed"; the score is a MAP fit over the whole comparison history,
refit after every round.
"""

__version__ = '1.0.0'
