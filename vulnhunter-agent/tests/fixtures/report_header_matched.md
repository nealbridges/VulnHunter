# VulnHunter Security Audit Report

**Run ID**: acme-api_VULNHUNT_RESULTS_2026-10-23-020000
**Repository**: https://github.com/acme/api
**Audit Date**: 2026-10-23
**Branch**: main [1a2a746]
**Model**: deepseek-v4.1
**Skills**: vulnhunt@1a2a746379a70021b8e9345f92d204d7177b3c11 (source 1a2a746379a70021b8e9345f92d204d7177b3c11)
**Skills**: vulnhunter-run@1a2a746379a70021b8e9345f92d204d7177b3c11 (source 1a2a746379a70021b8e9345f92d204d7177b3c11)
**Skills match source**: yes
**Findings Summary**: 1 High+, 0 High, 2 Medium, 1 Low, 0 Informational

## Findings

| ID | Title | Severity | CWE | Status |
|----|-------|----------|-----|--------|
| F-001 | SQL injection in /search | High+ | CWE-89 | PoC confirmed |
