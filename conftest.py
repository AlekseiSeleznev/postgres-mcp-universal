"""Top-level pytest bootstrap for running tests from repository root."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
GATEWAY_ROOT = REPO_ROOT / "gateway"

if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))
