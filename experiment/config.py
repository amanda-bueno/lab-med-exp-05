from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BASE_URL = os.getenv("LAB05_BASE_URL", "http://127.0.0.1:8000")
USER_ID = int(os.getenv("LAB05_USER_ID", "100"))
PAGE = int(os.getenv("LAB05_PAGE", "1"))
LIMIT = int(os.getenv("LAB05_LIMIT", "50"))
WARMUP = int(os.getenv("LAB05_WARMUP", "10"))
REPETITIONS = int(os.getenv("LAB05_REPETITIONS", "100"))
DELAY_SECONDS = float(os.getenv("LAB05_DELAY_SECONDS", "0.1"))
RAW_RESULTS = Path(os.getenv("LAB05_RAW_RESULTS", DATA_DIR / "raw_results.csv"))
