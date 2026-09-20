"""
Second-pass vision reasoning: given the aerial photo and representative
evidence frames, ask Gemini WHERE around the confirmed roof point each
failed finding is physically located (compass bearing), so pins reflect
real spatial reasoning instead of a fixed decorative ring.
"""
import json
import time

from PIL import Image

MODEL_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]

PROMPT_TEMPLATE = """You are a wildfire inspector positioning findings on an aerial
(bird's-eye) photo of a house. The white crosshair in the aerial image marks the
confirmed roof center. North is up in this image.

You are given:
1. The aerial photo (image 1).
2. Ground-level evidence photos from a walk-around video (remaining images),
   each labeled with which finding it illustrates.

For EACH finding listed below, infer the most likely COMPASS BEARING (0-359 degrees,
0=North, 90=East, 180=South, 270=West) from the roof center toward where that
problem is physically located on the property, using clues in the ground photos
(shadows, sun angle, visible neighboring structures, fence orientation, roofline
shape matching the aerial silhouette). If you truly cannot tell, spread remaining
unclear findings evenly and say so in reasoning.

Findings to place:
{finding_list}

Reply with STRICT JSON, no markdown:
{{
  "placements": [
    {{"finding_index": 0, "bearing_degrees": 135, "distance": "near|mid|far",
      "reasoning": "one sentence citing the visual clue used"}}
  ]
}}
distance: "near" = within a few feet of the wall (Zone 0 type issues),
"mid" = elsewhere on the lot (sheds, canopy), "far" = property edge."""


def _encode(image: Image.Image):
    return image.copy()


def place_findings_on_aerial(aerial_image: Image.Image, failed_items: list, evidence_frames: list):
    """Returns list aligned with failed_items: [{bearing, distance, reasoning}, ...].
    Falls back to an even spread with a note if the AI call fails entirely."""
    if not failed_items:
        return []

    finding_list = "\n".join(
        f"{i}. {item['plain_title']} — {item['fix']}"
        for i, item in enumerate(failed_items)
    )
    prompt = PROMPT_TEMPLATE.format(finding_list=finding_list)

    contents = [prompt, _encode(aerial_image)]
    for frame in evidence_frames[:4]:
        contents.append(_encode(frame))

    from google import genai
    from google.genai import types
    import os

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return _fallback_spread(failed_items, "no API key available")

    client = genai.Client(api_key=key)

    data = None
    for model_id in MODEL_CHAIN:
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.15, response_mime_type="application/json"),
            )
            data = json.loads(resp.text)
            break
        except Exception as e:
            print(f"aerial reasoning engine {model_id} failed: {str(e)[:120]}")
            time.sleep(0.3)

    if not data or "placements" not in data:
        return _fallback_spread(failed_items, "vision engines unavailable")

    placements_by_index = {}
    for p in data["placements"]:
        try:
            placements_by_index[int(p["finding_index"])] = {
                "bearing": float(p.get("bearing_degrees", 0)) % 360,
                "distance": p.get("distance", "mid"),
                "reasoning": p.get("reasoning", "AI-estimated placement."),
            }
        except Exception:
            continue

    result = []
    n = len(failed_items)
    for i in range(n):
        if i in placements_by_index:
            result.append(placements_by_index[i])
        else:
            result.append({
                "bearing": (360.0 / n) * i,
                "distance": "mid",
                "reasoning": "AI did not return a placement for this item; evenly spread as fallback.",
            })
    return result


def _fallback_spread(failed_items, reason):
    n = max(len(failed_items), 1)
    return [
        {
            "bearing": (360.0 / n) * i,
            "distance": "mid",
            "reasoning": f"Even spread used ({reason}).",
        }
        for i in range(len(failed_items))
    ]