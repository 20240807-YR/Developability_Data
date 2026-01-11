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

    return json.loads(txt)


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
    df = pd.read_csv(core6_csv)

    df["pred_variance_n"] = norm01_series(df["pred_variance"])
    df["SoD_n"] = norm01_series(df["SoD"])
    df["SoMS_n"] = norm01_series(df["SoMS"])

    df["fallback_score"] = (
        0.5 * df["pred_variance_n"]
        + 0.3 * df["SoD_n"]
        + 0.2 * df["SoMS_n"]
    )

    agg = (
        df.groupby(["antibody_key", "governance_signal"], as_index=False)
        .agg(fallback_score=("fallback_score", "min"))
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
):
    def _pick(df):
        avail = df[~df["antibody_key"].isin(used)]
        if avail.empty:
            avail = df
        if avail.empty:
            return None, [], None
        ranked = avail.head(top_k)
        return (
            ranked.iloc[0]["antibody_key"],
            ranked.iloc[1:]["antibody_key"].tolist(),
            float(ranked.iloc[0]["fallback_score_n"]),
        )

    sel, alts, score = _pick(core6_ok)
    if sel:
        return sel, alts, score, "CORE6_NONCRITICAL"

    if allow_use_critical:
        sel, alts, score = _pick(core6_all)
        if sel:
            return sel, alts, score, "CORE6_WITH_CRITICAL"

    return None, [], None, "NO_CANDIDATE"


def ensure_fallback_log_header(run_dir: Path):
    path = run_dir / "fallback_log.csv"
    if not path.exists() or path.stat().st_size == 0:
        path.write_text(
            "step,trigger,previous_allocation,fallback_allocation,alternatives,"
            "fallback_score_n,selection_source,reason,policy_fallback_target\n"
        )


# =========================================================
# Main
# =========================================================
def main():
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    CORE11_DIR = PROJECT_ROOT / "core" / "core_11"
    ART_ROOT = CORE11_DIR / "artifacts" / "core11"
    SCENARIO_DIR = CORE11_DIR / "scenarios"
    CORE6_CSV = PROJECT_ROOT / "core" / "artifact" / "core6" / "core6_state_trace.csv"

    SCENARIO_KEY = os.environ["CORE11_SCENARIO"]
    RUN_ID = os.environ["CORE11_RUN_ID"]

    RUN_DIR = ART_ROOT / RUN_ID / SCENARIO_KEY
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    scenario = load_scenario(SCENARIO_DIR, SCENARIO_KEY)

    dump_json(RUN_DIR / "scenario.json", scenario)
    dump_json(
        RUN_DIR / "run_meta.json",
        {
            "run_id": RUN_ID,
            "scenario": SCENARIO_KEY,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    cfg = load_run_config(
        run_id=RUN_ID,
        policy_key="STATE_BASED",
        scenario_key=SCENARIO_KEY,
        seed=42,
        t_steps=int(scenario["T_STEPS"]),
        out_dir=RUN_DIR,
    )

    core6_ok, core6_all = load_core6_candidates(CORE6_CSV)
    core6_map = {
        r["antibody_key"]: r
        for _, r in core6_all.iterrows()
    }

    state = init_state(scenario["candidate_pool"][0])
    logger = LoggerBundle(RUN_DIR)

    used_core6 = set()
    hazard_threshold = float(scenario["hazard_threshold"])
    drift_step = float(scenario["drift_per_step"])
    TOP_K = 3

    for step in range(int(cfg.t_steps)):
        cur = state.current_allocation

        if cur in scenario["candidates"]:
            info = scenario["candidates"][cur]
            proxy, risk = info["proxy_survivability"], info["operational_risk"]
        else:
            info = core6_map[cur]
            proxy, risk = info["proxy_survivability"], info["operational_risk"]

        hazard = hazard_from_score(proxy)
        want_switch = should_request_switch(hazard, hazard_threshold)

        decision = decide_allocation(step, cur, cur, want_switch)
        policy_fb = check_fallback(state, hazard, scenario["candidate_pool"], hazard_threshold)

        if policy_fb:
            sel, alts, score, src = pick_core6_fallback(
                core6_ok, core6_all, used_core6, TOP_K, True
            )

            logger.log_fallback(SimpleNamespace(**{
                "step": step,
                "trigger": "HAZARD_THRESHOLD_EXCEEDED",
                "previous_allocation": cur,
                "fallback_allocation": sel,
                "alternatives": json.dumps(alts),
                "fallback_score_n": score,
                "selection_source": src,
                "reason": "FALLBACK_CORE6_SELECTED" if sel else "NO_CANDIDATE",
                "policy_fallback_target": str(policy_fb),
            }))

            if sel:
                used_core6.add(sel)
                decision.allocation_id = sel
                decision.switched = True
                decision.reason = "FALLBACK_CORE6_SELECTED"

        state.current_allocation = decision.allocation_id
        state = update_dynamics(state, hazard, risk, drift_step)

        logger.log_decision(decision)
        logger.log_state(state)

    logger.flush()
    ensure_fallback_log_header(RUN_DIR)

    checksum = compute_checksum(RUN_DIR)
    save_checksum(RUN_ID, checksum, RUN_DIR)


if __name__ == "__main__":
    main()