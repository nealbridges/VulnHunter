"""LLM-as-judge: compare vulnhunter scan results against benchmark findings."""

import json
import os
import time
import urllib.error
import urllib.request

from local_harness.config import (
    JUDGE_MAX_RETRIES,
    JUDGE_RETRY_BACKOFF_MULTIPLIER,
    JUDGE_RETRY_INITIAL_BACKOFF,
    JUDGE_RETRY_MAX_BACKOFF,
    JUDGE_TIMEOUT,
    MODEL,
)

JUDGE_SYSTEM_PROMPT = """You are a security finding comparator. Your job is to determine whether a vulnerability scanner's output detected specific known vulnerabilities.

You will receive:
1. The scanner's full results report
2. One or more benchmark findings to check

For EACH benchmark finding, determine if the scanner detected the SAME vulnerability.
The scanner may use different terminology, different finding IDs, or describe the vulnerability at a different level of detail. What matters is whether the SAME security issue was identified.

Matching criteria (ALL must be true for "detected"):
- Same vulnerability CLASS — OR the scanner found a vulnerability earlier in the
  same data flow whose fix would also prevent the benchmark finding (e.g., scanner
  found path traversal and proposed input validation that would also block the
  downstream XSS the benchmark describes). When the root cause fix is the same,
  a shallower classification still counts as detection.
- Same LOCATION (same file or closely related files in the same component)
- Same ROOT CAUSE (same missing check, same unsanitized input, same flawed logic)

It is NOT required that:
- The scanner uses the same finding ID
- The description is word-for-word identical
- Every specific detail matches (line numbers may differ slightly)
- The severity rating matches

A finding that is a duplicate/subset of another detected finding should also count as detected if the core issue is the same.

Output ONLY a valid JSON array with one object per benchmark finding:
[{"finding_id": "...", "detected": true/false, "confidence": "high"|"medium"|"low", "reasoning": "1-2 sentence explanation", "matched_finding_id": "scanner finding ID or null"}]"""


def read_results_report(results_dir):
    """Read the scanner's README.md report from a results directory."""
    readme_path = os.path.join(results_dir, "README.md")
    if not os.path.isfile(readme_path):
        return None
    with open(readme_path) as f:
        return f.read()


def judge_findings_batch(results_report, findings, model=None):
    """Judge multiple benchmark findings against one scan result in a single LLM call.

    Args:
        results_report: Content of the scanner's README.md
        findings: List of benchmark finding dicts (finding_id, type, description)
        model: Model to use (defaults to config.MODEL)

    Returns: List of judgment dicts, one per finding.
    """
    if model is None:
        model = MODEL

    findings_text = "\n\n".join(
        [
            f"### Benchmark Finding: {f['finding_id']} (Type: {f['type']})\n{f['description']}"
            for f in findings
        ]
    )

    prompt = f"""## Scanner Results Report

{results_report}

---

## Benchmark Findings to Evaluate

{findings_text}

---

For EACH benchmark finding above, determine if the scanner detected it. Respond with ONLY a JSON array."""

    backoff = JUDGE_RETRY_INITIAL_BACKOFF

    for attempt in range(JUDGE_MAX_RETRIES + 1):
        try:
            result = _invoke_judge(prompt, model)
        except TimeoutError:
            return [
                {
                    "finding_id": f["finding_id"],
                    "detected": None,
                    "confidence": None,
                    "reasoning": "judge timed out",
                    "matched_finding_id": None,
                }
                for f in findings
            ]

        if result.returncode != 0 and _is_judge_rate_limited(result):
            if attempt < JUDGE_MAX_RETRIES:
                print(
                    f"    [judge] 429 rate limit on attempt {attempt + 1}, "
                    f"retrying in {backoff:.0f}s ...",
                    flush=True,
                )
                time.sleep(backoff)
                backoff = min(backoff * JUDGE_RETRY_BACKOFF_MULTIPLIER, JUDGE_RETRY_MAX_BACKOFF)
                continue
            return [
                {
                    "finding_id": f["finding_id"],
                    "detected": None,
                    "confidence": None,
                    "reasoning": "judge failed: 429 rate limit (retries exhausted)",
                    "matched_finding_id": None,
                }
                for f in findings
            ]

        if result.returncode != 0:
            error = (
                result.stderr.strip()[:200] if result.stderr else f"exit code {result.returncode}"
            )
            return [
                {
                    "finding_id": f["finding_id"],
                    "detected": None,
                    "confidence": None,
                    "reasoning": f"judge failed: {error}",
                    "matched_finding_id": None,
                }
                for f in findings
            ]

        return _parse_judge_output(result.stdout, findings)


def _invoke_judge(prompt, model):
    """One chat completion against the host's OpenAI-compatible endpoint.

    ``VULNHUNT_BASE_URL`` is the endpoint the harness is already using.
    There is no default and no vendor CLI.
    """
    base = os.environ.get("VULNHUNT_BASE_URL", "").rstrip("/")
    if not base:
        return type(
            "R", (), {"returncode": 2, "stdout": "", "stderr": "VULNHUNT_BASE_URL is not set"}
        )()
    if not model:
        model = os.environ.get("VULNHUNT_MODEL", "")
    if not model:
        return type(
            "R", (), {"returncode": 2, "stdout": "", "stderr": "VULNHUNT_MODEL is not set"}
        )()
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
    ).encode()
    request = urllib.request.Request(
        base + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=JUDGE_TIMEOUT) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": f"{exc.code} {detail}"})()
    except TimeoutError as exc:
        raise TimeoutError(str(exc)) from exc
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            raise TimeoutError(str(exc.reason)) from exc
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": str(exc.reason)})()
    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return type(
            "R",
            (),
            {"returncode": 1, "stdout": "", "stderr": "judge response had no message content"},
        )()
    return type("R", (), {"returncode": 0, "stdout": text, "stderr": ""})()


def _is_judge_rate_limited(result):
    """Detect an HTTP 429 from the completion endpoint."""
    combined = (result.stderr or "") + (result.stdout or "")
    return "429" in combined and ("rate_limit" in combined or "rate limit" in combined.lower())


def _parse_judge_output(raw_output, findings):
    """Parse the judge's JSON output, handling common formatting issues."""
    text = raw_output.strip()

    # Try to extract JSON array from the response
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        judgments = json.loads(text)
        if isinstance(judgments, list):
            return judgments
    except json.JSONDecodeError:
        pass

    # If parsing fails, return error judgments
    return [
        {
            "finding_id": f["finding_id"],
            "detected": None,
            "confidence": None,
            "reasoning": "failed to parse judge output",
            "matched_finding_id": None,
        }
        for f in findings
    ]
