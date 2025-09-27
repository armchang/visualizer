import html
import dash
import plotly.graph_objects as graph
import pandas as pd
from plotly.subplots import make_subplots
from dash import html, dcc
from config import config 

def plot_signal_equity(df, equity_df, title, pair_name="ETHUSDT"):

    fig_width = len(df) * 40

    # Create subplot with 2 rows (candles + equity), shared x-axis
    plt = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        row_heights=[0.7, 0.3],
        subplot_titles=("Backtest Chart", "Equity Curve")
    )

    # ---- Top: Candlestick chart ----
    plt.add_trace(
        graph.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Candles",
            increasing=dict(
                line=dict(color='green', width=2),   # thicker green for bullish
                fillcolor='green'
            ),
            decreasing=dict(
                line=dict(color='red', width=2),     # thicker red for bearish
                fillcolor='red'
            )
        ),
        row=1, col=1
    )

    # Add trailing stop as a dashed line
    plt.add_trace(
        graph.Scatter(
            x=df.index,
            y=df["trailing_stop"],
            mode="lines",
            line=dict(color="orange", dash="dash"),
            name="Trailing Stop"
        ),
        row=1, col=1
    )

    # Add Buy/Sell markers
    # Horizontal offset. Assume your data is 4h candles → shift by 2h to move to right edge
    candle_width = pd.Timedelta(hours=4)
    shift = candle_width / 2   # half a bar width

    buy_mask = df["buy_signal"]
    sell_mask = df["sell_signal"]

    buy_idx = df.index[buy_mask]
    sell_idx = df.index[sell_mask]
    buy_idx_shifted  = buy_idx  + shift
    sell_idx_shifted = sell_idx + shift

    # Vertical offset (move markers above/below candles)
    pct_offset = 0.05  # 0.3% of price
    buy_y = (df.loc[buy_mask, "low"] * (1 - pct_offset)).values
    sell_y = (df.loc[sell_mask, "high"] * (1 + pct_offset)).values

    # Now use buy_idx_shifted / sell_idx_shifted for the x-values
    plt.add_trace(graph.Scatter(
        x=buy_idx, y=buy_y, mode="markers",
        marker=dict(symbol="triangle-up", size=10, color="limegreen",
                line=dict(color="black", width=2)),
        name="Buy"
    ), row=1, col=1)

    plt.add_trace(graph.Scatter(
        x=sell_idx, y=sell_y, mode="markers",
        marker=dict(symbol="triangle-down", size=10, color="crimson",
                line=dict(color="black", width=2)),
        name="Sell"
    ), row=1, col=1)

    # ---- Bottom: Equity curve ----
    plt.add_trace(
        graph.Scatter(
            x=equity_df.index,
            y=equity_df["equity"],
            mode="lines",
            line=dict(color="blue"),
            name="Equity"
        ),
        row=2, col=1
    )

    # 📏 Expand y-axis range to make candles taller
    price_min = df["low"].min()
    price_max = df["high"].max()
    price_range = price_max - price_min
    padding = price_range * 0.01

    plt.update_yaxes(
        range=[price_min - padding, price_max + padding],
        row=1, col=1
    )
    
    # Layout settings
    plt.update_layout(
        xaxis=dict(
        rangeslider=dict(visible=False),
        fixedrange = False
    ),
    xaxis2=dict(fixedrange=False),
    title=f"{pair_name} Backtest Chart with Equity Curve",
    template="plotly_white",
    height=800,
    width=fig_width,
    margin=dict(t=60, b=50, l=60, r=60),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return plt

def run(df, equity_df):
    fig = plot_signal_equity(df, equity_df, "UT Bot Signals", config.PAIR_NAME)

    # Dash app
    app = dash.Dash(__name__)


    # Layout with true horizontal scrolling
    app.layout = html.Div([
        html.Div([                                                              
            dcc.Graph(id="chart", figure=fig, config={'scrollZoom':False, 'displayModeBar' : True})
        ], style={"width": "10000px"})                                                           # 👈 Full width of the chart (scrollable content)
        ], id="scroll-container", style={
                "width": "100%",
                "overflowX": "auto",
                "whiteSpace": "nowrap",
                "height": "100%"
        })
    app.run()