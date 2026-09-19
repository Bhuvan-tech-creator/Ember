"""Framework grading (unchanged semantics) + weighted score & uncertainty band."""
from scoring import score_band, WEIGHTS

CLASSES = [
    "wood_roof", "tile_roof", "vent_open", "vent_screened",
    "wood_fence_attached", "vegetation_at_wall",
    "open_rafter_eaves", "soffited_eaves", "gutter_debris",
    "tree_over_roof", "storage_under_deck", "outbuilding_near",
    "firewood_propane_near", "ladder_fuels",
]

MANUAL_ITEMS = {
    "windows": "Multi-pane / tempered windows? (hard to verify from video)",
    "firewise": "Firewise USA / Fire Risk Reduction community membership?",
}

def _ai(presence, fail_key, pass_key=None):
    if fail_key and presence.get(fail_key):
        return "fail", f"AI flagged '{fail_key}' in the footage."
    if pass_key and presence.get(pass_key):
        return "pass", f"AI confirmed '{pass_key}' in the footage."
    return "unknown", "Not visible enough in the frames — verify on site."

def _manual(val):
    if val == "Yes / pass":
        return "pass"
    if val == "No / fail":
        return "fail"
    return "unknown"

PLAIN = {
    "roof": ("Roof material",
             "Your roof covering resists embers — a landing ember dies there instead of "
             "igniting the house. It's the single most valuable structural protection.",
             "The footage shows an easily-ignitable roof covering. Ember rain can last for "
             "hours before flames arrive; a Class-A roof replacement is the most expensive "
             "fix here, and the most decisive.", 3),
    "zone0": ("The critical first 5 feet (Zone 0)",
              "Nothing combustible touches the walls — embers pile into wall corners like "
              "snowdrifts and simply smolder out.",
              "Vegetation or wood-mulch sits against the house; embers accumulate exactly "
              "there and smolder for hours. Rake-back to gravel is one weekend and the "
              "highest-return fix on this list.", 1),
    "fence": ("Fencing attached to the house",
              "No wood fence runs into the structure, so a burning fence can't act as a "
              "fuse into the wall.",
              "A wood fence physically touches the house — a classic fuse. Replace the last "
              "5 ft with metal panel or a metal gate; small cost, big payoff.", 1),
    "firewood": ("Firewood / propane near walls",
                 "No fuel cylinders or firewood are stacked against the home.",
                 "Combustible fuel was spotted within arm's reach of the wall. Move firewood "
                 "30+ ft away and park grill propane in the open — fuel against siding is a "
                 "pre-staged ignition point.", 1),
    "vents": ("Attic & crawl-space vent screens",
              "Vents are screened with fine mesh; embers can't slip into the attic — the "
              "invisible pathway that burns homes from the inside out.",
              "Vents appear open or coarse-mesh. Embers pass a 1/4-inch gap like dust "
              "through a sieve. Ember-rated covers (~$40 each) install in an afternoon.", 1),
    "windows": ("Window glazing",
                "Multi-pane tempered glazing holds far longer under radiant heat, keeping "
                "the building sealed.",
                "Single-pane glass can shatter from radiant heat alone, opening a doorway "
                "for embers. Budget-dependent but essential in a serious plan.", 3),
    "eaves": ("Eaves & roofline overhang",
              "Eaves are enclosed/soffited — no rafter-tail shelves where wind piles embers.",
              "Open rafter tails are visible: natural ember pockets against bare wood. "
              "Boxed soffits close the shelf.", 2),
    "gutters": ("Gutter cleanliness",
                "Gutters appear clear; nothing smolders inches below your roof edge.",
                "Leaf/needle debris is visible in the gutters — a landing platform directly "
                "under the roof. Clean before fire season; consider mesh guards.", 1),
    "canopy": ("Defensible space — canopy & ladder fuels",
               "No overhanging branches and no 'ladder' of shrubs under trees; fire can't "
               "climb or drop onto the structure.",
               "Branches reach over the roof or shrubs ladder up into tree crowns, giving "
               "fire a route to jump upward and drop onto the house. Trim canopy to 10 ft "
               "from the structure.", 2),
    "deck": ("Under-deck storage",
             "No combustible storage hides under built spaces — decks funnel embers into "
             "unseen pockets against the house.",
             "Storage sits beneath deck/stair space: the trapped-ember magnet firefighters "
             "warn about. Clear it; then enclose with 1/8-inch mesh.", 2),
    "outbuilding": ("Detached structures (30-ft buffer)",
                    "No shed stands close enough to burn long enough against your siding.",
                    "A shed/outbuilding stands within ~30 ft — it burns hard and radiates "
                    "against your wall. Relocate, harden, or buffer it.", 3),
    "firewise": ("Community-level program",
                 "The community participates in a recognized risk-reduction program — "
                 "neighbors lowering each other's risk.",
                 "Nearby lots are part of your risk. Firewise participation is free and "
                 "unlocks insurer recognizance.", 3),
}

def evaluate(presence: dict, manual: dict) -> dict:
    items = []
    def add(key, title, status, evidence, fix):
        pt, pp, pf, prio = PLAIN[key]
        items.append({"key": key, "title": title, "status": status,
                      "evidence": evidence, "priority": prio, "plain_title": pt,
                      "plain": pp if status == "pass" else pf, "fix": fix,
                      "weight": WEIGHTS.get(key, 0)})

    s, ev = _ai(presence, "wood_roof", "tile_roof")
    add("roof", "1. Class-A Fire-Resistant Roof", s, ev, "Class-A asphalt/tile/metal roof.")
    s, ev = _ai(presence, "vegetation_at_wall")
    add("zone0", "2. Ember-Resistant Zone 0 (0–5 ft)", s, ev, "Rake to gravel/soil within 5 ft.")
    s, ev = _ai(presence, "wood_fence_attached")
    add("fence", "3. No Wood Fence Contacting Structure", s, ev, "Metal panel/gate for last 5 ft.")
    s, ev = _ai(presence, "firewood_propane_near")
    add("firewood", "4. No Combustible Storage at Walls", s, ev, "Relocate 30+ ft into open area.")
    s, ev = _ai(presence, "vent_open", "vent_screened")
    add("vents", "5. Ember-Resistant Vents", s, ev, "1/8-in mesh or ember-rated vents.")
    add("windows", "6. Upgraded Windows",
        _manual(manual.get("windows", "Not sure")), "Homeowner attestation.",
        "Dual-pane tempered glazing.")
    s, ev = _ai(presence, "open_rafter_eaves", "soffited_eaves")
    add("eaves", "7. Closed / Soffited Eaves", s, ev, "Box rafter tails with soffits.")
    s, ev = _ai(presence, "gutter_debris")
    add("gutters", "8. Clean Gutters", s, ev, "Clear debris before fire season.")
    can_fail = presence.get("tree_over_roof") or presence.get("ladder_fuels")
    add("canopy", "9. Canopy & Ladder Fuels",
        "fail" if can_fail else "unknown",
        "AI flagged overhanging canopy / ladder fuels." if can_fail
        else "Not visible enough — verify in person.",
        "10-ft horizontal / 6-ft vertical separation.")
    s, ev = _ai(presence, "storage_under_deck")
    add("deck", "10. Cleared Under-Deck Space", s, ev, "Clear + enclose with mesh.")
    s, ev = _ai(presence, "outbuilding_near")
    add("outbuilding", "11. Detached Structures ≥ 30 ft", s, ev, "Relocation or hardening.")
    add("firewise", "12. Community Risk Program",
        _manual(manual.get("firewise", "Not sure")), "Homeowner attestation.",
        "Enroll the community in Firewise USA.")

    lo, mid, hi = score_band(items)
    nf = sum(1 for i in items if i["status"] == "fail")
    risk_label = {0: "LOW", 1: "MODERATE", 2: "HIGH"}.get(min(nf, 2), "SEVERE")
    return {"items": items, "score": mid, "band": (lo, hi), "risk_label": risk_label}