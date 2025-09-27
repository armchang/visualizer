import matplotlib.pyplot as plt
from config import config

def plot_signals(df, title, ax=None):
    standalone = False
    if (ax is None):                                                                # If no axis is provided, create a new figure and axis
        fig, ax = plt.subplots(figsize=(12, 6))                                     # Set figure size for better visibility 
        standalone = True              
    ax.plot(df.index, df["close"], label="Close")
    ax.plot(df.index, df["trailing_stop"], label="Trailing Stop", linestyle="--")
    ax.scatter(df[df["buy_signal"]].index, df[df["buy_signal"]]["close"], label="Buy", marker="^", color="green")
    ax.scatter(df[df["sell_signal"]].index, df[df["sell_signal"]]["close"], label="Sell", marker="v", color="red")
    ax.set_title(title)
    ax.legend()
    if (standalone):
        plt.tight_layout()
        plt.show()
    
def plot_equity_curve(equity_df, title, ax=None):
    standalone = False
    if (ax is None):
        fig, ax = plt.subplots(figsize=(10, 4))
        standalone = True
    ax.plot(equity_df.index, equity_df["equity"], label="Equity")
    ax.set_title(title)
    ax.set_xlabel("Time")
    ax.set_ylabel("Account Balance")
    ax.grid(True)
    if (standalone):
        plt.tight_layout()
        plt.show()

def plot_signal_equity(df, equity_df):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    plot_signals(df, f"{config.PAIR_NAME} UT Bot Signals", ax=ax1)
    plot_equity_curve(equity_df, "Equity Curve", ax=ax2)
    plt.tight_layout()
    plt.show()