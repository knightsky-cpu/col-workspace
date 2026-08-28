from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIVE_TESTS_DIR = REPOSITORY_ROOT / "live-tests"

for path in (REPOSITORY_ROOT, LIVE_TESTS_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
