# ADR-006: Where to focus is arithmetic over readings, not a model's ranking

- **Status:** Accepted
- **Date:** 2026-10-08
- **Deciders:** Nicolas Cravino
- **Scope:** the Focus next and Let go panels

---

## Context

With 170 projects the useful question stops being "what is each one" and
becomes "which one do I open tomorrow, and which can I stop carrying". A model
asked that directly will answer, fluently, and give a different order on the
next run with no way to say why one project beat another.

## Decision

**The model answers small questions; the page does the ranking.**

- Per project the model reports `stage`, `distance` (days, weeks, months),
  `next_step` and `blocker`, and, against a private `goals.md`, a goal fit of
  0-3. Each is a short judgement on evidence it was shown.
- `atlas.focus_score` multiplies named factors (goal fit, momentum, stage,
  distance, at-risk, tiny) into 0-100. Every factor is shown on hover.
- `atlas.let_go` collects reasons, each tagged measured or read, and lists a
  project once it has one certain reason or enough lesser ones.
- One final call sees only the top five, with their facts, and may pick up to
  three and say why now. It may disagree with the formula, in words. Names it
  invents are dropped.

Both panels live inside the generated section, per ADR-004: without
`review.json` the page is unchanged.

## Consequences

The weights are opinions, written down in one place (`STAGE_W`, `DISTANCE_W`,
`FIT_W`) where they can be argued with. Goal fit is cached by a hash of
`goals.md`, so editing goals costs a few batched calls, not a full re-read.
Let go is a suggestion to a human; nothing archives, moves or deletes a repo.
