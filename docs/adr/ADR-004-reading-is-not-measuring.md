# ADR-004: A model may read the code; it may never be quoted as measurement

- **Status:** Accepted
- **Date:** 2026-09-12
- **Deciders:** Nicolas Cravino
- **Scope:** everything `review.py` produces

---

## Context

`survey.py` can tell you a project is 27,644 lines of Python last touched on
Tuesday. It cannot tell you what the project *is*. Across 52 projects, a third
have no README blurb worth the name, and names like `project-a`, `project-b` and
`project-c` mean nothing six months later.

A language model reading the tree, the README and the last five commit subjects
can answer that — and, given every one-liner at once, can answer the question no
single repo can: **which of these are doing the same work?**

That output is a different KIND of thing from a line count. It is a claim. It
will sometimes be wrong, confidently. The temptation is to blend it into the
page because it reads well.

## Decision

**Keep the two kinds of knowledge separate all the way down, and say which is which.**

| | measured | read |
|---|---|---|
| produced by | `survey.py` | `review.py` |
| stored in | `survey.json` | `review.json` |
| on the page | the existing sections | one section, dashed border, labelled *generated* |
| if absent | there is no page | the page is exactly as it was |

Concretely:

- `review.py` is a **separate script**. `atlas.py` renders it if `review.json`
  exists and never mentions it otherwise. Nothing above the review section
  changes shape when the model runs.
- The review section opens with a plain-language line naming the model, the
  date, how many projects were read, and the sentence *"a model's reading of
  your code, not a measurement of it."*
- Model one-liners appear on tiles in italics and in tooltips behind the words
  **read as**. They never overwrite the README blurb in the data.
- A brief the model refused or mangled is stored as an `error`, and a project
  too thin to read is stored as `skipped`. Absence is recorded, not hidden.
- The synthesis pass may only name projects that exist. Members it invents are
  dropped before render, and a cluster left with fewer than two members is dropped.

**Local only.** The endpoint is an OpenAI-compatible server on your own machine.
There is no cloud fallback and no API key, because adding one would turn "read my
private repos" into "upload my private repos" behind a flag.

## Non-goals

- Acting on the recommendations. `archive-one` is a suggestion to a human, never
  a script that archives.
- Embeddings, a vector store, similarity search. The overlap question is a
  reasoning question, and 52 one-liners fit in a prompt.
- A cloud model, an API key, or a `--yes-upload-my-code` flag.

## Consequences

The page now carries two voices, and a reader can always tell which is speaking.
Turning the model off removes a section and breaks nothing.

The cost is a second artefact to keep fresh: `review.json` can describe a project
as it was two months ago. Briefs are fingerprinted on the evidence that produced
them, so a changed repo re-reads and an unchanged one does not — but a project
nobody has committed to still shows its old reading, correctly.

The rule to keep: **when a tool starts generating claims instead of counting
things, the page has to say so out loud, in the same place it says it.**
