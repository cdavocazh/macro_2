#!/usr/bin/env python3
"""One-off: split NYMEX natural-gas futures out of the FRED Henry Hub spot file.

`historical_data/natural_gas_fred.csv` was holding two different instruments:

    natural_gas_price   FRED Henry Hub SPOT (daily, 1997 ->), written by the FRED extractor
    natural_gas         NYMEX front-month FUTURES, written every 5 min by macro2-ibkr-stream

No row carries both, and on dates where both exist the futures sit a median +0.7% away
from spot (range -6.5% to +9.0%), so anything reading the file as one series was mixing
instruments. `ibkr_streaming.py` now routes NG to `natural_gas_ibkr.csv`; this moves the
26,812 futures rows already written there into that file and leaves the FRED series clean.

Dry run by default; the source file is copied to .deploy_backup_20260921/data/ before any
rewrite, under the same per-file lock the collectors take.

  python scripts/split_natural_gas_20260921.py
  python scripts/split_natural_gas_20260921.py --apply
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from extract_historical_data import OUTPUT_DIR, _atomic_to_csv, _csv_lock  # noqa: E402

SRC = "natural_gas_fred.csv"
DST = "natural_gas_ibkr.csv"
SRC_COL = "natural_gas"            # the IBKR column inside the FRED file
DST_COL = "natural_gas_futures"    # what ibkr_streaming.py writes from now on
BACKUP_DIR = os.path.join(ROOT, ".deploy_backup_20260921", "data")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    a = ap.parse_args()
    src_path = os.path.join(OUTPUT_DIR, SRC)
    dst_path = os.path.join(OUTPUT_DIR, DST)
    if not os.path.exists(src_path):
        print(f"  {SRC} not present — nothing to do")
        return 0

    with _csv_lock(src_path):
        d = pd.read_csv(src_path)
        if SRC_COL not in d.columns:
            print(f"  {SRC}: no '{SRC_COL}' column — already split")
            return 0
        fut = d[d[SRC_COL].notna()].copy()
        spot = d[d[SRC_COL].isna()].copy()
        both = int((d[SRC_COL].notna() & d.get("natural_gas_price", pd.Series(dtype=float)).notna()).sum())
        if both:
            raise SystemExit(f"{SRC}: {both} rows carry BOTH instruments — refusing to split automatically")
        print(f"  {SRC}: {len(d)} rows -> {len(spot)} FRED spot kept, {len(fut)} IBKR futures moved to {DST}")
        if fut.empty:
            print("  nothing to move (this host never ran the IBKR stream)")
            spot_out = spot.drop(columns=[SRC_COL])
            if a.apply and list(spot_out.columns) != list(d.columns):
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(src_path, os.path.join(BACKUP_DIR, SRC))
                _atomic_to_csv(spot_out, src_path)
                print(f"  dropped the empty '{SRC_COL}' column from {SRC}")
            return 0
        print(f"    futures span {fut['date'].min()} -> {fut['date'].max()}")
        print(f"    spot    span {spot['date'].min()} -> {spot['date'].max()}")
        if not a.apply:
            print("  DRY RUN — re-run with --apply")
            return 0
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(src_path, os.path.join(BACKUP_DIR, SRC))
        moved = fut[["timestamp", "date", SRC_COL]].rename(columns={SRC_COL: DST_COL})
        with _csv_lock(dst_path):
            if os.path.exists(dst_path):
                existing = pd.read_csv(dst_path)
                moved = pd.concat([existing, moved], ignore_index=True).drop_duplicates(
                    subset=["timestamp"], keep="last")
            _atomic_to_csv(moved.sort_values("timestamp"), dst_path)
        _atomic_to_csv(spot.drop(columns=[SRC_COL]), src_path)
        print(f"  wrote {len(moved)} rows to {DST}; {SRC} now holds the FRED spot series only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
