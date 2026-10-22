import pandas as pd
import sys
import numpy as np


def clean_bonuses(csv_file):
    df = pd.read_csv(csv_file)

    # Convert amount to numeric
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

    # Remove zero/negative amounts and NaN
    df = df[df['amount'] > 0].copy()

    # Drop id, transactiontype, bonusfixed, balance (internal fields)
    for c in ['id', 'transactiontype', 'bonusfixed', 'balance']:
        if c in df.columns:
            df = df.drop(columns=[c])

    # Convert numeric columns
    for col in ['minwithdraw', 'maxwithdraw', 'rollover', 'perceived_value']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Calculate ratio for reference
    df['ratio'] = (df['minwithdraw'] / df['amount']).round(2)

    # Weighted Score:
    # (Amount / Effective Minimum Withdrawal) * sqrt(Maximum Withdrawal)
    # For the current dataset, Effective Minimum Withdrawal is the
    # supplied minimum withdrawal requirement.
    effective_min = df['minwithdraw']
    df['weighted_score'] = np.where(
        effective_min > 0,
        (df['amount'] / effective_min) * np.sqrt(df['maxwithdraw'].clip(lower=0)),
        np.nan,
    )
    df['weighted_score'] = df['weighted_score'].round(4)

    # Only remove extreme outliers: ratio > 500x (meaningless bonuses)
    df = df[df['ratio'] <= 500].copy()

    # Deduplicate by url + name + amount
    before = len(df)
    df = df.drop_duplicates(subset=['url', 'name', 'amount'], keep='first')

    # Sort by weighted score descending when available.
    if 'weighted_score' in df.columns:
        df = df.sort_values('weighted_score', ascending=False, na_position='last')
    elif 'perceived_value' in df.columns:
        df = df.sort_values('perceived_value', ascending=False)

    # Move ratio and weighted_score after rollover
    cols = df.columns.tolist()
    for col in ['ratio', 'weighted_score']:
        if col in cols:
            cols.remove(col)
    if 'rollover' in cols:
        ri = cols.index('rollover') + 1
        cols[ri:ri] = ['ratio', 'weighted_score']
    df = df[[c for c in cols if c in df.columns]]

    print(f"Filtered: {before} -> {len(df)} rows ({before - len(df)} removed)")
    return df


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "data/Dayne_Bonuses.csv"
    df = clean_bonuses(csv_file)
    df.to_csv('data/Dayne_Bonuses_Cleaned.csv', index=False)
    print(f'Saved: data/Dayne_Bonuses_Cleaned.csv ({len(df)} rows)')
