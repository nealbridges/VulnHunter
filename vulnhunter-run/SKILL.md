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

1. **Clone.** If the user gave a git URL, run `vh clone <url> --dest <dir>`.
   If they gave a checkout, use that directory and skip the clone.
2. **Hunt.** Invoke the `vulnhunt` skill on that checkout. Use this harness's
   subagents for the phase fan-out the skill describes. Do not shell out to
   another product's agent CLI. Wait until the skill finishes.
3. **Results.** Run `vh find-results <checkout>`. One directory must be
   printed. If none is printed, stop and say the hunt produced no results.
   Do not invent a results directory.
4. **Manifest.** Run `vh write-manifest <results-dir>`, then
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
