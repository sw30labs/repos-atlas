# ADR-007: OpenAI as the one remote endpoint

- **Status:** Accepted
- **Date:** 2026-10-08
- **Deciders:** Nicolas Cravino
- **Supersedes:** the "Local only" rule in [ADR-004](ADR-004-reading-is-not-measuring.md)

---

## Context

ADR-004 kept every reading on this machine: no cloud fallback, no API key. In
practice a 170-project review needs a model server running for an hour, and the
machine does not always have one. A hosted model reads the same evidence in
minutes.

## Decision

**Allow exactly one remote endpoint, `https://api.openai.com`, and make every
run say out loud that it is being used.**

- The endpoint comes from `--base` or `ATLAS_LLM_BASE`, in the shell or a
  git-ignored `.env`. When it is OpenAI, the evidence leaves the machine; the
  run prints a `CLOUD:` line before the first call, and the page's generated
  banner names `api.openai.com` instead of "locally".
- Remote hosts are an allow-list (`CLOUD` in `review.py`), not a pattern: https,
  default port, no userinfo, query or fragment. A typo is refused, not uploaded.
- `OPENAI_API_KEY` is attached only to requests for that host. A local server
  never sees it. Proxies stay bypassed and redirects stay refused.
- OpenAI's current models take `max_completion_tokens` (which also pays for
  hidden reasoning) and only the default temperature, so the request changes
  shape by endpoint.
- What is sent is unchanged from ADR-004: a bounded README excerpt, a short file
  tree, recent commit subjects, summary metadata.

## Consequences

The privacy promise is now "local unless you configure OpenAI", not "local".
Everything else in ADR-004 stands: readings stay labelled and separate, and
nothing acts on a suggestion. Adding a second provider means adding it to
`CLOUD` and to this record, deliberately.
