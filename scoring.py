"""Feature 12 — weighted ignition-risk scoring with honest uncertainty bands.
Unknown items flex the score into a [low, high] band instead of pretending certainty."""

WEIGHTS = {   # relative contribution to structure-ignition pathways (planning weights)
    "roof": 25, "zone0": 16, "fence": 7, "firewood": 5, "vents": 12,
    "windows": 4, "eaves": 6, "gutters": 6, "canopy": 8,
    "deck": 4, "outbuilding": 3, "firewise": 4,
}

def score_band(items):
    total = sum(WEIGHTS[i["key"]] for i in items if i["key"] in WEIGHTS)
    ok_lo = ok_hi = 0
    for it in items:
        w = WEIGHTS.get(it["key"], 0)
        if it["status"] == "pass":
            ok_lo += w; ok_hi += w
        elif it["status"] == "fail":
            pass
        else:                       # unknown → flex band both ways
            ok_hi += w
    total = max(total, 1)
    lo = round(100 * ok_lo / total)
    hi = round(100 * ok_hi / total)
    mid = round((lo + hi) / 2)
    return lo, mid, hi