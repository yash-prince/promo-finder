"""Web UI for the Promo Finder.   Run:  streamlit run app.py

Upload episode .txt files (or one .zip) -> press Run -> see ranked promos, where the hook and
cliffhanger sit inside each clip, the full episode with the clip highlighted, and quality checks.
"""
import html
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
import llm
from evaluate import judge
from finder import find_all
from parser import fmt, load_folder
from ranker import rank

llm.load_env()
st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")

MAX_FILES, MAX_BYTES = 200, 5_000_000


# ---------- helpers ----------
def save_uploads(files) -> str:
    """Write uploaded .txt files (or .zip of them) into a fresh temp folder; returns the folder path."""
    folder = tempfile.mkdtemp(prefix="promo_in_")
    n = 0
    for f in files:
        data = f.getvalue()
        if f.name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    name = Path(info.filename).name          # flatten: ignore any folder paths in the zip
                    if name.lower().endswith(".txt") and info.file_size < MAX_BYTES and n < MAX_FILES:
                        (Path(folder) / f"{n:04d}_{name}").write_bytes(z.read(info))
                        n += 1
        elif f.name.lower().endswith(".txt") and len(data) < MAX_BYTES and n < MAX_FILES:
            (Path(folder) / f"{n:04d}_{Path(f.name).name}").write_bytes(data)
            n += 1
    return folder


def esc(s: str) -> str:
    return html.escape(s or "")


def clip_lines(ep, start, end):
    """Content lines inside a segment, as (start_time, label, text)."""
    out = []
    for b in ep.beats:
        if b.kind == "CAMERA" or b.start < start - 0.01 or b.end > end + 0.01:
            continue
        label = b.speaker if b.kind == "DIALOGUE" else b.kind.lower()
        out.append((b.start, label, b.text))
    return out


def clip_html(ep, seg, hook_window=3.0) -> str:
    lines = clip_lines(ep, seg.start, seg.end)
    rows = []
    for i, (t, label, text) in enumerate(lines):
        is_hook = t - seg.start <= hook_window
        is_last = i == len(lines) - 1
        bg, tag = ("#fff3cd", " 🪝 HOOK") if is_hook else (("#f8d7da", " ⛓ CLIFFHANGER (cut here)") if is_last else ("transparent", ""))
        rows.append(f'<div style="background:{bg};padding:3px 8px;border-radius:4px;margin:2px 0">'
                    f'<code>{fmt(t)}</code> <b>{esc(label)}</b>: {esc(text)}<b style="color:#555">{tag}</b></div>')
    return "".join(rows)


def episode_html(ep, segs) -> str:
    rows = []
    for b in ep.beats:
        if b.kind == "CAMERA":
            continue
        inside = any(s.start - 0.01 <= b.start and b.end <= s.end + 0.01 for s in segs)
        label = b.speaker if b.kind == "DIALOGUE" else b.kind.lower()
        style = "background:#d1e7dd;" if inside else "color:#888;"
        rows.append(f'<div style="{style}padding:2px 8px;border-radius:4px"><code>{fmt(b.start)}</code> '
                    f'<b>{esc(label)}</b>: {esc(b.text)}</div>')
    return "".join(rows)


# ---------- sidebar ----------
with st.sidebar:
    st.header("Settings")
    model = st.text_input("Model (LiteLLM string)", llm.DEFAULT_MODEL,
                          help="e.g. gemini/gemini-3-flash-preview, groq/llama-3.3-70b-versatile, anthropic/claude-sonnet-4-5")
    key_in = st.text_input("API key (optional if set in .env)", type="password")
    if key_in:
        prov = model.split("/")[0].upper()
        os.environ[f"{ {'GEMINI': 'GEMINI', 'GOOGLE': 'GEMINI'}.get(prov, prov) }_API_KEY"] = key_in
    batch = st.slider("Episodes per LLM call", 1, 10, 5, help="Bigger = fewer requests (free tiers allow few per day)")
    top_n = st.slider("Promos to show", 5, 40, 15)
    do_judge = st.checkbox("Run independent quality check", True)
    mock = st.checkbox("Mock mode (no LLM, plumbing test only)", False)
    st.caption("LLM answers are cached on disk, so re-running the same input is instant and free.")

st.title("🎬 Promo Finder")
st.write("Reads microdrama screenplays and finds the best **20–60 s promo clips**: a **hook** in the first 3 seconds, "
         "a **cliffhanger** at the cut, and enough context for a viewer who has never seen the show.")

tab_run, tab_how = st.tabs(["▶ Run", "ℹ How it works"])

with tab_how:
    st.markdown("""
**Code does the exact work, the LLM does the judgement.**

| Step | Who | What happens |
|---|---|---|
| 1. Parse | code | Each screenplay becomes timed lines (dialogue / action / sound). Camera notes are dropped. |
| 2. Find | LLM | Reads several episodes per call + a one-line summary of every episode. Proposes 2–4 promos per episode with segments, hook, cliffhanger, reason. |
| 3. Validate | code | Every start/end must match a **real line boundary**. Invented timestamps are rejected, cuts are snapped so no line is cut in half, length forced into 20–60 s, duplicates removed. |
| 4. Rank | LLM | One call ranks all candidates. It sees the **real first and last line** of each clip, not just the finder's claim. |
| 5. Judge | LLM | A separate "new viewer" sees *only the clip text* and scores hook / cliffhanger / standalone. This checks the picks. |

**How the hook is identified:** the opening 3 seconds of the clip. The finder is told to start on the hook itself (a slap, reveal or shocking line).
**How the cliffhanger is identified:** the clip must *end* on an unresolved moment. The finder names it, the ranker re-reads the final line, the judge scores whether it truly leaves the viewer hanging.
In the results, 🪝 marks lines in the first 3 s and ⛓ marks the final line where the clip is cut.
""")

with tab_run:
    st.subheader("1 · Input")
    ups = st.file_uploader("Episode screenplays: several .txt files, or one .zip of them", type=["txt", "zip"],
                           accept_multiple_files=True)
    folder_path = st.text_input("…or a local folder path (for quick demos)", "")
    limit = st.number_input("Only first N episodes (0 = all)", 0, 500, 0)

    if st.button("🚀 Find promos", type="primary"):
        folder = save_uploads(ups) if ups else folder_path.strip()
        if not folder or not Path(folder).is_dir():
            st.error("Upload files or give a valid folder path.")
            st.stop()
        try:
            with st.status("Running pipeline…", expanded=True) as status:
                st.write("**1/4 Parsing screenplays (code)**")
                episodes = load_folder(folder, int(limit) or None)
                eps = {e.number: e for e in episodes}
                st.write(f"→ {len(episodes)} episodes, {sum(len(e.beats) for e in episodes)} timed entries")

                st.write("**2/4 LLM proposes promos, then code validates every timestamp**")
                cands, log = find_all(episodes, model, 3, 8, mock, batch)
                st.write(f"→ {log['raw_candidates']} proposed → {log['valid']} valid "
                         f"({len(log['rejected'])} rejected, {log['duplicates_removed']} duplicates)")

                st.write("**3/4 LLM ranks all candidates (sees the real first/last lines)**")
                ranked = rank(cands, eps, model, 8, mock)
                st.write(f"→ {len(ranked)} ranked")

                stats = None
                if do_judge and not mock and ranked:
                    st.write("**4/4 Independent 'new viewer' judge checks the clips**")
                    stats = judge(ranked, eps, model, 8)
                    st.write(f"→ top-10 would post: {stats['top_k_would_post']}/{stats['top_k']}")
                status.update(label="Done", state="complete")
            st.session_state.update(ranked=ranked, eps=eps, log=log, stats=stats)
        except Exception as e:                                   # show a readable message, not a stack trace
            st.error(f"Run failed: {str(e)[:600]}")
            st.stop()

    if "ranked" in st.session_state:
        ranked, eps = st.session_state["ranked"], st.session_state["eps"]
        log, stats = st.session_state["log"], st.session_state["stats"]
        st.subheader("2 · Results — post in this order")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Episodes", log["episodes"])
        c2.metric("Candidates proposed", log["raw_candidates"])
        c3.metric("Valid after code checks", log["valid"])
        c4.metric("Rejected by validator", len(log["rejected"]))

        if stats:
            st.info(f"**Quality check:** the independent judge would post {stats['top_k_would_post']}/{stats['top_k']} "
                    f"of the top picks but only {stats['bottom_k_would_post']}/{stats['bottom_k']} of the bottom picks. "
                    f"Avg cliffhanger score top {stats['top_k_avg']['cliffhanger']} vs bottom {stats['bottom_k_avg']['cliffhanger']}. "
                    f"The finder over-scores its own hooks by {stats['finder_vs_judge_hook_gap']} points on average.")

        rows = [{"rank": r.rank, "episode": r.candidate.segments[0].episode,
                 "segments": " + ".join(f"{fmt(s.start)}-{fmt(s.end)}" for s in r.candidate.segments),
                 "duration_s": round(r.candidate.duration, 1), "hook": r.candidate.hook,
                 "cliffhanger": r.candidate.cliffhanger, "why_it_works": r.candidate.why, "ranking_reason": r.reason}
                for r in ranked]
        d1, d2 = st.columns(2)
        import csv
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys())) if rows else None
        if w:
            w.writeheader(); w.writerows(rows)
            d1.download_button("⬇ Download CSV", buf.getvalue(), "promos.csv", "text/csv")
            d2.download_button("⬇ Download JSON", json.dumps(rows, indent=2), "promos.json", "application/json")

        for r in ranked[:top_n]:
            c = r.candidate
            seg_txt = " + ".join(f"Ep {s.episode} · {fmt(s.start)} → {fmt(s.end)}" for s in c.segments)
            with st.expander(f"#{r.rank}  ·  {seg_txt}  ·  {c.duration:.0f}s  ·  score {r.score:.0f}"):
                a, b = st.columns([3, 2])
                with a:
                    st.markdown(f"**🪝 Hook:** {c.hook}")
                    st.markdown(f"**⛓ Cliffhanger:** {c.cliffhanger}")
                    st.markdown(f"**Why it works:** {c.why}")
                    st.markdown(f"**Why this rank:** {r.reason}")
                    if c.notes:
                        st.warning("Flags: " + "; ".join(sorted(set(c.notes))))
                with b:
                    if r.judge:
                        j = r.judge
                        st.markdown("**Independent judge** (sees only the clip)")
                        st.progress(min(1.0, float(j.get("hook", 0)) / 10), text=f"Hook {j.get('hook')}/10")
                        st.progress(min(1.0, float(j.get("cliffhanger", 0)) / 10), text=f"Cliffhanger {j.get('cliffhanger')}/10")
                        st.progress(min(1.0, float(j.get("standalone", 0)) / 10), text=f"Standalone {j.get('standalone')}/10")
                        st.caption(f"Would post: {j.get('would_post')} · Weakness: {j.get('problem')}")
                    else:
                        st.caption("Not in the judged sample (top 10 + bottom 5).")
                st.markdown("**The clip as a viewer would see it** (🪝 first 3 s, ⛓ cut point)")
                for s in c.segments:
                    st.markdown(clip_html(eps[s.episode], s), unsafe_allow_html=True)
                if st.checkbox("Show full episode with clip highlighted", key=f"full_{c.id}"):
                    ep = eps[c.segments[0].episode]
                    st.markdown(episode_html(ep, [s for s in c.segments if s.episode == ep.number]),
                                unsafe_allow_html=True)

        if log["rejected"]:
            with st.expander(f"Candidates rejected by the validator ({len(log['rejected'])})"):
                for rj in log["rejected"]:
                    st.write(f"{rj['id']}: {rj['reason']}")
