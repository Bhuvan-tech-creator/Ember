import base64
import io
import os
import tomllib

from rules import evaluate


def load_key():
    if os.environ.get("GEMINI_API_KEY"):
        return

    try:
        with open(".streamlit/secrets.toml", "rb") as secrets_file:
            secrets = tomllib.load(secrets_file)
            os.environ["GEMINI_API_KEY"] = secrets["GEMINI_API_KEY"]
    except Exception:
        pass


def _image_to_b64(image, quality=78):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def analyze(
    video_bytes,
    address,
    manual,
    selected_target=None,
    demo=False,
    on_progress=None,
):
    progress = on_progress or (lambda percent, message: None)

    output = {
        "notes": [],
        "logs": [],
    }

    load_key()

    demo = demo or not os.environ.get("GEMINI_API_KEY")

    progress(6, "Video received — decoding…")

    if demo:
        presence = {
            "tile_roof": True,
            "vegetation_at_wall": True,
            "vent_open": True,
        }
        highlighted = []
        vegetation_overlays = []
        vegetation_percent = 0.0
        output["notes"] = [
            "Demo mode — set GEMINI_API_KEY for live analysis."
        ]
        progress(30, "Demo mode — skipping live CV layers")

    else:
        progress(12, "Picking informative frames with motion + sharpness analysis…")

        from analysis_extra import sample_with_motion, vegetation_stats

        local_logs = []

        class Logger:
            def write(self, message):
                local_logs.append(str(message))

            def warning(self, message):
                local_logs.append("warning: " + str(message))

        key_frames, sampling_stats = sample_with_motion(
            video_bytes,
            Logger(),
            max_frames=6,
        )

        if not key_frames:
            raise RuntimeError(
                "No decodable frames — re-record in H.264 / "
                "'Most Compatible' mode."
            )

        output["logs"].extend(local_logs)

        progress(
            26,
            f"Kept {len(key_frames)} key frames — measuring vegetation coverage…",
        )

        vegetation_overlays, vegetation_percent, _ = vegetation_stats(key_frames)

        progress(
            36,
            (
                f"ExG measurement complete "
                f"({vegetation_percent * 100:.1f}% vegetation detected) — "
                f"contacting vision engines…"
            ),
        )

        from vision_ai import inspect_frames, votes_to_presence, draw_highlights

        def on_engine_try(index, engine_name):
            progress(
                38 + index * 6,
                f"Trying vision engine {index + 1}/5: {engine_name}…",
            )

        votes, notes, highlight_definitions = inspect_frames(
            key_frames,
            log=None,
            on_try=on_engine_try,
        )

        presence = votes_to_presence(votes)

        if (
            vegetation_percent > 0.06
            and not presence.get("vegetation_at_wall")
        ):
            presence["vegetation_at_wall"] = True
            output["logs"].append(
                "ExG pixel measurement corroborated vegetation near the structure."
            )

        progress(72, "AI verdicts received — drawing evidence overlays…")

        highlighted = draw_highlights(
            key_frames,
            highlight_definitions,
        )

        output["notes"] = notes
        output["key_frames"] = len(key_frames)

    progress(78, "Scoring against the 12-measure hardening framework…")

    result = evaluate(presence, manual)

    failed_items = sorted(
        [
            item
            for item in result["items"]
            if item["status"] == "fail"
        ],
        key=lambda item: -item["weight"],
    )

    parcel = None
    parcel_b64 = None

    if selected_target:
        target_latitude, target_longitude = selected_target

        progress(
            86,
            "Rendering aerial parcel map around the user-confirmed roof target…",
        )

        try:
            from geomap import render_final_finding_map

            parcel = render_final_finding_map(
                target_latitude=target_latitude,
                target_longitude=target_longitude,
                findings=failed_items,
            )

            if parcel:
                parcel_b64 = base64.b64encode(parcel["png"]).decode("utf-8")

        except Exception as error:
            output["logs"].append(
                f"Aerial map could not be generated: {error}"
            )

    elif address.strip():
        output["logs"].append(
            "No roof target was selected; parcel map omitted to avoid "
            "placing findings on an unverified property."
        )

    progress(92, "Computing tamper-evident integrity fingerprint…")

    from integrity import make_fingerprint

    fingerprint = make_fingerprint(
        result,
        address or "Not provided",
    )

    progress(96, "Rendering official technical evidence packet…")

    evidence_images = (highlighted or []) + vegetation_overlays[:2]
    evidence_b64 = [
        _image_to_b64(image)
        for image in evidence_images
    ]

    from report import build_pdf

    pdf_bytes = build_pdf(
        result=result,
        evidence_images=evidence_images,
        address=address or "Not provided",
        parcel=parcel,
        fingerprint=fingerprint,
    )

    progress(100, "Complete ✅")

    output.update(
        {
            "score": result["score"],
            "band": list(result["band"]),
            "risk": result["risk_label"],
            "fingerprint": fingerprint,
            "items": result["items"],
            "parcel": parcel_b64,
            "parcel_stats": (
                {
                    "perimeter_m": parcel.get("perimeter_m", 0),
                    "area_m2": parcel.get("area_m2", 0),
                    "conceptual": parcel.get("conceptual", False),
                    "mode": parcel.get("mode", "satellite"),
                    "target_lat": parcel.get("target_lat"),
                    "target_lon": parcel.get("target_lon"),
                }
                if parcel
                else None
            ),
            "evidence": evidence_b64,
            "veg_pct": round(vegetation_percent, 4),
            "pdf_b64": base64.b64encode(pdf_bytes).decode("utf-8"),
            "demo": demo,
        }
    )

    return output