import json
from pathlib import Path
import numpy as np
from .types import RunConfig


def load_run_config(
    run_id: str,
    policy_key: str,
    scenario_key: str,
    seed: int,
    t_steps: int,
    out_dir: Path,
) -> RunConfig:
    cfg = RunConfig(
        run_id=run_id,
        policy_key=policy_key,
        scenario_key=scenario_key,
        seed=seed,
        t_steps=t_steps,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run_config.json").write_text(
        json.dumps(cfg.__dict__, indent=2),
        encoding="utf-8",
    )

    np.random.seed(seed)
    return cfg