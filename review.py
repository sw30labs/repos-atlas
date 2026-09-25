#!/usr/bin/env python3
"""Read every project with a local model and say what it actually is.

survey.py measures. This reads. Two passes against an OpenAI-compatible endpoint
served from your own machine - Inferencer, LM Studio, llama.cpp, vLLM, anything:

  1. map    one call per project -> one-liner, kind, stage, what it does, keywords
  2. reduce one call over all of them -> which projects overlap, and what to do

Writes review.json. atlas.py picks it up if it is there and ignores it if not.
Nothing leaves the machine. Stdlib only.

  python3 review.py                     # all projects, cached, resumable
  python3 review.py --limit 5           # taste test
  python3 review.py --model GLM-5.3     # something faster
  python3 review.py --only my-project --refresh
"""
import argparse, hashlib, ipaddress, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from urllib.parse import urlsplit, urlunsplit

from atlas import DOMAIN_OF, DOMAINS   # the grouping the page already uses

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("ATLAS_ROOT") or os.path.dirname(HERE)
DEFAULT_BASE = os.environ.get("ATLAS_LLM_BASE", "http://127.0.0.1:54321/v1")
DEFAULT_MODEL = os.environ.get("ATLAS_LLM_MODEL", "DeepSeek-V4.1")

# ---------------------------------------------------------------- transport

def local_url(url):
    """Accept only literal loopback addresses (localhost is normalized)."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
        if (parts.scheme not in ("http", "https") or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment):
            raise ValueError
        host = "127.0.0.1" if host == "localhost" else host
        address = ipaddress.ip_address(host)
        if not address.is_loopback:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("model endpoint must be an HTTP(S) loopback URL without credentials, query, or fragment") from None
    netloc = f"[{address}]" if address.version == 6 else str(address)
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError("model server redirects are disabled to keep evidence local")

def local_open(request, timeout):
    # Environment/system proxies must not forward private evidence off-machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    return opener.open(request, timeout=timeout)

def _post(url, payload, timeout):
    req = urllib.request.Request(
        local_url(url), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with local_open(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def _get(url, timeout=15):
    with local_open(local_url(url), timeout=timeout) as r:
        return json.loads(r.read().decode())

def resolve_model(base, want):
    """Turn 'DeepSeek-V4.1' into the id the server actually wants.

    Inferencer lists prompt-cache shards next to real models - dozens of
    'mlx_cache/DeepSeek-V4.1-MLX-Q4i_<hash>_v/0f' entries. They accept a request
    and return an empty completion, which looks like a model problem and is not.
    Real models never live under mlx_cache/, so drop those first.
    """
    ids = [m["id"] for m in _get(base.rstrip("/") + "/models")["data"]]
    real = [i for i in ids if not i.startswith("mlx_cache/")]
    hits = [i for i in real if want.lower() in i.lower()]
    if not hits:
        raise SystemExit(
            f"no model matching {want!r}. Loadable models on this server:\n  " +
            "\n  ".join(sorted(real) or ["(none)"]))
    return sorted(hits, key=len)[0]

def chat(base, model, system, user, max_tokens, timeout, retries=2, deadline=None):
    """One completion. Returns the assistant text, reasoning traces stripped.

    `system` is byte-identical on every call and `user` carries the variable
    part, so a server doing prefix caching gets a long shared prefix to reuse.
    """
    payload = {"model": model, "stream": False, "temperature": 0.2,
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    last = None
    for attempt in range(retries + 1):
        # A per-request timeout is not a budget: three retries of a 140s timeout is
        # seven minutes. Every attempt has to fit inside what is actually left.
        this = timeout
        if deadline is not None:
            left = deadline - time.time()
            if left < 5:
                raise RuntimeError(last or "deadline reached before the call")
            this = min(timeout, int(left))
        try:
            d = _post(base.rstrip("/") + "/chat/completions", payload, this)
            msg = d["choices"][0]["message"]
            # Reasoning models put their scratchpad in a sibling field, or inline
            # in <think> tags. Neither is the answer.
            text = msg.get("content") or ""
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
            if text.strip():
                return text, d.get("usage", {})
            last = "empty completion"
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < retries and (deadline is None or deadline - time.time() > 10):
            time.sleep(2 * (attempt + 1))
        else:
            break
    raise RuntimeError(last)

def chat_json(base, model, system, user, max_tokens, timeout, check, deadline=None):
    """chat() that insists on usable JSON. Reasoning models answer thin prompts
    with an essay, or echo the input back; one blunt re-ask is cheaper than
    losing the project. `check` decides what usable means."""
    text, usage = chat(base, model, system, user, max_tokens, timeout, deadline=deadline)
    obj = extract_json(text)
    if obj is not None and check(obj):
        return obj
    if deadline is not None and deadline - time.time() < 20:
        raise ValueError("unusable JSON and no time left to re-ask")
    nudge = (user + "\n\nYou replied with prose or echoed the input. Reply again with "
             "ONLY the JSON object described above: start at { and end at }. English only.")
    text, usage = chat(base, model, system, nudge, max_tokens, timeout, deadline=deadline)
    obj = extract_json(text)
    if obj is not None and check(obj):
        return obj
    raise ValueError("no usable JSON after a re-ask; reply began %r" % text.strip()[:70])

def pick_brief(obj, name):
    """Accept either {"<name>": {...}} or a bare {...} - both show up in practice."""
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("one_liner"), str):
        return obj
    v = obj.get(name)
    return v if isinstance(v, dict) and isinstance(v.get("one_liner"), str) else None

def extract_json(text):
    """First balanced {...} in the text.

    Models prepend 'Output', wrap things in ```json, or add a closing remark.
    Scanning for a balanced object survives all three; json.loads does not.
    """
    depth = start = 0
    instr = esc = False
    for i, c in enumerate(text):
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
            continue
        if c == '"': instr = True
        elif c == "{":
            if depth == 0: start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i + 1])
                except json.JSONDecodeError: depth = 0
    return None

# ---------------------------------------------------------------- evidence

def _git(path, args):
    try:
        r = subprocess.run(["git", "--no-optional-locks"] + args, cwd=path,
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

SKIP = {".git", "node_modules", "__pycache__", "dist", "build", "target",
        "vendor", "generated", ".venv", "venv"}

def tree(path, depth=2):
    out = []
    for dirpath, dirnames, filenames in os.walk(path):
        rel = os.path.relpath(dirpath, path)
        d = 0 if rel == "." else rel.count(os.sep) + 1
        if d >= depth:
            dirnames[:] = []
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP and not d.startswith("."))
        keep = sorted(f for f in filenames if not f.startswith("."))[:14]
        out.append(("" if rel == "." else rel + "/") + " ".join(keep))
        if len(out) > 26: break
    return "\n".join(l for l in out if l.strip())[:1000]

def evidence(rec, root=None):
    """Everything the model gets about one project. Capped, so a huge repo and a
    tiny one cost about the same."""
    root = os.path.realpath(os.path.expanduser(root or ROOT))
    name = rec["name"]
    if not name or name in (".", "..") or os.path.basename(name) != name:
        raise ValueError("survey project names must be immediate child directories")
    path = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, path]) != root:
        raise ValueError("project resolves outside the surveyed folder")
    parts = [f"name: {rec['name']}"]
    for fn in ("README.md", "readme.md", "README.rst", "README.txt"):
        p = os.path.join(path, fn)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="ignore") as f:
                parts.append("README (truncated):\n" + f.read(1400))
            break
    else:
        parts.append("README: none")
    if rec.get("loc"):
        parts.append("languages by line count: " + ", ".join(
            f"{k} {v}" for k, v in list(rec["loc"].items())[:6]))
    if rec.get("markers"):
        parts.append("markers: " + ", ".join(rec["markers"]))
    if rec.get("is_git"):
        log = _git(path, ["log", "-5", "--format=- %s"])
        if log: parts.append("recent commits:\n" + log[:500])
    parts.append("file tree (2 levels):\n" + tree(path))
    return "\n\n".join(parts)

# ---------------------------------------------------------------- prompts

BRIEF_SYSTEM = """You read source repositories and report what they are. You are
terse, concrete and unimpressed. You never market. You always answer in English.

You are given one or more projects, each introduced by a line of the form
=== PROJECT: <name> ===

Return ONE JSON object and nothing else, with one entry per project you were
given, keyed by its exact name:

{
  "<exact project name>": {
    "one_liner": "what it is, max 14 words, no adjectives like powerful or seamless",
    "kind":  "library|cli|service|dashboard|pipeline|dataset|docs|experiment|config",
    "stage": "sketch|working|shipped",
    "does":  ["concrete capability", "another", "at most three"],
    "keywords": ["5-8", "lowercase", "single", "words", "for", "matching"],
    "confidence": "high|medium|low"
  }
}

Rules:
- One entry per project given. Never merge two projects, never add one.
- Judge each project only on its own evidence. They are unrelated.
- Describe what the code does, not what the README claims it will do.
- stage: "sketch" = scaffolding or notes; "working" = runs and does the thing;
  "shipped" = tagged, documented, packaged or clearly in use.
- confidence "low" if the evidence is thin. Say so rather than inventing.
- Never repeat the project name inside one_liner.
- Think briefly. These are short judgements, not essays.
"""

SYNTH_SYSTEM = """You are given one-line descriptions of the projects one
engineer keeps in a single area of their work. Find the real overlaps.

An overlap is two or more projects that do substantially the SAME WORK - not
projects that merely share a topic or a language. "Both use Python" is not an
overlap. "Both implement a discover -> rank -> render newsletter pipeline" is.

Return ONE JSON object and nothing else:

{
  "clusters": [
    {
      "name": "short name for what they have in common",
      "members": ["exact-project-names", "from-the-list"],
      "evidence": "one sentence citing what specifically is duplicated",
      "call": "merge|keep-separate|extract-shared|archive-one",
      "why": "one sentence, honest, may say the split is justified"
    }
  ],
  "notes": ["at most ONE observation about this area as a whole"]
}

Rules:
- Use project names EXACTLY as given. Never invent a name.
- At most 3 clusters. Fewer is better. A cluster needs >= 2 members. Zero is a
  valid answer: return {"clusters": [], "notes": [...]}.
- Be brief. One sentence each for evidence and why. Do not restate the list.
- "keep-separate" is a legitimate call. Do not manufacture consolidation.
- notes: patterns worth saying out loud, not compliments.
- Do NOT compare every pair. Scan the list once for the obvious duplicates,
  report those, and stop. This is a shortlist, not an exhaustive analysis.
- Think briefly. Long deliberation here is wasted; the answer is either obvious
  from the one-liners or it is not there.
"""

# ---------------------------------------------------------------- passes

def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception: return default

def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)

def fingerprint(rec, ev):
    return hashlib.sha256((rec.get("last", "") + str(rec.get("commits", "")) +
                           ev).encode()).hexdigest()[:16]

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help="OpenAI-compatible endpoint")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="substring of the model id")
    ap.add_argument("--limit", type=int, help="only the first N projects needing work")
    ap.add_argument("--only", action="append", help="only this project (repeatable)")
    ap.add_argument("--refresh", action="store_true", help="ignore cached briefs")
    ap.add_argument("--batch", type=int, default=1,
                    help="projects per model call (default 1). Batching amortises thinking "
                         "time, but DeepSeek-V4.1 starts echoing input above ~2 - raise it "
                         "only if your model holds up.")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per call")
    ap.add_argument("--budget", type=int,
                    help="stop starting new batches once N seconds have passed. A batch "
                         "already in flight is allowed to finish - abandoning it would not "
                         "stop the server generating it, only hide the result.")
    ap.add_argument("--no-synthesis", action="store_true", help="skip the overlap pass")
    ap.add_argument("--synthesis-only", action="store_true",
                    help="re-run just the cross-project pass over the briefs already read")
    a = ap.parse_args()
    try:
        a.base = local_url(a.base)
    except ValueError as e:
        ap.error(str(e))

    survey = load(os.path.join(HERE, "survey.json"), None)
    if not survey:
        raise SystemExit("no survey.json - run: python3 survey.py")

    model = resolve_model(a.base, a.model)
    out_path = os.path.join(HERE, "review.json")
    out = load(out_path, {})
    briefs = out.get("briefs", {})

    todo = [] if a.synthesis_only else survey["repos"]
    if a.only:
        want = {o.lower() for o in a.only}
        todo = [r for r in todo if r["name"].lower() in want]
    print(f"model   {model}\nserver  {a.base}\nprojects {len(todo)}\n")

    queued, t0, done, failed = [], time.time(), 0, 0
    deadline = None
    for rec in todo:
        ev = evidence(rec, root=survey.get("root") or ROOT)
        fp = fingerprint(rec, ev)
        if not a.refresh and briefs.get(rec["name"], {}).get("fingerprint") == fp:
            continue
        if len(ev) < 220:
            briefs[rec["name"]] = {"skipped": "too little on disk to read",
                                   "fingerprint": fp, "model": None}
            continue
        queued.append((rec, ev, fp))
    if a.limit: queued = queued[:a.limit]
    print(f"{len(queued)} need reading, {len(todo) - len(queued)} cached\n")

    batches = [queued[i:i + max(1, a.batch)] for i in range(0, len(queued), max(1, a.batch))]
    for bi, batch in enumerate(batches, 1):
        call_timeout = a.timeout
        if a.budget:
            # a deadline that only gates the START of a project is not a deadline:
            # one slow project sails straight past it. Shrink the HTTP timeout to
            # whatever is left, and stop when there is not enough left to try.
            left = a.budget - (time.time() - t0)
            if left <= 0:
                remaining = sum(len(b) for b in batches[bi - 1:])
                print(f"\n-- budget reached, {remaining} left. Run again to continue.")
                break
            deadline = None
        t = time.time()
        names = [r["name"] for r, _, _ in batch]
        label = f"[{bi}/{len(batches)}] {len(batch)}x"
        user = "\n\n".join(f"=== PROJECT: {r['name']} ===\n{ev}" for r, ev, _ in batch)
        try:
            obj = chat_json(a.base, model, BRIEF_SYSTEM, user, 500 + 300 * len(batch),
                            call_timeout,
                            lambda o: any(pick_brief(o, n) for n in names), deadline)
            got = 0
            for rec, _, fp in batch:
                one = pick_brief(obj, rec["name"])
                if one is None:
                    failed += 1
                    print(f"      {rec['name']:<38} missing from reply")
                    continue
                one["fingerprint"] = fp; one["model"] = model
                briefs[rec["name"]] = one
                done += 1; got += 1
                print(f"      {rec['name']:<38} {one['one_liner'][:54]}")
            print(f"{label:<44} {time.time()-t:5.1f}s  {got}/{len(batch)} read")
        except Exception as e:
            failed += len(batch)
            print(f"{label:<44} {time.time()-t:5.1f}s  FAILED {e}")
        # write after every project: a 70-minute run must never lose work
        out = {"briefs": briefs, "model": model, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               **({"synthesis": out["synthesis"]} if "synthesis" in out else {})}
        save(out_path, out)

    if not a.no_synthesis and briefs:
        # One call over fifty projects asks the model to consider 1,225 pairs, and
        # it will try. Overlap lives inside a family of work - two newsletter
        # pipelines, two threat-model tools - so ask one family at a time. Smaller
        # prompts, sharper answers, and each group caches on its own.
        syn = out.get("synthesis") or {"clusters": [], "notes": [], "scope": "per-domain"}
        by_dom = {}
        for n, b in sorted(briefs.items()):
            if b.get("one_liner"):
                by_dom.setdefault(DOMAIN_OF.get(n, "Meta & Tooling"), []).append((n, b))
        done_doms = {c.get("domain") for c in syn["clusters"]} | set(syn.get("empty", []))
        groups = sorted([(d, m) for d, m in by_dom.items()
                         if len(m) >= 3 and d not in done_doms], key=lambda g: len(g[1]))
        print(f"\noverlaps: {len(groups)} groups to look at, "
              f"{len(by_dom) - len(groups)} already done or too small")
        for dom, members in groups:
            if a.budget and time.time() - t0 > a.budget:
                print("-- budget reached; run again to finish the overlap pass")
                break
            listing = "\n".join(f"{n}: {b['one_liner']} [{b.get('kind','?')}]"
                                 for n, b in members)
            t = time.time()
            try:
                got = chat_json(a.base, model, SYNTH_SYSTEM, listing, 900, a.timeout,
                                lambda o: isinstance(o.get("clusters"), list))
                known = {n for n, _ in members}
                kept = []
                for c in got.get("clusters", []):
                    # models invent members; only names in THIS group are allowed
                    c["members"] = [m for m in c.get("members", []) if m in known]
                    if len(c["members"]) >= 2:
                        c["domain"] = dom
                        kept.append(c)
                syn["clusters"].extend(kept)
                for note in (got.get("notes") or [])[:1]:
                    syn["notes"].append({"domain": dom, "text": note})
                if not kept:
                    syn.setdefault("empty", []).append(dom)
                print(f"  {dom:<32} {time.time()-t:5.1f}s  {len(kept)} cluster(s)")
            except Exception as e:
                print(f"  {dom:<32} {time.time()-t:5.1f}s  FAILED {e}")
            syn["model"] = model
            out["synthesis"] = syn
            save(out_path, out)

    print(f"\n{done} read, {failed} failed, {time.time()-t0:.0f}s total -> {out_path}")
    print("now run: python3 atlas.py")

if __name__ == "__main__":
    main()
