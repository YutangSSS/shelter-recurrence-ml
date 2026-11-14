"""Download the public Austin Animal Center dataset from Hugging Face at a pinned revision.

Every file is checked against a SHA-256 so a run on a laptop and a run in CI read the same bytes.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "jason1966/aaronschlegel_austin-animal-center-shelter-intakes-and-outcomes"
REVISION = "4621420f23e9008de4581d971b1a9626d2ccd506"
FILES = {
    "aac_intakes.csv": "e2533003483573ee67c3cf0f04249ee633784d85fc87cffa014afbf2bd512de5",
    "aac_outcomes.csv": "a64dc2ad497c3309b1fff80600d4bfe8e2ae4c2d0a7fe3935859825de38479b3",
}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    for name, expected in FILES.items():
        path = DATA_DIR / name
        if path.exists() and sha256(path) == expected:
            print(f"ok      {name}")
            continue
        url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{name}"
        print(f"fetch   {name}")
        urllib.request.urlretrieve(url, path)
        got = sha256(path)
        if got != expected:
            print(f"SHA-256 mismatch for {name}: {got}", file=sys.stderr)
            return 1
        print(f"ok      {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
