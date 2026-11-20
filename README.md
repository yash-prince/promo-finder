# Promo Finder — Kuku Assignment, Problem 1

Reads a folder of microdrama screenplays (one `.txt` per episode) and returns a ranked list of 20–60 s promo clips
with episode, start/end timestamps of every segment, hook, cliffhanger and why it works.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env            # paste a free Gemini key from https://aistudio.google.com/apikey
python run.py --input "<folder with episode .txt files>" --out output
```
Outputs: `output/report.md` (read this), `promos.csv` (for the editor), `promos.json`, `pipeline_log.json`.

Other useful flags: `--limit 5` (first 5 episodes only) · `--top 20` · `--no-judge` · `--mock` (no API, plumbing test only).

## Web UI (easiest way to demo)
```bash
streamlit run app.py      # opens http://localhost:8501
```
Pick a **provider** (Gemini / OpenAI / Anthropic / Groq), a **model** (or a custom id) and paste your **API key** in the sidebar.
The key is sent only with that session's requests and is never stored.
Upload episode `.txt` files (or one `.zip`), press **Find promos**. See ranked promos, hook/cliffhanger highlighted
inside each clip, the full episode with the clip marked, and the independent quality scores. Download CSV/JSON.

## Swap the model (one flag, no code change)
```bash
python run.py --input ... --model gemini/gemini-2.5-pro
python run.py --input ... --model groq/llama-3.3-70b-versatile      # needs GROQ_API_KEY
python run.py --input ... --model anthropic/claude-sonnet-4-5       # needs ANTHROPIC_API_KEY
```

## How it works
1. `parser.py` — code parses the screenplay into timed beats (dialogue / action / sound / camera).
2. `finder.py` — LLM reads each episode (+ one-line summary of every episode) and proposes 2–4 promos. Parallel, cached.
3. `validate.py` — code checks every timestamp really exists in the script, snaps cuts to line boundaries,
   enforces 20–60 s, removes duplicates. Invented timestamps are rejected.
4. `ranker.py` — one LLM call ranks all valid candidates (it sees the real first/last line of each clip).
5. `evaluate.py` — an independent "new viewer" LLM sees only the clip text and scores it; used to check the ranking.
6. `report.py` — writes the outputs.

Re-runs are free: LLM answers are cached in `.cache/` (delete it to force fresh calls).

## Tests
`python tests.py "<episode folder>"` (no API key needed).

## Known limits
- Cannot join moments across different episodes (only within one episode).
- Works from the script, not the video: it cannot see acting, music or pacing.
- Hook/cliffhanger taste is an LLM judgement; the code only guarantees valid timestamps and lengths.
- `--mock` is only a plumbing test, its picks are not meaningful.
