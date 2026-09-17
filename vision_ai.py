import io
import json
import os

from PIL import Image, ImageDraw
import streamlit as st

MODEL_ID = "gemini-2.5-flash"
MAX_IMAGES_PER_CALL = 6

PROMPT = """You are a certified wildfire home-hardening inspector in California performing a
comprehensive video-frame audit against the state 'Safer from Wildfires' framework.

Inspect the attached walk-around frames with care. Assess EVERY item below, studying all
frames before answering. Answer 'yes|no|unclear' — 'unclear' ONLY when the feature is truly
not visible, not because you are hurried.

Visible elements to judge: roofing material; attic/gable/foundation vents and their mesh;
fences and gates contacting the house; vegetation, mulch or bark beds touching or within
roughly 5 ft of exterior walls; eaves (open rafter tails vs boxed/soffited); rain gutters
(trapped leaves/pine needles = debris); tree canopy or branches overreaching the roofline;
combustible items stored beneath decks or stairs; sheds/outbuildings closer than ~30 ft;
firewood piles or propane tanks near walls; 'ladder fuels' (shrubs growing directly under
tree canopies that would carry ground fire upward).

Reply with STRICT JSON, no markdown, no code fences:
{
  "wood_shake_roof": "yes|no|unclear",
  "tile_or_composite_roof": "yes|no|unclear",
  "open_vents": "yes|no|unclear",
  "screened_vents": "yes|no|unclear",
  "wood_fence_touching_house": "yes|no|unclear",
  "vegetation_or_mulch_touching_wall": "yes|no|unclear",
  "open_rafter_eaves_visible": "yes|no|unclear",
  "soffited_eaves_visible": "yes|no|unclear",
  "gutters_with_debris_visible": "yes|no|unclear",
  "tree_branches_over_roof": "yes|no|unclear",
  "items_stored_under_deck": "yes|no|unclear",
  "shed_or_outbuilding_within_30ft": "yes|no|unclear",
  "firewood_or_propane_near_house": "yes|no|unclear",
  "ladder_fuels_shrubs_under_trees": "yes|no|unclear",
  "evidence_sentence": "1-2 sentences describing the most decision-relevant observations",
  "highlights": [
    {"frame_index": 0, "label": "short label", "box": [x1, y1, x2, y2]}
  ]
}
Include up to 6 highlight entries — one per frame that shows a genuine risk OR a clearly
compliant feature worth documenting. frame_index is 0-based over the attached images in the
order sent; box values are normalized 0-1. Empty list if nothing concrete. Never invent
conditions that are not visibly present."""

def _get_client():
    from google import genai
    key = None
    try:
        key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass
    key = key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found")
    return genai.Client(api_key=key)

def inspect_frames(frames, log=None):
    client = _get_client()
    from google.genai import types
    frames = frames[:MAX_IMAGES_PER_CALL]
    contents = [PROMPT] + [f.copy() for f in frames]
    if log:
        log.write(f"   …{len(frames)} frames, 14-point inspection, one request")

    resp = client.models.generate_content(
        model=MODEL_ID,
        contents=contents,
        config=types.GenerateContentConfig(temperature=0.1,
                                           response_mime_type="application/json"),
    )
    data = json.loads(resp.text)
    votes = {k: [v] for k, v in data.items()
             if k not in ("evidence_sentence", "highlights")}
    evidence = [data["evidence_sentence"]] if data.get("evidence_sentence") else []
    highlights = data.get("highlights") or []
    return votes, evidence, highlights if isinstance(highlights, list) else []

def votes_to_presence(votes):
    def yes(key):
        return "yes" in votes.get(key, [])
    return {
        "wood_roof": yes("wood_shake_roof"),
        "tile_roof": yes("tile_or_composite_roof"),
        "vent_open": yes("open_vents"),
        "vent_screened": yes("screened_vents"),
        "wood_fence_attached": yes("wood_fence_touching_house"),
        "vegetation_at_wall": yes("vegetation_or_mulch_touching_wall"),
        "open_rafter_eaves": yes("open_rafter_eaves_visible"),
        "soffited_eaves": yes("soffited_eaves_visible"),
        "gutter_debris": yes("gutters_with_debris_visible"),
        "tree_over_roof": yes("tree_branches_over_roof"),
        "storage_under_deck": yes("items_stored_under_deck"),
        "outbuilding_near": yes("shed_or_outbuilding_within_30ft"),
        "firewood_propane_near": yes("firewood_or_propane_near_house"),
        "ladder_fuels": yes("ladder_fuels_shrubs_under_trees"),
    }

def draw_highlights(frames, highlights):
    out = []
    for hl in highlights[:6]:
        idx = hl.get("frame_index", 0)
        if not (0 <= idx < len(frames)):
            continue
        img = frames[idx].copy()
        w, h = img.size
        try:
            x1, y1, x2, y2 = [float(v) for v in hl["box"]]
        except Exception:
            continue
        px = (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))
        d = ImageDraw.Draw(img)
        for i in range(4):
            d.rectangle([px[0]-i, px[1]-i, px[2]+i, px[3]+i], outline=(193, 82, 47))
        d.rectangle([px[0], max(0, px[1]-26), px[0]+200, px[1]], fill=(193, 82, 47))
        d.text((px[0]+6, max(0, px[1]-22)), hl.get("label", "finding")[:26], fill="white")
        out.append(img)
    return out