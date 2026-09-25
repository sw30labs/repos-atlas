# ADR-002: The survey must not mutate the repos it reads

- **Status:** Accepted
- **Date:** 2026-09-12
- **Deciders:** Nicolas Cravino
- **Trigger:** this bit us on the first run

---

## Context

`git status --porcelain` is a read command. It also refreshes the index, and to do
that it takes `.git/index.lock`. Normally it releases it and you never know.

On the first run across 38 repos the sandbox could not unlink, and five repos were
left holding a stale `.git/index.lock`:

```
warning: unable to unlink '.../example-project/.git/index.lock': Operation not permitted
```

A stale lock blocks the *next* real git command in that repo. A read-only tool had
quietly armed five landmines in working repositories.

## Decision

**Every git invocation goes through one wrapper that prepends `--no-optional-locks`.**

```python
if args and args[0] == "git":
    args = ["git", "--no-optional-locks"] + args[1:]
```

One chokepoint, in `run()`. Not a flag on each call site — call sites get added and
the next one forgets.

More generally: **this tool opens files for reading and writes nothing except its
own two outputs.** No fetch, no gc, no maintenance, no config writes.

## Non-goals

- Detecting and cleaning locks left by someone else. Not our mess; deleting another
  process's lock is how you corrupt an index.
- `git fetch` to compute ahead/behind. It touches the network and writes refs, for
  a number nobody asked for.

## Consequences

`--no-optional-locks` makes `git status` skip the index refresh, so it can be
marginally slower and can report a file as dirty that a refresh would have cleared
— a stat-dirty file with unchanged content. Wrong in the harmless direction.

The rule to keep: a tool that reads your repos gets exactly one privilege, and it
is `open(path, "rb")`.
