import hashlib
import json
from pathlib import Path


def compute_checksum(log_dir: Path) -> str:
    h = hashlib.sha256()

    for p in sorted(log_dir.glob("*.csv")):
        h.update(p.read_bytes())

    return h.hexdigest()


def save_checksum(run_id: str, checksum: str, out_dir: Path):
    payload = {
        "run_id": run_id,
        "checksum": checksum,
    }
    (out_dir / "replay_checksum.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )