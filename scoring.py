from __future__ import annotations

"""
Feature 12 — weighted ignition-risk scoring with honest uncertainty bands.
Unknown items flex the score into a [low, high] band instead of pretending certainty.
"""

from typing import Dict, Iterable, Tuple


# Relative contribution to structure-ignition pathways (planning weights).
WEIGHTS: Dict[str, int] = {
    "roof": 25,
    "zone0": 16,
    "fence": 7,
    "firewood": 5,
    "vents": 12,
    "windows": 4,
    "eaves": 6,
    "gutters": 6,
    "canopy": 8,
    "deck": 4,
    "outbuilding": 3,
    "firewise": 4,
}


def score_band(items: Iterable[Dict[str, object]]) -> Tuple[int, int, int]:
    """
    Compute a [low, mid, high] hardening score band given framework items.

    Each item dict must at least contain:
        - "key": framework key (matches WEIGHTS keys)
        - "status": "pass" | "fail" | "unknown"

    Returns:
        (lo, mid, hi): integers in [0, 100].
    """
    total = sum(WEIGHTS[i["key"]] for i in items if i.get("key") in WEIGHTS)

    ok_lo = 0
    ok_hi = 0

    for it in items:
        key = str(it.get("key", ""))
        status = str(it.get("status", "")).lower()
        w = WEIGHTS.get(key, 0)

        if status == "pass":
            ok_lo += w
            ok_hi += w
        elif status == "fail":
            # explicit failure: weight contributes nothing
            continue
        else:
            # unknown → flex band both ways
            ok_hi += w

    total = max(total, 1)
    lo = round(100 * ok_lo / total)
    hi = round(100 * ok_hi / total)
    mid = round((lo + hi) / 2)

    return lo, mid, hi