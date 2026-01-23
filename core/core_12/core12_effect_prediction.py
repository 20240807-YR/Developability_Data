from Bio.SeqUtils.ProtParam import ProteinAnalysis
from Bio import SeqIO
import pandas as pd
import numpy as np

# -------------------------
# Load original sequences
# -------------------------
seqs = {}
for record in SeqIO.parse("antibodies.fasta", "fasta"):
    seqs[record.id] = str(record.seq)

# -------------------------
# Load mutation suggestions
# -------------------------
suggestions = pd.read_csv("core12_sequence_improvement_suggestions.csv")

rows = []

for _, r in suggestions.iterrows():
    key = f"{r['Antibody']}_{r['Chain']}"
    if key not in seqs:
        continue

    seq = seqs[key]
    pos = int(r["Position"]) - 1
    suggested = r["Suggested"]

    # -------------------------
    # Case 1: single residue substitution
    # -------------------------
    if isinstance(suggested, str) and len(suggested) == 1:
        if pos < 0 or pos >= len(seq):
            continue

        mutated = seq[:pos] + suggested + seq[pos+1:]

        pa_orig = ProteinAnalysis(seq)
        pa_mut = ProteinAnalysis(mutated)

        rows.append({
            "Antibody": r["Antibody"],
            "Chain": r["Chain"],
            "Position": r["Position"],
            "Original": r["Original"],
            "Suggested": suggested,
            "pI_before": round(pa_orig.isoelectric_point(), 2),
            "pI_after": round(pa_mut.isoelectric_point(), 2),
            "Delta_pI": round(pa_mut.isoelectric_point() - pa_orig.isoelectric_point(), 2),
            "Charge_pH7_before": round(pa_orig.charge_at_pH(7.0), 2),
            "Charge_pH7_after": round(pa_mut.charge_at_pH(7.0), 2),
            "Delta_charge": round(pa_mut.charge_at_pH(7.0) - pa_orig.charge_at_pH(7.0), 2),
            "Prediction_type": "Quantitative",
            "Reason": r["Reason"]
        })

    # -------------------------
    # Case 2: motif-level substitution (DG/NG etc.)
    # -------------------------
    else:
        rows.append({
            "Antibody": r["Antibody"],
            "Chain": r["Chain"],
            "Position": r["Position"],
            "Original": r["Original"],
            "Suggested": r["Suggested"],
            "pI_before": np.nan,
            "pI_after": np.nan,
            "Delta_pI": np.nan,
            "Charge_pH7_before": np.nan,
            "Charge_pH7_after": np.nan,
            "Delta_charge": np.nan,
            "Prediction_type": "Qualitative",
            "Reason": r["Reason"] + " (motif-level change)"
        })

df = pd.DataFrame(rows)
df.to_csv("core12_effect_prediction.csv", index=False)
print(df)
