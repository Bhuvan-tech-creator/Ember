import tempfile
import traceback

import cv2
import numpy as np
import streamlit as st
from PIL import Image

from rules import evaluate, CLASSES, MANUAL_ITEMS
from report import build_pdf

FRAME_EVERY = 15
BLUR_THRESHOLD = 80.0
DEDUP_THRESHOLD = 28.0
MAX_KEY_FRAMES = 6

st.set_page_config(page_title="EmberCert", page_icon="🌿", layout="wide")

# ---------- calm natural-green styling ----------
st.markdown("""
<style>
    .block-container {padding-top: 2.5rem; max-width: 1050px;}
    [data-testid="stAppViewContainer"] {background: #f4f6f0;}
    .hero {
        background: linear-gradient(135deg, #1b4332 0%, #2d6a4f 55%, #74a892 100%);
        padding: 2.2rem 2.4rem; border-radius: 18px; margin-bottom: 1.6rem;
        box-shadow: 0 6px 24px rgba(27,67,50,.18);
    }
    .hero h1 {color: #ffffff; margin: 0; font-size: 2.3rem; letter-spacing: .5px;}
    .hero p {color: #d8f3dc; margin: .4rem 0 0 0; font-size: 1.02rem; line-height: 1.55;}
    .stButton>button[kind="primary"] {
        background: #2d6a4f; border: none; border-radius: 10px;
        padding: .65rem 1.4rem; font-weight: 600;
    }
    .stButton>button[kind="primary"]:hover {background: #1b4332;}
    [data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #d8e2d3; border-radius: 14px;
        padding: 14px 18px; box-shadow: 0 2px 8px rgba(27,67,50,.06);
    }
    [data-testid="stExpander"] {background:#ffffff; border:1px solid #dce5d6; border-radius:12px;}
    .fixcard {
        background:#ffffff; border:1px solid #d8e2d3; border-left:5px solid #c1522f;
        border-radius:12px; padding:14px 18px; margin-bottom:.7rem;
    }
    .badge {display:inline-block; background:#e8f2ec; color:#1b4332; border-radius:999px;
            padding:1px 10px; font-size:.78rem; font-weight:600; margin-right:6px;}
    h2, h3 {color: #1b4332;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>🌿 EmberCert</h1>
  <p>Upload a 30-second walk-around video of a house. AI reviews the footage frame by frame,
     grades the home against California's official <b>Safer from Wildfires</b> framework,
     and generates an insurer-ready evidence packet — complete with annotated proof photos.</p>
</div>
""", unsafe_allow_html=True)

def _demo_results():
    return ({k: False for k in CLASSES} | {"tile_roof": True, "vegetation_at_wall": True},
            ["Demo evidence line (no API key set)."], [])

def is_sharp(gray):
    return cv2.Laplacian(gray, cv2.CV_64F).var() > BLUR_THRESHOLD

def too_similar(a, b):
    a = cv2.resize(a, (64, 36)).astype(np.float32)
    b = cv2.resize(b, (64, 36)).astype(np.float32)
    return np.mean(np.abs(a - b)) < DEDUP_THRESHOLD

def extract_key_frames(video_bytes, log):
    stats = {"read": 0, "blurry_skipped": 0, "dup_skipped": 0}
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name
    cap = cv2.VideoCapture(tmp_path)
    if not cap.isOpened():
        log.warning("❌ Could not open the video — likely HEVC. Re-record in "
                    "'Most Compatible' mode (iPhone: Settings → Camera → Formats).")
        return [], stats
    frames, prev_gray, i = [], None, 0
    while len(frames) < MAX_KEY_FRAMES:
        ok, frame = cap.read()
        if not ok:
            break
        stats["read"] += 1
        if i % FRAME_EVERY == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if not is_sharp(gray):
                stats["blurry_skipped"] += 1
            elif prev_gray is not None and too_similar(gray, prev_gray):
                stats["dup_skipped"] += 1
            else:
                prev_gray = gray
                frames.append(Image.fromarray(frame[:, :, ::-1]))
        i += 1
    cap.release()
    return frames, stats

def get_api_key():
    try:
        k = st.secrets.get("GEMINI_API_KEY")
        if k:
            return k
    except Exception:
        pass
    import os
    return os.environ.get("GEMINI_API_KEY")

DEMO_MODE = get_api_key() is None

colL, colR = st.columns([1, 1], gap="large")
with colL:
    st.subheader("1 · Upload the video")
    uploaded = st.file_uploader("Walk the full perimeter; keep the wall in frame.",
                                type=["mp4", "mov"])
    address = st.text_input("Property address (appears on the PDF)")
    if DEMO_MODE:
        st.warning("No GEMINI_API_KEY → DEMO MODE (fake results).")
    else:
        st.success("✅ Live AI mode (Gemini vision).")
    st.subheader("2 · Two quick attested items")
    manual = {}
    for key, label in MANUAL_ITEMS.items():
        manual[key] = st.radio(label, ["Yes / pass", "No / fail", "Not sure"],
                               horizontal=True, key=key)

if uploaded:
    video_bytes = uploaded.getvalue()
    with colR:
        st.subheader("Preview")
        st.video(video_bytes)

    if st.button("🌿 Analyze this home", type="primary", use_container_width=True):
        logs = st.status("Analyzing…", expanded=True)
        logs.write("**1/4** Video received (%0.1f MB)." % (len(video_bytes) / 1e6))
        try:
            if DEMO_MODE:
                presence, evidence_notes, highlighted = _demo_results()
                logs.write("**2/4** Demo mode — skipping frame extraction and AI calls.")
            else:
                logs.write("**2/4** Extracting sharp, non-duplicate key frames…")
                key_frames, stats = extract_key_frames(video_bytes, logs)
                logs.write(f"   …read {stats['read']} frames, kept {len(key_frames)} "
                           f"(skipped {stats['blurry_skipped']} blurry, "
                           f"{stats['dup_skipped']} duplicates).")
                if not key_frames:
                    st.error("No usable frames read. Re-record with H.264/'Most Compatible'.")
                    logs.update(state="error", label="No usable frames")
                    st.stop()
                logs.write("**3/4** Comprehensive 14-point vision inspection…")
                from vision_ai import inspect_frames, votes_to_presence, draw_highlights
                votes, evidence_notes, highlights = inspect_frames(key_frames, logs)
                presence = votes_to_presence(votes)
                highlighted = draw_highlights(key_frames, highlights)
                logs.write("**3/4** AI verdicts: " + str(votes))

            logs.write("**4/4** Scoring + building documents…")
            result = evaluate(presence, manual)
            pdf = build_pdf(result, highlighted, address=address or "Not provided")
            logs.update(state="complete", label="✅ Analysis complete")
        except Exception:
            logs.update(state="error", label="💥 Something failed — details below")
            st.code(traceback.format_exc())
            st.stop()

        st.divider()
        passes = [i for i in result["items"] if i["status"] == "pass"]
        fails = sorted([i for i in result["items"] if i["status"] == "fail"],
                       key=lambda i: i["priority"])
        unknowns = [i for i in result["items"] if i["status"] == "unknown"]

        tab_rundown, tab_findings, tab_evidence, tab_pdf = st.tabs(
            ["🗣️ Plain-English Rundown", "📋 Technical Findings",
             "🖼️ Evidence Frames", "📄 Official Packet"])

        with tab_rundown:
            m1, m2, m3 = st.columns(3)
            m1.metric("Hardening score", f"{result['score']:.0f} / 100")
            m2.metric("Ember-ignition risk", result["risk_label"])
            m3.metric("AI-assessed measures",
                      f"{len([i for i in result['items'] if 'AI' in i['evidence']])} / "
                      f"{len(result['items'])}")
            if passes:
                st.success("**What's already protecting this home:**\n\n" +
                           "\n".join(f"- **{p['plain_title']}** — {p['plain']}"
                                     for p in passes))
            if fails:
                st.markdown("#### 🔧 What to fix, in the order that matters")
                for n, item in enumerate(fails, 1):
                    st.markdown(
                        f"<div class='fixcard'><span class='badge'>Priority {n}</span>"
                        f"<b>{item['plain_title']}</b><br>{item['plain']}"
                        f"<br><small><b>Recommended fix:</b> {item['fix']}</small></div>",
                        unsafe_allow_html=True)
            else:
                st.success("No failures detected. 🎉")
            if unknowns:
                with st.expander("❔ Couldn't verify from the video"):
                    for u in unknowns:
                        st.write(f"- {u['title']}: {u['evidence']}")

        with tab_findings:
            for item in result["items"]:
                emoji = {"pass": "✅", "fail": "❌", "unknown": "❔"}[item["status"]]
                with st.expander(f"{emoji} {item['title']} — {item['status'].upper()}",
                                 expanded=False):
                    st.write(item["evidence"])
                    if item["status"] == "fail":
                        st.warning(f"Fix: {item['fix']}")
            for note in evidence_notes:
                st.caption(f"👁️ AI witness note: {note}")

        with tab_evidence:
            if highlighted:
                st.image(highlighted, width=340,
                         caption=[f"Exhibit {chr(65+i)} — AI-flagged region"
                                  for i in range(len(highlighted))])
            else:
                st.info("No regions were flagged in this footage.")

        with tab_pdf:
            st.download_button("📄 Download the official evidence packet (PDF)",
                               data=pdf, file_name="embercert_report.pdf",
                               mime="application/pdf", use_container_width=True)
            st.caption("Branded, insurer-ready, with annotated evidence photos.")