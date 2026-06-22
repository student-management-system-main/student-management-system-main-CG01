"""
Standalone model training script.
Reads the Excel dataset and trains LR + DT models directly.
No database connection required.
"""

import sys
import json
import datetime
from pathlib import Path

# ── locate dataset ──────────────────────────────────────────────────────────
CANDIDATES = [
    r"C:\Users\Hp\Desktop\student-management-system-main\cleaned_output_data (1).xlsx",
    r"C:\Users\Hp\Desktop\student-management-system-main\cleaned-output-data (1).xlsx",
    str(Path(__file__).parent.parent.parent / "cleaned_output_data (1).xlsx"),
    str(Path(__file__).parent.parent.parent / "cleaned-output-data (1).xlsx"),
]

DATASET_PATH = None
for p in CANDIDATES:
    if Path(p).exists():
        DATASET_PATH = p
        break

if not DATASET_PATH:
    print("ERROR: Dataset not found. Tried:")
    for p in CANDIDATES:
        print(f"  {p}")
    sys.exit(1)

print(f"Dataset: {DATASET_PATH}")

# ── imports ─────────────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score

# ── load data ────────────────────────────────────────────────────────────────
df = pd.read_excel(DATASET_PATH, engine="openpyxl")
print(f"Rows loaded: {len(df)}")
print(f"Columns: {list(df.columns)}")

# ── build feature matrix ─────────────────────────────────────────────────────
today = datetime.date.today()
rows_X, rows_y = [], []

for _, row in df.iterrows():
    try:
        # 0 payment_history_ratio
        phr = float(row["hist_payment_freq_score"])
        phr = max(0.0, min(1.0, phr))

        # 1 overdue_invoice_count
        overdue = float(1 if int(row["current_payment_status"]) == 1 else 0)

        # 2 total_outstanding_balance
        balance = max(0.0, float(row["outstanding_balance"] or 0))

        # 3 enrollment_duration_days
        enroll = pd.to_datetime(row["enrollment_date"]).date()
        duration = float(max(0, (today - enroll).days))

        # 4 historical_default_rate  (late_count / 5 capped at 1)
        late = float(row["hist_late_payment_count"] or 0)
        default_rate = min(1.0, late / 5.0)

        # 5 avg_days_to_pay  (negative proximity = already past due)
        proximity = float(row["due_date_proximity_days"] or 0)
        avg_days = -proximity

        # 6 partial_payment_count
        net_fee = float(row["annual_net_fee"] or 0)
        partial = float(1 if (balance > 0 and net_fee > 0) else 0)

        X_row = [phr, overdue, balance, duration, default_rate, avg_days, partial]

        # label: risk_label >= 1 → at-risk
        label = 1 if int(row["risk_label"]) >= 1 else 0

        rows_X.append(X_row)
        rows_y.append(label)
    except Exception as e:
        continue

X = np.array(rows_X, dtype=np.float64)
y = np.array(rows_y, dtype=np.int32)

print(f"\nFeature matrix: {X.shape}")
print(f"Label counts  : {dict(zip(*np.unique(y, return_counts=True)))}")

# ── train / test split ───────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42
)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s  = scaler.transform(X_test)

# ── train models ─────────────────────────────────────────────────────────────
print("\nTraining Logistic Regression ...")
lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
lr.fit(X_train_s, y_train)

print("Training Decision Tree ...")
dt = DecisionTreeClassifier(max_depth=8, random_state=42)
dt.fit(X_train_s, y_train)

# ── cross-validated ROC-AUC ──────────────────────────────────────────────────
print("\nCross-validating (5-fold) ...")
lr_scores = cross_val_score(
    LogisticRegression(max_iter=1000, C=1.0, random_state=42),
    X_train_s, y_train, cv=5, scoring="roc_auc"
)
dt_scores = cross_val_score(
    DecisionTreeClassifier(max_depth=8, random_state=42),
    X_train_s, y_train, cv=5, scoring="roc_auc"
)

lr_roc = float(np.mean(lr_scores))
dt_roc = float(np.mean(dt_scores))
new_roc = float(np.mean([lr_roc, dt_roc]))

print(f"  LR  ROC-AUC : {lr_roc:.4f}")
print(f"  DT  ROC-AUC : {dt_roc:.4f}")
print(f"  Ensemble    : {new_roc:.4f}")

# ── save models ──────────────────────────────────────────────────────────────
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY   = MODELS_DIR / "registry.json"

# load existing registry
registry = {}
if REGISTRY.exists():
    with open(REGISTRY) as f:
        registry = json.load(f)

current_roc = float(registry.get("current_roc_auc") or 0.0)
print(f"\nCurrent registry ROC-AUC : {current_roc:.4f}")

replaced = new_roc > current_roc

if replaced:
    old_ver = registry.get("version")
    if old_ver:
        raw = old_ver.lstrip("v").split(".")
        try:
            ver = f"v{raw[0]}.{raw[1]}.{int(raw[2])+1}"
        except Exception:
            ver = "v1.0.0"
    else:
        ver = "v1.0.0"

    lr_path     = MODELS_DIR / f"model_lr_{ver}.joblib"
    dt_path     = MODELS_DIR / f"model_dt_{ver}.joblib"
    scaler_path = MODELS_DIR / f"scaler_{ver}.joblib"

    joblib.dump(lr,     lr_path)
    joblib.dump(dt,     dt_path)
    joblib.dump(scaler, scaler_path)

    registry.update({
        "active_lr"      : str(lr_path),
        "active_dt"      : str(dt_path),
        "active_scaler"  : str(scaler_path),
        "version"        : ver,
        "current_roc_auc": new_roc,
        "trained_at"     : datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
        "n_samples"      : len(y),
    })
    with open(REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"\n✅  Model REPLACED  →  version {ver}")
    print(f"   Saved to: {MODELS_DIR}")
else:
    print(f"\n⚠️   Model NOT replaced (new {new_roc:.4f} ≤ current {current_roc:.4f})")

print("\n── Summary ─────────────────────────────────")
print(f"  Samples    : {len(y)}")
print(f"  New AUC    : {new_roc:.4f}")
print(f"  Replaced   : {replaced}")
print(f"  Version    : {registry.get('version')}")
print("────────────────────────────────────────────")
