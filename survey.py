#!/usr/bin/env python3
"""Walk every project under the parent directory and record what it is.

Writes survey.json beside this file. Read-only: uses --no-optional-locks so it can
never leave a stale .git/index.lock in a repo it inspected.

  python3 survey.py                  # map the parent directory
  python3 survey.py --root ~/work    # map somewhere else (or ATLAS_ROOT=~/work)
  python3 survey.py --quiet          # only the summary line on stderr
"""
import argparse, os, subprocess, json, sys, time
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

HERE = os.path.dirname(os.path.abspath(__file__))

LANG = {
 ".py":"Python",".ipynb":"Notebook",".js":"JavaScript",".mjs":"JavaScript",".cjs":"JavaScript",
 ".ts":"TypeScript",".tsx":"TypeScript",".jsx":"JavaScript",".go":"Go",".rs":"Rust",
 ".swift":"Swift",".c":"C",".h":"C",".cpp":"C++",".cc":"C++",".hpp":"C++",".m":"Obj-C",
 ".java":"Java",".kt":"Kotlin",".rb":"Ruby",".php":"PHP",".sh":"Shell",".bash":"Shell",
 ".zsh":"Shell",".md":"Markdown",".html":"HTML",".css":"CSS",".scss":"CSS",
 ".yml":"YAML",".yaml":"YAML",".json":"JSON",".toml":"TOML",".sql":"SQL",
 ".scad":"OpenSCAD",".stl":"3D",".step":"3D",".f3d":"3D",".tex":"TeX",".lua":"Lua",
 ".ex":"Elixir",".r":"R",".jl":"Julia",".hcl":"HCL",".tf":"Terraform",".proto":"Proto",
}
CODE = {"Python","JavaScript","TypeScript","Go","Rust","Swift","C","C++","Obj-C","Java",
        "Kotlin","Ruby","PHP","Shell","SQL","Lua","Elixir","R","Julia","OpenSCAD"}

# Directories that hold somebody else's code, or machine output. Counting these
# is what turns "my project" into "a Python distribution with a project in it".
SKIP_NAMES = {
 "node_modules","site-packages","vendor","third_party","thirdparty","bower_components",
 "dist","build","out","target","generated","_build","cmake-build-debug",
 "__pycache__","env","venv","envs","miniconda3","anaconda3","Pods","Carthage",
 "DerivedData","bin","obj","coverage","htmlcov",
}
def is_env(path):
    """A virtualenv / conda env announces itself. Trust that over any name list."""
    for marker in ("pyvenv.cfg", "conda-meta"):
        if os.path.exists(os.path.join(path, marker)): return True
    return False

def prune(dirpath, dirnames):
    keep = []
    for d in dirnames:
        if d in SKIP_NAMES: continue
        # dot-directories are config, cache and environments - never source.
        if d.startswith(".") and d != ".github": continue
        if d.endswith(".egg-info") or d.endswith(".dist-info"): continue
        if is_env(os.path.join(dirpath, d)): continue
        keep.append(d)
    return keep

def run(args, cwd, timeout=25):
    if args and args[0] == "git":
        args = ["git", "--no-optional-locks"] + args[1:]
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

def readme_blurb(path):
    for name in ("README.md","readme.md","README.MD","README.rst","README.txt","README"):
        p = os.path.join(path, name)
        if not os.path.isfile(p): continue
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f.read(8000).splitlines()]
        except Exception:
            return ""
        out = []
        for l in lines:
            if not l or l.startswith(("#","![","[![","---","===","<","|",">")): continue
            out.append(l)
            if len(" ".join(out)) > 180: break
        return " ".join(out)[:260]
    return ""

def redact_origin(origin):
    """Drop URL credentials, query strings and fragments before saving a remote."""
    if "://" not in origin:
        return origin
    try:
        parts = urlsplit(origin)
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parts.port is not None:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return "[invalid remote URL]"

def walk(path):
    exts, loc = Counter(), Counter()
    nfiles = nbytes = 0
    markers = set()
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = prune(dirpath, dirnames)
        rel = os.path.relpath(dirpath, path)
        if os.path.basename(dirpath).lower() in ("test","tests","spec","__tests__"):
            markers.add("tests")
        if rel.startswith(".github"): markers.add("ci")
        for fn in filenames:
            nfiles += 1
            fl = fn.lower()
            if fl in ("dockerfile","docker-compose.yml","docker-compose.yaml"): markers.add("docker")
            if fl in ("license","license.md","license.txt","copying"): markers.add("license")
            if fl in ("pyproject.toml","setup.py","package.json","cargo.toml","go.mod"): markers.add("packaged")
            if fl == "makefile": markers.add("make")
            if fl == "skill.md": markers.add("skill")
            if fl.startswith("test_") or fl.endswith("_test.py"): markers.add("tests")
            fp = os.path.join(dirpath, fn)
            try: sz = os.path.getsize(fp)
            except OSError: sz = 0
            nbytes += sz
            lang = LANG.get(os.path.splitext(fn)[1].lower())
            if not lang: continue
            exts[lang] += 1
            if (lang in CODE or lang == "Markdown") and sz < 2_000_000:
                try:
                    with open(fp, "rb") as f: loc[lang] += f.read().count(b"\n") + 1
                except OSError: pass
    return exts, loc, nfiles, nbytes, markers

def survey(ROOT, quiet=False):
    repos = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path) or name.startswith("."): continue
        if os.path.realpath(path) == os.path.realpath(HERE): continue  # don't survey ourselves
        isgit = os.path.isdir(os.path.join(path, ".git"))
        exts, loc, nfiles, nbytes, markers = walk(path)
        r = {"name": name, "is_git": isgit, "files": nfiles, "bytes": nbytes,
             "langs": dict(exts.most_common(8)), "loc": dict(loc.most_common(8)),
             "markers": sorted(markers), "blurb": readme_blurb(path)}
        if isgit:
            n = run(["git","rev-list","--count","HEAD"], path)
            r["commits"]      = int(n) if n.isdigit() else 0
            r["branch"]       = run(["git","rev-parse","--abbrev-ref","HEAD"], path)
            r["origin"]       = redact_origin(run(["git","config","--get","remote.origin.url"], path))
            r["last"]         = run(["git","log","-1","--format=%cI"], path)
            r["born"]         = run(["git","log","--format=%cI"], path).split("\n")[-1]
            r["last_subject"] = run(["git","log","-1","--format=%s"], path)[:140]
            r["authors"]      = [a for a,_ in Counter(
                [a for a in run(["git","log","--format=%an"], path).split("\n") if a]).most_common(6)]
            r["dirty"]        = len([l for l in run(["git","status","--porcelain"], path).split("\n") if l.strip()])
            r["months"]       = dict(Counter([d for d in run(
                ["git","log","--format=%cd","--date=format:%Y-%m"], path).split("\n") if d]))
            r["recent30"]     = int(run(["git","rev-list","--count","--since=30.days.ago","HEAD"], path) or 0)
            r["tags"]         = len([t for t in run(["git","tag"], path).split("\n") if t])
        repos.append(r)
        if not quiet: print("  ok", name, file=sys.stderr)
    out = os.path.join(HERE, "survey.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "root": ROOT, "repos": repos}, f, indent=1)
    print(f"surveyed {len(repos)} projects under {ROOT} -> {out}")

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.environ.get("ATLAS_ROOT") or os.path.dirname(HERE),
                    help="folder of repos to map (default: parent of this script)")
    ap.add_argument("--quiet", action="store_true", help="only the summary line")
    a = ap.parse_args()
    ROOT = os.path.realpath(os.path.expanduser(a.root))
    survey(ROOT, a.quiet)

if __name__ == "__main__":
    main()
