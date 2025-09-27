import numpy as np
import pandas as pd

# ---------- Indicators (pure pandas) ----------
def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def rsi(close, period=14):
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(period).mean() / down.rolling(period).mean()
    return 100 - (100 / (1 + rs))

def true_range(df):
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def atr(df, period=14):
    return true_range(df).rolling(period, min_periods=period).mean()

def adx(df, period=14):
    # Wilder's ADX (simplified smoothing via rolling mean)
    up_move = df['high'].diff()
    down_move = -df['low'].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(df)
    tr_n = tr.rolling(period).sum()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).sum() / tr_n
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).sum() / tr_n
    dx = ( (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0,np.nan) ) * 100
    return dx.rolling(period).mean()

def bollinger_bandwidth(close, period=20):
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = ma + 2*sd
    lower = ma - 2*sd
    bbw = (upper - lower) / ma  # relative bandwidth
    return bbw

def choppiness_index(df, period=14):
    tr = true_range(df)
    sum_tr = tr.rolling(period).sum()
    high_n = df['high'].rolling(period).max()
    low_n = df['low'].rolling(period).min()
    # 100 * log10(sum(TR)/ (HighN-LowN)) / log10(period)
    raw = sum_tr / (high_n - low_n)
    return 100 * np.log10(raw) / np.log10(period)

def macd_hist(close, fast=12, slow=26, signal=9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line - signal_line

# ---------- Feature engineering on df ----------
# Build regime features on your candle df
def build_regime_features(df):
    out = df.copy()
    out['ema50'] = ema(out['close'], 50)
    out['ema200'] = ema(out['close'], 200)
    out['ema_slope'] = out['ema50'].diff()
    out['rsi14'] = rsi(out['close'], 14)
    out['atr14'] = atr(out, 14)
    out['adx14'] = adx(out, 14)
    out['bbw20'] = bollinger_bandwidth(out['close'], 20)
    out['chop14'] = choppiness_index(out, 14)
    out['macd_hist'] = macd_hist(out['close'])
    out['dist_from_ema50_pct'] = (out['close'] - out['ema50']) / out['ema50']

    # ATR percentile over rolling window (~90 days or fallback)
    win = 24 * 90 if out.index.inferred_type == 'datetime64' else 500
    out['atr_pct'] = out['atr14'].rolling(win, min_periods=50).rank(pct=True)

    out['hour'] = out.index.hour
    out['dow'] = out.index.dayofweek  # 0 = Monday

    # Sideways detection flag
    out['is_sideways'] = (
        (out['adx14'] < 15) &
        (out['bbw20'] < out['bbw20'].rolling(200).quantile(0.3)) &
        (out['rsi14'].between(40, 60))
    ).astype(int)

    # ✅ Add binned columns for rule matching
    out['dist_ema_bin'] = pd.cut(out['dist_from_ema50_pct'],
        [-np.inf, -0.02, -0.005, 0.005, 0.02, np.inf],
        labels=['<=-2%', '-2%..-0.5%', '~flat', '0.5%..2%', '>=2%']
    )

    out['rsi14_bin'] = pd.cut(out['rsi14'], [0, 30, 40, 60, 70, 100],
        labels=['RSI<=30','30-40','40-60','60-70','>=70']
    )

    out['adx14_bin'] = pd.cut(out['adx14'], [0,10,15,20,40,100],
        labels=['<10','10-15','15-20','20-40','>=40']
    )

    out['atr_pct_bin'] = pd.cut(out['atr_pct'], [0,0.1,0.2,0.5,0.8,1.0],
        labels=['<=10%','10-20%','20-50%','50-80%','>80%']
    )

    out['bbw20_bin'] = pd.qcut(out['bbw20'], q=5, labels=['Q1(low)','Q2','Q3','Q4','Q5(high)'])
    out['chop14_bin'] = pd.qcut(out['chop14'], q=5, labels=['Q1','Q2','Q3','Q4','Q5'])

    out['hour_bin'] = pd.cut(out['hour'], [-0.1, 4, 8, 12, 16, 20, 24],
        labels=['0-4','4-8','8-12','12-16','16-20','20-24']
    )

    return out

# ---------- Merge trades with entry-time features d----------
# Attach those to your trades
def attach_trade_context(
    df_feat: pd.DataFrame,
    trades_df: pd.DataFrame,
    entry_col: str = "entry_time",
    bar: str = "4h",
    tz: str = "UTC",
):
    """
    As-of join (backward) each trade's entry time to the most recent candle's
    feature row within `bar` tolerance. Robust to tz differences and non-exact
    timestamp matches.
    """

    # --- 0) Normalize timezones & columns ---
    df_feat = df_feat.sort_index().copy()
    if df_feat.index.tz is None:
        df_feat.index = df_feat.index.tz_localize(tz)
    else:
        df_feat.index = df_feat.index.tz_convert(tz)

    # Accept common fallbacks if entry_col isn't present
    if entry_col not in trades_df.columns:
        for c in ("entry_time", "time", "open_time"):
            if c in trades_df.columns:
                entry_col = c
                break
        else:
            raise KeyError(f"'{entry_col}' not found in trades_df (tried entry_time/time/open_time).")

    trades_tmp = trades_df.copy()
    trades_tmp["_entry_time_utc"] = pd.to_datetime(trades_tmp[entry_col], utc=True)

    # --- 1) Prep right table for merge_asof ---
    right = df_feat.reset_index()
    right.columns.values[0] = "bar_time"  # Force rename first column safely
    right = right.sort_values("bar_time")

    # --- 2) As-of merge (backward) within one bar tolerance ---
    merged = pd.merge_asof(
        trades_tmp.sort_values("_entry_time_utc"),
        right,
        left_on="_entry_time_utc",
        right_on="bar_time",
        direction="backward",
        tolerance=pd.Timedelta(bar),
    )

    # Drop trades that couldn’t be matched within tolerance (e.g., before first bar)
    unmatched = merged["bar_time"].isna().sum()
    if unmatched:
        print(f"[attach_trade_context] ⚠️  Dropped {unmatched} trades outside tolerance {bar}")
        merged = merged[merged["bar_time"].notna()].copy()

    # --- 3) Keep/rename useful feature columns & add loss label ---
    desired_feats = [
        "rsi14","adx14","atr14","atr_pct","bbw20","chop14","macd_hist",
        "ema_slope","dist_from_ema50_pct","hour","dow","is_sideways"
    ]
    present_feats = [c for c in desired_feats if c in merged.columns]

    out = merged.copy()

    # 🔥 Always add pnl column if missing
    if "pnl" not in out.columns and "pnl_pct" not in out.columns:
        out["pnl"] = np.nan

    # 🔥 Always add is_loss column (handles NaN gracefully)
    if "pnl" in out.columns:
        out["is_loss"] = out["pnl"].lt(0).astype(int)
    elif "pnl_pct" in out.columns:
        out["is_loss"] = out["pnl_pct"].lt(0).astype(int)
    else:
        out["is_loss"] = 0  # fallback

    # Keep original trade columns + attached features
    keep_cols = list(trades_df.columns) + ["bar_time"] + present_feats + ["is_loss"]
    keep_cols = [c for c in keep_cols if c in out.columns]
    return out[keep_cols].reset_index(drop=True)



# ---------- Quick univariate pattern scan ----------
def pattern_report(trades_ctx):
    bins = {
        'rsi14_bin': pd.cut(trades_ctx['rsi14'], [0,30,40,60,70,100],
                            labels=['RSI<=30','30-40','40-60','60-70','>=70']),
        'adx14_bin': pd.cut(trades_ctx['adx14'], [0,10,15,20,40,100],
                            labels=['<10','10-15','15-20','20-40','>=40']),
        'atr_pct_bin': pd.cut(trades_ctx['atr_pct'], [0,0.1,0.2,0.5,0.8,1.0],
                              labels=['<=10%','10-20%','20-50%','50-80%','>80%']),
        'bbw20_bin': pd.qcut(trades_ctx['bbw20'], q=5, labels=['Q1(low)','Q2','Q3','Q4','Q5(high)']),
        'chop14_bin': pd.qcut(trades_ctx['chop14'], q=5, labels=['Q1','Q2','Q3','Q4','Q5']),
        'dist_ema_bin': pd.cut(trades_ctx['dist_from_ema50_pct'],
                               [-np.inf,-0.02,-0.005,0.005,0.02,np.inf],
                               labels=['<=-2%','-2%..-0.5%','~flat','0.5%..2%','>=2%']),
        'hour_bin': pd.cut(trades_ctx['hour'], [-0.1,4,8,12,16,20,24],
                           labels=['0-4','4-8','8-12','12-16','16-20','20-24'])
    }
    tmp = trades_ctx.copy()
    for k,v in bins.items():
        tmp[k] = v
    keys = [k for k in bins.keys()] + ['dow','is_sideways']
    
    tables = {}
    for key in keys:
        g = tmp.groupby(key, dropna=False, observed=False).agg(
            n=('is_loss','size'),
            loss_rate=('is_loss','mean'),
            avg_pnl=('pnl' if 'pnl' in tmp.columns else 'pnl_pct','mean')
        ).sort_values('loss_rate', ascending=False)
        tables[key] = g
    return tables

# ---------- Simple rule: identify the worst bins ----------
def propose_filters(tables, min_trades=25, top_k_per_feature=1, loss_rate_floor=0.60):
    """
    For each feature table, pick up to top_k bins where:
      - sample size >= min_trades
      - loss rate >= loss_rate_floor
    Returns list of human-readable rules.
    """
    rules = []
    for feat, tab in tables.items():
        if tab.empty: 
            continue
        sub = tab[tab['n'] >= min_trades].copy()
        sub = sub[sub['loss_rate'] >= loss_rate_floor].head(top_k_per_feature)
        for idx, row in sub.iterrows():
            rules.append((feat, str(idx), int(row['n']), float(row['loss_rate'])))
    return sorted(rules, key=lambda x: -x[3])  # sort by loss rate desc
