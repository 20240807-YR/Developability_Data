from anarci import anarci
from Bio import SeqIO
import pandas as pd
import re

AROMATIC = set("FWY")
HYDROPHOBIC = set("AILMFWV")

def extract_cdr_positions(seq):
    res = anarci([("q", seq)], scheme="IMGT")
    numbering = res[0][0][0][0]

    cdr_pos = []
    for ((pos, _), aa) in numbering:
        if aa == "-":
            continue
        if 27 <= pos <= 38 or 56 <= pos <= 65 or 105 <= pos <= 117:
            cdr_pos.append((pos, aa))
    return cdr_pos


rows = []

for record in SeqIO.parse("antibodies.fasta", "fasta"):
    name = record.id
    seq = str(record.seq)

    antibody, chain = name.rsplit("_", 1)
    cdr_positions = extract_cdr_positions(seq)
    cdr_indices = {pos for pos, _ in cdr_positions}

    # -------------------------
    # Antibody A – aromatic CDR-H3
    # -------------------------
    if antibody == "Antibody_A" and chain == "VH":
        for pos, aa in cdr_positions:
            if aa in AROMATIC:
                suggestion = {"F": "L", "Y": "S", "W": "H"}[aa]
                rows.append({
                    "Antibody": antibody,
                    "Chain": chain,
                    "Position": pos,
                    "Original": aa,
                    "Suggested": suggestion,
                    "Reason": "Reduce aromatic-driven self-association (CDR-H3)"
                })

    # -------------------------
    # Antibody B – framework hydrophobic hotspot
    # -------------------------
    if antibody == "Antibody_B":
        stretch = []
        for i, aa in enumerate(seq, start=1):
            if aa in HYDROPHOBIC and i not in cdr_indices:
                stretch.append((i, aa))
                if len(stretch) >= 4:
                    mid = stretch[len(stretch)//2]
                    rows.append({
                        "Antibody": antibody,
                        "Chain": chain,
                        "Position": mid[0],
                        "Original": mid[1],
                        "Suggested": "S",
                        "Reason": "Break hydrophobic framework hotspot (viscosity risk)"
                    })
                    stretch = []
            else:
                stretch = []

    # -------------------------
    # Antibody C – DG / acidic motif
    # -------------------------
    if antibody == "Antibody_C":
        for i in range(len(seq)-1):
            motif = seq[i:i+2]
            if motif in ["DG", "NG"]:
                rows.append({
                    "Antibody": antibody,
                    "Chain": chain,
                    "Position": i+1,
                    "Original": motif,
                    "Suggested": motif.replace("G", "A"),
                    "Reason": "Reduce deamidation / cleavage liability"
                })
        for i, aa in enumerate(seq, start=1):
            if aa in ["D", "E"] and i in cdr_indices:
                rows.append({
                    "Antibody": antibody,
                    "Chain": chain,
                    "Position": i,
                    "Original": aa,
                    "Suggested": "N",
                    "Reason": "Reduce acidic CDR liability (purification loss)"
                })

df = pd.DataFrame(rows)
df.to_csv("core12_sequence_improvement_suggestions.csv", index=False)
print(df)
