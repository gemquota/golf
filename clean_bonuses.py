import pandas as pd
import sys
import numpy as np
from pathlib import Path
import shutil
from statistics import median
from urllib.parse import urlparse
from bonus_scoring import score_bonus


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

    # Estimate missing fields from the same site first, then the dataset.
    def host(value):
        try:
            return (urlparse(str(value)).hostname or '').lower().removeprefix('www.')
        except Exception:
            return ''

    df['_score_host'] = df['url'].map(host) if 'url' in df.columns else ''
    maximums = pd.to_numeric(df['maxwithdraw'], errors='coerce') if 'maxwithdraw' in df.columns else pd.Series(np.nan, index=df.index)
    rollovers = pd.to_numeric(df['rollover'], errors='coerce') if 'rollover' in df.columns else pd.Series(np.nan, index=df.index)
    known_max = maximums[maximums > 0].dropna()
    known_roll = rollovers[rollovers >= 0].dropna()
    global_max = float(known_max.median()) if not known_max.empty else None
    global_roll = float(known_roll.median()) if not known_roll.empty else None
    site_max = df.assign(_v=maximums).loc[maximums > 0].groupby('_score_host')['_v'].median().to_dict()
    site_roll = df.assign(_v=rollovers).loc[rollovers >= 0].groupby('_score_host')['_v'].median().to_dict()

    def score_row(row):
        h = row.get('_score_host', '')
        result = score_bonus(
            amount=row.get('amount'),
            minwithdraw=row.get('minwithdraw'),
            site_minwithdraw=row.get('site_minwithdraw'),
            maxwithdraw=row.get('maxwithdraw'),
            rollover=row.get('rollover'),
            site_maxwithdraw=site_max.get(h),
            site_rollover=site_roll.get(h),
            global_maxwithdraw=global_max,
            global_rollover=global_roll,
        )
        return pd.Series(result)

    score_columns = df.apply(score_row, axis=1)
    for column in score_columns.columns:
        df[column] = score_columns[column]
    df['ratio'] = (pd.to_numeric(df['effective_minwithdraw'], errors='coerce') / df['amount']).round(4)

    if 'perceived_value' in df.columns:
        df['perceived_value'] = pd.to_numeric(df['perceived_value'], errors='coerce')
        df['perceived_value_rank'] = df['perceived_value'].rank(ascending=False, method='min', na_option='bottom').astype('Int64')
        df['weighted_score_v1_rank'] = df['weighted_score_v1'].rank(ascending=False, method='min', na_option='bottom').astype('Int64')
        df['weighted_score_rank'] = df['weighted_score'].rank(ascending=False, method='min', na_option='bottom').astype('Int64')
        df['score_rank_change'] = df['perceived_value_rank'] - df['weighted_score_rank']
    df.drop(columns=['_score_host'], inplace=True, errors='ignore')

    df = df[df['ratio'].isna() | (df['ratio'] <= 500)].copy()
    before = len(df)
    df = df.drop_duplicates(subset=['url', 'name', 'amount'], keep='first')

    if 'weighted_score' in df.columns:
        df = df.sort_values('weighted_score', ascending=False, na_position='last')
    elif 'perceived_value' in df.columns:
        df = df.sort_values('perceived_value', ascending=False)

    cols = df.columns.tolist()
    for col in ['effective_minwithdraw', 'ratio', 'rollover_ratio_average', 'weighted_score_v1', 'weighted_score', 'score_confidence', 'score_status', 'score_maxwithdraw_source', 'score_rollover_source', 'score_maxwithdraw_used', 'score_rollover_used']:
        if col in cols:
            cols.remove(col)
    if 'rollover' in cols:
        ri = cols.index('rollover') + 1
        cols[ri:ri] = ['effective_minwithdraw', 'ratio', 'rollover_ratio_average', 'weighted_score_v1', 'weighted_score', 'score_confidence', 'score_status', 'score_maxwithdraw_source', 'score_rollover_source', 'score_maxwithdraw_used', 'score_rollover_used']
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
