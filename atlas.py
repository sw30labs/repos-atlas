#!/usr/bin/env python3
"""Build a single self-contained HTML atlas of a folder of projects.

Reads survey.json (see survey.py), writes index.html. No dependencies.
"""
import argparse, json, os, sys, html, datetime, math
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime.now()

def load_domains(path=None):
    """Read optional local groupings without publishing a personal inventory."""
    path = path or os.path.join(HERE, "domains.json")
    try:
        with open(path, encoding="utf-8") as f:
            groups = json.load(f)
    except FileNotFoundError:
        groups = {}
    if not isinstance(groups, dict):
        raise ValueError("domains.json must be an object mapping groups to project-name lists")
    seen = set()
    for group, names in groups.items():
        if not group.strip() or not isinstance(names, list) or any(
                not isinstance(n, str) or not n.strip() for n in names):
            raise ValueError("each domain needs a name and a list of nonempty project names")
        for name in names:
            if name in seen:
                raise ValueError(f"project {name!r} appears in more than one domain entry")
            seen.add(name)
    groups.setdefault("Meta & Tooling", [])
    return list(groups.items())

DOMAINS = load_domains()
DOMAIN_OF = {n: d for d, names in DOMAINS for n in names}

# sequential blue, recent -> stale (more recent = darker)
RAMP = [("#0d366b","#fff"),("#184f95","#fff"),("#256abf","#fff"),
        ("#3987e5","#fff"),("#86b6ef","#0b0b0b"),("#cde2fb","#0b0b0b"),
        ("#b9b7ae","#0b0b0b")]
BUCKETS = [(7,"this week"),(30,"this month"),(90,"this quarter"),
           (365,"this year"),(10**9,"over a year"),(None,"no history")]
NO_HISTORY = 6

def days_since(iso):
    if not iso: return None
    try: d = datetime.datetime.fromisoformat(iso.replace("Z","+00:00")).replace(tzinfo=None)
    except Exception: return None
    return max(0, (NOW - d).days)

def bucket(days):
    if days is None: return NO_HISTORY
    for i,(lim,_) in enumerate(BUCKETS):
        if lim is None: break          # legend sentinel, not a real limit
        if days <= lim: return i
    return 5

def human(n):
    if n is None: return "-"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}k"
    return str(n)

def bytes_h(n):
    for u in ("B","KB","MB","GB"):
        if n < 1024: return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"

def spark(r, tail=12):
    """A tiny commit sparkline from a repo's per-month counts, last `tail` months."""
    months = r.get("months") or {}
    bars = []
    y, m = NOW.year, NOW.month
    for _ in range(tail):
        key = f"{y:04d}-{m:02d}"
        bars.append(months.get(key, 0))
        m -= 1
        if m == 0: y, m = y - 1, 12
    bars.reverse()
    peak = max(bars) or 1
    out = []
    for v in bars:
        h = (v / peak) * 100 if v else 0
        out.append(f'<i style="height:{max(h,3):.0f}%;opacity:{1 if v else .25}"></i>')
    title = ", ".join(f"{v}" for v in bars)
    return f'<span class="spark" title="commits per month, oldest&rarr;newest: {title}">{",".join(out)}</span>'

REVIEW = {}          # what the model said, if review.py has run

def load(survey_path=None, include_review=True):
    with open(survey_path or os.path.join(HERE, "survey.json"), encoding="utf-8") as f:
        d = json.load(f)
    global REVIEW
    try:
        if include_review:
            with open(os.path.join(HERE, "review.json"), encoding="utf-8") as f:
                REVIEW = json.load(f)
        else:
            REVIEW = {}
    except Exception:
        REVIEW = {}
    briefs = REVIEW.get("briefs", {})
    for r in d["repos"]:
        r["brief"] = briefs.get(r["name"]) or {}
        r["total_loc"] = sum(r["loc"].values())
        r["code_loc"]  = sum(v for k,v in r["loc"].items() if k != "Markdown")
        r["doc_loc"]   = r["loc"].get("Markdown", 0)
        r["days"]      = days_since(r.get("last"))
        r["age"]       = days_since(r.get("born"))
        r["recent30"]  = int(r.get("recent30", 0))
        r["bucket"]    = NO_HISTORY if not r["is_git"] else bucket(r["days"])
        r["domain"]    = DOMAIN_OF.get(r["name"], "Meta & Tooling")
        r["top_lang"]  = max(r["loc"], key=r["loc"].get) if r["loc"] else "-"
        r["published"] = bool(r.get("origin"))
        flags = []
        if r.get("dirty"): flags.append(("warning", f"{r['dirty']} uncommitted"))
        if r["is_git"] and not r["published"]: flags.append(("serious","no remote"))
        if not r["is_git"] and r["total_loc"] > 500: flags.append(("serious","not under git"))
        if r["days"] is not None and r["days"] > 90: flags.append(("critical", f"cold {r['days']}d"))
        r["flags"] = flags
    return d

CSS = r"""
:root{
  color-scheme: light;
  --bg:#f4f3f0; --surface-1:#fcfcfb; --surface-2:#eeede9; --line:#dedcd6;
  --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#83817a;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300;
  --other:#b4b2ab;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --accent:#2a78d6;
}
:root[data-theme="dark"], :root:where(:not([data-theme="light"])){}
@media (prefers-color-scheme: dark){
  :root:where(:not([data-theme="light"])){
    color-scheme: dark;
    --bg:#121211; --surface-1:#1a1a19; --surface-2:#232322; --line:#33332f;
    --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#8b8a80;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300;
    --other:#6a6960; --accent:#3987e5;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#121211; --surface-1:#1a1a19; --surface-2:#232322; --line:#33332f;
  --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#8b8a80;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300;
  --other:#6a6960; --accent:#3987e5;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--bg); color:var(--ink);
  font:14px/1.5 ui-sans-serif,-apple-system,"SF Pro Text","Helvetica Neue",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px;margin:0 auto;padding-block:40px 72px;padding-left:20px;padding-right:20px}
h1{font-size:30px;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em;font-weight:640}
h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink-3);
   margin:46px 0 14px;font-weight:640}
h3{font-size:13px;margin:22px 0 9px;font-weight:640;color:var(--ink-2);letter-spacing:.01em}
.sub{color:var(--ink-2);margin:0 0 4px;font-size:14px;max-width:62ch}
.meta{color:var(--ink-3);font-size:12px;margin-top:10px;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
.card{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:18px 20px}

/* KPI row */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(146px,1fr));gap:10px;margin-top:26px}
.kpi{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .v{font-size:28px;font-weight:660;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.1}
.kpi .k{font-size:11px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.07em;margin-top:5px}
.kpi .d{font-size:11px;color:var(--ink-2);margin-top:3px}

/* month columns */
.months{display:flex;align-items:flex-end;gap:2px;height:150px;margin-top:6px}
.mcol{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;
      height:100%;position:relative;cursor:default}
.mbar{width:100%;background:var(--s1);border-radius:4px 4px 0 0;min-height:2px;transition:filter .12s}
.mcol:hover .mbar{filter:brightness(1.15)}
.mcol.zero .mbar{background:var(--line)}
.mlab{white-space:nowrap;font-size:9.5px;color:var(--ink-3);margin-top:7px;font-variant-numeric:tabular-nums;
      writing-mode:vertical-rl;transform:rotate(180deg);letter-spacing:.02em}
.mval{position:absolute;top:-17px;font-size:10px;color:var(--ink-2);font-variant-numeric:tabular-nums}

/* map */
.legend{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:0 0 16px;font-size:11.5px;color:var(--ink-2)}
.legend .sw{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;
            vertical-align:-1px;border:1px solid rgba(128,128,128,.25)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:8px}
.tile{border-radius:10px;padding:11px 12px 10px;min-height:86px;display:flex;flex-direction:column;
      justify-content:space-between;border:1px solid rgba(0,0,0,.10);overflow:hidden;
      transition:transform .1s ease, box-shadow .1s ease}
.tile:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.18);z-index:2}
.tile.big{grid-column:span 2}
.tile .n{font-size:12.5px;overflow-wrap:anywhere;font-weight:640;line-height:1.25;word-break:break-word;letter-spacing:-.005em}
.tile .s{font-size:10.5px;opacity:.88;margin-top:4px;font-variant-numeric:tabular-nums;line-height:1.4}
.pips{display:flex;gap:4px;margin-top:7px;flex-wrap:wrap}
.pip{font-size:9px;padding:1.5px 5px;border-radius:999px;background:rgba(255,255,255,.22);
     border:1px solid rgba(255,255,255,.3);white-space:nowrap;font-weight:600;letter-spacing:.02em}
.tile.lt .pip{background:rgba(0,0,0,.07);border-color:rgba(0,0,0,.14)}
.tile .sp{display:flex;align-items:flex-end;gap:2px;height:26px;margin-top:8px;padding-top:4px}
.spark{display:inline-flex;align-items:flex-end;gap:1.5px;height:14px;margin-top:6px}
.spark i{flex:1;min-width:2px;background:currentColor;border-radius:1px 1px 0 0}


/* language stack */
.stack{display:flex;height:34px;border-radius:7px;overflow:hidden;gap:2px;background:transparent}
.seg{height:100%;min-width:3px}
.stack-labels{display:flex;flex-wrap:wrap;gap:12px;margin-top:11px;font-size:11.5px;color:var(--ink-2)}
.stack-labels b{color:var(--ink);font-weight:620;font-variant-numeric:tabular-nums}

/* attention */
.alist{display:grid;gap:7px}
.arow{display:flex;align-items:center;gap:11px;background:var(--surface-1);border:1px solid var(--line);
      border-radius:9px;padding:10px 13px}
.arow .ic{width:17px;text-align:center;flex:0 0 auto;font-size:12px}
.arow .nm{font-weight:620;font-size:12.5px;min-width:172px}
.arow .tx{color:var(--ink-2);font-size:12px}
.arow .rt{margin-left:auto;color:var(--ink-3);font-size:11px;font-variant-numeric:tabular-nums;
          white-space:nowrap;padding-left:12px}
.good{color:var(--good)} .warning{color:var(--warning)} .serious{color:var(--serious)} .critical{color:var(--critical)}

/* table */
.tools{display:flex;gap:9px;align-items:center;margin-bottom:11px;flex-wrap:wrap}
input[type=search]{background:var(--surface-1);border:1px solid var(--line);border-radius:8px;
  padding:7px 11px;color:var(--ink);font:inherit;font-size:12.5px;min-width:190px}
input[type=search]:focus{outline:2px solid var(--accent);outline-offset:1px}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface-1)}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
th{color:var(--ink-3);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;
   cursor:pointer;user-select:none;position:sticky;top:0;background:var(--surface-2);z-index:1}
th:hover{color:var(--ink)}
tbody tr:hover{background:var(--surface-2)}
tbody tr:last-child td{border-bottom:none}
td.nm{font-weight:600}
td.ol{max-width:300px;overflow:hidden;text-overflow:ellipsis;font-style:italic;color:var(--ink-2)}
td.br{max-width:132px;overflow:hidden;text-overflow:ellipsis}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:7px;vertical-align:0px}

/* read by a model - deliberately not styled like the measured sections */
.tile .ol{font-size:10px;opacity:.72;margin-top:5px;line-height:1.35;font-style:italic;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.genbar{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;background:var(--surface-2);
  border:1px dashed var(--line);border-radius:10px;padding:11px 14px;margin-bottom:14px;font-size:12px}
.genbar b{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3)}
.genbar .w{color:var(--ink-2)}
.cl{background:var(--surface-1);border:1px solid var(--line);border-left:3px solid var(--ink-3);
  border-radius:10px;padding:14px 16px;margin-bottom:9px}
.cl h4{margin:0 0 8px;font-size:13.5px;font-weight:640;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.call{font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
  padding:2.5px 8px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin:9px 0 8px}
.chip{font-size:11px;padding:3px 9px;border-radius:999px;background:var(--surface-2);
  border:1px solid var(--line);font-weight:560}
.cl p{margin:0;color:var(--ink-2);font-size:12.5px;line-height:1.5}
.cl p.why{margin-top:5px;color:var(--ink-3)}
.notes{margin:16px 0 0;padding-left:20px;color:var(--ink-2);font-size:12.5px}
.notes li{margin-bottom:6px}

/* tooltip */
#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;background:var(--surface-1);
  color:var(--ink);border:1px solid var(--line);border-radius:9px;padding:9px 11px;font-size:11.5px;
  box-shadow:0 8px 26px rgba(0,0,0,.28);z-index:99;max-width:270px;line-height:1.45}
#tip b{font-size:12.5px;display:block;margin-bottom:3px}
#tip .r{color:var(--ink-2);font-variant-numeric:tabular-nums}
.themebtn{margin-left:auto;background:var(--surface-1);border:1px solid var(--line);border-radius:8px;
  padding:7px 12px;color:var(--ink-2);font:inherit;font-size:12px;cursor:pointer}
.themebtn:hover{color:var(--ink)}
.foot{margin-top:54px;padding-top:18px;border-top:1px solid var(--line);color:var(--ink-3);font-size:11.5px}
@media (max-width:640px){
  .tile.big{grid-column:span 1}
  h1{font-size:23px}
  .arow{flex-wrap:wrap} .arow .nm{min-width:0} .arow .rt{margin-left:0;padding-left:28px}
  .mlab{font-size:8px}
}
"""

JS = r"""
const tip = document.getElementById('tip');
function showTip(e, h){ tip.innerHTML = h; tip.style.opacity = 1; moveTip(e); }
function moveTip(e){
  const pad = 14, w = tip.offsetWidth, hh = tip.offsetHeight;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > innerWidth - 8)  x = e.clientX - w - pad;
  if (y + hh > innerHeight - 8) y = e.clientY - hh - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip(){ tip.style.opacity = 0; }
document.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('mouseenter', e => showTip(e, el.dataset.tip));
  el.addEventListener('mousemove', moveTip);
  el.addEventListener('mouseleave', hideTip);
});

// table sort
document.querySelectorAll('#tbl th').forEach((th, i) => {
  th.addEventListener('click', () => {
    const tb = document.querySelector('#tbl tbody');
    const rows = [...tb.rows];
    const desc = th.dataset.dir !== 'desc';
    document.querySelectorAll('#tbl th').forEach(o => { if (o!==th) delete o.dataset.dir; });
    th.dataset.dir = desc ? 'desc' : 'asc';
    rows.sort((a, b) => {
      const av = a.cells[i].dataset.v, bv = b.cells[i].dataset.v;
      const an = parseFloat(av), bn = parseFloat(bv);
      const num = !isNaN(an) && !isNaN(bn) && av !== '' && bv !== '';
      let c = num ? an - bn : String(av).localeCompare(String(bv));
      return desc ? -c : c;
    });
    rows.forEach(r => tb.appendChild(r));
  });
});

// search
const box = document.getElementById('q');
box.addEventListener('input', () => {
  const q = box.value.toLowerCase().trim();
  let shown = 0;
  document.querySelectorAll('#tbl tbody tr').forEach(r => {
    const hit = !q || r.dataset.search.includes(q);
    r.style.display = hit ? '' : 'none'; if (hit) shown++;
  });
  document.querySelectorAll('.tile').forEach(t => {
    const hit = !q || t.dataset.search.includes(q);
    t.style.opacity = hit ? 1 : .12;
  });
  document.getElementById('count').textContent = shown + ' shown';
});

// theme
const btn = document.getElementById('theme');
btn.addEventListener('click', () => {
  const cur = document.documentElement.dataset.theme;
  const sysDark = matchMedia('(prefers-color-scheme: dark)').matches;
  const next = cur ? (cur === 'dark' ? 'light' : 'dark') : (sysDark ? 'light' : 'dark');
  document.documentElement.dataset.theme = next;
  btn.textContent = next === 'dark' ? 'Light mode' : 'Dark mode';
});
"""

def esc(s): return html.escape(str(s or ""))

def build(d):
    R = d["repos"]
    git = [r for r in R if r["is_git"]]
    total_loc  = sum(r["total_loc"] for r in R)
    total_code = sum(r["code_loc"] for r in R)
    commits    = sum(r.get("commits", 0) for r in git)
    months = Counter()
    for r in git:
        for k, v in r.get("months", {}).items(): months[k] += v
    span_lo, span_hi = (min(months), max(months)) if months else ("-", "-")
    touched_30 = len([r for r in git if r["days"] is not None and r["days"] <= 30])
    dirty_n    = len([r for r in git if r.get("dirty")])
    dirty_files= sum(r.get("dirty", 0) for r in git)

    o = []
    A = o.append
    A(f'<div class="wrap"><div class="tools" style="margin-bottom:0">'
      f'<div style="flex:1"><h1>REPOS Atlas</h1>'
      f'<p class="sub">Every project in your chosen folder &mdash; '
      f'what it is, how big it got, when you last touched it, and what is quietly unfinished.</p></div>'
      f'<button class="themebtn" id="theme">Toggle theme</button></div>')
    A(f'<div class="meta">Surveyed {esc(d["generated"][:16].replace("T"," "))} &nbsp;·&nbsp; '
      f'{len(R)} directories &nbsp;·&nbsp; {len(git)} git repositories</div>')

    # ---- KPI row
    kpis = [
      (human(total_code), "lines of code", f"+{human(sum(r['doc_loc'] for r in R))} lines of docs"),
      (str(len(R)), "projects", f"{len(git)} under git, {len(R)-len(git)} not"),
      (str(commits), "commits", f"{span_lo} &rarr; {span_hi}"),
      (str(touched_30), "active this month", f"of {len(git)} repos"),
      (str(dirty_n), "with uncommitted work", f"{dirty_files} files total"),
      (bytes_h(sum(r["bytes"] for r in R)), "on disk", f"{sum(r['files'] for r in R):,} files"),
    ]
    A('<div class="kpis">')
    for v, k, sub in kpis:
        A(f'<div class="kpi"><div class="v">{v}</div><div class="k">{k}</div><div class="d">{sub}</div></div>')
    A('</div>')

    # ---- Pulse
    A('<h2>Commit pulse</h2>')
    allm = []
    if months:
        y, m = map(int, span_lo.split("-")); ey, em = map(int, span_hi.split("-"))
        while (y, m) <= (ey, em):
            allm.append(f"{y:04d}-{m:02d}")
            m += 1
            if m == 13: y, m = y + 1, 1
    peak = max(months.values()) if months else 1
    A('<div class="card"><div class="months">')
    for k in allm:
        v = months.get(k, 0)
        hpct = (v / peak) * 100 if peak else 0
        zero = " zero" if v == 0 else ""
        vl = f'<span class="mval">{v}</span>' if v >= peak * .45 else ""
        A(f'<div class="mcol{zero}" data-tip="<b>{k}</b><span class=r>{v} commit'
          f'{"s" if v!=1 else ""}</span>">{vl}<div class="mbar" style="height:{hpct:.1f}%"></div>'
          f'<div class="mlab">{k}</div></div>')
    A('</div></div>')
    top3 = sorted(months.items())[-3:]
    if months:
        A(f'<div class="meta">Peak month: <b>{max(months, key=months.get)}</b> with {peak} commits. '
          f'The last three months hold {sum(v for _,v in top3)} of {commits} lifetime commits '
          f'({sum(v for _,v in top3)*100//max(commits,1)}%).</div>')
    else:
        A('<div class="meta">No commit history found in this survey.</div>')

    # ---- Map
    A('<h2>The map</h2>')
    A('<p class="sub">Grouped by what it is for. Tile shade shows how recently it moved &mdash; '
      'darker is fresher. Wider tiles carry more code.</p>')
    used = {r["bucket"] for r in R}
    A('<div class="legend"><span style="color:var(--ink-3)">last touched:</span>')
    for i, (_, lab) in enumerate(BUCKETS + [(None, "no history")]):
        if i not in used or i > NO_HISTORY: continue
        A(f'<span><span class="sw" style="background:{RAMP[i][0]}"></span>{lab}</span>')
    A('</div>')
    locs = sorted((r["total_loc"] for r in R), reverse=True)
    big_cut = locs[max(0, len(locs)//5)] if locs else 0
    for dom, _ in DOMAINS:
        members = sorted([r for r in R if r["domain"] == dom],
                         key=lambda r: (r["bucket"], -r["total_loc"]))
        if not members: continue
        dloc = sum(r["total_loc"] for r in members)
        A(f'<h3>{esc(dom)} <span style="color:var(--ink-3);font-weight:500">'
          f'&nbsp;{len(members)} projects · {human(dloc)} lines</span></h3><div class="grid">')
        for r in members:
            bg, fg = RAMP[r["bucket"]]
            lt = " lt" if r["bucket"] >= 4 else ""
            big = " big" if r["total_loc"] >= big_cut and big_cut > 0 else ""
            when = (f'{r["days"]}d ago' if r["days"] is not None else "no commits")
            pips = "".join(f'<span class="pip">{esc(t)}</span>' for _, t in r["flags"][:2])
            langs = ", ".join(list(r["loc"])[:3]) or "-"
            ol = r["brief"].get("one_liner")
            if ol:
                blurb = ('<span style="opacity:.75">read as</span> ' + esc(ol[:160]))
                does = r["brief"].get("does") or []
                if does:
                    blurb += "<br>" + esc(" · ".join(does[:3])[:170])
            else:
                blurb = esc(r["blurb"][:200]) if r["blurb"] else "<i>no README blurb</i>"
            tipbits = [f'<b>{esc(r["name"])}</b>', f'<span class=r>{esc(dom)}</span>',
                       f'<div style="margin:6px 0">{blurb}</div>',
                       f'<span class=r>{human(r["total_loc"])} lines · {r["files"]:,} files · {bytes_h(r["bytes"])}</span>']
            if r["is_git"]:
                born = f' · {r["age"]}d old' if r.get("age") is not None else ""
                tipbits.append(f'<br><span class=r>{r.get("commits",0)} commits · branch '
                               f'{esc(r.get("branch") or "?")} · last {when}{born}</span>')
                tipbits.append(f'<div style="margin-top:6px">{spark(r)} '
                               f'<span style="color:var(--ink-3);font-size:10px">'
                               f'{r["recent30"]} commits last 30d</span></div>')
                if r.get("last_subject"):
                    tipbits.append(f'<div style="margin-top:5px;opacity:.8">&ldquo;{esc(r["last_subject"][:90])}&rdquo;</div>')
            else:
                tipbits.append('<br><span class=r>not a git repository</span>')
            tipbits.append(f'<br><span class=r>{esc(langs)}</span>')
            # One escape for the tooltip HTML and another for its data attribute.
            tip = esc("".join(tipbits))
            search = (r["name"] + " " + dom + " " + langs + " " + r["blurb"]
                      + " " + (r["brief"].get("one_liner") or "")
                      + " " + " ".join(r["brief"].get("keywords") or []))
            A(f'<div class="tile{lt}{big}" style="background:{bg};color:{fg}" data-tip="{tip}" '
              f'data-search="{esc(search.lower())}">'
              f'<div><div class="n">{esc(r["name"])}</div>'
              f'<div class="s">{human(r["total_loc"])} lines · {when}'
              f'{" · " + str(r["recent30"]) + " commits/30d" if r["is_git"] and r["recent30"] else ""}</div>'
              + (f'<div class="ol">{esc(ol)}</div>' if ol else "")
              + (f'<div class="sp">{spark(r)}</div>' if r["is_git"] else "")
              + '</div>'
              f'<div class="pips">{pips}</div></div>')
        A('</div>')
    return o, R, git, months, commits

SERIES = ["var(--s1)","var(--s2)","var(--s3)","var(--s4)","var(--s5)","var(--s6)"]
CALL = {"keep-separate": ("good", "&#10003;", "keep separate"),
        "merge":         ("warning", "&#9679;", "merge"),
        "extract-shared":("serious", "&#9650;", "extract shared"),
        "archive-one":   ("critical", "&#9632;", "archive one")}
ICON = {"warning":"&#9679;","serious":"&#9650;","critical":"&#9632;","good":"&#10003;"}

def build_rest(o, R, git, months, commits):
    A = o.append
    # ---- language mix
    lang = Counter()
    for r in R:
        for k, v in r["loc"].items(): lang[k] += v
    top = lang.most_common(6)
    rest = sum(v for k, v in lang.items() if k not in dict(top))
    total = sum(lang.values()) or 1
    A('<h2>What it is written in</h2>')
    A('<div class="card"><div class="stack">')
    segs = list(top) + ([("Other", rest)] if rest else [])
    for i, (k, v) in enumerate(segs):
        c = SERIES[i] if i < len(SERIES) else "var(--other)"
        tip = esc(f'<b>{esc(k)}</b><span class=r>{v:,} lines · {v/total*100:.1f}%</span>')
        A(f'<div class="seg" style="background:{c};width:{v/total*100:.2f}%" '
          f'data-tip="{tip}"></div>')
    A('</div><div class="stack-labels">')
    for i, (k, v) in enumerate(segs):
        c = SERIES[i] if i < len(SERIES) else "var(--other)"
        A(f'<span><span class="sw" style="background:{c}"></span>{esc(k)} '
          f'<b>{human(v)}</b> <span style="color:var(--ink-3)">{v/total*100:.0f}%</span></span>')
    A('</div></div>')

    # ---- attention
    rank = {"critical": 0, "serious": 1, "warning": 2}
    items = []
    for r in R:
        for sev, txt in r["flags"]:
            items.append((rank[sev], sev, r, txt))
    items.sort(key=lambda t: (t[0], -t[2]["total_loc"]))
    A('<h2>Quietly unfinished</h2>')
    A('<p class="sub">Not errors &mdash; just the things a machine notices and a person forgets. '
      'Sorted by how much code is sitting behind each one.</p>')
    if not items:
        A('<div class="card">Nothing outstanding. Every repo is committed, remote-backed and warm.</div>')
    else:
        A('<div class="alist">')
        for _, sev, r, txt in items[:22]:
            note = {"critical": "no commits in over three months",
                    "serious": "lives only on this machine",
                    "warning": "changes on disk that are not committed"}[sev]
            A(f'<div class="arow"><span class="ic {sev}">{ICON[sev]}</span>'
              f'<span class="nm">{esc(r["name"])}</span>'
              f'<span class="tx"><b>{esc(txt)}</b> &mdash; {note}</span>'
              f'<span class="rt">{human(r["total_loc"])} lines</span></div>')
        A('</div>')
        if len(items) > 22:
            A(f'<div class="meta">&hellip; and {len(items)-22} more, all in the table below.</div>')

    # ---- read by a model
    syn = REVIEW.get("synthesis") or {}
    briefs = REVIEW.get("briefs", {})
    read = [b for b in briefs.values() if b.get("one_liner")]
    if read:
        A('<h2>Read by a local model</h2>')
        model = (REVIEW.get("model") or "").split("/")[-1]
        A(f'<div class="genbar"><b>generated</b><span class="w">'
          f'{esc(model)} &middot; {esc((REVIEW.get("generated") or "")[:10])} &middot; '
          f'{len(read)} of {len(R)} projects read locally. Everything in this section is a '
          f'model&rsquo;s reading of your code, not a measurement of it. Second opinion, not record.'
          f'</span></div>')
        # review.py already filters invented members, but the promise that a name
        # on this page is a real directory is made HERE, so it is enforced here.
        # review.json can be older than the survey, or hand-edited.
        real = {r["name"] for r in R}
        clusters = []
        for c in (syn.get("clusters") or []):
            c = dict(c, members=[m for m in (c.get("members") or []) if m in real])
            if len(c["members"]) >= 2:
                clusters.append(c)
        if clusters:
            A('<h3>Where projects overlap</h3>')
            for c in clusters:
                cls, icon, lab = CALL.get(c.get("call", ""), ("", "&#8226;", c.get("call", "?")))
                dom = f'<span style="color:var(--ink-3);font-weight:500;font-size:11.5px">{esc(c["domain"])}</span>' if c.get("domain") else ""
                A(f'<div class="cl"><h4>{esc(c.get("name","?"))}'
                  f'<span class="call {cls}">{icon} {esc(lab)}</span>{dom}</h4><div class="chips">')
                for m in c["members"]:
                    A(f'<span class="chip">{esc(m)}</span>')
                A('</div>')
                if c.get("evidence"): A(f'<p>{esc(c["evidence"])}</p>')
                if c.get("why"):      A(f'<p class="why">{esc(c["why"])}</p>')
                A('</div>')
        elif syn:
            A('<div class="card">The model found no two projects doing substantially the '
              'same work within the groups it reviewed.</div>')
        notes = syn.get("notes") or []
        if notes:
            A('<h3>What it noticed</h3><ul class="notes">')
            for n in notes[:4]:
                if isinstance(n, dict):
                    A(f'<li><b>{esc(n.get("domain",""))}</b> &mdash; {esc(n.get("text",""))}</li>')
                else:
                    A(f'<li>{esc(n)}</li>')
            A('</ul>')
        if not syn:
            A('<div class="meta">Briefs are in. Run <code>python3 review.py</code> again to '
              'add the cross-project pass.</div>')

    # ---- table
    A('<h2>Every project</h2>')
    A('<div class="tools"><input type="search" id="q" placeholder="Filter by name, language, topic&hellip;">'
      f'<span class="meta" id="count" style="margin:0">{len(R)} shown</span>'
      '<span class="meta" style="margin:0 0 0 auto">Click any column to sort</span></div>')
    cols = [("Project","nm"),("Domain","d"),("Lines","n"),("Code","n"),("Docs","n"),
            ("Commits","n"),("30d","n"),("Last","n"),("Uncommitted","n"),("Files","n"),("Size","n"),
            ("Branch","d"),("Top language","d"),("Reads as","d")]
    A('<div class="tblwrap"><table id="tbl"><thead><tr>')
    for c, _ in cols: A(f'<th>{c}</th>')
    A('</tr></thead><tbody>')
    for r in sorted(R, key=lambda r: -r["total_loc"]):
        bg = RAMP[r["bucket"]][0]
        days = r["days"]
        lastcell = f'{days}d' if days is not None else '&mdash;'
        cells = [
          (f'<span class="dot" style="background:{bg}"></span>{esc(r["name"])}', r["name"].lower(), "nm"),
          (esc(r["domain"]), r["domain"], ""),
          (human(r["total_loc"]), r["total_loc"], ""),
          (human(r["code_loc"]), r["code_loc"], ""),
          (human(r["doc_loc"]), r["doc_loc"], ""),
          (str(r.get("commits","")) if r["is_git"] else "&mdash;", r.get("commits",-1) if r["is_git"] else -1, ""),
          (str(r["recent30"]) if r["is_git"] else "&mdash;", r["recent30"] if r["is_git"] else -1, ""),
          (lastcell, days if days is not None else 99999, ""),
          (str(r.get("dirty",0)) if r["is_git"] else "&mdash;", r.get("dirty",0), ""),
          (f'{r["files"]:,}', r["files"], ""),
          (bytes_h(r["bytes"]), r["bytes"], ""),
          (esc(r.get("branch") or "&mdash;") if r["is_git"] else "&mdash;", r.get("branch",""), "br"),
          (esc(r["top_lang"]), r["top_lang"], ""),
          (esc(r["brief"].get("one_liner") or ""), r["brief"].get("one_liner") or "", "ol"),
        ]
        search = esc((r["name"] + " " + r["domain"] + " " + " ".join(r["loc"]) + " " + r["blurb"]
                      + " " + (r["brief"].get("one_liner") or "")
                      + " " + " ".join(r["brief"].get("keywords") or [])).lower())
        A(f'<tr data-search="{search}">')
        for txt, v, cls in cells:
            A(f'<td{(" class=" + cls) if cls else ""} data-v="{esc(v)}">{txt}</td>')
        A('</tr>')
    A('</tbody></table></div>')
    A(f'<div class="foot">Built by walking the selected project folder and reading its git history. '
      f'Regenerate with <code>python3 survey.py --root /path/to/projects &amp;&amp; python3 atlas.py</code>. '
      f'Sizes exclude <code>.git</code>, <code>node_modules</code>, virtualenvs, build output and vendored trees.</div>')
    A('</div><div id="tip"></div>')
    return o

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="store_true", help="render fictional sample data to demo.html")
    a = ap.parse_args()
    global DOMAINS, DOMAIN_OF, NOW
    if a.demo:
        DOMAINS = load_domains(os.path.join(HERE, "domains.example.json"))
        DOMAIN_OF = {n: group for group, names in DOMAINS for n in names}
        path = os.path.join(HERE, "examples", "survey.demo.json")
        with open(path, encoding="utf-8") as f:
            NOW = datetime.datetime.fromisoformat(json.load(f)["generated"])
        d = load(path, include_review=False)
    else:
        try:
            d = load()
        except FileNotFoundError:
            ap.error("no survey.json; run python3 survey.py --root /path/to/projects first")
    o, R, git, months, commits = build(d)
    if a.demo:
        o.insert(1, '<div class="meta">Demo: all project names, descriptions, and measurements are fictional.</div>')
    o = build_rest(o, R, git, months, commits)
    doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>REPOS Atlas</title><style>' + CSS + '</style></head><body>'
           + "".join(o) + '<script>' + JS + '</script></body></html>')
    out = os.path.join(HERE, "demo.html" if a.demo else "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"wrote {out}  ({len(doc)/1024:.0f} KB, {len(R)} projects)")

if __name__ == "__main__":
    main()
