"""Test session setup — repo root on sys.path, and CWD anchored to the root.

Tests live under tests/ but some read fixtures by repo-relative path
(eval/fixtures/..., eval/security_fixtures/...). Anchoring the working directory
to the repo root here keeps those paths valid no matter where pytest is invoked
from, and putting the root on sys.path lets `import cidra` work without install.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
