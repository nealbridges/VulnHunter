---
name: runtime-provisioner
description: VulnHunter sandbox-depth decision procedure. For every 2b verdict — confirmation AND elimination — classify the proof requirements, climb the cheapest-sufficient-first probe ladder (call the real function, then the real parser, then the container), choose the sandbox that supports the rung reached, record the Runtime line, and ensure a behavioural claim is never recorded as static: it either executes at the real boundary or is HOLD-UNVERIFIED with its probe named. No mocks at the boundary without an explicit, severity-capping EXECUTED-MOCK record. Use during the vulnhunt scan's Phase 2b when recording any verdict.
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

### Cheapest-sufficient-first probe ladder (G2.4) — decide this FIRST

Before choosing any sandbox, decide how deep the evidence needs to go. Each rung
is cheaper than the next and each is strictly better than reasoning about a
string:

1. **Call the real function** on the real payload, in-process, at the version
   the target pins. This settles "what does the sanitizer actually emit".
2. **Feed that output to the real downstream parser** at the pinned production
   version (`sqlparser`, the ORM, the template engine, `json.Unmarshal`).
   This settles "what does the consumer actually do with it". Rung 2 is the one
   that would have caught `escapeVisibility`: the sanitizer's output looks safe,
   and the parser's treatment of the backslash is what breaks it.
3. **Only then the container**, when the impact claim needs the real dependency
   end-to-end (a network service, a database, a runtime the host lacks).

A **reimplementation** of the parser does not count as a probe. If you rewrite
the parser's behaviour in a test helper, you have tested your belief about the
parser, which is `static-trace` wearing a test's clothes. Rung 2 means importing
the actual library.

Having fixed the rung, choose the sandbox that supports it. Fixed preference
order; never skip a cheaper option without written cause:

1. **Docker container** (default — uniform, disposable, matches CI, immune
   to host drift, and the only way to reach rung 3 when the host lacks the
   dependency). Record the image and version tag.
2. **In-process harness**, only if the dependency cannot containerize cheaply
   (e.g. a licensed mainframe-backed service in the target's own infra).
   Record the harness description and the exact dependency version pinned.
3. **Static trace only** when the claim is **structural**. This MUST be
   justified in writing on the finding — it is never the default, and it is never
   available to a behavioural claim (see Step 4).

   **Claim type decides the runtime; runnability does NOT decide the claim type.**
   The order matters. Classify the claim first: is the deciding question about
   this repository's control/data flow (structural), or about what a dependency
   does with a value (behavioural)? Only then ask whether the boundary can be
   exercised.

   - Structural → static trace is legitimate.
   - Behavioural and runnable → execute it (rung 1/2/3).
   - Behavioural and NOT runnable → `HOLD-UNVERIFIED`, never `static`. "I could
     not run it, therefore I call it structural" is the loop this step used to
     permit: an unrunnable dependency reclassified itself out of the requirement
     that it be run.

### Payload discipline (G2.5)

A probe is only evidence if the payload could actually break the defense:

- **Cover each interpolation position.** A query with three interpolated values
  needs a payload at each one, not one payload aimed at the most obvious.
- **Include tails that survive the sanitizer.** If the sanitizer doubles quotes,
  the payload must contain a quote whose survival changes the meaning — the
  `escapeVisibility` case needed a trailing `\` that the doubling does not
  neutralize.
- **Use payloads valid in the target grammar.** A payload the parser rejects
  as malformed proves nothing about the sink.
- **Rejection is not safety.** If the payload is rejected, that shows *the
  payload* was malformed — not that the sink is safe — unless the rejection
  happened before the value was interpreted. An early 400 does not prove the
  query was safe; it proves the door was shut before the room was inspected.

## Step 3 — Execute at the chosen depth

Medium and above must execute in a container **unless the probe ladder above
already settled the behavioural claim in-process**. A rung-1/rung-2 probe that
executes the real function and the real parser satisfies the execution
requirement for a *behavioural* claim; the container is then required only for
the *impact* claim (end-to-end). Record which rung closed the claim.

No exceptions to "Medium+ must execute something": a mock is allowed only when
the real dependency is genuinely unavailable, and then the finding MUST record
`EXECUTED-MOCK` and its severity ceiling is Low until a real-boundary run is done.

**What EXECUTED-MOCK settles.** Running against a mock executes *your* code, not
the claim. It confirms how your call site behaves; it says nothing about what the
dependency does with the payload. So on its own it does **not** close a
behavioural claim — and a run that only ever reached a mock leaves the claim
`HOLD-UNVERIFIED` with the real-dependency probe named, severity capped at Low.
Do not record EXECUTED-MOCK as if it were an `executed-probe`: the evidence field
distinguishes them, and a behavioural verdict may not be closed by a mock.

## Step 4 — Record the runtime on the finding

Every finding MUST carry a Runtime line in one of these forms. These are
mutually exclusive: **one** Runtime line per finding. The one combination that is
not a single form is `EXECUTED-MOCK` on a behavioural claim — the mock records
*what ran*, and the claim still carries its HOLD disposition on the same finding
(see Step 5); record it as `Runtime: EXECUTED-MOCK — <what was mocked>; severity
ceiling Low; claim HOLD-UNVERIFIED — probe: <real-dependency probe>`, one line,
not two.

- `Runtime: docker:<image>@<tag>`
- `Runtime: in-process:<description>` — include the probe rung that closed the
  behavioural claim, e.g. `in-process:rung-2 (real sqlparser v1.9.0)`
- `Runtime: static — <justification>` — **only for a STRUCTURAL claim**. A
  behavioural claim recorded as `static` is a contradiction: either something
  executed, or the verdict is `HOLD-UNVERIFIED`.
- `Runtime: EXECUTED-MOCK — <what was mocked and why>; severity ceiling Low`
- `Runtime: HOLD-UNVERIFIED — probe: <what to call, with what payload, fed to what>`
  — the honest form for a behavioural claim nothing has executed yet. The
  verdict itself is defined once in `vulnhunt/SKILL.md`; this skill uses that
  definition and does not restate it.

A finding without a Runtime line is incomplete and MUST NOT be reported.

## Step 5 — Cross-check before hand-off

Before handing the finding to `poc-impact`, verify:

- the Runtime line is present and well-formed;
- the claim type is recorded, and the evidence type is permitted for it: a
  **structural** claim may rest on `static-trace`; a **behavioural** claim may
  not;
- the recorded runtime actually executed the boundary (not a proxy for it);
- for Medium+: either the run was at rung 1/2 against the real dependency or in
  a container, or `EXECUTED-MOCK` is recorded with the severity ceiling noted.
  **`EXECUTED-MOCK` satisfies the "must execute something" requirement, not the
  "settled the claim" requirement.** If a behavioural claim's only execution was
  against a mock, it must also carry `Runtime: HOLD-UNVERIFIED` with the
  real-dependency probe: the mock proved your call site works, not what the
  dependency does. Recording EXECUTED-MOCK and stopping there is the
  read-source-only mistake with a process attached;
- a behavioural finding not yet executed is recorded with a HOLD disposition
  and routed (Medium+ → Phase 3a, Low → report Unverified section). Write it on
  the SAME Runtime line as any execution form (see Step 4), e.g.
  `Runtime: EXECUTED-MOCK — <what>; claim HOLD-UNVERIFIED — probe: ...` — not as
  a second `Runtime:` line. **A HOLD is a valid hand-off**, not a failure: it carries the probe
  forward. What is not valid is recording `Runtime: static` on a behavioural
  claim — that asserts the claim was settled when nothing ran.

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
