# core/core_11/run/run_core11.py
from __future__ import annotations

from pathlib import Path
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from types import SimpleNamespace

import pandas as pd

# ==============================
# Engine imports
# ==============================
from core.core_11.engine.bootstrap import load_run_config
from core.core_11.engine.state_machine import init_state
from core.core_11.engine.dynamics import update_dynamics
from core.core_11.engine.policy_engine import hazard_from_score, should_request_switch
from core.core_11.engine.scheduler import decide_allocation
from core.core_11.engine.fallback_engine import check_fallback
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
        raise ValueError(f"Scenario JSON parse failed:\n{path.resolve()}\n{e}") from e


def dump_json(path: Path, obj: dict, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=sort_keys)


def norm01_series(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").fillna(0.0)
    mn, mx = float(s.min()), float(s.max())
    den = (mx - mn) if (mx - mn) > 1e-12 else 1.0
    return (s - mn) / den


def load_core6_candidates(core6_csv: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Core6 state_trace에서 fallback 후보 풀을 만든다.

    반환:
      - core6_ok   : governance_signal != CRITICAL
      - core6_all  : 전체 (CRITICAL 포함)

    score(낮을수록 덜 위험):
      fallback_score = 0.5*pred_variance_n + 0.3*SoD_n + 0.2*SoMS_n
    """
    if not core6_csv.exists():
        raise FileNotFoundError(f"Core6 state trace not found: {core6_csv.resolve()}")

    df = pd.read_csv(core6_csv)

    required = ["antibody_key", "pred_variance", "SoD", "SoMS", "governance_signal"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Core6 csv missing columns: {missing}")

    df = df.copy()
    df["antibody_key"] = df["antibody_key"].astype(str)
    df["governance_signal"] = df["governance_signal"].astype(str)

    # normalize on whole distribution
    df["pred_variance_n"] = norm01_series(df["pred_variance"])
    df["SoD_n"] = norm01_series(df["SoD"])
    df["SoMS_n"] = norm01_series(df["SoMS"])

    df["fallback_score"] = (
        0.5 * df["pred_variance_n"]
        + 0.3 * df["SoD_n"]
        + 0.2 * df["SoMS_n"]
    )

    # antibody 대표 점수: 최소 score
    agg = (
        df.groupby(["antibody_key", "governance_signal"], as_index=False)
          .agg(
              fallback_score=("fallback_score", "min"),
              pred_variance_n=("pred_variance_n", "mean"),
              SoD_n=("SoD_n", "mean"),
              SoMS_n=("SoMS_n", "mean"),
          )
    )

    agg["fallback_score_n"] = norm01_series(agg["fallback_score"])
    agg["proxy_survivability"] = (1.0 - agg["fallback_score_n"]).clip(0, 1)
    agg["operational_risk"] = agg["fallback_score_n"].clip(0, 1)

    core6_all = agg.sort_values("fallback_score_n").reset_index(drop=True)
    core6_ok = core6_all[core6_all["governance_signal"] != "CRITICAL"].reset_index(drop=True)
    return core6_ok, core6_all


def pick_core6_fallback(
    core6_ok: pd.DataFrame,
    core6_all: pd.DataFrame,
    used: set,
    top_k: int,
    allow_use_critical: bool,
) -> Tuple[Optional[str], List[str], Optional[float], str]:
    """
    1) non-critical에서 선택
    2) 없으면(allocation 소진 포함) allow_use_critical이면 전체에서 선택
    """
    def _pick(df_: pd.DataFrame) -> Tuple[Optional[str], List[str], Optional[float]]:
        if df_.empty:
            return None, [], None
        avail = df_[~df_["antibody_key"].isin(list(used))].copy()
        if avail.empty:
            avail = df_.copy()
        if avail.empty:
            return None, [], None
        ranked = avail.head(top_k)
        sel = str(ranked.iloc[0]["antibody_key"])
        alts = [str(x) for x in ranked.iloc[1:]["antibody_key"].tolist()]
        score = float(ranked.iloc[0]["fallback_score_n"])
        return sel, alts, score

    sel, alts, score = _pick(core6_ok)
    if sel is not None:
        return sel, alts, score, "CORE6_NONCRITICAL"

    if allow_use_critical:
        sel, alts, score = _pick(core6_all)
        if sel is not None:
            return sel, alts, score, "CORE6_WITH_CRITICAL"

    return None, [], None, "NO_CANDIDATE"


def ensure_csv_header(path: Path, header: List[str]) -> None:
    """
    파일이 없거나 0바이트면 header-only로 생성.
    (cold처럼 이벤트가 없을 때 EmptyDataError 방지)
    """
    if (not path.exists()) or path.stat().st_size == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(",".join(header) + "\n", encoding="utf-8")


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

    # 너 프로젝트 구조 기준(지금 스샷 구조)
    CORE6_CSV = PROJECT_ROOT / "core" / "artifact" / "core6" / "core6_state_trace.csv"

    ART_ROOT.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------
    # Required env
    # -----------------------------------------------------
    SCENARIO_KEY = os.environ.get("CORE11_SCENARIO")
    RUN_ID = os.environ.get("CORE11_RUN_ID")
    if not SCENARIO_KEY or not RUN_ID:
        raise RuntimeError(
            "CORE11_SCENARIO / CORE11_RUN_ID env vars are required.\n"
            "예: CORE11_RUN_ID=core11_demo_003 CORE11_SCENARIO=hot python3 -m core.core_11.run.run_core11\n"
            "보통은 run_matrix.py가 둘 다 주입함."
        )

    # -----------------------------------------------------
    # Load scenario
    # -----------------------------------------------------
    scenario = load_scenario(SCENARIO_DIR, SCENARIO_KEY)

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
    dump_json(RUN_DIR / "policy_snapshot.json", scenario.get("policy_snapshot", {}))
    dump_json(
        RUN_DIR / "run_meta.json",
        {
            "run_id": RUN_ID,
            "scenario": SCENARIO_KEY,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "project_root": str(PROJECT_ROOT),
            "core6_csv": str(CORE6_CSV),
        },
    )

    # -----------------------------------------------------
    # Scenario contract validation
    # -----------------------------------------------------
    required_keys = ["T_STEPS", "candidate_pool", "candidates", "hazard_threshold", "drift_per_step"]
    missing = [k for k in required_keys if k not in scenario]
    if missing:
        raise KeyError(f"Scenario '{SCENARIO_KEY}' missing keys: {missing}")

    # -----------------------------------------------------
    # Bootstrap config
    # -----------------------------------------------------
    cfg = load_run_config(
        run_id=RUN_ID,
        policy_key=scenario.get("policy_key", "STATE_BASED"),
        scenario_key=SCENARIO_KEY,
        seed=int(os.environ.get("CORE11_SEED", "42")),
        t_steps=int(scenario["T_STEPS"]),
        out_dir=RUN_DIR,
    )

    # run_config snapshot (리플레이/검증용)
    try:
        dump_json(RUN_DIR / "run_config_snapshot.json", cfg.__dict__)
    except Exception:
        if isinstance(cfg, dict):
            dump_json(RUN_DIR / "run_config_snapshot.json", cfg)

    # -----------------------------------------------------
    # Load Core6 candidate pool (Demo2 핵심)
    # -----------------------------------------------------
    core6_ok, core6_all = load_core6_candidates(CORE6_CSV)

    dump_json(
        RUN_DIR / "core6_pool_snapshot.json",
        {
            "n_candidates_ok": int(len(core6_ok)),
            "n_candidates_all": int(len(core6_all)),
            "top10_ok": core6_ok.head(10).to_dict(orient="records"),
            "top10_all": core6_all.head(10).to_dict(orient="records"),
        },
    )

    # lookup map (allocation이 CORE6로 바뀌면 여기서 score 가져옴)
    core6_map: Dict[str, Dict[str, object]] = {
        str(r["antibody_key"]): {
            "proxy_survivability": float(r["proxy_survivability"]),
            "operational_risk": float(r["operational_risk"]),
            "fallback_score_n": float(r["fallback_score_n"]),
            "governance_signal": str(r["governance_signal"]),
        }
        for _, r in core6_all.iterrows()
    }

    # -----------------------------------------------------
    # Init
    # -----------------------------------------------------
    pool = list(scenario["candidate_pool"])
    if not pool:
        raise ValueError("scenario['candidate_pool'] is empty")

    state = init_state(pool[0])
    logger = LoggerBundle(RUN_DIR)

    hazard_threshold = float(scenario["hazard_threshold"])
    drift_step = float(scenario["drift_per_step"])

    used_core6 = set()
    TOP_K = int(os.environ.get("CORE11_TOPK", "3"))
    ALLOW_USE_CRITICAL = os.environ.get("CORE11_ALLOW_CRITICAL", "1") == "1"

    # -----------------------------------------------------
    # Main loop
    # -----------------------------------------------------
    for step in range(int(cfg.t_steps)):
        cur = str(state.current_allocation)

        # 현재 allocation feature source 결정
        if cur in scenario["candidates"]:
            info = scenario["candidates"][cur]
            proxy = float(info["proxy_survivability"])
            risk = float(info["operational_risk"])
            src = "SCENARIO"
            core6_score = None
            core6_gov = None
        elif cur in core6_map:
            proxy = float(core6_map[cur]["proxy_survivability"])
            risk = float(core6_map[cur]["operational_risk"])
            src = "CORE6"
            core6_score = float(core6_map[cur]["fallback_score_n"])
            core6_gov = str(core6_map[cur]["governance_signal"])
        else:
            raise KeyError(f"Current allocation '{cur}' not found in scenario nor core6_map")

        hazard = hazard_from_score(proxy)
        want_switch = should_request_switch(hazard, hazard_threshold)

        decision = decide_allocation(step, cur, cur, want_switch)

        # check_fallback은 "트리거 여부"만 사용
        policy_fb = check_fallback(state, hazard, pool, hazard_threshold)

        fallback_triggered = False
        if policy_fb:
            sel, alts, score, sel_src = pick_core6_fallback(
                core6_ok=core6_ok,
                core6_all=core6_all,
                used=used_core6,
                top_k=TOP_K,
                allow_use_critical=ALLOW_USE_CRITICAL,
            )

            fb_obj = SimpleNamespace(**{
                "step": step,
                "trigger": "HAZARD_THRESHOLD_EXCEEDED",
                "previous_allocation": cur,
                "fallback_allocation": sel,
                "alternatives": json.dumps(alts, ensure_ascii=False),
                "fallback_score_n": score,
                "selection_source": sel_src,
                "reason": "FALLBACK_CORE6_SELECTED" if sel else "NO_CANDIDATE",
                "policy_fallback_target": str(policy_fb),
            })
            logger.log_fallback(fb_obj)

            if sel:
                used_core6.add(sel)
                decision.allocation_id = sel
                decision.switched = True
                decision.reason = "FALLBACK_CORE6_SELECTED"
                fallback_triggered = True

        # 적용
        state.current_allocation = str(decision.allocation_id)

        # dynamics는 "최종 allocation" 기준으로 업데이트
        new_id = str(state.current_allocation)
        if new_id in scenario["candidates"]:
            new_info = scenario["candidates"][new_id]
            new_proxy = float(new_info["proxy_survivability"])
            new_risk = float(new_info["operational_risk"])
            new_src = "SCENARIO"
            new_core6_score = None
            new_core6_gov = None
        elif new_id in core6_map:
            new_proxy = float(core6_map[new_id]["proxy_survivability"])
            new_risk = float(core6_map[new_id]["operational_risk"])
            new_src = "CORE6"
            new_core6_score = float(core6_map[new_id]["fallback_score_n"])
            new_core6_gov = str(core6_map[new_id]["governance_signal"])
        else:
            raise KeyError(f"New allocation '{new_id}' not found in scenario nor core6_map")

        new_hazard = hazard_from_score(new_proxy)
        state = update_dynamics(state, new_hazard, new_risk, drift_step)

        # logging
        logger.log_decision(decision)
        logger.log_state(state)

        # ✅ audit는 반드시 남겨야 함 (지금 네 파일이 비었던 원인)
        logger.log_audit({
            "step": step,
            "prev_allocation": cur,
            "allocation": new_id,
            "allocation_source": new_src,
            "proxy_survivability": new_proxy,
            "hazard": new_hazard,
            "hazard_threshold": hazard_threshold,
            "want_switch": bool(want_switch),
            "fallback_evaluated": True,
            "fallback_triggered": bool(fallback_triggered),
            "core6_fallback_score_n": new_core6_score,
            "core6_governance_signal": new_core6_gov,
        })

    # -----------------------------------------------------
    # Finalize
    # -----------------------------------------------------
    logger.flush()

    # cold처럼 fallback이 0회여도 CSV 파서가 죽지 않게 헤더 보장
    ensure_csv_header(
        RUN_DIR / "fallback_log.csv",
        [
            "step",
            "trigger",
            "previous_allocation",
            "fallback_allocation",
            "alternatives",
            "fallback_score_n",
            "selection_source",
            "reason",
            "policy_fallback_target",
        ],
    )

    checksum = compute_checksum(RUN_DIR)
    save_checksum(RUN_ID, checksum, RUN_DIR)

    print("✅ Core11 run completed")
    print("run_id   :", RUN_ID)
    print("scenario :", SCENARIO_KEY)
    print("checksum :", checksum)
    print("logs in  :", RUN_DIR.resolve())
    print("")


if __name__ == "__main__":
    main()