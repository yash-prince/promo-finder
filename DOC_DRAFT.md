# Promo Finder — Solution Doc (Problem 1)  *(edit in your own words before exporting to a 2-page PDF)*

**Name / Roll no. / Branch:** ______ **Problem chosen:** 1 — Find the Promos

## 1. Why this problem
Its input pack is real, so I could run the tool on 50 episodes and check the output, instead of only describing it. The task is also repeatable: Kuku releases a new show every week, and an editor spends hours on each one.

## 2. Assumptions (the brief was silent)
- Timestamps are per-episode (each episode restarts at 00:00).
- A promo may join several moments from one episode. I did not build cross-episode joins.
- I only have the script, not the video, so "hook in the first 3 seconds" means the first line or action of the clip.
- Camera-direction lines are noise for judging story, so I drop them to save tokens (they remain in the files).
- The tool takes any folder of episode `.txt` files in this format, because the interview run will use a new show.

## 3. How it works (code does exact work, LLM does judgement)
1. **Parse (code):** turn each screenplay into timed lines.
2. **Find (LLM):** reads 5 episodes per call plus a one-line summary of every episode. It proposes 2–4 promos per episode, each with the segments, hook, cliffhanger and why it works.
3. **Validate (code):** every start and end must match a real line boundary in the script. Invented timestamps are rejected, cuts are snapped so no line is cut in half, and length must be 20–60 s.
4. **Rank (LLM, one call):** it sees the real first and last line of each clip, not just the finder's own description.
5. **Independent judge (LLM):** it sees only the clip text, like a new viewer. This is how I check the picks.
6. **Output:** `report.md`, `promos.csv`, `promos.json`, `pipeline_log.json`.

The model is one flag (`--model`), so a stronger model can be swapped in with no code change.

## 4. Results on the full pack (raw outputs in `output/`)
- 50 episodes → 89 candidates → 89 valid → top 40 ranked → report shows the top 20.
- The validator rejected 0 and changed 0. With the "copy times exactly" instruction, Gemini copied timestamps reliably. The validator is a safety net here, and tests show it does reject invented times and bad lengths.
- The top 40 cover 34 different episodes, so the list isn't one plot beat repeated.

## 5. Quality check, including failures
Independent judge on the top 10 vs the bottom 5:

| | hook | cliffhanger | standalone | would post |
|---|---|---|---|---|
| top 10 | 7.3 | 7.9 | 8.8 | 10 of 10 |
| bottom 5 | 5.4 | 5.2 | 8.0 | 2 of 5 |

The ranking does separate stronger from weaker clips. Where it picks badly:
- **Resolved endings ranked high.** #1 (Ep18 01:13–01:55) ends on the characters escaping a fire. The judge scored its cliffhanger 4/10 ("resolves the tension"), yet the ranker put it first. The ranker over-rewards spectacle.
- **Exposition ranked low but still listed.** #37 (Ep20) is pure explanation (hook 3, cliffhanger 3). #40 (Ep49) ends on legal strategy talk (cliffhanger 3).
- **Finder over-scores its own hooks.** Its hook score differs from the judge's by 2.7 points on average, so I treat self-scores as hints only.
- **Same model family.** The judge is also a Gemini model, so its taste is correlated with the finder's. I have not watched the video, so acting, music and pacing are unchecked. A human editor must review the top picks.
- **Cliffhangers are clean but quiet.** Several clips end on a line of dialogue, not a visual shock.

## 6. Scale and cost
- A 50-episode show is about 47k tokens of script. Batching 5 episodes per call plus one rank call and one judge call gave about 12 requests in total, which fits a free tier.
- LLM answers are cached on disk, so re-runs cost nothing.
- Batches are independent, so more shows can run in parallel. Cost grows linearly with episodes. The rank call only sees candidates, never full scripts.
- Human in the loop: the editor reviews the ranked list, watches the top picks, and fixes the cut points.

## 7. What I would do next
Cross-episode promos (end of episode N + start of N+1), use real video or audio signals, compare picks against the picks of the editors, and track which promos actually perform after posting. That is how I would know it worked with a real team.

## 8. AI tools and where they got it wrong
- **Tools:** Claude Code (design, code, review), Gemini (the model inside the tool).
- **Mistake 1:** the AI chose the default model `gemini-2.5-flash`. It had been retired, so the first run failed with a 404.
- **Mistake 2:** my first design made one call per episode plus one per judged clip, about 70 requests. Gemini's free tier allows about 20 per day per model, so the run died partway through. I redesigned the finder to batch 5 episodes per call and the judge to score all clips in one call.
- **Mistake 3:** a patch script written by the AI corrupted two files with literal line breaks, caught by compiling the code.
