---
name: runtime-provisioner
description: VulnHunter sandbox-depth decision procedure. For each confirmed finding, classify its proof requirements, choose the cheapest sufficient sandbox (Docker container by default), record the runtime on the finding, and ensure Medium+ findings execute against the real dependency — no mocks at the boundary without an explicit, severity-capping EXECUTED-MOCK record. Use during the vulnhunt scan's Phase 2b after a finding is confirmed.
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

Fixed preference order; never skip a cheaper option without written cause:

1. **Docker container** (default — uniform, disposable, matches CI, immune
   to host drift). Record the image and version tag.
2. **In-process harness**, only if the dependency cannot containerize cheaply
   (e.g. a licensed mainframe-backed service in the target's own infra).
   Record the harness description and the exact dependency version pinned.
3. **Static trace only** when the boundary genuinely cannot be exercised.
   This MUST be justified in writing on the finding — it is never the default.

## Step 3 — Execute at the chosen depth

Medium and above must execute in a container. No exceptions. A mock is
allowed only when the real dependency is genuinely unavailable, and then the
finding MUST record `EXECUTED-MOCK` and its severity ceiling is Low until a
real-boundary run is done.

## Step 4 — Record the runtime on the finding

Every finding MUST carry a Runtime line in one of these forms:

- `Runtime: docker:<image>@<tag>`
- `Runtime: in-process:<description>`
- `Runtime: static — <justification>`
- `Runtime: EXECUTED-MOCK — <what was mocked and why>; severity ceiling Low`

A finding without a Runtime line is incomplete and MUST NOT be reported.

## Step 5 — Cross-check before hand-off

Before handing the finding to `poc-impact`, verify:

- the Runtime line is present and well-formed;
- the recorded runtime actually executed the boundary (not a proxy for it);
- for Medium+: the run was in a container, or `EXECUTED-MOCK` is recorded
  with the severity ceiling noted.

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
