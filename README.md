# VulnHunter

> [!NOTE]
> **A maintained fork** of [Capital One's
> VulnHunter](https://github.com/capitalone/VulnHunter) (Apache-2.0) — built to
> run on **any agent harness**, not just Claude Code. This fork's focus:
> **harness portability**, **sandboxed (containerized) exploit validation**,
> and **measured-impact PoCs**. See
> [Why the changes](#why-the-changes) ·
> [What this fork changes](#what-this-fork-changes) ·
> [The numbers](#the-numbers-behind-the-fork).

> **From pattern-matching to provability.**

VulnHunter is an open-source, **agentic AI security tool** that applies proactive, attacker-first analysis directly to source code. 

Unlike traditional, passive SAST scanners that flag suspicious patterns and often cause false positives, VulnHunter reasons like an adversary. It **identifies** which defects are actually exploitable, maps prospective attack paths, and proposes targeted, evidence-backed fixes.

Modern software supply chains are deeply interconnected. A single vulnerability in a widely-used open-source component can ripple across thousands of enterprises simultaneously.

VulnHunter was developed internally at Capital One and open-sourced for the community. This fork carries that work forward — same methodology, reworked to run on **any agent harness**, with **sandboxed (containerized) exploit validation** and **measured-impact PoCs** as the roadmap. See [What this fork changes](#what-this-fork-changes).

----

> **Dual-use caution**
> VulnHunter performs dual-use cybersecurity work (vulnerability discovery and
> exploitation). Expect guardrails: most commercially available models apply
> dual-use cyber safeguards, and aggressive exploitation behavior can trip
> rate limits or usage flags. VulnHunter's development and testing ran on
> open-weight, community-provided models — de-risked, abliterated, and
> uncensored — which are the models likely to matter for organizational use
> going forward. Audit only code you own or are otherwise authorized to
> audit.

---

> [!IMPORTANT]
> **Prerequisites & Model Requirements**
> VulnHunter's methodology is built to run on **open-weight, community-provided
> models** — the de-risked, abliterated, uncensored ones organizations can
> actually deploy. A capable reasoning model is required; the strongest model
> your harness offers gives the best results, but the methodology does not
> depend on a specific vendor's frontier model. **You supply your own model
> access.**

---

## What this fork changes

| Capability | Upstream (Capital One) | This fork | Status |
| :--- | :--- | :--- | :--- |
| **Harness portability** | Skills invoke Claude Code specifically; installer targets `~/.claude/skills`; model gates hardcode Opus; harness pins `claude-opus-4-8` | Skills are harness-portable prompt files (any harness with a skills directory + subagents); `VULNHUNT_SKILLS_DIR` / `VULNHUNT_AGENTS_DIR` / `VULNHUNT_BIN_DIR` / `VULNHUNT_HOST_CMD` / `VULNHUNT_MODEL` environment contract; model gates rephrased to "your harness's most capable reasoning model" | **Shipped** |
| **No-guess installer** | `install.sh` assumes `~/.claude/skills` | Explicit directories, honors `GROK_HOME` semantics, writes the `vh` launcher to `VULNHUNT_BIN_DIR`/`~/.local/bin`, installs the `vulnhunter-run` skill + agent definition; Windows `.cmd` equivalents updated | **Shipped** |
| **`vulnhunter-run` operator skill** | — (absent) | Unattended operator: clone → hunt → find-results → write/validate the scan manifest, with explicit stop rules and no improvisation | **Shipped** |
| **Benchmark/judge hardening** | Fixed model + basic retry | Model via environment, retry/backoff configuration, `analyze_misses` pipeline loss-point tracing, per-finding history tracking | **Shipped** |
| **Harness-neutral report language** | Claude-specific prose throughout the skills | Harness-neutral tool language (Agent → subagent, Claude CLI → harness session) | **Shipped** |
| **Sandbox-first exploit validation** | Exploit tests may be static traces; runtime choice ad hoc | Docker-first runtime provisioning; the runtime recorded per finding; Medium+ severity must execute | **In progress** |
| **Measured-impact PoCs** | PoCs are documents; impact asserted | Executable PoC + impact number in the finding (rows exposed, requests amplified, key-hours stranded) | **In progress** |

## Why the changes

VulnHunter's methodology is host-agnostic by nature: it is prompt procedure, not tool binding. The upstream project grew up inside Claude Code — a coherent choice, and the right first home. But the agent-harness landscape has broadened, and a security methodology that installs into only one of them stops being an audit capability and starts being a vendor feature. This fork makes four changes, each with a reason.

### 1. Harness portability — your team's harness is not our harness

Every skill here is a portable prompt file with an explicit environment contract (`VULNHUNT_SKILLS_DIR`, `VULNHUNT_AGENTS_DIR`, `VULNHUNT_MODEL`, `VULNHUNT_HOST_CMD`), and the model gates now ask for *your harness's most capable reasoning model* instead of a specific product. **Better means:** the same methodology installs into whatever harness your team already runs — and becomes comparable *across* harnesses in benchmark runs, which is how this fork is developed.

### 2. A no-guess installer — "where do skills go" is a per-harness answer

The upstream installer copied skills into `~/.claude/skills` unconditionally. On a machine running two harnesses — or a harness with a relocated home — that guess installs into the wrong place, silently. The fork's installer asks, or takes environment variables, and fails loudly with the exact instruction when the answer is missing. **Better means:** safe on multi-harness machines, correct under relocated homes, loud instead of silent when misconfigured.

### 3. Execution depth as a recorded decision — "provability" should not depend on model instinct

The original design already demands falsification and exploit tests. What it left open was *how hard* to work to actually execute them: static trace, mocked test, or a real containerized server. In one six-run benchmark against a single commit, that discretion produced anywhere from 3 to 42 findings — and opposite verdicts on the same sink, one proven against a mock, one closed by a test against a real server. This fork adds a runtime-provisioning procedure (Docker-first, recorded per finding) and a PoC discipline where impact is **measured** — rows leaked, ×-amplification, key-hours stranded — not narrated. **Better means:** a finding's validity no longer depends on which model had the instinct to stand up a container. *(In progress — the build plan is on the public roadmap; ask in issues or watch the repo's Discussions.)*

### 4. Operator ergonomics — a remediation loop compounds when it runs nightly

New in this fork: `vulnhunter-run`, an unattended operator that clones, hunts, locates results, and writes and validates the scan manifest with explicit stop rules. The benchmark tooling gains model configuration via environment, retry/backoff knobs, and loss-point analysis for missed findings. **Better means:** the difference between a tool you demo and a tool you schedule.

## The numbers behind the fork

We benchmark VulnHunter against itself: six full scans of one real production Go service — same commit, five harness/model stacks. The numbers below are from those runs, and they're why this fork exists.

| | |
|---|---|
| **14×** | spread in confirmed findings across runs of the same commit. The process measuring itself was the first vulnerability — closing that gap is this fork's build plan. |
| **42/42** | confirmed findings carried executable exploit tests — every one PASS, every one with its own PoC. No finding ships on a hunch. |
| **55%** | of candidate findings eliminated or downgraded by the adversarial verification pass before reaching you. Others scan. VulnHunter litigates. |
| **315** | attacker-controlled inputs inventoried in a single scan — every one traced, every disposition written. Completeness is a discipline, not an aspiration. |
| **20/20** | adversarial payloads executed against a live server in one run — outcome-measured, not asserted. |

<details>
<summary><strong>Where these numbers come from</strong></summary>

Six complete VulnHunter scans were run against one commit of the same
production Go service, across five harness/model stacks, over roughly three
weeks. Every figure above traces to retained scan artifacts — per-input
disposition tables, adversarial verdict tables, PoCs, and executed exploit
tests. Raw outputs are retained by the maintainer; ask, or re-run it
yourself.

</details>

---

## Why VulnHunter is Different

* **Attacker-First Forward Analysis:** Conventional tools often leverage "sink-first" analysis, looking at potentially dangerous code patterns to search backward for a hypothetical attacker, flooding teams with false positives. VulnHunter flips this model to simulate a bad actor's exact journey. It begins at potential attacker-accessible entry points (APIs, network messages, file uploads) and reasons *forward* to evaluate whether an attacker can truly break through.
* **Falsification Engine:** After finding a potential vulnerability, VulnHunter runs a structured reasoning workflow specifically designed to *disprove* its own argument. It searches for flawed assumptions, logic gaps, or security controls that would block the attack. It is designed to immediately discard findings that rely on unsupported assumptions. What reaches you is a high-priority, actionable defect. On the roadmap: an **independent adversarial verifier** — a separate agent whose only job is to disprove the finding, rather than asking the hunter to grade its own homework (see the build plan).
* **Evidence-Backed Remediation:** When a defect survives the falsification engine, VulnHunter maps the exact exploit path, explains the structural flaw, details the specific capabilities or access an attacker would gain, and generates focused, targeted code changes for review.
* **PoC or It Didn't Happen:** A vulnerability isn't a vulnerability until it's *proven*. Every confirmed finding carries a proof-of-concept — ideally executed, with the impact **measured** (rows exposed, requests amplified, credentials stranded) rather than narrated. Findings without working PoCs are labeled as such, so you always know what you're looking at.

---

## The Closed Loop: Hunt → Fix → Verify

VulnHunter ships as three composable agent skills that form a complete, automated remediation loop:

| Skill | Phase | Core Responsibility |
| :--- | :--- | :--- |
| **`/vulnhunt`** | **Hunt** | Maps entry points to dangerous sinks. Filters findings through a multi-stage falsification pipeline (Recon → Parallel Hunt → Adversarial Disprove → Capability Filter). Emits only verified issues with an executable exploit and a proposed fix. |
| **`/vulnhunter-fix`** | **Fix** | Developer-led, test-driven remediation. It writes an exploit demo, creates a failing security test (**RED**), implements the code fix (**GREEN**), verifies the exploit is blocked without regressions, and cuts a reviewable PR. |
| **`/vulnhunt-fix-verify`** | **Verify** | A completely separate, read-only agent that independently validates whether a finding was successfully remediated. It emits a per-finding verdict so fixes are proven, not taken on faith. |

> **Note:** For running this loop unattended at scale, `vulnhunter-agent/` wraps the scanner in a headless runtime, while `harness/` drives it across multiple repositories in batch.

> **On the naming:** the suite is **VulnHunter**, but the core scanner command is `/vulnhunt` (and the verifier `/vulnhunt-fix-verify`) — the shorter form is intentional, not a typo. The `/vulnhunter-fix` remediation skill and the `vulnhunter-agent/` runtime keep the full spelling.

---

## Repository Layout

Each component is organized into a self-contained subtree:

| Path | Description |
| :--- | :--- |
| `vulnhunt/` | The core `/vulnhunt` scanner skill (Prompt-only: `SKILL.md` + phases). See [`vulnhunt/README.md`](vulnhunt/README.md). |
| `vulnhunter-fix/` | The `/vulnhunter-fix` skill, its companion Python helper package, and tests. See [`vulnhunter-fix/README.md`](vulnhunter-fix/README.md). |
| `vulnhunt-fix-verify/` | The `/vulnhunt-fix-verify` standalone verification skill (Prompt-only). See [`vulnhunt-fix-verify/README.md`](vulnhunt-fix-verify/README.md). |
| `vulnhunter-agent/` | Config-driven headless runtime wrapper that runs scans and files GitHub issues. See [`vulnhunter-agent/README.md`](vulnhunter-agent/README.md). |
| `harness/` | Developer tooling for running large batch-scans and benchmarking detection accuracy. See [`harness/README.md`](harness/README.md). |
| `vh/` | Deterministic operator CLI for a single scan: clone, find the results directory, write and validate the scan manifest, and launch the host's headless command. No model SDK. |

---

## Requirements & Setup

### Prerequisites
* An agent harness (e.g. Claude Code, omp, Codex, or similar) with access to a capable reasoning model — open-weight, community-provided models are the primary development target. **You supply your own model access.**
* Python 3.12+ (Required only for the runtime agent and the benchmarking harness).
* *Responsibility Check:* Ensure you are only scanning code bases you are explicitly authorized to analyze.

### Installation

```bash
# Clone the repository
git clone https://github.com/nealbridges/VulnHunter.git
cd VulnHunter

# Skills and agents directories are required. This script does not guess.
# If GROK_HOME is set, use that home. Do not use ~/.grok when GROK_HOME
# points somewhere else, and do not use ~/.claude/skills unless this
# process is Claude Code.
#   VULNHUNT_SKILLS_DIR="$GROK_HOME/skills" \
#   VULNHUNT_AGENTS_DIR="$GROK_HOME/agents" \
#   ./install.sh
./install.sh
```

On Windows, use the `.cmd` equivalents from a `cmd.exe` or PowerShell prompt:

```bat
git clone https://github.com/nealbridges/VulnHunter.git
cd VulnHunter

REM Set VULNHUNT_SKILLS_DIR to this harness's skills directory first.
.\install.cmd

REM (Optional) To clean up or remove installed skills
REM .\uninstall.cmd
```

> [!NOTE]
> `install.sh`/`install.cmd` copy files directly (rather than symlinking) because symlinks can break `find`/`glob` functionality inside subagents. Re-run the install script after pulling updates to refresh your local environment.
>
> **Any harness:** the skills are plain prompt files. `install.sh` copies them
> into `VULNHUNT_SKILLS_DIR`, copies `agents/vulnhunter.md` into
> `VULNHUNT_AGENTS_DIR` when that is set, and writes a `vh` launcher to
> `VULNHUNT_BIN_DIR` or `~/.local/bin`. `~/.local/bin` has to be on `PATH`.
> A model installing into the harness it is running uses `$GROK_HOME/skills`
> and `$GROK_HOME/agents` when `GROK_HOME` is set.

---

## Usage Guide

### 1. Run the Scanner
Install the `vulnhunt` skill into your harness (see above), open a session on the host's most capable reasoning model, and invoke:

```text
/vulnhunt
```

The skill also loads `vulnhunt/phases/`. If your harness does not follow a skill's subdirectories on its own, add that `phases/` directory to the session the same way you add any other path.

### 2. Run the Fixer
The fixer requires `git`, the GitHub CLI (`gh`) authenticated to your target repositories, and its Python helpers installed (`pip install -e ".[dev]"` inside the `vulnhunter-fix/` directory).

Install the `vulnhunter-fix` skill and invoke:

```text
/vulnhunter-fix
```
*See [`vulnhunter-fix/README.md`](vulnhunter-fix/README.md) for advanced operational modes and configuration settings.*

### 3. Run the Fix Verifier
The verifier runs strictly read-only over trusted roots under a tight tool envelope (Read/Write/Edit/Glob/Grep/subagent — **no shell execution, no network access**). The caller must pre-create the output (`out`) directory.

Install the `vulnhunt-fix-verify` skill (it reads `vulnhunt-fix-verify/phases/`) and invoke:

```text
/vulnhunt-fix-verify repo=<abs_path> report=<abs_path> fixed=VULN-001,... out=<abs_path> [comments=<abs_path>] [additional_repos=<path1>,<path2>]
```

---

## Automation & Scale

### Headless Runtime Agent (`vulnhunter-agent/`)
For non-interactive or CI/CD pipelines, `vulnhunter-agent/` wraps the scanner into a headless workflow. It clones targets, executes `/vulnhunt`, publishes results, and opens GitHub issues for confirmed bugs. Model and credential wiring for that runtime live in its own README; the skills above do not depend on it. 

Review the [`vulnhunter-agent/README.md`](vulnhunter-agent/README.md) for deployment blueprints.

### Local Harness (`harness/`)
The `harness/` directory provides workstation-scale developer tooling. To initialize, run `cd harness && pip install -e ".[dev]"`.

#### Batch Scanning
Manage your target list in `harness/local_harness/batch/REPO_LIST.txt` (one GitHub URL per line, lines starting with `#` are ignored):

```bash
cd harness
python -m local_harness.batch.run scan                  # Clone and scan every repo in the list
python -m local_harness.batch.run scan --resume         # Skip repositories already processed
python -m local_harness.batch.run status                # Monitor progress across your batch
python -m local_harness.batch.run collect               # Gather all findings for centralized review
```

#### Benchmarking Mode
Evaluate scanner accuracy against a known-vulnerable vulnerability corpus (Clone → Scan → LLM-Judge → Tally Metrics):

```bash
python -m local_harness.benchmark.run                  # Execute full benchmark run
python -m local_harness.benchmark.run --repos "name"   # Benchmark a single target repository
python -m local_harness.benchmark.run --tally-only      # Re-generate the analytical report only
```

> **Bring Your Own Corpus:** This repository ships with a minimal synthetic example (`harness/local_harness/benchmark/ground_truth/EXAMPLE.json`) mapped to public targets like OWASP NodeGoat, Juice Shop, and WebGoat. Build out your own testing suites inside `ground_truth/<repo>.json`. Define your target scanning/judging engines in `harness/local_harness/config.py`.

### Operator CLI (`vh/`)
`vh` is a deterministic, model-free companion for a single scan run. It sequences the mechanical steps around a hunt and validates the output shape:

```bash
vh clone <url> --dest <dir>                    # shallow-clone the target
vh find-results <checkout>                     # print *_VULNHUNT_RESULTS_* directories
vh write-manifest <results-dir> --exit-code 4  # write scan_manifest.json; record the agent exit code
vh validate-manifest <results-dir>             # check the manifest against the schema rules
VULNHUNT_HOST_CMD="<one-shot>" vh host <prompt-file>   # run the harness's headless one-shot
```

`--exit-code` records the exit code the hunt actually produced (0-4; an invalid value is recorded as 1). When the flag is omitted, the exit code is derived from the results directory: a non-empty `README.md` scan report means 0, anything else means 1. `vh write-manifest` writes a schema-shaped stub manifest — it never populates `findings`; the headless runtime agent (`vulnhunter-agent/`) is the writer that extracts real findings from the scan report.

---

## Running Tests

Each Python component maintains its own isolated testing suite. Run them using `pytest`:

```bash
cd harness          && pip install -e ".[dev]" && python -m pytest tests/ --cov=local_harness
cd vulnhunter-fix   && pip install -e ".[dev]" && python -m pytest -q
cd vulnhunter-agent && pip install -e ".[dev]" && python -m pytest -q
python -m pytest vh/tests -q    # from the repository root; vh is a plain package
```

---

## Contributing, Security & License

* **A Note on Models:** VulnHunter's methodology is developed against open-weight, community-provided models — de-risked, abliterated, and uncensored — the deployment reality most organizations are heading toward. The skills are harness-portable prompt files that work with any agent harness; only the headless runtime (`vulnhunter-agent/`) and `harness/` remain Claude-Code-based.
* **Contributing:** See [CONTRIBUTING.md](CONTRIBUTING.md) to propose core framework improvements, prompt updates, or wider model support configurations.
* **Security:** Review [SECURITY.md](SECURITY.md) for instructions on how to safely report security vulnerabilities found within VulnHunter itself.
* **License:** Distributed under the terms of the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
