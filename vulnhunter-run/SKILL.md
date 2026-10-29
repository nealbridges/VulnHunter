---
name: vulnhunter-run
description: Unattended VulnHunter operator. Clone a repo, run the vulnhunt skill with this harness's own tools and subagents, then write and check the scan manifest. Does not call a model SDK and does not name a harness. 
trigger:
  - /vulnhunter-run
  - user asks to scan a repository unattended
  - user asks to run vulnhunter headlessly
---

# VulnHunter operator

You are the operator, not the hunter. The hunt methodology lives in the
`vulnhunt` skill. Your harness runs that skill with its own model, tools,
and subagents. You only sequence the steps and refuse to improvise when a
step fails.

## Install into the harness that is running you

When asked to install these skills, run `install.sh` from the repository
root. Do not guess a directory.

- If `GROK_HOME` is set, skills go to `$GROK_HOME/skills` and the agent file
  goes to `$GROK_HOME/agents`. Do not write to `~/.grok` when `GROK_HOME` is
  a different directory.
- Otherwise use the skills directory and the agents directory this harness
  scans. Do not use `~/.claude/skills` unless this process is Claude Code.
- The same `install.sh` writes `vh` to `~/.local/bin` unless
  `VULNHUNT_BIN_DIR` is set. `vh` is what later steps call. It is not
  `python3 -m vh` from some other checkout.

```bash
VULNHUNT_SKILLS_DIR="$GROK_HOME/skills" \
VULNHUNT_AGENTS_DIR="$GROK_HOME/agents" \
./install.sh
```

Omit `GROK_HOME` from that command when it is unset, and pass this harness's
own two directories instead.

The `vh` commands do not talk to a model.

## Steps

0. **Verify the skill set.** Resolve the skills directory *this harness will
   actually load*, following its documented root precedence, and the source
   checkout the skill was installed from. Then run:

   ```bash
   vh check-skills --root <this harness's skills dir> --source <source checkout>
   ```

   `vh` does not know which harness is running — you supply the root. It
   compares the installed bytes against the **source working tree** and the
   recorded install commit against source `HEAD`. Both must agree for the
   check to pass, which is why a dirty source checkout cannot produce a clean
   proof: the bytes are real, but they are not provably `HEAD`'s bytes. On
   exit 0 the skill set matches source: carry on.

   On a non-zero exit, reinstall with `install.sh` into that root and re-check
   once. If it still fails, **STOP** and report both commits for every
   drifted skill — a hunt on a stale skill cannot be compared to any other
   run, and every procedure fix it was supposed to carry is absent. Exit 2
   means the invocation is wrong (root not found, a source path with no skill
   layout, or no skill there came from that source): fix the paths, do not
   treat it as drift.

   Carry forward, for the report's header (Phase 4): for each skill, the
   commit its bytes are attributable to (`bytes_from` in `--json`), the source
   commit it was compared against, whether the whole set matched, and whether
   the source checkout was dirty. A run whose skills do not match source — or
   whose source was dirty, leaving `bytes_from` unknown — MUST record
   `Skills match source: no` and MUST NOT claim cross-run comparability.

1. **Clone.** If the user gave a git URL, run `vh clone <url> --dest <dir>`.
   If they gave a checkout, use that directory and skip the clone.
2. **Hunt.** Invoke the `vulnhunt` skill on that checkout. Use this harness's
   subagents for the phase fan-out the skill describes. Do not shell out to
   another product's agent CLI. Wait until the skill finishes.
3. **Results.** Run `vh find-results <checkout>`. One directory must be
   printed. If none is printed, stop and say the hunt produced no results.
   Do not invent a results directory.
4. **Manifest.** If the README's first line starts with
   `# VulnHunter scan STOPPED`, pass `--exit-code 1`
   (`vh write-manifest <results-dir> --exit-code 1`), because
   `vh write-manifest` treats any non-empty README as exit 0. Otherwise run
   `vh write-manifest <results-dir>`. Then run
   `vh validate-manifest <results-dir>`. If validation fails, stop and report
   the error. Do not hand-edit the manifest to force a pass.
5. **Stop.** Tell the user the results path and whether the manifest
   validated. Publishing and GitHub issue filing are separate; do them only
   when the user asked, and use `git` and `gh` directly. Do not claim an
   issue was filed unless `gh` printed the URL.

## Headless lab use

A batch runner sets `VULNHUNT_HOST_CMD` to this harness's headless one-shot.
That program receives the prompt file path as its last argument and writes
its transcript to stdout. `vh host <prompt-file>` is the only launcher.
There is no default command.
