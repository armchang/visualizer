import pandas as pd
import sqlite3


def get_ohlcv_data(db_path, table_name, pair_name):
    with sqlite3.connect(db_path) as conn:
        query = f"""
            SELECT open_time, open, high, low, close, volume
            FROM {table_name}
            WHERE pair = ?
            ORDER BY open_time ASC
        """
        # Retrieve the data from database
        df = pd.read_sql(query, conn, params=(pair_name,), parse_dates=["open_time"])
        df["open_time_index"] = df["open_time"]
        df.set_index("open_time_index", inplace=True)

    return df

def crop_date_range(df, years):
    df.index = pd.to_datetime(df.index, utc=True)                                   # Ensure the index is in UTC    
    end_date = pd.Timestamp.now(tz='UTC')
    start_date = end_date - pd.DateOffset(years=years)

    return df.loc[start_date:end_date]

def resample_ohlcv(df, interval):
    resampled = df.resample(interval).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    # ✅ Restore open_time column using the resampled index
    resampled["open_time"] = resampled.index

    return resampled

    