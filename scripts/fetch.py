import pandas as pd
import sqlite3
from urllib.parse import unquote


def get_ohlcv_data(database_type, database_url, table_name, pair_name):
    if database_type == "postgresql":
        df = _fetch_postgresql(database_url, table_name, pair_name)
    elif database_type == "sqlite":
        df = _fetch_sqlite(database_url, table_name, pair_name)
    else:
        raise ValueError(f"Unsupported database type: {database_type!r}")

    if df.empty:
        raise ValueError(f"No data found for pair {pair_name!r}.")

    df["open_time"] = pd.to_datetime(df["open_time"])
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column])

    df.set_index("open_time", inplace=True, drop=False)
    df.index.name = "open_time_index"
    df = df.sort_index()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)                                       # Remove timezone from index
    return df


def _fetch_postgresql(database_url, table_name, pair_name):
    import psycopg
    from psycopg import sql

    query = sql.SQL("""
        SELECT open_time, open, high, low, close, volume
        FROM {}
        WHERE pair = %s
        ORDER BY open_time ASC
    """).format(sql.Identifier(table_name))

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (pair_name,))
            columns = [column.name for column in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=columns)


def _fetch_sqlite(database_url, table_name, pair_name):
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("SQLite DATABASE_URL must use sqlite:///path or sqlite:///:memory:")

    database_path = unquote(database_url[len(prefix):])
    if not database_path:
        raise ValueError("SQLite DATABASE_URL must include a database path")

    quoted_table_name = '"' + table_name.replace('"', '""') + '"'
    query = f"""
        SELECT open_time, open, high, low, close, volume
        FROM {quoted_table_name}
        WHERE pair = ?
        ORDER BY open_time ASC
    """
    with sqlite3.connect(database_path) as connection:
        return pd.read_sql_query(query, connection, params=(pair_name,))

def crop_date_range(df, years):
    df.index = pd.to_datetime(df.index, utc=True)                                   # Ensure the index is in UTC    
    end_date = pd.Timestamp.now(tz='UTC')
    start_date = end_date - pd.DateOffset(years=years)

    return df.loc[start_date:end_date]
