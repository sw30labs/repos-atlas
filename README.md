# repos-atlas

[![CI](https://github.com/sw30labs/repos-atlas/actions/workflows/ci.yml/badge.svg)](https://github.com/sw30labs/repos-atlas/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Dependencies](https://img.shields.io/badge/runtime_dependencies-none-1baf7a)](#requirements)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)

**A local map of your projects: what they are, how big they got, when they last
moved, and what is quietly unfinished.**

Point it at a folder of repositories. It reads files and Git history, then writes
one self-contained HTML page with a commit-pulse chart, project map, language
mix, attention list, and searchable, sortable table. An optional local model can
summarize projects and suggest where their work overlaps.

The [bundled demo data](examples/survey.demo.json) uses fictional project names
and measurements. Render it with the command below before scanning your own repos.

## Requirements

- Python 3.10 or newer and Git on your PATH.
- A browser for the generated page. No server, package install, CDN, or account.
- Optional: an OpenAI-compatible model server on the same machine.

The scripts use only the Python standard library. CI covers Linux, macOS, and
Windows. On Windows, use `python` if `python3` is not available.

## Try the demo

```bash
git clone https://github.com/sw30labs/repos-atlas.git
cd repos-atlas
python3 atlas.py --demo
```

Open `demo.html` in your browser. This uses only the included fictional fixture;
it does not scan your folders or read a local model's output. On macOS, run
`open demo.html`; on Linux, `xdg-open demo.html`; on Windows, `start demo.html`.
On a POSIX machine, `./setup_and_run.sh --demo` renders that page and opens it.

## Map your projects

```bash
python3 survey.py --root /path/to/projects
python3 atlas.py
```

Open `index.html` in your browser. Every Git repo under the root is a project, at
any depth, so a folder that groups repos (`clients/acme-api`) is searched through
and its repos are listed by relative path. A top-level folder with no repo inside
is still a project of its own. With no `--root`, the survey uses `ATLAS_ROOT`
or the parent folder of these scripts, and skips repos-atlas itself.

On a POSIX machine, `./setup_and_run.sh --root /path/to/projects` checks Python
3.10+ and Git, runs the unit tests, surveys, renders, and opens the page.
`./setup_and_run.sh --help` lists `--setup-only`, `--no-tests`, `--no-browser`,
`--quiet`, and `--review`. Arguments after `--` are passed to `review.py`.

```bash
python3 survey.py --root ~/work --quiet
# Or, in a POSIX shell:
ATLAS_ROOT=~/work python3 survey.py
```

The walk and the render are separate so changing the page does not require
re-reading all your repositories. Outputs are written beside the scripts.

**Keep your generated files private.** `survey.json`, `review.json`, `index.html`,
and your optional `domains.json` can reveal project names, local paths, authors,
README excerpts, and commit subjects. Git ignores these files; it does not
anonymize them. Use `--demo` for public screenshots and examples.

## Group projects

By default, all projects appear in **Meta & Tooling**. Copy
[`domains.example.json`](domains.example.json) to `domains.json`, then replace
the fictional entries with your directory names:

```json
{
  "Apps": ["my-api", "my-dashboard"],
  "Research": ["my-experiment"]
}
```

Names match exactly; unlisted projects stay in Meta & Tooling. Each project may
belong to one group. Both the page and model overlap pass use this configuration.
`domains.json` stays local and is ignored by Git.

## Read it with a local model

Run the survey first, then start a model server on your machine and choose a
substring of a loaded model's ID:

```bash
python3 review.py --base http://127.0.0.1:54321/v1 --model your-loaded-model --limit 5
python3 review.py --budget 1200
python3 review.py --only my-project --refresh
python3 review.py --synthesis-only
python3 atlas.py
```

Defaults are `http://127.0.0.1:54321/v1` and a model matching `DeepSeek-V4.1`.
Override them with `--base` / `--model` or `ATLAS_LLM_BASE` / `ATLAS_LLM_MODEL`,
set in the shell or in a `.env` beside the scripts (see `.env.example`; real
environment variables win). Use the same settings on subsequent runs. Compatible
local servers include llama.cpp, LM Studio, vLLM, and Inferencer.

### OpenAI

```bash
cp .env.example .env    # sets https://api.openai.com/v1 and gpt-6-luna; add OPENAI_API_KEY
python3 review.py --limit 5
```

With `ATLAS_LLM_BASE=https://api.openai.com/v1` the evidence described below
**leaves your machine** for OpenAI, and each run prints a `CLOUD:` line saying so
before the first call. `api.openai.com` is the only remote endpoint accepted; the
key is sent only there, never to a local server. Pass `--base
http://127.0.0.1:<port>/v1` to keep a single run local. The page names where the
reading happened in the generated banner.

The reviewer uses the folder recorded in `survey.json`, including when you ran
`survey.py --root` elsewhere. It sends a bounded README excerpt, a short file
tree, recent commit subjects, and summary metadata to your chosen endpoint.
Only loopback HTTP(S) endpoints and `https://api.openai.com` are accepted;
proxies and redirects are disabled. A local server's logging and network
behavior, and OpenAI's data handling, are outside this tool's control. See [SECURITY.md](SECURITY.md).

Each brief also records the one next step, the distance to usable (days, weeks,
months) and any blocker the evidence shows. Then come overlap suggestions within
each group containing at least three briefs. Results are cached and written
after each batch. Changed evidence triggers a new brief; `--refresh` forces it.
`--budget` stops starting new work after the budget, while an in-flight request
can continue up to `--timeout`. There is no concurrency flag.

Model statements are labelled **generated**, stored in `review.json`, and kept
separate from measurements. Suggestions never change your repositories.

### Focus next and Let go

Copy `goals.example.md` to `goals.md` (ignored by Git) and write what you are
trying to get done. `review.py` then scores each project 0-3 against those goals,
and the page gains two panels at the top of the generated section:

- **Focus next** ranks read projects by goal fit &times; momentum &times; stage
  &times; distance to usable, nudged up for work that is uncommitted or never
  pushed. Hover a score to see each factor. The model picks up to three from
  the top five and says why now. Without `goals.md`, every project gets the same
  neutral goal fit.
- **Let go** lists archive candidates. Measured reasons: a name like
  `-todelete` or `-old`, an empty repo, an older variant of a sibling that kept
  moving, months without a commit. Read reasons: never past a sketch, outside
  every goal, duplicated by another project. It warns when a candidate is the
  only copy.

Changing `goals.md` re-scores goal fit only; briefs stay cached. `--no-focus`
skips both passes. See [ADR-006](docs/adr/ADR-006-focus-is-arithmetic.md).

## What it measures

| Measure | Meaning |
|---|---|
| Lines | Newline-based counts for recognized code and Markdown files under 2 MB |
| Recency | Days since the latest commit; darker tiles are more recent |
| Momentum | Commits in the last 30 days and a 12-month commit sparkline |
| Age | Days since the oldest reachable commit in the current history |
| Attention | Uncommitted work, missing origin, unversioned code, or no commits for 90+ days |
| Shape | Files, bytes, languages, branch, README blurb, and monthly commit counts |

The survey prunes dependency and build directories and detects Python/Conda
environments by marker files. Every Git call uses `--no-optional-locks`. The tools
do not fetch, push, stage, commit, or intentionally write inside inspected repos.

## Limits

- Counts are approximate, based on extensions and newlines, not a code parser.
- The scan does not honor `.gitignore`. Dot-directories other than `.github` are
  skipped; the named dependency/build exclusions are in `survey.py`.
- The search stops at the first repo on each path: repos nested inside another
  repo, and submodules, count toward their parent. Git worktrees and submodules
  with a `.git` file are recognized as repos. Only the `origin` remote is recorded.
- Existing shallow history limits commit totals and age. Git commands that time
  out or fail produce empty metadata; large histories can therefore be incomplete.
- A configured remote is not proof of a backup or a public repository.
- The page is a snapshot. Re-run the survey and render to refresh it.
- Model output can be wrong or stale. Review it before making any decision.

## Development

```bash
python3 -m unittest -v
python3 atlas.py --demo
```

Tests cover parsing, formatting, grouping, local HTTP restrictions, HTML escaping,
and a real temporary Git repository. They do not need a model or your project
folder. See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow and
[SECURITY.md](SECURITY.md) for vulnerability reporting.

## Design decisions

- [One static file](docs/adr/ADR-001-one-static-file.md)
- [Read-only survey](docs/adr/ADR-002-survey-does-not-mutate.md)
- [Environment pruning by marker](docs/adr/ADR-003-prune-environments-by-marker.md)
- [Model readings separate from measurements](docs/adr/ADR-004-reading-is-not-measuring.md)
- [Local reasoning-server behavior](docs/adr/ADR-005-local-reasoning-server-contract.md)
- [Focus is arithmetic over readings](docs/adr/ADR-006-focus-is-arithmetic.md)
- [OpenAI as an opt-in endpoint](docs/adr/ADR-007-openai-endpoint.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
