# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stage 0.5 of the open-coding pipeline: a seeded human review surface.

Renders an eyeball-able review sample over the deterministic consolidation
records produced by ``scripts/consolidate_opencoding.py`` (its
``_consolidation_records.json``). This is the manual gate Sylvain runs BEFORE
committing to Stage 1 codebook induction: a chance to read the actual material
-- question text, both coders' mechanisms/errors, primary factors -- on a
representative, reproducible slice rather than all 594 traces.

PURE deterministic. NO LLM calls, NO clustering, NO mutation of inputs. Inputs
(the records JSON and the sampled trace ``.md`` files) are opened read-only; the
only writes are the review artifact(s).

The sampler is seeded (``--seed``) and stratified by ``(set, verdict)`` so that
correct / wrong / abstained are all represented roughly proportionally, with a
guaranteed minimum per non-empty stratum (``--min-per-stratum``) so the rare
``abstained`` cell never drops out. With the default ``--set orig`` only the
main study traces are sampled; ``rerun_divergent`` (the flip sub-study, a subset
of orig qids) is excluded unless explicitly requested.

The question/prompt TEXT is not in the records, so for each SAMPLED trace only
(never all 594) the matching ``<indir>/<set>/<trace_id>.md`` is read and its
``## Question``, ``## Final predicted answer`` (the agent's own answer) and
``## Reference answer (ground truth)`` sections are extracted. One card is
rendered per sampled trace: a metadata header, the question, then the agent's
predicted answer next to the ground-truth answer (so they can be compared), then
both coders side by side (mechanisms, errors, primary factor), plus a
clearly-labelled empty slot for the future Stage-2 census labels.

Outputs (written next to the records by default):
  * ``review_sample_<date>.html`` -- single self-contained file, inline CSS +
    vanilla JS for filter-by-verdict/set and free-text search. No external/CDN
    assets.
  * ``review_sample_<date>.md``   -- the same content as a cleanly sectioned
    markdown doc for nvim / Obsidian.

Usage:
    uv run python scripts/build_review_sample.py
    uv run python scripts/build_review_sample.py --set all --n 60 --format html
    uv run python scripts/build_review_sample.py --seed 20260629 --n 40
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import date

DEFAULT_INDIR = "outputs/analysis/opencoding_full_20260626"
VALID_VERDICTS = ("correct", "wrong", "abstained")
SETS = ("orig", "rerun_divergent")
CODERS = (("minimax", "MiniMax-M3"), ("claude", "claude-opus"))
DEFAULT_SEED = 20260629


# --------------------------------------------------------------------------- #
# Trace .md section extraction (read-only)
# --------------------------------------------------------------------------- #
def extract_section(md_text: str, header: str) -> str:
    """Return the text under a ``## header`` line up to the next markdown heading.

    Matches the exact heading line (``^##? ... header``), then collects every
    following line until the next line that starts with ``#``. Returns "" when
    the header is absent.
    """
    lines = md_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^#{1,6}\s+" + re.escape(header) + r"\s*$", ln.strip()):
            start = i + 1
            break
    if start is None:
        return ""
    out: list[str] = []
    for ln in lines[start:]:
        if re.match(r"^#{1,6}\s", ln):
            break
        out.append(ln)
    return "\n".join(out).strip()


def extract_section_until(md_text: str, header: str, stop_titles) -> str:
    """Collect text under ``header`` until a heading whose title is in stop_titles.

    Unlike :func:`extract_section` (which stops at the NEXT heading of any level),
    this stops only at a heading matching one of ``stop_titles``. A section whose
    body itself contains markdown sub-headings -- e.g. the agent's
    ``## Final predicted answer`` often embeds ``## ...`` summary headings -- is
    therefore captured in full instead of being truncated at the first sub-heading.
    """
    lines = md_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^#{1,6}\s+" + re.escape(header) + r"\s*$", ln.strip()):
            start = i + 1
            break
    if start is None:
        return ""
    stop_norm = {t.lower() for t in stop_titles}
    out: list[str] = []
    for ln in lines[start:]:
        m = re.match(r"^#{1,6}\s+(.*?)\s*$", ln)
        if m and m.group(1).strip().lower() in stop_norm:
            break
        out.append(ln)
    return "\n".join(out).strip()


def read_trace_text(indir: str, subset: str, trace_id: str) -> tuple[str, str, str, bool]:
    """Return (question, predicted, ground_truth, md_found) for one sampled trace.

    Reads the trace .md read-only. ``predicted`` is the agent's own
    ``## Final predicted answer``. Missing file or missing section yields empty
    strings (surfaced later as a data-coverage note), never a fabricated value.
    """
    path = os.path.join(indir, subset, trace_id + ".md")
    if not os.path.isfile(path):
        return "", "", "", False
    with open(path, encoding="utf-8") as f:
        text = f.read()
    question = extract_section(text, "Question")
    # The agent's answer and the ground truth can themselves contain markdown
    # sub-headings, so bound them by the NEXT known trace section rather than the
    # first heading.
    predicted = extract_section_until(
        text, "Final predicted answer", ["Reference answer (ground truth)"])
    ground_truth = extract_section_until(
        text, "Reference answer (ground truth)",
        ["Judge verdict and reasoning", "Instruction"])
    return question, predicted, ground_truth, True


# --------------------------------------------------------------------------- #
# Stratified seeded sampling
# --------------------------------------------------------------------------- #
def allocate(sizes: dict[tuple, int], n: int, min_per: int) -> dict[tuple, int]:
    """Allocate ``n`` draws across strata, proportional with a floor + capacity.

    Each non-empty stratum first gets ``min(min_per, size)`` guaranteed draws;
    remaining slots are handed out greedily to whichever stratum is furthest
    below its proportional share and still has capacity. Deterministic. If the
    floors alone already meet/exceed ``n`` the floor allocation is returned as-is
    (so the rare strata are never starved, even if it slightly overshoots ``n``).
    """
    keys = [k for k in sizes if sizes[k] > 0]
    total = sum(sizes[k] for k in keys)
    alloc = {k: min(min_per, sizes[k]) for k in keys}
    while sum(alloc.values()) < n:
        best, best_deficit = None, None
        for k in keys:
            if alloc[k] >= sizes[k]:
                continue
            deficit = n * sizes[k] / total - alloc[k]
            if best is None or deficit > best_deficit:
                best, best_deficit = k, deficit
        if best is None:  # no capacity left anywhere
            break
        alloc[best] += 1
    return alloc


def stratified_sample(records: list[dict], n: int, min_per: int, seed: int):
    """Return (sampled_records, alloc) using seeded per-stratum sampling.

    Strata are ``(set, verdict)``; iteration order is fixed (SETS x VALID_VERDICTS)
    and each stratum's population is sorted by question_id before sampling, so the
    result is fully reproducible for a given seed.
    """
    buckets: dict[tuple, list[dict]] = {}
    for r in records:
        buckets.setdefault((r["set"], r["verdict"]), []).append(r)
    sizes = {k: len(v) for k, v in buckets.items()}
    alloc = allocate(sizes, n, min_per)

    rng = random.Random(seed)
    sampled: list[dict] = []
    for s in SETS:
        for v in VALID_VERDICTS:
            key = (s, v)
            k = alloc.get(key, 0)
            if not k:
                continue
            pool = sorted(buckets[key], key=lambda r: r["question_id"])
            sampled.extend(rng.sample(pool, k))
    sampled.sort(key=lambda r: (SETS.index(r["set"]), VALID_VERDICTS.index(r["verdict"]),
                                r["question_id"]))
    return sampled, alloc


# --------------------------------------------------------------------------- #
# Build the render model (one dict per card), tracking missing fields
# --------------------------------------------------------------------------- #
def build_cards(sampled: list[dict], indir: str):
    cards = []
    missing: list[str] = []  # human-readable coverage notes
    for r in sampled:
        question, predicted, ground_truth, md_found = read_trace_text(indir, r["set"], r["trace_id"])
        if not md_found:
            missing.append(f"{r['set']}/{r['trace_id']}: trace .md not found")
        else:
            if not question:
                missing.append(f"{r['set']}/{r['trace_id']}: empty/absent Question section")
            if not predicted:
                missing.append(f"{r['set']}/{r['trace_id']}: empty/absent Final predicted answer section")
            if not ground_truth:
                missing.append(f"{r['set']}/{r['trace_id']}: empty/absent Reference answer section")
        for fld in ("project", "category", "num_iterations", "num_tool_calls", "cell_id"):
            if r.get(fld) in (None, ""):
                missing.append(f"{r['set']}/{r['trace_id']}: missing record field '{fld}'")
        for coder_key, _label in CODERS:
            c = r["coders"].get(coder_key)
            if c is None:
                missing.append(f"{r['set']}/{r['trace_id']}: coder '{coder_key}' is null (parse failure)")
        cards.append({
            "record": r,
            "question": question,
            "predicted": predicted,
            "ground_truth": ground_truth,
        })
    return cards, missing


def composition(sampled: list[dict]) -> dict:
    by_set = Counter(r["set"] for r in sampled)
    by_verdict = Counter(r["verdict"] for r in sampled)
    by_set_verdict = Counter((r["set"], r["verdict"]) for r in sampled)
    return {"by_set": by_set, "by_verdict": by_verdict, "by_set_verdict": by_set_verdict}


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #
def md_coder_block(c: dict | None) -> list[str]:
    if c is None:
        return ["_coder output unavailable (parse failure)_", ""]
    L: list[str] = []
    L.append(f"- **reported verdict:** {c.get('reported_verdict') or '_(none)_'}")
    if c.get("parse_repairs"):
        L.append(f"- **parse repairs:** {', '.join(c['parse_repairs'])}")
    L.append("")
    for kind in ("mechanisms", "errors"):
        items = c.get(kind) or []
        L.append(f"**{kind.capitalize()}** ({len(items)}):")
        if not items:
            L.append("- _(none)_")
        for it in items:
            label = it.get("label") or "_(no label)_"
            ev = it.get("evidence") or ""
            line = f"- **{label}**"
            if ev:
                line += f" — _{ev}_"
            L.append(line)
        L.append("")
    L.append(f"**Primary factor:** {c.get('primary_factor') or '_(none)_'}")
    L.append("")
    return L


def render_md(cards, comp, alloc, args, indir, records_path) -> str:
    L: list[str] = []
    w = L.append
    w(f"# Open-coding review sample")
    w("")
    w(f"_Generated {date.today().isoformat()} (deterministic, no LLM)._  ")
    w(f"_Seed `{args.seed}` · set filter `{args.set}` · target n `{args.n}` · "
      f"min-per-stratum `{args.min_per_stratum}` · cards `{len(cards)}`._")
    w("")
    w(f"Source records: `{records_path}`. Trace text read read-only from "
      f"`{indir}/<set>/<trace_id>.md`. This is a human review surface for the "
      f"pre-induction gate; the empty **Stage-2 census labels** slot on each card "
      f"is left for later annotation.")
    w("")
    w("## Sample composition")
    w("")
    w("| set | correct | wrong | abstained | total |")
    w("| --- | --: | --: | --: | --: |")
    for s in SETS:
        if comp["by_set"].get(s):
            row = [comp["by_set_verdict"].get((s, v), 0) for v in VALID_VERDICTS]
            w(f"| `{s}` | {row[0]} | {row[1]} | {row[2]} | {comp['by_set'][s]} |")
    tot = [comp["by_verdict"].get(v, 0) for v in VALID_VERDICTS]
    w(f"| **all** | {tot[0]} | {tot[1]} | {tot[2]} | {len(cards)} |")
    w("")

    for idx, card in enumerate(cards, 1):
        r = card["record"]
        w("---")
        w("")
        w(f"## {idx}. `{r['trace_id']}` — {r['verdict']} · {r['set']}")
        w("")
        w(f"- **trace_id:** `{r['trace_id']}`  ·  **qid:** {r['question_id']}  ·  "
          f"**verdict:** {r['verdict']}  ·  **set:** {r['set']}")
        w(f"- **project:** {r.get('project')}  ·  **category:** {r.get('category')}  ·  "
          f"**iterations:** {r.get('num_iterations')}  ·  **tool calls:** {r.get('num_tool_calls')}")
        w(f"- **cell_id:** `{r.get('cell_id')}`")
        w("")
        w("### Question")
        w("")
        w(card["question"] or "_(question text unavailable)_")
        w("")
        w("### Agent answer (LLM)")
        w("")
        w(card["predicted"] or "_(agent answer unavailable)_")
        w("")
        w("### Reference answer (ground truth)")
        w("")
        w(card["ground_truth"] or "_(ground truth unavailable)_")
        w("")
        for coder_key, coder_label in CODERS:
            w(f"### Coder: {coder_label} (`{coder_key}`)")
            w("")
            L.extend(md_coder_block(r["coders"].get(coder_key)))
        w("### Stage-2 census labels")
        w("")
        w("> _(empty — reserved for later census annotation)_")
        w("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# HTML rendering (self-contained: inline CSS + vanilla JS, no external assets)
# --------------------------------------------------------------------------- #
def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def html_coder_block(c: dict | None) -> str:
    if c is None:
        return '<div class="coder"><p class="muted">coder output unavailable (parse failure)</p></div>'
    parts = ['<div class="coder">']
    rv = _h(c.get("reported_verdict") or "(none)")
    parts.append(f'<p class="rv">reported verdict: <b>{rv}</b>')
    if c.get("parse_repairs"):
        parts.append(f' · <span class="muted">repairs: {_h(", ".join(c["parse_repairs"]))}</span>')
    parts.append("</p>")
    for kind in ("mechanisms", "errors"):
        items = c.get(kind) or []
        parts.append(f'<p class="kind">{kind.capitalize()} ({len(items)})</p>')
        if not items:
            parts.append('<p class="muted">(none)</p>')
        else:
            parts.append("<ul>")
            for it in items:
                label = _h(it.get("label") or "(no label)")
                ev = _h(it.get("evidence") or "")
                ev_html = f' <span class="ev">— {ev}</span>' if ev else ""
                parts.append(f"<li><b>{label}</b>{ev_html}</li>")
            parts.append("</ul>")
    parts.append(f'<p class="pf"><span class="kind">Primary factor</span><br>'
                 f'{_h(c.get("primary_factor") or "(none)")}</p>')
    parts.append("</div>")
    return "".join(parts)


def render_html(cards, comp, alloc, args, indir, records_path) -> str:
    today = date.today().isoformat()
    rows = []
    for s in SETS:
        if comp["by_set"].get(s):
            r = [comp["by_set_verdict"].get((s, v), 0) for v in VALID_VERDICTS]
            rows.append(f"<tr><td><code>{s}</code></td><td>{r[0]}</td><td>{r[1]}</td>"
                        f"<td>{r[2]}</td><td>{comp['by_set'][s]}</td></tr>")
    tot = [comp["by_verdict"].get(v, 0) for v in VALID_VERDICTS]
    rows.append(f"<tr class='tot'><td><b>all</b></td><td>{tot[0]}</td><td>{tot[1]}</td>"
                f"<td>{tot[2]}</td><td>{len(cards)}</td></tr>")

    cards_html = []
    for idx, card in enumerate(cards, 1):
        r = card["record"]
        coders_html = "".join(
            f'<div class="coder-col"><h4>{_h(label)} <span class="muted">({_h(key)})</span></h4>'
            f"{html_coder_block(r['coders'].get(key))}</div>"
            for key, label in CODERS
        )
        cards_html.append(f"""
<section class="card" data-verdict="{_h(r['verdict'])}" data-set="{_h(r['set'])}">
  <div class="cardhead">
    <span class="idx">#{idx}</span>
    <span class="tid">{_h(r['trace_id'])}</span>
    <span class="badge v-{_h(r['verdict'])}">{_h(r['verdict'])}</span>
    <span class="badge set">{_h(r['set'])}</span>
    <span class="meta">qid {_h(r['question_id'])} · project {_h(r.get('project'))} ·
      cat {_h(r.get('category'))} · iters {_h(r.get('num_iterations'))} ·
      tools {_h(r.get('num_tool_calls'))} · <code>{_h(r.get('cell_id'))}</code></span>
  </div>
  <div class="qa">
    <div class="q"><h5>Question</h5><p>{_h(card['question']) or '<span class="muted">(unavailable)</span>'}</p></div>
  </div>
  <div class="ans">
    <div class="pa"><h5>Agent answer (LLM)</h5><p>{_h(card['predicted']) or '<span class="muted">(unavailable)</span>'}</p></div>
    <div class="gt"><h5>Reference answer (ground truth)</h5><p>{_h(card['ground_truth']) or '<span class="muted">(unavailable)</span>'}</p></div>
  </div>
  <div class="coders">{coders_html}</div>
  <div class="stage2"><h5>Stage-2 census labels</h5>
    <p class="muted">(empty — reserved for later census annotation)</p></div>
</section>""")

    head = f"""<header>
<h1>Open-coding review sample</h1>
<p class="sub">Generated {today} · deterministic, no LLM · seed <code>{args.seed}</code> ·
set filter <code>{args.set}</code> · target n <code>{args.n}</code> ·
min-per-stratum <code>{args.min_per_stratum}</code> · <b>{len(cards)}</b> cards</p>
<p class="sub">Records: <code>{_h(records_path)}</code> · trace text read read-only from
<code>{_h(indir)}/&lt;set&gt;/&lt;trace_id&gt;.md</code></p>
<table class="comp"><thead><tr><th>set</th><th>correct</th><th>wrong</th>
<th>abstained</th><th>total</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</header>"""

    controls = """<div class="controls">
  <label>verdict
    <select id="fVerdict"><option value="">all</option>
    <option value="correct">correct</option><option value="wrong">wrong</option>
    <option value="abstained">abstained</option></select></label>
  <label>set
    <select id="fSet"><option value="">all</option>
    <option value="orig">orig</option><option value="rerun_divergent">rerun_divergent</option></select></label>
  <label>search <input id="fSearch" type="text" placeholder="free text…"></label>
  <span id="count" class="muted"></span>
</div>"""

    css = """
:root{--bg:#fbfbfa;--fg:#1d1d1f;--muted:#6b6b70;--line:#e2e2df;--card:#fff;
  --ok:#1f7a3d;--okbg:#e6f4ea;--bad:#b3261e;--badbg:#fbe9e7;--abs:#8a5a00;--absbg:#fdf3e0;}
*{box-sizing:border-box}
body{font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  margin:0;color:var(--fg);background:var(--bg)}
header,.controls,main{max-width:1100px;margin:0 auto;padding:0 20px}
header{padding-top:24px}
h1{margin:0 0 4px;font-size:24px}
.sub{margin:2px 0;color:var(--muted);font-size:13px}
code{background:#f0f0ee;padding:1px 5px;border-radius:4px;font-size:.92em}
table.comp{border-collapse:collapse;margin:12px 0;font-size:13px}
table.comp th,table.comp td{border:1px solid var(--line);padding:4px 10px;text-align:right}
table.comp th:first-child,table.comp td:first-child{text-align:left}
table.comp tr.tot{background:#f4f4f2;font-weight:600}
.controls{position:sticky;top:0;background:var(--bg);padding:12px 20px;border-bottom:1px solid var(--line);
  display:flex;gap:18px;align-items:center;flex-wrap:wrap;z-index:5}
.controls label{font-size:13px;color:var(--muted);display:flex;gap:6px;align-items:center}
.controls select,.controls input{font:inherit;font-size:13px;padding:4px 6px;border:1px solid var(--line);border-radius:6px}
.controls input{width:260px}
main{padding-top:18px;padding-bottom:60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:14px 0;
  box-shadow:0 1px 2px rgba(0,0,0,.03)}
.cardhead{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:8px}
.idx{color:var(--muted);font-variant-numeric:tabular-nums}
.tid{font-weight:700;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.badge.set{background:#eef;color:#334}
.v-correct{background:var(--okbg);color:var(--ok)}
.v-wrong{background:var(--badbg);color:var(--bad)}
.v-abstained{background:var(--absbg);color:var(--abs)}
.meta{font-size:12px;color:var(--muted);margin-left:auto}
.qa{margin:12px 0}
.ans{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:12px 0}
.qa h5,.ans h5,.coders h5,.stage2 h5,.coder-col h4{margin:0 0 4px;font-size:12px;text-transform:uppercase;
  letter-spacing:.04em;color:var(--muted)}
.qa p,.ans p{margin:0;white-space:pre-wrap}
.pa h5{color:#7a4a00}
.coders{display:grid;grid-template-columns:1fr 1fr;gap:18px;border-top:1px solid var(--line);padding-top:12px}
.coder-col h4{font-size:13px;text-transform:none;color:var(--fg);letter-spacing:0}
.coder .rv{margin:2px 0 8px;font-size:13px}
.kind{margin:8px 0 2px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
.coder ul{margin:2px 0 6px;padding-left:18px}
.coder li{margin:2px 0}
.ev{color:var(--muted);font-style:italic}
.pf{margin:8px 0 0;font-size:13px}
.muted{color:var(--muted)}
.stage2{border-top:1px dashed var(--line);margin-top:12px;padding-top:10px}
@media(max-width:760px){.ans,.coders{grid-template-columns:1fr}}
"""

    js = """
(function(){
  var v=document.getElementById('fVerdict'),s=document.getElementById('fSet'),
      q=document.getElementById('fSearch'),count=document.getElementById('count'),
      cards=Array.prototype.slice.call(document.querySelectorAll('.card'));
  function apply(){
    var vv=v.value,sv=s.value,qq=q.value.toLowerCase().trim(),n=0;
    cards.forEach(function(c){
      var ok=(!vv||c.dataset.verdict===vv)&&(!sv||c.dataset.set===sv)&&
             (!qq||c.textContent.toLowerCase().indexOf(qq)>=0);
      c.style.display=ok?'':'none'; if(ok)n++;
    });
    count.textContent=n+' / '+cards.length+' shown';
  }
  v.onchange=s.onchange=apply; q.oninput=apply; apply();
})();
"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Open-coding review sample · {today}</title>
<style>{css}</style></head>
<body>
{head}
{controls}
<main>{''.join(cards_html)}</main>
<script>{js}</script>
</body></html>
"""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indir", default=DEFAULT_INDIR,
                    help="open-coding output dir (contains orig/ and rerun_divergent/ and the records)")
    ap.add_argument("--records", default=None,
                    help="records JSON path (default: <indir>/_consolidation_records.json)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"random seed for reproducible sampling (default: {DEFAULT_SEED})")
    ap.add_argument("--n", type=int, default=40, help="target number of sampled cards (default: 40)")
    ap.add_argument("--set", choices=("orig", "rerun_divergent", "all"), default="orig",
                    help="which set(s) to sample from (default: orig)")
    ap.add_argument("--min-per-stratum", type=int, default=3,
                    help="guaranteed minimum draws per non-empty (set,verdict) stratum (default: 3)")
    ap.add_argument("--format", choices=("html", "md", "both"), default="both",
                    help="output format(s) (default: both)")
    ap.add_argument("--out-prefix", default=None,
                    help="output path without extension "
                         "(default: <indir>/review_sample_<date>)")
    args = ap.parse_args(argv)

    indir = args.indir
    records_path = args.records or os.path.join(indir, "_consolidation_records.json")
    if not os.path.isfile(records_path):
        print(f"error: records file not found: {records_path}", file=sys.stderr)
        return 2

    with open(records_path, encoding="utf-8") as f:
        records = json.load(f)

    if args.set != "all":
        records = [r for r in records if r["set"] == args.set]
    if not records:
        print(f"error: no records after set filter '{args.set}'", file=sys.stderr)
        return 2

    sampled, alloc = stratified_sample(records, args.n, args.min_per_stratum, args.seed)
    cards, missing = build_cards(sampled, indir)
    comp = composition(sampled)

    out_prefix = args.out_prefix or os.path.join(
        indir, f"review_sample_{date.today().strftime('%Y%m%d')}")
    written = []
    if args.format in ("md", "both"):
        md_path = out_prefix + ".md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_md(cards, comp, alloc, args, indir, records_path))
        written.append(md_path)
    if args.format in ("html", "both"):
        html_path = out_prefix + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(cards, comp, alloc, args, indir, records_path))
        written.append(html_path)

    print(f"sampled {len(cards)} cards (seed {args.seed}, set '{args.set}', "
          f"target n {args.n}, min-per-stratum {args.min_per_stratum})")
    for s in SETS:
        if comp["by_set"].get(s):
            parts = ", ".join(f"{comp['by_set_verdict'].get((s, v), 0)} {v}" for v in VALID_VERDICTS)
            print(f"  {s}: {comp['by_set'][s]} ({parts})")
    print("  totals: " + ", ".join(f"{comp['by_verdict'].get(v, 0)} {v}" for v in VALID_VERDICTS))
    for p in written:
        print(f"wrote -> {p}")
    if missing:
        print(f"data-coverage notes: {len(missing)} field(s) missing/empty on sampled traces:",
              file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
