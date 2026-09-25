# ADR-001: One static HTML file, no server

- **Status:** Accepted
- **Date:** 2026-09-12
- **Deciders:** Nicolas Cravino
- **Style:** Karpathy-simple — smallest thing that answers the question

---

## Context

The output is a dashboard. The reflex is a small web server: Flask, a `/api/repos`
endpoint, a frontend that fetches it. That buys live data and costs a process to
start, a port to remember, and a thing that rots when you come back in March.

The data changes when *you* change it — you commit, you start a project. Not on a
timer. Nobody needs a websocket to learn that they have not touched `example-project`
since August.

## Decision

**`atlas.py` writes one self-contained `index.html`. There is no server and no
build step.** All CSS and JS are inlined. No CDN, no web fonts, no `fetch`.

The survey and the render are separate scripts on purpose. The walk is slow and
the page is cheap; editing the layout should not re-read 40 repos.

| | |
|---|---|
| Output | one file, ~110 KB, opens from disk or a USB stick |
| Interactivity | search, sort, hover, theme toggle — all client-side on data baked into the page |
| Refresh | re-run two scripts |

## Non-goals

- Live updating, file watching, a daemon
- A packaged CLI, a `pyproject.toml`, an entry point
- Any dependency beyond the standard library

## Consequences

Good: it works offline, it survives being emailed, nothing to install or start,
and it will still open in five years.

Bad: the numbers are as old as the last run, and the page carries its data inside
it — the file is large for what it shows, and regenerating is the only refresh.
Accepted. If this ever needs to be live, that is a different program.
