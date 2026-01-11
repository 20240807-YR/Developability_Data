# core/core_11/run/run_core11.py
from __future__ import annotations

from pathlib import Path
import json
import os
from datetime import datetime

# ==============================
# Engine imports
# ==============================
from core.core_11.engine.bootstrap import load_run_config
from core.core_11.engine.state_machine import init_state
from core.core_11.engine.dynamics import update_dynamics
from core.core_11.engine.policy_engine import hazard_from_score, should_request_switch
from core.core_11.engine.scheduler import decide_allocation
from core.core_11.engine.fallback_engine import check_fallback, build_fallback_event
from core.core_11.engine.logger import LoggerBundle
from core.core_11.engine.replay import compute_checksum, save_checksum


# =========================================================
# Utilities
# =========================================================
def load_scenario(scenario_dir: Path, scenario_key: str) -> dict:
    path = scenario_dir / f"{scenario_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path.resolve()}")

    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        raise ValueError(f"Scenario file is EMPTY: {path.resolve()}")

    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Scenario JSON parse failed:\n{path.resolve()}\n{e}"
        ) from e


def dump_json(path: Path, obj: dict, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=sort_keys)


# =========================================================
# Main
# =========================================================
def main():
    # -----------------------------------------------------
    # Paths
    # -----------------------------------------------------
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    CORE11_DIR = PROJECT_ROOT / "core" / "core_11"
    ART_ROOT = CORE11_DIR / "artifacts" / "core11"
    SCENARIO_DIR = CORE11_DIR / "scenarios"

    ART_ROOT.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------
    # Scenario
    # -----------------------------------------------------
    SCENARIO_KEY = os.environ.get("CORE11_SCENARIO", "cold")
    scenario = load_scenario(SCENARIO_DIR, SCENARIO_KEY)

    # -----------------------------------------------------
    # Run ID (run_matrix에서 반드시 주입)
    # -----------------------------------------------------
    RUN_ID = os.environ.get("CORE11_RUN_ID")
    if not RUN_ID:
        raise RuntimeError(
            "CORE11_RUN_ID is not set.\n"
            "→ run_core11.py는 run_matrix.py를 통해 실행해야 함."
        )

    # -----------------------------------------------------
    # Output directory
    # -----------------------------------------------------
    RUN_DIR = ART_ROOT / RUN_ID / SCENARIO_KEY
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    print("\n🚀 Core11 start")
    print("  run_id   :", RUN_ID)
    print("  scenario :", SCENARIO_KEY)
    print("  out_dir  :", RUN_DIR.resolve())
    print("")

    # -----------------------------------------------------
    # Snapshots
    # -----------------------------------------------------
    dump_json(RUN_DIR / "scenario.json", scenario)

    dump_json(
        RUN_DIR / "policy_snapshot.json",
        scenario.get("policy_snapshot", {}),
    )

    dump_json(
        RUN_DIR / "run_meta.json",
        {
            "run_id": RUN_ID,
            "scenario_key": SCENARIO_KEY,
            "created_at_utc": datetime.utcnow().isoformat(),
            "project_root": str(PROJECT_ROOT),
        },
    )

    # -----------------------------------------------------
    # Scenario contract validation
    # -----------------------------------------------------
    required_keys = [
        "T_STEPS",
        "candidate_pool",
        "candidates",
        "hazard_threshold",
        "drift_per_step",
    ]
    missing = [k for k in required_keys if k not in scenario]
    if missing:
        raise KeyError(
            f"Scenario '{SCENARIO_KEY}' missing keys: {missing}"
        )

    # -----------------------------------------------------
    # Bootstrap config
    # -----------------------------------------------------
    cfg = load_run_config(
        run_id=RUN_ID,
        policy_key=scenario.get("policy_key", "STATE_BASED"),
        scenario_key=SCENARIO_KEY,
        seed=int(os.environ.get("CORE11_SEED", 42)),
        t_steps=int(scenario["T_STEPS"]),
        out_dir=RUN_DIR,
    )

    try:
        dump_json(RUN_DIR / "run_config_snapshot.json", cfg.__dict__)
    except Exception:
        if isinstance(cfg, dict):
            dump_json(RUN_DIR / "run_config_snapshot.json", cfg)

    # -----------------------------------------------------
    # Init
    # -----------------------------------------------------
    fallback_pool = list(scenario["candidate_pool"])
    if not fallback_pool:
        raise ValueError("scenario['candidate_pool'] is empty")

    state = init_state(fallback_pool[0])
    logger = LoggerBundle(RUN_DIR)

    hazard_threshold = float(scenario["hazard_threshold"])

    # -----------------------------------------------------
    # Main loop
    # -----------------------------------------------------
    for step in range(int(cfg.t_steps)):
        current_id = state.current_allocation
        candidate_info = scenario["candidates"][current_id]

        proxy_surv = float(candidate_info["proxy_survivability"])
        hazard = hazard_from_score(proxy_surv)

        want_switch = should_request_switch(hazard, hazard_threshold)

        decision = decide_allocation(
            step=step,
            current=current_id,
            candidate=current_id,
            allow_switch=want_switch,
        )

        fallback_target = check_fallback(
            state=state,
            hazard=hazard,
            fallback_pool=fallback_pool,
            threshold=hazard_threshold,
        )

        fallback_triggered = False
        if fallback_target and fallback_target != current_id:
            logger.log_fallback(
                build_fallback_event(step, current_id, fallback_target)
            )
            decision.allocation_id = fallback_target
            decision.switched = True
            decision.reason = "FALLBACK_TRIGGERED"
            fallback_triggered = True

        # apply decision
        state.current_allocation = decision.allocation_id

        # dynamics update
        state = update_dynamics(
            state,
            hazard,
            float(candidate_info["operational_risk"]),
            float(scenario["drift_per_step"]),
        )

        # logging
        logger.log_decision(decision)
        logger.log_state(state)
        logger.log_audit(
            {
                "step": step,
                "proxy_survivability": proxy_surv,
                "hazard": hazard,
                "hazard_threshold": hazard_threshold,
                "want_switch": bool(want_switch),
                "fallback_evaluated": True,
                "fallback_triggered": fallback_triggered,
                "allocation": state.current_allocation,
            }
        )

    # -----------------------------------------------------
    # Finalize
    # -----------------------------------------------------
    logger.flush()

    checksum = compute_checksum(RUN_DIR)
    save_checksum(cfg.run_id, checksum, RUN_DIR)

    print("✅ Core11 run completed")
    print("run_id   :", RUN_ID)
    print("scenario :", SCENARIO_KEY)
    print("checksum :", checksum)
    print("logs in  :", RUN_DIR.resolve())
    print("")


if __name__ == "__main__":
    main()