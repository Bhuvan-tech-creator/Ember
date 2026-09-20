from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

# Ordered chain of Gemini models to try, fail-fast on overload.
MODEL_CHAIN: List[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]

MAX_IMAGES_PER_CALL: int = 6

PROMPT: str = """You are a certified wildfire home-hardening inspector in California performing a
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
  "vegetation_or_mulch_within_5ft_of_wall": "yes|no|unclear",
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
conditions that are not visibly present.
"""


def _get_client():
    """Return an initialized Gemini client or raise if the API key is missing."""
    from google import genai

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found — set it in env or secrets.")
    return genai.Client(api_key=key)


def inspect_frames(
    frames: List[Image.Image],
    log: Any = None,
    on_try: Any = None,
) -> Tuple[Dict[str, List[str]], List[str], List[Dict[str, Any]]]:
    """
    Run the vision-language inspection over up to MAX_IMAGES_PER_CALL frames.

    Returns:
        votes: mapping from JSON field name to list of model votes ("yes|no|unclear").
        evidence: list of human-readable evidence sentences.
        highlights: list of highlight dicts with frame_index, label, and box.
    """
    from google.genai import types

    client = _get_client()
    frames = frames[:MAX_IMAGES_PER_CALL]
    contents: List[Any] = [PROMPT] + [f.copy() for f in frames]

    data: Dict[str, Any] | None = None
    used_model: str | None = None
    tried: List[str] = []

    for i, model_id in enumerate(MODEL_CHAIN):
        tried.append(model_id)
        if on_try:
            on_try(i, model_id)
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(resp.text)
            used_model = model_id
            break
        except Exception as e:  # keep fail-fast behavior but avoid crashing
            if log is not None:
                try:
                    log.write(f"engine {model_id} failed fast: {str(e)[:120]}")
                except Exception:
                    pass
            else:
                print(f"engine {model_id} failed fast: {str(e)[:120]}")
            time.sleep(0.4)

    if data is None:
        raise RuntimeError(
            "All free Gemini vision engines are momentarily overloaded "
            f"(tried: {', '.join(tried)}). Wait 5–30 minutes and analyze again."
        )

    # Collect votes for each key (excluding metadata fields).
    votes: Dict[str, List[str]] = {
        k: [v]
        for k, v in data.items()
        if k not in ("evidence_sentence", "highlights")
    }

    evidence: List[str] = []
    if isinstance(data.get("evidence_sentence"), str) and data["evidence_sentence"].strip():
        evidence.append(data["evidence_sentence"].strip())

    if used_model:
        evidence.append(f"Vision engine: {used_model}")

    highlights_raw = data.get("highlights") or []
    highlights: List[Dict[str, Any]] = highlights_raw if isinstance(highlights_raw, list) else []

    return votes, evidence, highlights


def votes_to_presence(votes: Dict[str, List[str]]) -> Dict[str, bool]:
    """
    Convert raw yes/no/unclear votes into boolean presence flags for downstream scoring.

    We treat any explicit 'yes' vote as presence; 'no' and 'unclear' are treated as absence.
    """

    def yes(key: str) -> bool:
        return any(v.strip().lower() == "yes" for v in votes.get(key, []))

    return {
        "wood_roof": yes("wood_shake_roof"),
        "tile_roof": yes("tile_or_composite_roof"),
        "vent_open": yes("open_vents"),
        "vent_screened": yes("screened_vents"),
        "wood_fence_attached": yes("wood_fence_touching_house"),
        # BUGFIX: match the actual JSON field name from the prompt so vegetation is detected correctly.
        "vegetation_at_wall": yes("vegetation_or_mulch_within_5ft_of_wall"),
        "open_rafter_eaves": yes("open_rafter_eaves_visible"),
        "soffited_eaves": yes("soffited_eaves_visible"),
        "gutter_debris": yes("gutters_with_debris_visible"),
        "tree_over_roof": yes("tree_branches_over_roof"),
        "storage_under_deck": yes("items_stored_under_deck"),
        "outbuilding_near": yes("shed_or_outbuilding_within_30ft"),
        "firewood_propane_near": yes("firewood_or_propane_near_house"),
        "ladder_fuels": yes("ladder_fuels_shrubs_under_trees"),
    }


def draw_highlights(frames: List[Image.Image], highlights: List[Dict[str, Any]]) -> List[Image.Image]:
    """
    Render bounding boxes and labels on selected frames based on highlight definitions.

    Each highlight dict must contain:
        - frame_index: 0-based index into frames
        - label: short text label
        - box: [x1, y1, x2, y2] normalized to 0–1 coordinates
    """
    out: List[Image.Image] = []

    for hl in highlights[:6]:
        idx = int(hl.get("frame_index", 0))
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

        # Draw a multi-pixel border for visual clarity.
        for i in range(4):
            d.rectangle(
                [px[0] - i, px[1] - i, px[2] + i, px[3] + i],
                outline=(193, 82, 47),
            )

        # Label background bar.
        label_y = max(0, px[1] - 26)
        d.rectangle(
            [px[0], label_y, px[0] + 200, px[1]],
            fill=(193, 82, 47),
        )

        label_text = str(hl.get("label", "finding"))[:26]
        d.text(
            (px[0] + 6, max(0, px[1] - 22)),
            label_text,
            fill="white",
        )

        out.append(img)

    return out