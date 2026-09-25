# ADR-005: What a local reasoning server actually does

- **Status:** Accepted
- **Date:** 2026-09-12
- **Deciders:** Nicolas Cravino
- **Trigger:** every one of these cost a wasted run against Inferencer + DeepSeek-V4.1

---

## Context

Talking to a local reasoning model is not talking to a hosted chat API. Five
things bit us in one afternoon, and each has a one-line fix that is invisible
unless you know why it is there.

## Decision

**1. `/v1/models` lists things that are not models.**
Inferencer advertises its prompt-cache shards alongside real models — dozens of
`mlx_cache/DeepSeek-V4.1-MLX-Q4i_<hash>_v/0f` entries. They accept a request and
return an **empty completion in three seconds**, which reads like a broken model
and is not. Real models never live under `mlx_cache/`. `resolve_model()` drops
that prefix, then substring-matches, so the config says `DeepSeek-V4.1` and stays
true when the quantisation changes.

**2. Cancelling the HTTP request does not stop the GPU.**
A client-side timeout abandons the *answer*, not the *work*. With batching off,
abandoned generations queue and block everything behind them — three of them took
the server from 7-second replies to unresponsive for several minutes. So
`--budget` gates **starting** a batch and lets an in-flight one finish. A deadline
that kills work in progress is worse than no deadline.

**3. Concurrency buys nothing and costs correctness.**
Three parallel requests: 98s wall against 80-98s each — fully serialised — and one
came back malformed. There is no `--concurrency` flag, on purpose.

**4. Batching trades accuracy for throughput, and the rate is bad.**
Amortising thinking across projects is sound in theory. In practice above ~2
projects per call this model started echoing READMEs back instead of emitting
keyed JSON. `--batch` defaults to 1 and the help says why.

**5. A reasoning model answers a thin prompt with an essay.**
Given 74 bytes of evidence it produced a paragraph of Chinese prose rather than
admit there was nothing to say. Hence: skip projects with almost nothing on disk
before spending 60 seconds; instruct English; re-ask once, bluntly; and parse
with a brace scanner rather than `json.loads`, because the reply reliably arrives
as `" Output\n{...}"`.

**And one that pays off:** keep the system prompt byte-identical across calls and
put the per-project evidence last. With the prefix cached, per-project time fell
from ~80s to ~27s. Prompt-cache-friendly message order is not a micro-optimisation
here; it is a 3x.

## Non-goals

- Streaming. Nothing watches the output as it arrives.
- Auto-tuning batch size or timeouts against an unknown server.
- Supporting servers that are not OpenAI-compatible.

## Consequences

The client is about 60 lines and every unusual line has a reason above it. Those
reasons are specific to reasoning models served locally with batching disabled; a
hosted API with real concurrency would want the opposite of points 2, 3 and 4.

The rule to keep: **a local model is a shared, serial, stateful resource on a
machine you also use.** Treat it like a build server, not like a web API.
