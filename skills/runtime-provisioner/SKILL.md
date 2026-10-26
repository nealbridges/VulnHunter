---
name: runtime-provisioner
description: VulnHunter sandbox-depth decision procedure. For every 2b verdict — confirmation AND elimination — climb the cheapest-sufficient-first probe ladder (real function, then real parser, then container), record the Runtime line, and never record a behavioural claim as static: it executes at the real boundary or is HOLD-UNVERIFIED with its probe named. No mocks at the boundary without a severity-capping EXECUTED-MOCK record. Use during the vulnhunt scan's Phase 2b when recording any verdict.
trigger:
  - /runtime-provisioner
  - user asks to decide sandbox depth or runtime for a finding
---

# Runtime Provisioner — the sandbox-depth decision

## Purpose

Every VulnHunter finding makes two claims: a **mechanism** (this input reaches
this sink) and an **impact** (an attacker gains something they did not have).
The mechanism claim is cheap to assert; the impact claim is only proven by
execution against the real dependency. This procedure decides, per finding,
how much runtime the impact claim needs, executes it, and records the choice
so the report can show *what was done to prove it* — not just that something
was done.

## Placement in the methodology

Phase 2b, per candidate — **after** confirmation (Phase 2b's adversarial
verify), because the sandbox decision depends on what the finding needs to
prove. The decision feeds `poc-impact` (Phase 3): the provisioned runtime is
where the PoC executes and the impact is measured.

## Step 1 — Classify proof requirements

For the candidate finding, enumerate what execution the impact claim needs:

- **Boundary type** — what does the sink live behind? (query grammar, HTTP
  client, queue, filesystem, crypto primitive, auth service, parser, ORM…)
- **Attacker-reachable surface** — which attacker-controlled inputs must
  flow to the sink for the impact to materialize?
- **Observable outcome** — what does "the attacker wins" look like?
  (a row returned, a file read, a request issued, a state change, a payload
  executed). If you cannot state the outcome in one sentence, return to the
  finding and restate it as an outcome before choosing a runtime.

## Step 2 — Choose the cheapest sufficient sandbox

### Probe ladder — cheapest sufficient first, decide this FIRST

1. **Call the real function** on the payload, in-process, at the pinned version
   (what the sanitizer actually emits).
2. **Feed that output to the real downstream parser** at the pinned production
   version — the SQL parser, ORM, template engine, URL parser, decoder (what the
   consumer actually does with it).
3. **Only then the container**, when the impact claim needs the dependency
   end-to-end.

A **reimplementation** of the parser is not a probe — it is `static-trace`.
Rung 2 means importing the actual library.

Then choose the sandbox that supports the rung. Fixed preference order; never
skip a cheaper option without written cause:

1. **Docker container** (default — uniform, disposable, matches CI, immune
   to host drift, and the only way to reach rung 3 when the host lacks the
   dependency). Record the image and version tag.
2. **In-process harness**, only if the dependency cannot containerize cheaply
   (e.g. a licensed mainframe-backed service in the target's own infra).
   Record the harness description and the exact dependency version pinned.
3. **Static trace only** when the claim is **structural**, justified in writing.
   Never the default, never available to a behavioural claim.

   **Claim type decides the runtime; runnability does not decide the claim
   type.** Structural → static is legitimate. Behavioural and runnable → execute
   it. Behavioural and not runnable → `HOLD-UNVERIFIED`, never `static`.

### Payload discipline

- **Cover each interpolation position**, not just the most obvious one.
- **Include tails that survive the sanitizer** — characters it does not handle.
- **Use payloads valid in the target grammar.**
- **Rejection is not safety** unless it happened before the value was
  interpreted.

## Step 3 — Execute at the chosen depth

Medium and above must execute in a container **unless a rung-1/2 probe already
settled the behavioural claim in-process**; the container is then needed only
for the end-to-end impact claim. Record which rung closed the claim.

A mock is allowed only when the real dependency is genuinely unavailable: record
`EXECUTED-MOCK`, severity ceiling Low until a real-boundary run. A mock executes
your call site, not the dependency, so it never closes a behavioural claim — the
claim stays `HOLD-UNVERIFIED` with the real-dependency probe named.

## Step 4 — Record the runtime on the finding

Every finding MUST carry **one** Runtime line in one of these forms. A mock on a
behavioural claim combines two on the same line:
`Runtime: EXECUTED-MOCK — <what was mocked>; severity ceiling Low; claim HOLD-UNVERIFIED — probe: <real-dependency probe>`.

- `Runtime: docker:<image>@<tag>`
- `Runtime: in-process:<description>` — name the rung, e.g.
  `in-process:rung-2 (real URL parser, pinned version)`
- `Runtime: static — <justification>` — **structural claims only**
- `Runtime: EXECUTED-MOCK — <what was mocked and why>; severity ceiling Low`
- `Runtime: HOLD-UNVERIFIED — probe: <what to call, with what payload, fed to what>`
  (defined in `vulnhunt/SKILL.md`)

A finding without a Runtime line is incomplete and MUST NOT be reported.

## Step 5 — Cross-check before hand-off

Before handing the finding to `poc-impact`, verify:

- the Runtime line is present and well-formed;
- the claim type is recorded and its evidence is permitted (behavioural may not
  rest on `static-trace`);
- the recorded runtime actually executed the boundary (not a proxy for it);
- for Medium+: rung 1/2 against the real dependency, a container, or
  `EXECUTED-MOCK` with the ceiling noted — and a mock-only behavioural claim also
  carries its HOLD on the same line;
- an unexecuted behavioural finding is a HOLD, routed (Medium+ → Phase 3a, Low →
  Unverified section). A HOLD is a valid hand-off; `static` on a behavioural
  claim is not.

## The blunt sentence

A mechanism-proving assertion is not an impact measurement. "The query string
contains `OR WorkflowId IS NOT NULL`" is the mechanism. The finding is "a
victim tenant's row was returned to the attacker's listing." If your test
asserts the first, it has not proven the second.

## Env contract

| Variable | Required | Purpose |
|---|---|---|
| `VULNHUNT_SKILLS_DIR` | no | Override the skills root this skill is loaded from. |
| `VULNHUNT_HOST_CMD` | no | Command prefix for harness session invocation, when the host harness must be driven explicitly. |
| `VULNHUNT_DIR` | no | Findings directory, when operating on a prepared scan workspace. |
