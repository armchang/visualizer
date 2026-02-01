def run(df, config, strategy):
    # === Step 1: Prepare data with indicators & signals ===
    df = strategy.prepare(df.copy(), config)

    # === Step 2: Initialize the trading state ===
    state = strategy.init_state(config)

    # === Step 3: Main backtest loop
    for i in range(len(df)):
        state.exited_this_bar = False
        row = df.iloc[i]

        # === Step 3.1: Update state context ===
        state.update_context(i, row, df)

        # === Step 3.2: Apply skip logic (cooldown, loss cap) ===
        if strategy.should_skip(i, row, state, config):
            continue

        # === Step 3.3: Check exit only if after entry ===
        if state.last_entry_bar is not None and i > state.last_entry_bar:
            strategy.check_exit(i, row, state, config)

        # === Step 3.4: Check for stop loss / breakeven ===
        strategy.check_stop(i, row, state, config)

        # === Step 3.5: Check entry (new trades) ===
        strategy.check_entry(i, row, df, state, config)

        # === Step 3.6: Record equity
        state.record_equity(df.index[i])

    # === Step 4: Return result DataFrames ===
    return state.to_equity_df(), state.to_trades_df()
