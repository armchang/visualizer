import scripts.engine as engine
from flask import Flask, render_template_string
import pandas as pd
from config import config


def run(df, equity_df, trades_df, metrics, debug=False):

    # Convert trades_df to simple records for HTML table
    trades_view = trades_df.copy()

    # Make sure time is printable (string) for the table
    if "time" in trades_view.columns:
        trades_view["time"] = pd.to_datetime(trades_view["time"]).astype(str)

    # Fill missing expected columns safely (optional)
    for col in ["pnl", "qty", "equity", "price"]:
        if col not in trades_view.columns:
            trades_view[col] = None
            
    trades_view["pnl"] = pd.to_numeric(trades_view.get("pnl"), errors="coerce").fillna(0)
    trades_data = trades_view.to_dict(orient="records")

    # Add final equity balance to metrics
    metrics["Final Balance"] = round(equity_df.iloc[-1]['equity'], 2)

    # ✅ Fix 1: Ensure index is datetime (needed for .astype(int))
    df.index = pd.to_datetime(df.index)

    # ✅ Fix 2: Create separate 'time' column BEFORE modifying index
    df["time"] = df.index.astype("int64") // 10**9  # UNIX time in seconds
    
    # Add Unix seconds column
    equity_df["time_unix"] = equity_df.index.astype("int64") // 10**9
    equity_markers = []
    entry_types = ["BUY", "SELL (SHORT)"]
    exit_types = ["SELL", "BUY (COVER)", "SELL (BREAKEVEN)", "SELL (TIME)", "SELL (STOP)", "BUY (COVER B/E)"]

    # Match trades to equity_df timestamps (same time format: UNIX seconds)
    for trade in trades_df.itertuples():
        if trade.type in entry_types:
            equity_markers.append({
                "time": int(pd.to_datetime(trade.time).timestamp()),
                "position": "belowBar",
                "color": "lime",
                "shape": "arrowUp",
                "text": f"{trade.type} Entry"
            })
        elif trade.type in exit_types:
            equity_markers.append({
                "time": int(pd.to_datetime(trade.time).timestamp()),
                "position": "aboveBar",
                "color": "red",
                "shape": "arrowDown",
                "text": f"{trade.type} Exit"
            })

    # Add drawdown markers
    drawdown_markers = []
    threshold = -0.51
    in_drawdown = False

    for ts, dd in equity_df["drawdown"].items():
        if not in_drawdown and dd <= threshold:
            # Entering a drawdown zone → mark it once
            drawdown_markers.append({
                "time": int(pd.to_datetime(ts).timestamp()),
                "position": "aboveBar",
                "color": "purple",
                "shape": "circle",
                "text": f"DD {dd:.0%}"
            })
            in_drawdown = True
        elif in_drawdown and dd > threshold:
            # Exiting drawdown zone → reset
            in_drawdown = False
    
    equity_markers = equity_markers + drawdown_markers

    # Sort for good measure
    equity_markers = sorted(equity_markers, key=lambda x: x["time"])    
    
    # ✅ Fix 3: Ensure signals align with candles
    signals = []
    if "buy_signal" in df.columns:
        for row in df[df["buy_signal"]].itertuples():
            signals.append({
                "time": int(row.time),               # Already in UNIX seconds
                "position": "belowBar",
                "color": "lime",
                "shape": "arrowUp",
                "text": "Buy"
            })

    if "sell_signal" in df.columns:
        for row in df[df["sell_signal"]].itertuples():
            signals.append({
                "time": int(row.time),
                "position": "aboveBar",
                "color": "red",
                "shape": "arrowDown",
                "text": "Sell"
            })

    # ✅ Sort signals by time (optional but recommended)
    signals = sorted(signals, key=lambda x: x["time"])

    trailing_stop_data = []

    if "trailing_stop" in df.columns:
        trailing_stop_data = (
            df[["time", "trailing_stop"]]
            .dropna()
            .rename(columns={"trailing_stop": "value"})
            .to_dict(orient="records")
    )
    
    # Convert equity_df into [{time: ..., value: ...}] format
    equity_data = (
        equity_df[["time_unix", "equity"]]
        .rename(columns={"time_unix": "time", "equity": "value"})
        .to_dict(orient="records")
    )
    
    # ============================
    # SMA LINES (UT-BOT ONLY)
    # ============================

    sma20_data = []
    sma50_data = []
    sma100_data = []
    sma200_data = []

    if "sma20" in df.columns:
        sma20_data = (
            df[["time", "sma20"]]
            .dropna()
            .rename(columns={"sma20": "value"})
            .to_dict(orient="records")
        )

    if "sma50" in df.columns:
        sma50_data = (
            df[["time", "sma50"]]
            .dropna()
            .rename(columns={"sma50": "value"})
            .to_dict(orient="records")
        )

    if "sma100" in df.columns:
        sma100_data = (
            df[["time", "sma100"]]
            .dropna()
            .rename(columns={"sma100": "value"})
            .to_dict(orient="records")
        )

    if "sma200" in df.columns:
        sma200_data = (
            df[["time", "sma200"]]
            .dropna()
            .rename(columns={"sma200": "value"})
            .to_dict(orient="records")
        )

    # Flask app
    app = Flask(__name__)

    @app.route("/")
    def chart():
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TradingView Lightweight Chart</title>
            <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                #chart {
                    width: 100%;
                    height: 600px;
                }
            </style>
        </head>
        <body>
            <h2>{{ pair_name }}/{{timeline}} Analysis Chart</h2>
            <div id="container" style="display:flex; flex-direction:column; height:800px;">
                <!-- Metrics overlay -->
                <div id="metrics-box"
                    style="position:absolute; top:80px; left:10px;
                            background:rgba(255,255,255,0.85);
                            border:1px solid #ccc;
                            border-radius:6px;
                            padding:8px;
                            font-size:13px;
                            line-height:1.4;
                            z-index:10;">
                    <b>Metrics</b><br>
                    Last Balance:
                    <span style="color: {{ 'green' if metrics['Final Balance'] > 0 else 'red' }}">
                    <b>{{ "{:,.2f}".format(metrics["Final Balance"]) }}</b>
                    </span><br>
                    Sharpe:
                    <span style="color: {{ 'green' if metrics['Sharpe Ratio'] > 0 else 'red' }}">
                    <b>{{ metrics["Sharpe Ratio"] }}</b>
                    </span><br> 
                    Annual Return:
                    <span style="color: {{ 'green' if metrics['Annual Return'] > 0 else 'red' }}">
                    <b>{{ (metrics["Annual Return"] * 100) | round(2) }}%</b>
                    </span></br>
                    Max Drawdown:
                    <span style="color: {{ 'green' if metrics['Max Drawdown'] > 0 else 'red' }}">
                    <b>{{ (metrics["Max Drawdown"] * 100) | round(2) }}%</b>
                    </span><br>
                    Win Rate:
                    <span style="color: {{ 'green' if metrics['Win Rate'] > 0 else 'red' }}">
                    <b>{{ (metrics["Win Rate"] * 100) | round(2) }}%</b>
                    </span><br>
                    Total Trades: {{ metrics["Total Trades"] }}<br>
                </div>
                <div id="price-chart" style="flex:3;"></div>
                <div id="equity-chart" style="flex:1;"></div>
            </div>
            <script>
                const priceElement = document.getElementById('price-chart');
                const equityElement = document.getElementById('equity-chart');
                                      
                const priceChart = LightweightCharts.createChart(priceElement, {
                    width: priceElement.clientWidth,
                    height: 600,
                    layout: { backgroundColor: '#fff', textColor: '#000' },
                    timeScale: { timeVisible: true, secondsVisible: false },
                });
                const sma20Line = priceChart.addLineSeries({
                    color: 'blue',
                    lineWidth: 1,
                    priceLineVisible: false,
                });
                const sma50Line = priceChart.addLineSeries({
                    color: 'purple',
                    lineWidth: 1,
                    priceLineVisible: false,
                });
                const sma100Line = priceChart.addLineSeries({
                    color: 'orange',
                    lineWidth: 2,
                    priceLineVisible: false,
                });
                const sma200Line = priceChart.addLineSeries({
                    color: 'red',
                    lineWidth: 2,
                    priceLineVisible: false,
                });
                const equityChart = LightweightCharts.createChart(equityElement, {
                    width: equityElement.clientWidth,
                    height: 200,
                    layout: { backgroundColor: '#fff', textColor: '#000' },
                    timeScale: { timeVisible: true, secondsVisible: false },
                });

                // Price chart series
                const candleSeries = priceChart.addCandlestickSeries();
                const trailingLine = priceChart.addLineSeries({
                    color: 'teal',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    priceLineVisible: false,
                });

                // ✅ Added for Volume
                const volumeSeries = priceChart.addHistogramSeries({
                    priceFormat: { type: 'volume' },
                    priceScaleId: '', // keep overlayed
                });
                     
                
                // Equity line
                const equitySeries = equityChart.addLineSeries({
                    color: 'blue',
                    lineWidth: 2,
                });
                                               
                // ✅ Fix 4: Use JSON.parse to inject safe serialized data
                const ohlcv = JSON.parse('{{ ohlcv_data | tojson | safe }}');
                // ✅ Normalize volume to shrink height (~20% of chart)
                const maxVol = Math.max(...ohlcv.map(c => c.volume));
                const volume = ohlcv.map(candle => ({
                    time: candle.time,
                    value: candle.volume / maxVol * 10,  // scale it low so bars are small
                    color: candle.close > candle.open
                        ? 'rgba(0,150,136,0.5)'
                        : (candle.close < candle.open
                            ? 'rgba(255,82,82,0.5)'
                            : 'rgba(128,128,128,0.5)'),
                }));
                const signals = JSON.parse('{{ signals | tojson | safe }}');
                const trailingStop = JSON.parse('{{ trailing_stop | tojson | safe }}');
                const equity = JSON.parse('{{ equity_data | tojson | safe }}');
                const equityMarkers = JSON.parse('{{ equity_markers | tojson | safe }}');
                // Inject and apply SMA data
                const sma20 = JSON.parse('{{ sma20_data | tojson | safe }}');
                const sma50 = JSON.parse('{{ sma50_data | tojson | safe }}');
                const sma100 = JSON.parse('{{ sma100_data | tojson | safe }}');
                const sma200 = JSON.parse('{{ sma200_data | tojson | safe }}');
                                                
                candleSeries.setData(ohlcv);
                candleSeries.setMarkers(signals);
                trailingLine.setData(trailingStop);
                equitySeries.setData(equity);
                equitySeries.setMarkers(equityMarkers);
                sma20Line.setData(sma20);
                sma50Line.setData(sma50);
                sma100Line.setData(sma100);
                sma200Line.setData(sma200);
                // ✅ Added for Volume
                volumeSeries.setData(volume);
                                      
                // Sync time scales
                function syncTimeScales(chartA, chartB) {
                    chartA.timeScale().subscribeVisibleTimeRangeChange(range => {
                        chartB.timeScale().setVisibleRange(range);
                    });
                }
                syncTimeScales(priceChart, equityChart);
                syncTimeScales(equityChart, priceChart);
                                      
            </script>
        </body>
        </html>
        """, 
        ohlcv_data=df[["time", "open", "high", "low", "close", "volume"]].to_dict(orient="records"),
        signals=signals,
        trailing_stop=trailing_stop_data,
        metrics=metrics,
        equity_data = equity_data,
        equity_markers=equity_markers,
        sma20_data=sma20_data,
        sma50_data=sma50_data,
        sma100_data=sma100_data,
        sma200_data=sma200_data,
        pair_name=config.PAIR_NAME,
        timeline=config.RESAMPLE_INTERVAL)

    @app.route("/trades")
    def trades():
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trades</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 12px; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; font-size: 13px; }
                th { background: #f5f5f5; text-align: left; }
                tr:nth-child(even) { background: #fafafa; }
                .pnl-pos { background: rgba(0, 200, 0, 0.12) !important; }
                .pnl-neg { background: rgba(255, 0, 0, 0.12) !important; }
            </style>
        </head>
        <body>
            <h2>Trades</h2>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Time</th>
                        <th>Type</th>
                        <th>Price</th>
                        <th>Qty</th>
                        <th>PNL</th>
                        <th>Equity</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in trades %}
                    <tr class="{% if (t.get('pnl') or 0) > 0 %}pnl-pos{% elif (t.get('pnl') or 0) < 0 %}pnl-neg{% endif %}">
                        <td>{{ loop.index }}</td>
                        <td>{{ t.get("time", "") }}</td>
                        <td>{{ t.get("type", "") }}</td>
                        <td>{{ "%.2f"|format(t.get("price", 0) or 0) }}</td>
                        <td>{{ t.get("qty", "") }}</td>
                        <td>{{ t.get("pnl", "") }}</td>
                        <td>{{ t.get("equity", "") }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </body>
        </html>
        """, trades=trades_data)

    app.run(debug=debug, use_reloader=False)
