

def add(df, target_vol=0.02, interval="4H", horizon_days=1, max_leverage=3.0):

    # Map interval to hours
    interval_hours_map = {
        "1h": 1,
        "2h": 2,
        "4h": 4,
        "30min": 0.5,
        "1d": 24,
        "1w": 24 * 7,
    }
    bar_hours = interval_hours_map.get(interval.upper(), 4)  # default to 4H if unknown

    # Calculate how many bars make up one full day based on the candle size
    bars_per_day = int(24 / bar_hours) if bar_hours < 24 else 1

    # Calculate how many bars to use for the volatility lookback period
    # For example, 1-day lookback = 6 bars for 4H candles
    lookback = bars_per_day * horizon_days

    # Make a copy of the DataFrame to avoid modifying the original
    df = df.copy()

    # Calculate simple return between each candle
    df['ret'] = df['close'].pct_change()

    # Compute rolling realized volatility (standard deviation of returns)
    # Shift(1) to avoid lookahead bias
    # Clip to avoid division by zero or extremely small values
    df['realized_vol'] = df['ret'].rolling(lookback).std().shift(1).clip(lower=1e-8)

    # Calculate position weight: how much to scale the trade size
    # The smaller the volatility, the larger the position (and vice versa)
    # Clip to prevent leverage from exceeding max_leverage (e.g., 3x)
    df['weight'] = (target_vol / df['realized_vol']).clip(upper=max_leverage)

    # Final position = direction signal × scaled position size
    # For example: signal = +1, weight = 1.5 → long 1.5x
    df['position'] = df['signal'] * df['weight']

    # Return the modified DataFrame with 'weight' and 'position' columns added
    return df