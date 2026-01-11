# core/core_11/run/run_core11.py

from __future__ import annotations

from pathlib import Path
import re
import json

# 🔧 패키지 경로 수정: core.core_11 기준
from core.core_11.engine.bootstrap import load_run_config
from core.core_11.engine.state_machine import init_state
from core.core_11.engine.dynamics import update_dynamics
from core.core_11.engine.policy_engine import hazard_from_score, should_request_switch
from core.core_11.engine.scheduler import decide_allocation
from core.core_11.engine.fallback_engine import check_fallback, build_fallback_event
from core.core_11.engine.logger import LoggerBundle
from core.core_11.engine.replay import compute_checksum, save_checksum


def next_run_id(artifacts_root: Path, prefix: str = "core11_demo_") -> str:
    """
    artifacts_root 아래 디렉토리를 스캔해서
    core11_demo_001, 002, ... 중 다음 run_id를 반환
    """
    artifacts_root.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(rf"{re.escape(prefix)}(\d+)")
    max_idx = 0

    for p in artifacts_root.iterdir():
        if not p.is_dir():
            continue
        m = pattern.fullmatch(p.name)
        if m:
            max_idx = max(max_idx, int(m.group(1)))

    return f"{prefix}{max_idx + 1:03d}"


def load_scenario(scenario_dir: Path, scenario_key: str) -> dict:
    """
    scenario json 로드 + 빈 파일/파싱 오류를 명확히 에러로 표시
    """
    path = scenario_dir / f"{scenario_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path.resolve()}")

    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        raise ValueError(
            f"Scenario file is EMPTY: {path.resolve()}\n"
            f"→ cold/hot/oscillation.json 내용이 비어있어서 JSONDecodeError가 난 상태."
        )

    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Scenario JSON parse failed: {path.resolve()}\n"
            f"→ {e}"
        ) from e


def main():
    # ------------------------
    # Paths
    # ------------------------
    # Developability_Data/ (프로젝트 루트)
    PROJECT_ROOT = Path(__file__).resolve().parents[3]

    # Developability_Data/core/core_11
    CORE11_DIR = PROJECT_ROOT / "core" / "core_11"

    # Developability_Data/core/core_11/artifacts/core11
    ART_ROOT = CORE11_DIR / "artifacts" / "core11"

    # Developability_Data/core/core_11/scenarios
    SCENARIO_DIR = CORE11_DIR / "scenarios"

    ART_ROOT.mkdir(parents=True, exist_ok=True)

    # ------------------------
    # Load scenario
    # ------------------------
    SCENARIO_KEY = "cold"  # cold / hot / oscillation
    scenario = load_scenario(SCENARIO_DIR, SCENARIO_KEY)

    # ------------------------
    # Auto run_id + per-run output dir
    # ------------------------
    RUN_ID = next_run_id(ART_ROOT)  # core11_demo_001, 002, ...
    RUN_DIR = ART_ROOT / RUN_ID / SCENARIO_KEY
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Core11 start: run_id={RUN_ID}, scenario={SCENARIO_KEY}")
    print("RUN_DIR:", RUN_DIR.resolve())

    # ------------------------
    # Bootstrap run
    # ------------------------
    # scenario contract 최소 요구
    required_keys = ["T_STEPS", "candidate_pool", "candidates", "hazard_threshold", "drift_per_step"]
    missing = [k for k in required_keys if k not in scenario]
    if missing:
        raise KeyError(f"Scenario missing keys: {missing}. scenario={SCENARIO_KEY}")

    cfg = load_run_config(
        run_id=RUN_ID,
        policy_key="STATE_BASED",
        scenario_key=SCENARIO_KEY,
        seed=42,
        t_steps=int(scenario["T_STEPS"]),
        out_dir=RUN_DIR,          # ✅ run별/시나리오별 폴더로 저장
    )

    # ------------------------
    # Candidate / fallback pool
    # ------------------------
    fallback_pool = list(scenario["candidate_pool"])
    if not fallback_pool:
        raise ValueError("scenario['candidate_pool'] is empty")

    initial_allocation = fallback_pool[0]

    # ------------------------
    # Init state & logger
    # ------------------------
    state = init_state(initial_allocation)

    # ✅ logger도 RUN_DIR로
    logger = LoggerBundle(RUN_DIR)

    # ------------------------
    # Main loop
    # ------------------------
    for step in range(cfg.t_steps):
        current_id = state.current_allocation

        if current_id not in scenario["candidates"]:
            raise KeyError(f"Candidate '{current_id}' not found in scenario['candidates']")

        candidate_info = scenario["candidates"][current_id]

        hazard = hazard_from_score(candidate_info["proxy_survivability"])
        want_switch = should_request_switch(
            hazard,
            float(scenario["hazard_threshold"]),
        )

        # policy decision (기본은 유지. fallback이 트리거되면 아래에서 덮어씀)
        decision = decide_allocation(
            step=step,
            current=current_id,
            candidate=current_id,
            allow_switch=want_switch,
        )

        # fallback check
        fallback_target = check_fallback(
            state=state,
            hazard=hazard,
            fallback_pool=fallback_pool,
            threshold=float(scenario["hazard_threshold"]),
        )

        if fallback_target:
            fb_event = build_fallback_event(
                step=step,
                prev=current_id,
                new=fallback_target,
            )
            logger.log_fallback(fb_event)

            # scheduler decision override
            decision.allocation_id = fallback_target
            decision.switched = True
            decision.reason = "FALLBACK_TRIGGERED"

        # apply decision
        state.current_allocation = decision.allocation_id

        # update dynamics
        state = update_dynamics(
            state=state,
            hazard=hazard,
            op_risk=float(candidate_info["operational_risk"]),
            drift_step=float(scenario["drift_per_step"]),
        )

        # logging
        logger.log_decision(decision)
        logger.log_state(state)
        logger.log_audit({
            "step": step,
            "hazard": hazard,
            "want_switch": bool(want_switch),
            "allocation": state.current_allocation,
        })

    # ------------------------
    # Flush logs
    # ------------------------
    logger.flush()

    # ------------------------
    # Replay checksum (RUN_DIR 기준)
    # ------------------------
    checksum = compute_checksum(RUN_DIR)
    save_checksum(cfg.run_id, checksum, RUN_DIR)

    print("✅ Core11 run completed")
    print("run_id:", cfg.run_id)
    print("scenario:", SCENARIO_KEY)
    print("checksum:", checksum)
    print("logs in:", RUN_DIR.resolve())


if __name__ == "__main__":
    main()