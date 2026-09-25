# ADR-003: Prune environments by marker file, not by name

- **Status:** Accepted
- **Date:** 2026-09-12
- **Deciders:** Nicolas Cravino
- **Trigger:** one missed directory, 1.1M phantom lines

---

## Context

First pass skipped a name list: `node_modules`, `.venv`, `venv`, `__pycache__`,
`dist`, `build`, `vendor`. It reported `example-project` at 1,109,136 lines — the
largest project by a factor of ten — and a 2.57M-line total.

It was `example-project/.conda/`. Not on the list. 25M lines of vendored Python and C
inside a directory the name list had never heard of.

The real number for that project is 47k. The list was not incomplete by accident;
a name list is *always* incomplete. `.conda`, `.mamba`, `env`, `envs`, `.direnv`,
`Pods`, `DerivedData`, and whatever the next tool calls its cache.

## Decision

**Ask the directory what it is.** A Python environment announces itself:

```python
def is_env(path):
    for marker in ("pyvenv.cfg", "conda-meta"):
        if os.path.exists(os.path.join(path, marker)): return True
    return False
```

Plus two structural rules that need no list at all:

- **Skip dot-directories**, except `.github`. Config, cache and environments live
  there. Source does not.
- **Skip `*.egg-info` and `*.dist-info`** by suffix.

The name list stays, as a fast first filter for the things that have no marker
(`node_modules`, `dist`, `target`). It is the backstop now, not the mechanism.

## Non-goals

- Reading `.gitignore` and honouring it. Tempting, and wrong: plenty of projects
  ignore build output that we still want to see the shape of, and plenty of
  vendored code is committed.
- Language detection beyond file extension.

## Consequences

`example-project` went 1.1M → 47k. The corpus went 2.57M → 1.43M lines. Every headline
number in the atlas moved, and the new ones are defensible.

A project that vendors dependencies without a marker file — a checked-in `lib/` of
someone else's C — still counts as yours. Correct, arguably: you are carrying it.

The rule to keep: **when a heuristic is a list of names, it is wrong and you will
find out later.** Ask the thing what it is.
