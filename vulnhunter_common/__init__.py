"""VulnHunter shared contract + runtime layer (plan §2.2, Phase 1 item 4).

This package is the machine-checkable home for the contracts that used to
live only in skill prose and were duplicated across runtimes:

- ``env``      — single source of truth for every ``VULNHUNT_*`` variable
- ``gitops``  — the one git clone/fetch/rev-parse implementation
- ``hostcmd`` — the one ``VULNHUNT_HOST_CMD`` launcher (resolution, spawn,
               timeout, transcript-on-stdout contract)
- ``manifest``— the ``scan_manifest.schema.json`` owner + validators

Layer: CONTRACT (machine-checked agreements) + RUNTIME (deterministic
mechanics shared by vh, harness, and the headless agent). It contains no
model SDK usage and never implements judgment — per §3.0 principle 3.
"""
