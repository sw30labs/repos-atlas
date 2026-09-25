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

## Map your projects

```bash
python3 survey.py --root /path/to/projects
python3 atlas.py
```

Open `index.html` in your browser. Each immediate child directory is treated as a
project, whether or not it uses Git. With no `--root`, the survey uses `ATLAS_ROOT`
or the parent folder of these scripts, and skips repos-atlas itself.

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
Override them with `--base` / `--model` or `ATLAS_LLM_BASE` / `ATLAS_LLM_MODEL`.
Use the same settings on subsequent runs. Compatible local servers include
llama.cpp, LM Studio, vLLM, and Inferencer.

The reviewer uses the folder recorded in `survey.json`, including when you ran
`survey.py --root` elsewhere. It sends a bounded README excerpt, a short file
tree, recent commit subjects, and summary metadata to your chosen local server.
Only loopback HTTP(S) endpoints are accepted; proxies and redirects are disabled.
Use a model server you trust to keep prompts local—its own logging and network
behavior are outside this tool's control. See [SECURITY.md](SECURITY.md).

There are two passes: one brief per project, then overlap suggestions within
each group containing at least three briefs. Results are cached and written
after each batch. Changed evidence triggers a new brief; `--refresh` forces it.
`--budget` stops starting new work after the budget, while an in-flight request
can continue up to `--timeout`. There is no concurrency flag.

Model statements are labelled **generated**, stored in `review.json`, and kept
separate from measurements. Suggestions never change your repositories.

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
- Only immediate child folders are projects. Nested repositories and submodules
  are not separately indexed; Git worktrees with a `.git` file are treated as
  ordinary folders. Only the `origin` remote is recorded.
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

## License

Apache-2.0. See [LICENSE](LICENSE).
