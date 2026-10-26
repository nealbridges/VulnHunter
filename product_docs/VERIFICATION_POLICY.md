# Verification policy

**PUBLISHED.** `product_docs/*` is gitignored, but this file is explicitly un-ignored because a
contributor or reviewer needs to know what standard a build is held to. It names no scan identifier — the
repo's leak guard scans it — so it is safe in public. The other `product_docs/` files stay private.

This policy exists because of a specific, expensive failure. Read that case first; the rules are only
convincing in light of it.

---

## 1. The case this policy is built from

A privacy guard was added to enforce one claim: *this public repo publishes no vocabulary from the private
scan runs used as test data.*

Over roughly five hours the guard was rebuilt **seventeen times** (seventeen squashed-feature commits; the
reflog records them) and reviewed **fourteen times**. Thirteen consecutive reviews returned REJECT. The
fourteenth approved, and only after the work was genuinely done.

At no point in that sequence was the test suite red. Every rebuild ended with a green suite, a clean
`ruff` run, and a commit message declaring the problem solved. The repo was still leaking.

The failures, in the order they were found:

| # | What I claimed | What was actually true | Who found it |
|---|---|---|---|
| 1 | "The guard scans the repo for private words." | It scanned one file — the requirements register. | reviewer |
| 2 | "Coverage is complete." | A glob list covered 153 of 322 tracked files and silently missed whole components. | reviewer |
| 3 | "The guard catches every separator form." | The matcher required whole words, so a CamelCase compound never matched the token inside it. My positive control **passed when it should have failed.** | reviewer |
| 4 | "The guard is exempt only for technical reasons." | The exempted module **spelled all 22 private words in plaintext**. It was exempt precisely because it held what needed checking. | reviewer |
| 5 | "Both sides are normalised." | Only the scanned text was; a hyphenated token matched only in one exact spelling. | reviewer |
| 6 | "Nothing in published text names the scan." | **The commit message named seven identifiers.** The tree was scrubbed; the prose describing the scrub was not. | reviewer |
| 7 | "The guard reports honestly." | The private word list was *itself* published — the repo scrubbed of those words published them anyway. | **the user** |
| 8 | "An empty guard cannot pass CI." | It could. Both tests that would catch an empty digest set skipped when the private docs were absent — which is CI's state exactly. Simulated at the time: an empty set gave 8 passed, 2 skipped, with the suite green. | reviewer |
| 9 | "The exposure inventory is accurate." | It was wrong in **five** ways: wrong group count, wrong ref mechanism, an understated file list, an intro contradicting its own table, and one ref called clean while another sentence counted a file in it. | reviewer |
| 10 | "The exposure inventory is accurate now." | Still wrong: a code symbol miscategorised as a party name, two refs called identical when their trees differ in 14 files, two tags credited with moving past a base they precede. | reviewer |

The pattern is the point:

* **The suite was green throughout.** Green meant "the tests I wrote pass," not "the claim is true." I
  reported the first as the second.
* **I wrote the guard and its evidence in the same pass.** So the evidence inherited my blind spots. That
  is why controls passed while the guard was broken — they asserted the behaviour I *believed* it had.
* **Exemptions hid the failure.** The one file that most needed checking was the one excluded from the
  check.
* **The checks that mattered ran nowhere.** They skipped in the environment (CI) where an empty guard would
  actually ship.
* **Review was load-bearing, not advisory.** Removing the reviewer would have shipped all ten defects.
* **I declared done twice and was wrong twice.** Once only the user caught it.

---

### How each number above was measured

A verifier should be able to reproduce every figure without trusting this document.

| Figure | Command that produces it |
|---|---|
| 17 rebuild commits | `git reflog \| grep -c "commit: feat(skills)"` (distinct SHAs: 17) |
| 14 review rounds, 13 REJECT | `ls product_docs/A2_REVIEW*.json \| wc -l`, then read each `structuredOutput.verdict` (the review JSONs are PRIVATE, kept in the maintainer's checkout; the count is a fact about the process, not an artifact the public needs) |
| 22 words in the plaintext seed | `git show 9f99f39:vulnhunter-agent/agent/_banned_words.py \| sed -n '/^_SEED = (/,/^)/p' \| grep -c '"'` |
| 153 of 322 files covered | `git worktree add --detach /tmp/x b588690`, then expand `PUBLISHED_GLOBS` in that tree and compare against `git ls-files` |
| 7 identifiers in a commit message | `git log -1 --format=%B 9f99f39 \| grep -o -iE "<identifier pattern>" \| sort -u \| wc -l` |
| empty set passes without private docs | clone this repo (which lacks the private docs), set `_BANNED_SPAN_SHA1 = frozenset({})` in `vulnhunter-agent/agent/_banned_words.py`, run `pytest vulnhunter-agent/tests/test_skill_contracts.py` |
| the 22-word seed | `git show 9f99f39:vulnhunter-agent/agent/_banned_words.py` — a historical commit, reproducible from a clone |

Two figures in an earlier draft were wrong and were corrected by measurement before commit: "eight
rebuilds" (actually seventeen) and "154 of 322" (actually 153). This is rule R7 applied to this document
itself.

---

## 2. Rules

These are mandatory for every build in Tier A/B/C. A build is not complete — not "mostly complete," not
"complete pending review" — until every applicable rule is satisfied.

### R1. A claim is not evidence. Test the claim.

Never report "the suite is green" as proof of a claim. State the claim, then show the check that would fail
if the claim were false.

For every claim, the build must answer: **which test fails if this claim is false?** If the answer is "the
suite passes either way," there is no evidence, only an assertion.

*Correct:* "No published file names a scan identifier — `test_no_published_file_mentions_a_scan_specific_identifier`
greps the tracked tree, and appending each of eight leak forms to `vulnhunt/SKILL.md` failed it eight
times."

*Wrong:* "The guard is in place and the suite is green."

### R2. Every guard needs a positive control run BEFORE the reviewer sees it.

A guard with no positive control is an unproven hypothesis. A positive control is a deliberate injection of
the exact defect the guard exists to catch, and it must be run by the author, before review, and its
result recorded.

The control must inject the defect **in the shape real defects take**, not the shape the guard finds
easiest. Four of the ten failures above survived because the control tested a form the guard already
handled:

* A control asserting a token typed exactly cannot reveal that CamelCase compounds fail.
* A control run against a fixture cannot reveal that the real repo is dirty.
* A control in a directory that skips cannot reveal anything about the directory that ships.

Required: at least one control per claim, in the *most realistic* form of the defect, and at least one
control that exercises the **failure path** — a guard that has never been seen to fail has not been tested.

### R3. Exemptions are guilty until proven.

Any file, directory or path excluded from a check must carry a written reason, and must have its **own**
direct check covering the property the exemption skips.

The exemption that caused failure #4 was justified by a true statement ("the module defines the digests by
construction, so scanning it would be redundant") that was irrelevant to the actual risk (the module also
held plaintext words). A true justification can still hide a real gap.

Test the exemption reason: *does it exempt the file from a check that would have failed?* If yes, write a
separate check for that property.

### R4. A check that skips is not a check.

Any test with a skip path must be enumerated, with what makes it skip, and the build must state which of
those paths are exercised in **CI**, since CI is where the code ships.

Failure #8 is the canonical case: the only tests capable of catching an empty guard required a private file
that CI does not have. The tests were correct, the guard was empty, and CI was green. The build's own
documentation said the guard was "verified."

Required: for each skipping test, either remove the skip (make the property checkable without the absent
dependency) or add a **non-skipping** test that covers the property the skip would otherwise cover.

### R5. Review by someone who did not write it is mandatory, and its findings are not optional.

Self-review is not review. The record above is unambiguous: every one of the ten defects was found by a
reviewer or the user, and every one was read past by me.

Rules for the review loop:

* The reviewer must be independent of the author, with tools, and must be asked to **verify claims against
  the artifact**, not to read the code for style.
* Every finding must be resolved by a change to the artifact or an explicit, reasoned rejection. "I fixed
  it" is not a resolution; "here is the check that now fails without the fix" is.
* **A blocking finding is never dismissed as cosmetic without an argument for why.** Two rounds were wasted
  on findings I first judged to be nits, and both were correct.
* A degenerate review (a handful of tool calls, a verdict with no citations) is **not** evidence of
  anything. Re-run it. Do not treat a cheap approval as an approval.

### R6. Do not declare done. Ask.

Twice in the record above, I reported success before asking, and twice I was wrong. The reviewer's
approval is the *reviewer's* claim, not mine to convert into a declaration.

The correct close is: "here is the claim, here is the control that failed then passed, here is the residual
I could not fix, please check it." The author states what is *verified* and what is *claimed* separately,
and never presents a claim as verified because a test passed.

### R7. State residuals precisely, then verify the statement against the artifact.

Failure #9 and #10 were both in the *description* of the residual exposure — not the code. Both were
correctable by measurement, and both were written from memory instead.

Any statement of residual risk must be **measured**, not estimated. If it says "two refs," fetch every ref
and count. If it says "ten files," grep and count. Then re-read the sentence against the number: the intro
said "7 files" above a table of 10 for two consecutive commits.

### R8. The commit message is part of the artifact.

Failure #6: the tree was scrubbed, and the commit message describing the scrub spelled seven of the
identifiers. A stranger reading the repo sees commit messages. Whatever invariant the code maintains, the
commit message must satisfy it too.

For any claim enforced by a test over files, ask whether the commit message is inside or outside the
enforcement perimeter. If outside, check it by hand.

---

## 3. Checklist to paste into each build

Every build in Tier A/B/C ends by answering all of these. "N/A" requires a reason.

```
CLAIM: <one sentence, falsifiable>

EVIDENCE (R1)
- Which test fails if this claim is false?
- Which test fails if the guard is silently disabled entirely?

POSITIVE CONTROL (R2)
- Defect injected, in its most realistic form:
- Result observed:
- Was a control run that exercised the FAILURE path?

EXEMPTIONS (R3)
- Files/paths excluded from the check:
- Reason each is excluded:
- Separate check covering the property the exemption skips:

SKIPS (R4)
- Tests that can skip:
- Why each skips:
- Does CI exercise that path? If not, what non-skipping test covers it?

INDEPENDENT REVIEW (R5)
- Reviewer, model, tool calls, verdict:
- Blocking findings and their resolutions (each with a check that fails without the fix):
- Any finding dismissed, and the argument for dismissing it:

NOT DECLARED DONE (R6)
- Claimed (not verified): what the reviewer must check:
- Verified: what is proven, and by which check:

RESIDUAL (R7)
- Measured facts, with the command that produced each number:
- What remains and is not fixable in place, and why:

MESSAGE (R8)
- Does the commit message satisfy the invariant being enforced?
- How was that checked?
```

---

## 4. Applying this to the pending builds

**A3 (scaffold + check-phase), 2026-10-27.** The phase scaffold generates a check phase. The claim will be
"a scaffolded phase checks X." The positive control is a scaffold with X deliberately broken. Before this
policy, A3 would have shipped with a green suite and an untested claim.

**B2 (elimination audit).** An audit that finds nothing is indistinguishable from an audit that cannot find
anything. R2 applies directly: inject a known-bad case and confirm the audit reports it.

**B3 (Unverified section).** The claim is that HOLDs survive every stage. Per R2, the control is to inject a
HOLD at each stage and confirm it is still counted at the end — not to inspect the markdown and assert the
word "HOLD" appears.

**B4 (inventory normalization).** Normalising data risks silent loss. Per R4, verify the count before and
after with an independent count, not with the normaliser's own report.

---

## 5. The one-sentence version

**Green means the tests I wrote pass. That is a different claim from "it works," and only someone who did
not write them can tell you whether you have mistaken one for the other.**
