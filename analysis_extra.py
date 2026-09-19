import cv2
import numpy as np
from PIL import Image

# ---------- Feature 4: motion-aware frame selection ----------

def sample_with_motion(video_bytes, log, every=15, max_frames=6, blur_thresh=80.0):
    """Pick the sharpest frames where the CAMERA WAS MOVING most —
    motion peaks = corners/side-changes = the informative footage."""
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(video_bytes)
        path = tmp.name
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        log.warning("Could not decode the video (HEVC?). Re-record in 'Most Compatible'.")
        return [], {}

    samples, prev_small, i, total = [], None, 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        total += 1
        if i % every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
            small = cv2.resize(gray, (96, 54))
            motion = (
                float(np.abs(cv2.calcOpticalFlowFarneback(
                    prev_small, small, None, 0.5, 3, 15, 3, 5, 1.2, 0)).mean())
                if prev_small is not None else 0.0
            )
            samples.append({"img": frame[:, :, ::-1], "sharp": sharp,
                            "motion": motion})
            prev_small = small
        i += 1
    cap.release()
    if not samples:
        return [], {}

    sharp_a = np.array([s["sharp"] for s in samples]); sharp_a /= (sharp_a.max() + 1e-6)
    mot_a = np.array([s["motion"] for s in samples]); mot_a /= (mot_a.max() + 1e-6)
    score = sharp_a * (0.4 + mot_a)
    keep = np.argsort(-score)[:max_frames]
    keep.sort()
    frames = [Image.fromarray(samples[k]["img"]) for k in keep]

    moved = float((mot_a[1:] > 0.25).mean())      # share of time the camera actually travelled
    coverage = "multi-side (good)" if moved > 0.5 else "single-side (verify perimeter)"
    stats = {"sampled": len(samples), "total": total, "coverage": coverage}
    return frames, stats

# ---------- Feature 2: ExG vegetation measurement ----------

def vegetation_stats(frames):
    """Excess-Green index on each key frame — citation-friendly remote sensing:
    ExG = 2G - R - B; mask = ExG > 20. Measured, not guessed."""
    overlays, pcts = [], []
    for f in frames:
        arr = np.asarray(f.convert("RGB")).astype(np.float32)
        R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        mask = (2 * G - R - B) > 20.0
        lower = mask[int(mask.shape[0] * 0.45):, :]
        pcts.append(float(lower.mean()))

        blend = arr.copy()
        blend[mask] = blend[mask] * 0.45 + np.array([34, 139, 34]) * 0.55
        overlays.append(Image.fromarray(blend.astype(np.uint8)))
    return overlays, (max(pcts) if pcts else 0.0), pcts