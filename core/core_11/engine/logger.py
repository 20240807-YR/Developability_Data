import pandas as pd
from pathlib import Path


class LoggerBundle:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.decision = []
        self.state = []
        self.fallback = []
        self.audit = []

    def log_decision(self, d):
        self.decision.append(d.__dict__)

    def log_state(self, s):
        self.state.append(s.__dict__)

    def log_fallback(self, f):
        self.fallback.append(f.__dict__)

    def log_audit(self, row):
        self.audit.append(row)

    def flush(self):
        pd.DataFrame(self.decision).to_csv(self.out_dir / "decision_log.csv", index=False)
        pd.DataFrame(self.state).to_csv(self.out_dir / "state_log.csv", index=False)
        pd.DataFrame(self.fallback).to_csv(self.out_dir / "fallback_log.csv", index=False)
        pd.DataFrame(self.audit).to_csv(self.out_dir / "audit_log.csv", index=False)