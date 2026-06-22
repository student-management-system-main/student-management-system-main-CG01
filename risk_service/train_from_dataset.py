"""
risk_service/train_from_dataset.py
-----------------------------------
Train the ML models directly from the provided Excel dataset.

This script:
  1. Reads the cleaned Excel dataset (cleaned-output-data.xlsx)
  2. Converts each row into feature vectors matching the 7-feature schema
  3. Trains Logistic Regression + Decision Tree models
  4. Evaluates with 5-fold cross-validated ROC-AUC
  5. Saves models to models/ directory and updates registry.json

Usage (run from risk_service/ directory):
    python train_from_dataset.py --dataset "path/to/cleaned-output-data.xlsx"

Requirements: 4.8
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import joblib
import numpy as np

# ---------------------------------------------------------------------------
# Ensure risk_service modules are importable
# ---------------------------------------------------------------------------
RISK_SERVICE_DIR = Path(__file__).parent
sys.path.insert(0, str(RISK_SERVICE_DIR))

from train import (
    MODELS_DIR,
    REGISTRY_PATH,
    _increment_patch,
    _load_registry,
    _save_registry,
)

# ---------------------------------------------------------------------------
# Column mapping from dataset to features
# ---------------------------------------------------------------------------
# Dataset columns used:
#   hist_payment_freq_score   → payment_history_ratio      (float 0-1)
#   current_payment_status    → overdue_invoice_count       (0=current, 1=overdue flag)
#   outstanding_balance       → total_outstanding_balance   (float)
#   enrollment_date           → enrollment_duration_days    (computed)
#   hist_late_payment_count   → historical_default_rate     (proxy)
#   due_date_proximity_days   → avg_days_to_pay             (proxy: negative=past due)
#   outstanding_balance > 0   → partial_payment_count       (binary flag)
#
# Label:  risk_label (0, 1, 2) — 0 = low risk, 1 = medium, 2 = high
#         We binarise: label >= 1 → defaulted (1), label == 0 → safe (0)


def load_dataset(xlsx_path: str) -> "pd.DataFrame":
    """Load the Excel dataset."""
    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas is required. Install it: pip install pandas openpyxl")
        sys.exit(1)

    path = Path(xlsx_path)
    if not path.exists():
        print(f"ERROR: File not found: {xlsx_path}")
        sys.exit(1)

    print(f"Loading dataset from: {path.resolve()}")
    df = pd.read_excel(xlsx_path, engine="openpyxl")
    print(f"  Loaded {len(df)} rows, columns: {list(df.columns)}")
    return df


def build_features_and_labels(df: "pd.DataFrame") -> tuple[np.ndarray, np.ndarray]:
    """
    Convert dataset rows to the 7-feature vectors used by the ML pipeline.

    Feature mapping:
      0  payment_history_ratio    ← hist_payment_freq_score
      1  overdue_invoice_count    ← current_payment_status (1 if overdue)
      2  total_outstanding_balance ← outstanding_balance
      3  enrollment_duration_days ← days since enrollment_date
      4  historical_default_rate  ← hist_late_payment_count / max(hist_late_payment_count, 5)
      5  avg_days_to_pay          ← -due_date_proximity_days (negative prox = past due)
      6  partial_payment_count    ← 1 if outstanding_balance > 0 and not fully zero

    Label: risk_label >= 1 → 1 (at risk), risk_label == 0 → 0 (safe)
    """
    import pandas as pd

    today = datetime.date.today()
    X_list = []
    y_list = []

    skipped = 0
    for _, row in df.iterrows():
        try:
            # Feature 0: payment_history_ratio (0.0–1.0)
            phr = float(row.get("hist_payment_freq_score", 0.5))
            phr = max(0.0, min(1.0, phr))

            # Feature 1: overdue_invoice_count (0 or 1 based on current status)
            status = int(row.get("current_payment_status", 0))
            overdue_count = float(1 if status == 1 else 0)

            # Feature 2: total_outstanding_balance
            outstanding = float(row.get("outstanding_balance", 0.0) or 0.0)
            outstanding = max(0.0, outstanding)

            # Feature 3: enrollment_duration_days
            enroll_raw = row.get("enrollment_date")
            if enroll_raw is not None and str(enroll_raw) not in ("", "nan", "NaT"):
                enroll_date = pd.to_datetime(enroll_raw).date()
                enrollment_days = float(max(0, (today - enroll_date).days))
            else:
                enrollment_days = 0.0

            # Feature 4: historical_default_rate
            # Proxy: late_count / 5 capped at 1.0 (5+ late payments = max risk)
            late_count = float(row.get("hist_late_payment_count", 0) or 0)
            hist_default_rate = min(1.0, late_count / 5.0) if late_count > 0 else 0.0

            # Feature 5: avg_days_to_pay
            # due_date_proximity_days: positive = days until due, negative = days past due
            # Convert to avg_days_to_pay: negative proximity means already past due (late)
            proximity = float(row.get("due_date_proximity_days", 0) or 0)
            # avg_days_to_pay = -proximity (past due = positive avg_days_to_pay)
            avg_days = -proximity

            # Feature 6: partial_payment_count
            # 1 if has outstanding balance > 0 (partial payment made but not complete)
            annual_net = float(row.get("annual_net_fee", 0.0) or 0.0)
            partial = float(1 if (outstanding > 0 and annual_net > 0) else 0)

            features = np.array(
                [phr, overdue_count, outstanding, enrollment_days,
                 hist_default_rate, avg_days, partial],
                dtype=np.float64,
            )

            # Label: risk_label >= 1 means at-risk (defaulted)
            risk_label = int(row.get("risk_label", 0) or 0)
            label = 1 if risk_label >= 1 else 0

            X_list.append(features)
            y_list.append(label)

        except Exception as exc:
            skipped += 1
            continue

    if skipped > 0:
        print(f"  Skipped {skipped} rows due to missing/invalid data")

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=np.int32)
    return X, y


def train_and_save(X: np.ndarray, y: np.ndarray) -> dict:
    """Train LR + DT models, evaluate, and save if improved."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split, cross_val_score

    n_samples = len(y)
    print(f"\nTraining on {n_samples} samples")
    print(f"  Label distribution: {np.bincount(y)} (0=safe, 1=at-risk)")

    if n_samples < 10:
        return {"error": f"Insufficient samples: {n_samples}", "replaced": False}

    # Stratified 80/20 split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train models
    print("\nTraining Logistic Regression...")
    lr_model = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    lr_model.fit(X_train_scaled, y_train)

    print("Training Decision Tree...")
    dt_model = DecisionTreeClassifier(max_depth=8, random_state=42)
    dt_model.fit(X_train_scaled, y_train)

    # 5-fold cross-validated ROC-AUC
    print("\nEvaluating with 5-fold cross-validation...")
    lr_cv_scores = cross_val_score(
        LogisticRegression(max_iter=1000, C=1.0, random_state=42),
        X_train_scaled, y_train, cv=5, scoring="roc_auc"
    )
    dt_cv_scores = cross_val_score(
        DecisionTreeClassifier(max_depth=8, random_state=42),
        X_train_scaled, y_train, cv=5, scoring="roc_auc"
    )

    lr_roc = float(np.mean(lr_cv_scores))
    dt_roc = float(np.mean(dt_cv_scores))
    new_roc_auc = float(np.mean([lr_roc, dt_roc]))

    print(f"  LR ROC-AUC:  {lr_roc:.4f} (±{np.std(lr_cv_scores):.4f})")
    print(f"  DT ROC-AUC:  {dt_roc:.4f} (±{np.std(dt_cv_scores):.4f})")
    print(f"  Ensemble:    {new_roc_auc:.4f}")

    # Load registry and compare
    registry = _load_registry()
    current_roc_auc = float(registry.get("current_roc_auc") or 0.0)
    print(f"\n  Current registry ROC-AUC: {current_roc_auc:.4f}")

    # Always replace on first run (current = 0.0) or if improved
    replaced = new_roc_auc > current_roc_auc

    if replaced:
        current_version = registry.get("version") or None
        new_version = _increment_patch(current_version)

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        lr_path = MODELS_DIR / f"model_lr_{new_version}.joblib"
        dt_path = MODELS_DIR / f"model_dt_{new_version}.joblib"
        scaler_path = MODELS_DIR / f"scaler_{new_version}.joblib"

        joblib.dump(lr_model, lr_path)
        joblib.dump(dt_model, dt_path)
        joblib.dump(scaler, scaler_path)

        registry["active_lr"] = str(lr_path)
        registry["active_dt"] = str(dt_path)
        registry["active_scaler"] = str(scaler_path)
        registry["version"] = new_version
        registry["current_roc_auc"] = new_roc_auc
        registry["trained_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        registry["n_samples"] = n_samples
        _save_registry(registry)

        print(f"\n✅ Model REPLACED — version {new_version}")
        print(f"   Saved to: {MODELS_DIR}")
    else:
        new_version = registry.get("version") or "v1.0.0"
        print(f"\n⚠️  Model NOT replaced (new {new_roc_auc:.4f} <= current {current_roc_auc:.4f})")

    return {
        "new_roc_auc": new_roc_auc,
        "current_roc_auc": current_roc_auc,
        "replaced": replaced,
        "version": new_version if replaced else registry.get("version", "v1.0.0"),
        "n_samples": n_samples,
        "lr_roc_auc": lr_roc,
        "dt_roc_auc": dt_roc,
    }


def main():
    parser = argparse.ArgumentParser(description="Train ML models from Excel dataset")
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).parent.parent / "cleaned-output-data (1).xlsx"),
        help="Path to the Excel dataset file",
    )
    args = parser.parse_args()

    # Try common locations if not found
    dataset_path = args.dataset
    candidates = [
        dataset_path,
        str(Path(__file__).parent.parent / "cleaned-output-data (1).xlsx"),
        str(Path(__file__).parent.parent / "cleaned_output_data (1).xlsx"),
        r"c:\Users\Hp\Desktop\student-management-system-main\cleaned_output_data (1).xlsx",
        r"c:\Users\Hp\Desktop\student-management-system-main\cleaned-output-data (1).xlsx",
    ]

    found_path = None
    for candidate in candidates:
        if Path(candidate).exists():
            found_path = candidate
            break

    if not found_path:
        print("ERROR: Could not find the dataset file.")
        print("Tried:")
        for c in candidates:
            print(f"  {c}")
        print("\nUsage: python train_from_dataset.py --dataset <path_to_xlsx>")
        sys.exit(1)

    print("=" * 60)
    print("  Smart University Fee Prediction — Model Training")
    print("=" * 60)

    # Load dataset
    df = load_dataset(found_path)

    # Build features and labels
    print("\nBuilding feature vectors from dataset...")
    X, y = build_features_and_labels(df)
    print(f"  Feature matrix shape: {X.shape}")
    print(f"  Labels: {np.bincount(y)} (safe=0, at-risk=1)")

    # Train
    result = train_and_save(X, y)

    print("\n" + "=" * 60)
    print("  Training Complete")
    print("=" * 60)
    print(f"  Samples used:      {result.get('n_samples')}")
    print(f"  New ROC-AUC:       {result.get('new_roc_auc', 0):.4f}")
    print(f"  Previous ROC-AUC:  {result.get('current_roc_auc', 0):.4f}")
    print(f"  Model replaced:    {result.get('replaced')}")
    print(f"  Model version:     {result.get('version')}")
    if result.get("error"):
        print(f"  Error: {result['error']}")


if __name__ == "__main__":
    main()
