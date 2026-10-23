import pandas as pd
import sys
import numpy as np
from pathlib import Path
import shutil


def clean_bonuses(csv_file):
    df = pd.read_csv(csv_file)
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df = df[df['amount'] > 0].copy()

    for c in ['id', 'transactiontype', 'bonusfixed', 'balance']:
        if c in df.columns:
            df = df.drop(columns=[c])

    for col in ['minwithdraw', 'site_minwithdraw', 'effective_minwithdraw', 'maxwithdraw', 'rollover', 'perceived_value']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    bonus_min = df['minwithdraw'] if 'minwithdraw' in df.columns else pd.Series(np.nan, index=df.index)
    site_min = df['site_minwithdraw'] if 'site_minwithdraw' in df.columns else pd.Series(np.nan, index=df.index)
    effective_min = bonus_min.where(bonus_min > 0, site_min)
    effective_min = effective_min.where(effective_min > 0, 50.0)
    df['effective_minwithdraw'] = effective_min
    df['ratio'] = (effective_min / df['amount']).round(4)

    rollover = pd.to_numeric(df['rollover'], errors='coerce') if 'rollover' in df.columns else pd.Series(np.nan, index=df.index)
    df['rollover_ratio_average'] = (rollover * 0.60 + df['ratio'] * 0.40).round(4)
    df['weighted_score'] = df['rollover_ratio_average']

    if 'perceived_value' in df.columns:
        df['perceived_value'] = pd.to_numeric(df['perceived_value'], errors='coerce')
        df['perceived_value_rank'] = df['perceived_value'].rank(ascending=False, method='min', na_option='bottom').astype('Int64')
        df['weighted_score_rank'] = df['weighted_score'].rank(ascending=True, method='min', na_option='bottom').astype('Int64')
        df['score_rank_change'] = df['perceived_value_rank'] - df['weighted_score_rank']

    df = df[df['ratio'].isna() | (df['ratio'] <= 500)].copy()
    before = len(df)
    df = df.drop_duplicates(subset=['url', 'name', 'amount'], keep='first')

    if 'weighted_score' in df.columns:
        df = df.sort_values('weighted_score', ascending=True, na_position='last')
    elif 'perceived_value' in df.columns:
        df = df.sort_values('perceived_value', ascending=False)

    cols = df.columns.tolist()
    for col in ['effective_minwithdraw', 'ratio', 'rollover_ratio_average', 'weighted_score']:
        if col in cols:
            cols.remove(col)
    if 'rollover' in cols:
        ri = cols.index('rollover') + 1
        cols[ri:ri] = ['effective_minwithdraw', 'ratio', 'rollover_ratio_average', 'weighted_score']
    df = df[[c for c in cols if c in df.columns]]

    print(f"Filtered: {before} -> {len(df)} rows ({before - len(df)} removed)")
    return df


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "data/Dayne_Bonuses.csv"
    enriched_copy = Path('data/Dayne_Bonuses_Enriched.csv')
    df = clean_bonuses(csv_file)
    df.to_csv('data/Dayne_Bonuses_Cleaned.csv', index=False)
    # Preserve the enriched input as its own explicit layer. The legacy shell
    # copies Dayne_Bonuses.csv into the viewer, so restore the raw snapshot there
    # after cleaning to make the Raw tab genuinely raw.
    if Path('data/Dayne_Bonuses_Raw.csv').exists():
        shutil.copy2(csv_file, enriched_copy)
        shutil.copy2('data/Dayne_Bonuses_Raw.csv', csv_file)
    print(f'Saved: data/Dayne_Bonuses_Cleaned.csv ({len(df)} rows)')
