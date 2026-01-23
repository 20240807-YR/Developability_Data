from anarci import anarci
from Bio import SeqIO
import pandas as pd

AROMATIC = set("FWY")

# -------------------------
# CDR extraction (IMGT)
# -------------------------
def extract_cdrs(seq, chain_type):
    res = anarci([("query", seq)], scheme="IMGT")
    numbering = res[0][0][0][0]

    cdrs = {"CDR1": "", "CDR2": "", "CDR3": ""}

    for ((pos, _), aa) in numbering:
        if aa == "-":
            continue

        if 27 <= pos <= 38:
            cdrs["CDR1"] += aa
        elif 56 <= pos <= 65:
            cdrs["CDR2"] += aa
        elif 105 <= pos <= 117:
            cdrs["CDR3"] += aa

    return cdrs


def aromatic_ratio(seq):
    if len(seq) == 0:
        return 0.0
    return round(sum(aa in AROMATIC for aa in seq) / len(seq), 3)


# -------------------------
# Main analysis
# -------------------------
rows = []

for record in SeqIO.parse("antibodies.fasta", "fasta"):
    antibody, chain = record.id.rsplit("_", 1)
    seq = str(record.seq)

    cdrs = extract_cdrs(seq, chain)

    for cdr, cseq in cdrs.items():
        rows.append({
            "Antibody": antibody,
            "Chain": chain,
            "CDR": cdr,
            "CDR_length": len(cseq),
            "CDR_aromatic_ratio": aromatic_ratio(cseq),
            "CDR_sequence": cseq
        })

df = pd.DataFrame(rows)
df.to_csv("core12_cdr_metrics.csv", index=False)

print(df)
