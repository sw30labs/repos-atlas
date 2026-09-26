#!/usr/bin/env bash
# Survey a folder of projects, render the atlas, and open it.
#
# Usage:
#   ./setup_and_run.sh                         # parent folder -> index.html
#   ./setup_and_run.sh --root ~/work
#   ./setup_and_run.sh --demo                  # fictional demo.html, no scan
#   ./setup_and_run.sh --setup-only            # Python, Git, and unit tests
#   ./setup_and_run.sh --no-tests --no-browser --quiet
#   ./setup_and_run.sh --review -- --limit 5   # then the local model pass
#   ./setup_and_run.sh --help
#
# Env: PYTHON_BIN (3.10+), ATLAS_ROOT, ATLAS_LLM_BASE, ATLAS_LLM_MODEL.
# Arguments after -- are passed to review.py. Stdlib only.
# The survey does not write inside the repos it reads.
set -euo pipefail

cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

SETUP_ONLY=0
RUN_TESTS=1
OPEN_BROWSER=1
QUIET=0
DEMO=0
REVIEW=0
ROOT=""
REVIEW_ARGS=()

usage() { awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; }

die() { echo "ERROR: $*" >&2; exit 2; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --setup-only) SETUP_ONLY=1 ;;
    --no-tests) RUN_TESTS=0 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --quiet) QUIET=1 ;;
    --demo) DEMO=1 ;;
    --review) REVIEW=1 ;;
    --root)
      [ "$#" -ge 2 ] && [ -n "${2:-}" ] || die "--root needs a folder"
      ROOT="$2"
      shift
      ;;
    --)
      shift
      if [ "$#" -gt 0 ]; then
        REVIEW_ARGS=("$@")
      fi
      REVIEW=1
      break
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option '$1' (try --help)" ;;
  esac
  shift
done

if [ "$DEMO" -eq 1 ] && [ "$REVIEW" -eq 1 ]; then
  die "--demo does not read a model; drop --review"
fi
if [ "$DEMO" -eq 1 ] && [ -n "$ROOT" ]; then
  die "--demo does not survey a folder; drop --root"
fi

say() { [ "$QUIET" -eq 1 ] || echo "==> $*"; }

if [ -n "${PYTHON_BIN:-}" ]; then
  if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "ERROR: PYTHON_BIN must be Python 3.10 or newer." >&2
    exit 1
  fi
else
  PYTHON_BIN=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
  if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: Install Python 3.10+ or set PYTHON_BIN." >&2
    exit 1
  fi
fi

say "Using $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: Git is required on PATH." >&2
  exit 1
fi

if [ "$RUN_TESTS" -eq 1 ]; then
  say "Running unit tests"
  "$PYTHON_BIN" -m unittest
  say "Tests passed"
fi

if [ "$SETUP_ONLY" -eq 1 ]; then
  say "Setup checks finished"
  exit 0
fi

open_page() {
  local page="$1"
  if [ "$OPEN_BROWSER" -eq 0 ]; then
    return 0
  fi
  case "$(uname -s)" in
    Darwin) open "$page" ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$page" >/dev/null 2>&1 || true
      else
        echo "Open $page in a browser."
      fi
      ;;
    MINGW*|MSYS*|CYGWIN*)
      cmd.exe /c start "" "$(cygpath -w "$page" 2>/dev/null || echo "$page")"
      ;;
    *) echo "Open $page in a browser." ;;
  esac
}

if [ "$DEMO" -eq 1 ]; then
  say "Rendering the fictional demo"
  "$PYTHON_BIN" atlas.py --demo
  open_page demo.html
  exit 0
fi

say "Surveying projects"
survey_cmd=("$PYTHON_BIN" survey.py)
if [ -n "$ROOT" ]; then
  survey_cmd+=(--root "$ROOT")
fi
if [ "$QUIET" -eq 1 ]; then
  survey_cmd+=(--quiet)
fi
"${survey_cmd[@]}"

if [ "$REVIEW" -eq 1 ]; then
  say "Reading projects with the local model"
  review_cmd=("$PYTHON_BIN" review.py)
  if [ "${#REVIEW_ARGS[@]}" -gt 0 ]; then
    review_cmd+=("${REVIEW_ARGS[@]}")
  fi
  "${review_cmd[@]}"
fi

say "Rendering index.html"
"$PYTHON_BIN" atlas.py
open_page index.html
