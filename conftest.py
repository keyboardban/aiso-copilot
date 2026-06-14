"""Pytest bootstrap.

- Makes the project root importable (src.* absolute imports).
- Forces the deterministic path (no embeddings) for tests so the suite is fast
  and stable regardless of whether sentence-transformers is installed. Set
  AISO_USE_EMBEDDINGS=1 before pytest only if you specifically want to exercise
  the embedding path. (This must run before any `src.config` import.)
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("AISO_USE_EMBEDDINGS", "0")

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
