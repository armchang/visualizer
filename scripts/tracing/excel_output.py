import os
import pandas as pd
from datetime import datetime

def export_nan(df, export=True, prefix="nan_output"):
    if not export:
        return
    # Create timestamp string (e.g., 2025-09-18_135500)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = os.path.join("scripts", "tracing", "files", f"{prefix}_{timestamp}.xlsx")

    # If index is datetime with tz, strip it
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # If any datetime columns have tz, strip them
    for col in df.select_dtypes(include=["datetimetz"]).columns:
        df[col] = df[col].dt.tz_localize(None)

    # Save only rows with NaN values
    df[df.isna().any(axis=1)].to_excel(output_dir, index=False)
    print(f"Saved NaN export: {output_dir}")


def export(df, export = True, prefix="output"):
    if not export:
        return
    # Create timestamp string
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # If index is datetime with tz, strip it
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # If any datetime columns have tz, strip them
    for col in df.select_dtypes(include=["datetimetz"]).columns:
        df[col] = df[col].dt.tz_localize(None)

    # Chunk saving
    rows_per_file = 1_000_000
    for i in range(0, len(df), rows_per_file):
        chunk = df.iloc[i:i+rows_per_file]
        filename = f"scripts/tracing/files/{prefix}_{timestamp}_part{i//rows_per_file+1}.xlsx"
        chunk.to_excel(filename, index=False)
        print(f"Saved export chunk: {filename}")
