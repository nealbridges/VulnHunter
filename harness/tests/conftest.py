"""Make the shared contract layer importable for in-place harness runs.

The component suites run with working-directory = the component (CI) or
from its directory locally; `vulnhunter_common` is installed as
`c1-vulnhunter-common` in CI, but local in-place runs may not have it
installed, so mirror the sys.path bootstrap that
`local_harness/benchmark/analyze_misses.py` already uses and add the
repository root explicitly.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
