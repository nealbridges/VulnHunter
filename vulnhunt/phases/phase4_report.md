# Final Report Format

> **Context**: All phases are complete. Compile the final report with all confirmed
> findings, all HOLD-UNVERIFIED findings (the `## Unverified` section), code
> smells, and the resolved input inventory.

## Final Report Format

**IMPORTANT**: All findings describe the original source code as it existed at
scan time. The audit does not modify source files.

**Each confirmed instance is a separate finding.** If the sweep produced 5 candidates
for the same root cause and 3 passed the full pipeline, the report contains 3
VULN-NNN entries — one per sink location, each with its own data flow, PoC, and
exploit test. They may share a root cause description and fix strategy, but each
gets its own ID and its own row in the summary table.

Start the report with a summary table of all confirmed findings.
**This table MUST have one row per exploit test PASS — not one row per root cause.**
If you have 2 root causes but 8 confirmed sink locations, the table has 8 rows.

**Universal Auth Gap exception**: if Phase 2b §9 emitted
`VULN-PLATFORM-AUTHN` or `VULN-PLATFORM-AUTHZ`, that row leads the
summary table. Its body lists every `SUBSUMED-BY: VULN-PLATFORM-*`
finding (ID, file:line, CWE that would have been raised) so post-fix
re-scan can confirm the expected-to-disappear set. Subsumed entries do
NOT get their own summary-table rows.

### Summary

| ID | Title | CWE | Severity | Runtime | Exploit Test | Measured Impact | Status |
|---|---|---|---|---|---|---|---|
| VULN-001 | [title] | CWE-XXX | High+/High/Medium/Low/Informational | docker:image@tag / in-process:desc / static | PASS/FAIL | [the number in the class's impact unit] | Confirmed/Fixed/Verified |
| ... | ... | ... | ... | ... | ... | ... | ... |

The `Runtime` column copies the finding's Phase 2b `Runtime:` line. The
`Measured Impact` column carries the Phase 3b measurement — the number in the
class's impact unit, with its denominator ("3 of 20 payloads returned
victim-tenant rows; 17 rejected fail-closed"), never the mechanism sentence.

**Confirmed invariant**: a row cannot be marked `Confirmed` unless it has (a)
an executed artifact in the recorded runtime — or a static trace where the
finding's recorded runtime is `static`, with its justification — and (b) a
Measured Impact number. A Confirmed row missing either is incomplete: go back
to Phase 3a/3b, do not narrate past the gap.

Then for each finding, provide the full detail:

### [VULN-NNN] Title
| Field | Value |
|---|---|
| **Title** | ... |
| **Input** | inventory # and description |
| **CWE** | CWE-XXX: [Name] |
| **Severity** | High+/High/Medium/Low/Informational |
| **Location** | file:line (primary instance) |
| **Entry Point** | ... |
| **Data Flow** | source -> ... -> sink |
| **Runtime** | the finding's recorded `Runtime:` line (Phase 2b) |
| **PoC** | `${VULNHUNT_DIR}/poc/VULN-NNN_description.md` |
| **Exploit Test** | `${VULNHUNT_DIR}/exploit_tests/test_vuln_NNN.py` — PASS/FAIL + reason |
| **Measured Impact** | the Phase 3b block: unit, result, basis, denominator, negative space |
| **Fix** | [inline diff or link] |
| **Root Cause** | [shared root cause name, if this instance is part of a sweep group] |
| **Status** | Confirmed / Fixed / Verified |

When severity is **Informational** or **Medium** under the Authorization
Delegation Rule (phase2b_verify.md §8), include one extra row:
| **Trust Model** | one-line note recorded in Phase 2b |

Every finding MUST include a CWE identifier. Use the most specific CWE that applies
(e.g., CWE-89 for SQL injection, not CWE-74 for generic injection).

**VALIDATION RULE**: A finding is INVALID if either the **PoC** or **Exploit Test**
field is empty, says "N/A", or says "see above." Each field MUST contain a file path
to the saved artifact. If you cannot produce a PoC or exploit test, the finding has
not been proven — but **what happens next depends on why**:

- If a probe was attempted and the claim failed, the finding is **eliminated** as a
  FALSE POSITIVE (evidence: `executed-probe`).
- If a probe was attempted and was **unrunnable** in this environment, the finding
  is **HOLD-UNVERIFIED** and belongs in the `## Unverified` section with the probe
  that would settle it named — not downgraded to Potential.
- If nothing was ever attempted and the claim is structural, downgrade to Potential.

Do not downgrade a behavioural HOLD to "Potential" to avoid the PoC requirement:
"Potential" is a judgement; a HOLD is a recorded fact about what was tried (see
the verdict vocabulary in `vulnhunt/SKILL.md`). A HOLD that vanishes into
"Potential" has lost its probe.

**Code smells go in a separate section.** Findings where the exploit test showed
"code runs but attack is mitigated" are NOT vulnerabilities. List them after the
vulnerability findings under a "Code Quality / Defense in Depth" heading.

**Each code smell MUST include a downgrade rationale** explaining:
1. Which gate it failed or which exploit test defense blocked it
2. The specific evidence (file:line of the mitigation, or the test output showing
   the attack was blocked)
3. What condition would need to change for this to become exploitable (e.g.,
   "if the allowlist is removed," "if this route is exposed in production,"
   "if the downstream service stops validating")

Format:
| Field | Value |
|---|---|
| **Location** | file:line |
| **Pattern** | what the code does |
| **Downgrade reason** | which gate failed + evidence (file:line of mitigation) |
| **Risk if conditions change** | what would make this exploitable |
| **Recommendation** | why it should still be fixed |

They do not get VULN-NNN IDs or PoC files.

**Code smell generation (MANDATORY):** Before writing the Code Quality section,
systematically review these sources — not just findings that failed exploit tests:

| Source | What to look for |
|---|---|
| Gate 2b near-misses | Sanitizer correct for current sink but fragile (caller-dependent, wrong layer) |
| Gate 1 near-misses | Code exploitable if route were ever exposed; dev-only guard is the only protection |
| Security config | Missing SameSite, permissive trust proxy, missing security headers |
| Crypto inventory | Weak algorithm/mode where exploitation prerequisite is not currently met |
| Defense-in-depth gaps | Service-layer functions relying on caller sanitization with no own validation |

Each entry: location, risk, what prevents current exploitation, why it should be fixed.

**Include the sweep verification table.** After the code smells section, include
the final Phase 3d sweep table showing each root cause, the grep pattern used,
instances found/fixed/remaining. This demonstrates completeness — every root cause
was hunted across the entire codebase, not just at the initially-discovered location.

Save all artifacts to the `${VULNHUNT_DIR}/` directory:
```
${VULNHUNT_DIR}/
  README.md                         # Summary report with links (generated last)
  poc/
    VULN-001_sql_injection.md       # Static or runnable PoC
    VULN-002_path_traversal.md
  exploit_tests/
    test_vuln_001_sql_injection.py  # Executable exploit test
    test_vuln_002_path_traversal.sh
```

### Generating the README

After all findings are finalized, create `${VULNHUNT_DIR}/README.md` as the entry point.

**The README MUST begin with this exact header structure** (fill in values):

```markdown
# VulnHunter Security Audit Report

**Run ID**: <VULNHUNT_DIR basename>
**Repository**: <full repo URL>
**Audit Date**: <YYYY-MM-DD>
**Branch**: <branch [short-commit-hash]>
**Model**: <model identifier>
**Skills**: <skill-name>@<installed-commit> (source <source-commit>) — one line per skill
**Skills match source**: <yes | no>
**Findings Summary**: <N High+, N High, N Medium, N Low, N Informational>
```

Field definitions:
- **Run ID** = basename of `VULNHUNT_DIR` (the results folder name, e.g.
  `smartops-cli_VULNHUNT_RESULTS_2026-05-14-072642`).
- **Repository** = the `Repository URL` value supplied in the /vulnhunt
  kickoff prompt's pre-resolved metadata block. The agent layer already
  normalized SSH origins to https and stripped any `.git` suffix; use the
  value literally without running git or doing further parsing.
- **Branch** = the `VULNHUNT_BRANCH` value supplied in the same metadata
  block. Format: `branch-name [abc1234]`, or `unknown` if the source
  isn't a git repo. Do not run git to recompute.
- **Model** = the model identifier reported by your host harness (e.g. the current model ID).
- **Skills** = one line per skill the run used, copied from the operator's
  `vh check-skills` output (Step 0 of `vulnhunter-run`). Record the skill
  name, the commit its bytes are **attributable** to (the `bytes_from` field
  in `--json`, or `unknown` when the check could not prove it), and the
  source commit it was compared against. Do not re-derive these — copy the
  values the check printed. Record `unknown` as written: it means the bytes
  matched but no commit could be proven to have produced them.
- **Skills match source** = `yes` only when the operator's Step 0 drift
  check exited 0 for every skill. Otherwise `no`, and the run MUST NOT
  claim cross-run comparability: results produced on a drifted skill set
  are not comparable to a run on source, and the report must say so.
  When the check printed a `dirty` marker, record `no (source checkout had
  uncommitted changes)`: the recorded commit equals `HEAD`, so those bytes
  are **not proven** to be that commit's bytes — the install may predate or
  postdate the edits. Do not record `yes` on a dirty checkout.

After the header, include:
- Summary table of findings (ID, title, severity, CWE, status)
- For each finding: input #, location, entry point, impact, links to PoC and exploit test files
- The `## Unverified` section for every open `HOLD-UNVERIFIED` finding (see below) —
  **omit it only when there are none.** A reader must be able to tell, from this
  checklist alone and without reading the rest of the document, whether the run
  left anything unsettled.
- The resolved input inventory table showing every input's disposition
  (CANDIDATE / SAFE / DESIGN-INTENT / HOLD-UNVERIFIED) as a completeness artifact.
  A HOLD input is not SAFE and not CANDIDATE-confirmed: it is unsettled, and it
  appears here as well as in the `## Unverified` section.
- "Not Found / Excluded" section listing checked-but-clean vulnerability classes
- Artifacts table linking all files in `${VULNHUNT_DIR}/`

**Clickable links**: Every finding row in the summary table and every finding section
MUST include relative markdown links to the corresponding PoC file (`poc/VULN-NNN_*.md`)
and exploit test file (`exploit_tests/test_vuln_NNN_*`). Use the format
`[PoC](poc/VULN-001_desc.md) | [Test](exploit_tests/test_vuln_001_desc.py)`.
A finding without clickable links to both artifacts is incomplete.

**Cross-check**: The README summary table MUST list every VULN-NNN from the report.
Count the findings in the report and count the rows in the README table — they must
match. If they don't, you missed findings when generating the README.

After writing the README, add a footer to each PoC file linking to its exploit test
and back to the README.

## The Unverified section (MANDATORY when non-empty)

`HOLD-UNVERIFIED` is defined once, in `vulnhunt/SKILL.md`'s verdict vocabulary —
this section uses that definition and does not restate it.

**Cross-check before writing.** The count of `HOLD-UNVERIFIED` entries in the
`## Unverified` section plus the HOLDs promoted or disproved in Phase 3a must
equal the Phase 2b HOLD total. If the Unverified section is absent, that is a
claim that no HOLD survived — verify it against `phase2b_output.md` rather than
assuming.

Every `HOLD-UNVERIFIED` finding from Phase 2b goes in its own top-level
section, headed `## Unverified` — unless Phase 3a promoted it (it is then a
confirmed row) or disproved it (it is then a FALSE POSITIVE row).

That includes HOLDs that never reached Phase 3a, and HOLDs whose probe could not
run: a HOLD is settled by evidence, not by the run ending. "It did not survive
Phase 3a" must not be read as "drop it" — an unrunnable probe is exactly the case
the Unverified section exists for. It is not a Code Quality section and not a
confirmed-findings section: it is the honest list of things this run could not
settle.

Format — one entry per HOLD:

```
### [UNVERIFIED-NNN] Title

**Potential severity:** High (unverified)
**Why it is a HOLD:** <the behavioural claim nothing has settled>
**Closing claim:** <what must be true for this to be a real vulnerability>
**Probe that would settle it:** <what to call, with what payload, fed to what>
**Why the probe did not run:** <no harness / dependency unavailable / deferred by severity>
```

Rules for this section:

- **Never counted as confirmed.** The summary's confirmed count excludes HOLDs.
  A reader who sees "3 confirmed" is entitled to believe those three were proven.
- **Never silently dropped.** Every HOLD from Phase 2b must be accounted for in
  exactly one of three places, and the three must reconcile to the Phase 2b
  HOLD count:
  1. rows in this Unverified section (still unresolved),
  2. Phase 3a promotions (probe confirmed → now a CONFIRMED VULN-NNN),
  3. Phase 3a disproofs (probe disproved → now a FALSE POSITIVE with
     `executed-probe` evidence, recorded in the verification table, not here).
  Count Phase 2b HOLDs; count (1) + (2) + (3). They must be equal. A disproved
  HOLD belongs to bucket 3, **not** to this section — that is the difference
  between "we could not settle it" and "we settled it and it was wrong".
  A promoted HOLD likewise leaves this section for bucket 2.
- **Never described as a false positive.** "We could not settle it" and "we
  disproved it" are different statements. Do not collapse them: only a HOLD
  sitting in this section is unsettled; a disproved one has moved to bucket 3.
- **Always carry the probe.** A HOLD without a named probe is a dropped finding
  wearing a label.

**If there are no HOLDs, still print the section, with the body `none`.** Its
absence must never be ambiguous: a reader cannot tell whether the run had no
HOLDs or the writer forgot the section. `## Unverified` followed by `none` says
"we looked, and nothing was left open" — which is a claim worth making out loud.
(BUILD_B3 §4.3 depends on this; an omitted section is also indistinguishable from
a lost one when reconciling against the Phase 2b HOLD count.)

## What NOT to Report

- Anything in test code, build scripts, vendored/third-party code, or generated code
  (see Operating Principle #5)
- Informational findings that aren't exploitable (exception: findings downgraded
  to Informational under the Authorization Delegation Rule ARE reported with
  full data flow and PoC — see phase2b_verify.md §8)
- Inputs with SAFE or DESIGN-INTENT dispositions in the inventory — these are not
  findings, but their dispositions ARE part of the audit record and should appear in
  the resolved inventory table in the report
- Dependencies with known CVEs — **do not perform deep analysis of dependency
  internals.** Instead: if you encounter a dependency CVE during hunting and the
  first-party code clearly invokes the vulnerable API path with attacker-controlled
  input (provable from the first-party call site alone), report it as a finding
  with the CVE reference.

  If exploitability would require analyzing the dependency's internal code to
  confirm, that is a **behavioural** claim and it is **`HOLD-UNVERIFIED`, not a
  Code Smell**: record it with the CVE number, its potential severity, and the
  probe that would settle it (run the affected dependency version against the
  payload). A Code Smell is an aesthetic opinion; this is an unsettled question
  about a real vulnerability, and the two must not share a bucket. Only downgrade
  to Code Smell if you can show the first-party call site cannot reach the
  vulnerable path at all — that is structural, so reading the code does settle it.
- Style issues or best-practice violations without security impact
- Theoretical vulnerabilities that require unrealistic preconditions
- Injection claims where the language/framework genuinely auto-sanitizes — but verify
  by reading the actual library, and check that the sanitizer matches the sink context.
  **Reading the library is not enough on its own when the claim is behavioural.** If
  the sanitizer's output looks safe but the deciding behaviour is what a *downstream*
  consumer does with that output, the claim is behavioural and belongs under the
  claim-typing rule: `executed-probe` or `HOLD-UNVERIFIED`, never "I read the source
  and it looks fine". Reading the library proves the sanitizer emits what it emits;
  it does not prove the parser agrees.
