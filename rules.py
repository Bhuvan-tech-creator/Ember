"""Maps AI detections + attested answers onto the official 10-measure
California 'Safer from Wildfires' framework and produces a hardening score."""

CLASSES = [
    "wood_roof", "tile_roof", "vent_open", "vent_screened",
    "wood_fence_attached", "vegetation_at_wall",
    "open_rafter_eaves", "soffited_eaves", "gutter_debris",
    "tree_over_roof", "storage_under_deck", "outbuilding_near",
    "firewood_propane_near", "ladder_fuels",
]

MANUAL_ITEMS = {
    "windows": "Multi-pane / tempered windows? (mostly not visible to AI)",
    "firewise": "Does your community hold Firewise USA or Fire Risk Reduction status?",
}

def _ai(presence, fail_key, pass_key=None):
    """'unclear' votes never fail a home; explicit sightings matter."""
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
             "Your roof covering resists embers — when burning embers rain down (they can "
             "travel a mile ahead of the flames), they land here and die instead of igniting "
             "the house. This is the single most valuable protection a structure can have.",
             "The video shows an easily-ignitable roof covering. Embers can fall for hours "
             "before flames ever arrive; a vulnerable roof is the most expensive fix here, "
             "but also the one that changes your survival odds the most.", 3),
    "zone0": ("The critical first 5 feet (Zone 0)",
              "Nothing combustible touches the walls. Embers pile into wall corners like "
              "snowdrifts — with nothing to burn there, they simply smolder out.",
              "Vegetation, mulch, or bark beds sit right against the house. Embers accumulate "
              "exactly there, smolder for hours, and transfer fire into the siding. Raking "
              "this back and laying gravel is one weekend and near-zero cost — the single "
              "highest-return fix on this list.", 1),
    "fence": ("Fencing attached to the house",
              "No wood fence runs into the structure, so a burning fence can't act as a "
              "fuse leading fire straight to your wall.",
              "A wood fence physically touches the house — a classic 'fuse' that carries "
              "flame along its length into the home. Replace the last 5 feet with metal "
              "fencing or a metal gate; it's a small, targeted change with big payoff.", 1),
    "vents": ("Attic & crawl-space vent screens",
              "Vents are screened with fine mesh. Embers can't slip into the attic — the "
              "hidden ignition pathway that destroys homes from the inside out.",
              "Vents appear open or coarse-mesh. Embers pass a 1/4-inch gap like dust "
              "through a sieve, then ignite insulation unseen. Ember-rated covers (~$40 "
              "each) install in an afternoon.", 1),
    "windows": ("Window glazing",
                "Multi-pane tempered glazing withstands radiant heat far longer, keeping "
                "the building sealed while embers swirl outside.",
                "Single-pane glass can shatter from radiant heat alone, giving embers an "
                "open doorway inside. Budget-dependent, but part of any serious hardening "
                "plan.", 3),
    "eaves": ("Eaves & roofline overhang",
              "Eaves are enclosed/soffited — no open rafter 'shelves' where wind-driven "
              "embers lodge.",
              "Open rafter tails were visible along the roofline: natural pockets where "
              "embers collect and smolder against bare wood. Boxed soffits close this gap.",
              2),
    "gutters": ("Gutter cleanliness",
                "Gutters appear clear — no dry leaf beds lying inches below the roof edge.",
                "Gutters hold visible leaf/needle debris. During ember storms, gutters are "
                "a landing platform directly under your roof; clean them before fire season "
                "and consider mesh guards.", 1),
    "canopy": ("Tree canopy over the roof",
               "No branches overhang the structure — fire can't drop from above and "
               "ember deposition on the roof stays low.",
               "Branches overhang the roof. In a fire, an overhanging limb drops embers and "
               "firebrands onto the most critical surface of the house. Trim so the canopy "
               "stays 10 feet clear and 6 feet off the ground.", 2),
    "deck": ("Under-deck storage",
             "Nothing combustible shelters under the deck — decks funnel embers into "
             "hidden pockets against the house.",
             "Storage was spotted beneath deck/stair spaces: exactly the trapped-ember "
             "magnet firefighters warn about. Clear it, then enclose with 1/8-inch mesh.", 2),
    "outbuilding": ("Detached structures (30-ft buffer)",
                    "No shed or outbuilding sits close enough to act as a fire-bridge "
                    "to the house.",
                    "A shed/outbuilding stands within ~30 feet of the house — close enough "
                    "to burn long and hard against your siding. Relocate it, fire-harden it, "
                    "or connect the two with a noncombustible buffer.", 3),
}

def evaluate(presence: dict, manual: dict) -> dict:
    items = []
    def add(key, title, status, evidence, fix):
        pt, pp, pf, prio = PLAIN[key]
        items.append({"key": key, "title": title, "status": status, "evidence": evidence,
                      "priority": prio, "plain_title": pt,
                      "plain": pp if status == "pass" else pf, "fix": fix})

    s, ev = _ai(presence, "wood_roof", "tile_roof")
    add("roof", "1. Class-A Fire-Resistant Roof", s, ev,
        "Replace with Class-A asphalt/tile/metal roofing.")
    s, ev = _ai(presence, "vegetation_at_wall")
    add("zone0", "2. Ember-Resistant Zone 0 (0–5 ft)", s, ev,
        "Clear to bare soil/gravel within 5 ft of walls; metal garden edging.")
    s, ev = _ai(presence, "wood_fence_attached")
    add("fence", "3. No Wood Fence Contacting Structure", s, ev,
        "Swap last 5 ft of fence for metal panel/gate.")
    s, ev = _ai(presence, "firewood_propane_near")
    add("zone0", "4. No Combustible Storage Near Walls (firewood / propane)", s, ev,
        "Move firewood 30+ ft away; relocate propane tanks to open areas.")
    s, ev = _ai(presence, "vent_open", "vent_screened")
    add("vents", "5. Ember-Resistant Vents", s, ev,
        "Install 1/8-in metal mesh or ember-rated vents.")
    s = _manual(manual.get("windows", "Not sure"))
    add("windows", "6. Upgraded Windows", s, "Homeowner attestation.",
        "Dual-pane tempered glazing.")
    s, ev = _ai(presence, "open_rafter_eaves", "soffited_eaves")
    add("eaves", "7. Closed / Soffited Eaves", s, ev, "Box in rafter tails with soffits.")
    s, ev = _ai(presence, "gutter_debris")
    add("gutters", "8. Clean Gutters", s, ev,
        "Clear debris; consider leaf-guard mesh before fire season.")
    can_fail = presence.get("tree_over_roof") or presence.get("ladder_fuels")
    add("canopy", "9. Defensible Space — Canopy & Ladder Fuels",
        "fail" if can_fail else ("unknown" if not any(k in presence for k in
            ("tree_over_roof", "ladder_fuels")) else "unknown"),
        "AI flagged overhanging canopy or ladder fuels." if can_fail
        else "Assessment limited by footage.",
        "Trim canopy 10 ft horizontal / 6 ft vertical; remove shrubs beneath trees.")
    s, ev = _ai(presence, "storage_under_deck")
    add("deck", "10. Cleared Under-Deck Space", s, ev,
        "Clear stored items; enclose underside with 1/8-in mesh.")
    s, ev = _ai(presence, "outbuilding_near")
    add("outbuilding", "11. Detached Structures ≥ 30 ft", s, ev,
        "Relocate/harden outbuildings; create noncombustible buffer.")

    scored = [i for i in items if i["status"] != "unknown"]
    score = 100 * sum(1 for i in scored if i["status"] == "pass") / max(len(scored), 1)
    nf = sum(1 for i in items if i["status"] == "fail")
    risk_label = {0: "LOW", 1: "MODERATE", 2: "HIGH"}.get(min(nf, 2), "SEVERE")
    return {"items": items, "score": score, "risk_label": risk_label}