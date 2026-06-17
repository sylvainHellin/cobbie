"""Fixed stratified dev-mini / dev-midi subsets of TESTSET for fast dev iterations.

dev-mini is a named, deterministic subset of the held-out TESTSET stratified by
category only (the 4 IFC-Bench categories). It is byte-stable across runs: the
selection is a pure function of question ids, so no RNG state can drift it. The
factorial runner selects it via ``--question-set dev-mini``; ``--limit`` and
``--question-ids`` are escape hatches over whichever set is chosen.

dev-midi is a larger sibling (~40 questions, ~10 per category) built by the same
round-robin draw. Because both subsets take a per-category prefix sorted by id
from the identical draw order, dev-midi is a strict superset of dev-mini: every
dev-mini id reappears in dev-midi. Cells already run over dev-mini therefore
reuse those result rows on resume instead of recomputing them.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List

from src.db.models import IfcBench

# Target subset size. Spread as evenly as possible across the 4 categories via a
# round-robin draw, so a typical run gets ~2-3 questions per category.
DEV_MINI_SIZE = 10

# dev-midi target size. Same round-robin draw, four strata, ~10 per category.
DEV_MIDI_SIZE = 40


def dev_mini_subset(testset: List[IfcBench], size: int = DEV_MINI_SIZE) -> List[IfcBench]:
    """Return a fixed stratified subset of *testset*, stratified by category.

    Deterministic by construction: questions are grouped by category, each
    group is sorted by id, then we draw round-robin across the categories
    (lowest category number first) taking the next-smallest id from each until
    *size* questions are collected. No random seed is involved, so the subset
    never changes between runs for a fixed *testset*.

    The returned list is sorted by question id.
    """
    by_category: dict[int, List[IfcBench]] = defaultdict(list)
    for q in testset:
        # Category 0/None should not occur (CHECK 1..4) but guard anyway.
        if q.category is None:
            continue
        by_category[q.category].append(q)

    for cat in by_category:
        by_category[cat].sort(key=lambda q: q.id)

    categories = sorted(by_category)
    cursors = {cat: 0 for cat in categories}

    picked: List[IfcBench] = []
    while len(picked) < size:
        progressed = False
        for cat in categories:
            if len(picked) >= size:
                break
            idx = cursors[cat]
            if idx < len(by_category[cat]):
                picked.append(by_category[cat][idx])
                cursors[cat] += 1
                progressed = True
        if not progressed:
            # Exhausted every category before reaching size.
            break

    picked.sort(key=lambda q: q.id)
    return picked


def dev_midi_subset(testset: List[IfcBench], size: int = DEV_MIDI_SIZE) -> List[IfcBench]:
    """Return the dev-midi subset: same draw as dev-mini, larger *size*.

    Shares ``dev_mini_subset``'s deterministic round-robin draw, so for a fixed
    *testset* the result is byte-stable across runs and is a strict superset of
    ``dev_mini_subset(testset)``: a larger size only extends each category's
    prefix, never reorders or drops the smaller subset's ids.

    The returned list is sorted by question id.
    """
    return dev_mini_subset(testset, size=size)


__all__ = ["dev_mini_subset", "dev_midi_subset", "DEV_MINI_SIZE", "DEV_MIDI_SIZE"]
