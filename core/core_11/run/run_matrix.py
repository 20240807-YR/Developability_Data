from pathlib import Path
import subprocess
import sys
import os
import re

# ------------------------
# Config
# ------------------------
SCENARIOS = ["cold", "hot", "oscillation"]

PYTHON = sys.executable
RUN_MODULE = "core.core_11.run.run_core11"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ART_ROOT = PROJECT_ROOT / "core" / "core_11" / "artifacts" / "core11"


# ------------------------
# Utilities
# ------------------------
def next_run_id(prefix="core11_demo_"):
    ART_ROOT.mkdir(parents=True, exist_ok=True)
    max_idx = 0
    for p in ART_ROOT.iterdir():
        if p.is_dir() and p.name.startswith(prefix):
            try:
                max_idx = max(max_idx, int(p.name.split("_")[-1]))
            except ValueError:
                pass
    return f"{prefix}{max_idx + 1:03d}"


def run_scenario(run_id: str, scenario: str):
    print(f"\n🚀 RUN {run_id} / {scenario}")

    env = os.environ.copy()
    env["CORE11_RUN_ID"] = run_id
    env["CORE11_SCENARIO"] = scenario

    subprocess.run(
        [PYTHON, "-m", RUN_MODULE],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )


# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    print("🧪 Core11 DEMO start")

    run_id = next_run_id()
    print("📦 run_id =", run_id)

    for scenario in SCENARIOS:
        run_scenario(run_id, scenario)

    print("\n✅ Core11 DEMO completed")
    print("Artifacts in:", (ART_ROOT / run_id).resolve())