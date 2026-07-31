"""Dashboard Streamlit simples — candles, features, regimes e labels.

Uso:  streamlit run crypto_bot/monitoring/dashboard.py
Requer: pip install -e ".[dashboard]"
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from crypto_bot.config import SETTINGS

st.set_page_config(page_title="CryptoBot Research", layout="wide")
st.title("📊 CryptoBot Research Engine")

# Conexão read-only para não conflitar com o coletor
con = duckdb.connect(SETTINGS.database.path, read_only=True)

symbol = st.sidebar.selectbox("Par", SETTINGS.symbols)
timeframe = st.sidebar.selectbox("Timeframe", SETTINGS.timeframes)

counts = con.execute(
    """
    SELECT timeframe, COUNT(*) AS candles,
           MIN(timestamp) AS first, MAX(timestamp) AS last
    FROM candles WHERE symbol = ? GROUP BY timeframe ORDER BY timeframe
    """,
    [symbol],
).fetchdf()
st.subheader(f"Cobertura — {symbol}")
st.dataframe(counts, use_container_width=True)

candles = con.execute(
    """
    SELECT timestamp, open, high, low, close, volume
    FROM candles WHERE symbol = ? AND timeframe = ?
    ORDER BY timestamp DESC LIMIT 500
    """,
    [symbol, timeframe],
).fetchdf()

if not candles.empty:
    st.subheader("Preço (close)")
    st.line_chart(candles.sort_values("timestamp").set_index("timestamp")["close"])

regimes = con.execute(
    """
    SELECT r.composite, COUNT(*) AS n
    FROM regimes r JOIN candles c ON r.candle_id = c.id
    WHERE c.symbol = ? AND c.timeframe = ?
    GROUP BY r.composite ORDER BY n DESC LIMIT 15
    """,
    [symbol, timeframe],
).fetchdf()

if not regimes.empty:
    st.subheader("Distribuição de regimes")
    st.bar_chart(regimes.set_index("composite")["n"])

labels = con.execute(
    """
    SELECT COUNT(*) AS total,
           AVG(future_return_1h) AS avg_ret_1h,
           AVG(future_return_1d) AS avg_ret_1d
    FROM candle_labels WHERE symbol = ? AND timeframe = ?
    """,
    [symbol, timeframe],
).fetchdf()
st.subheader("Labels")
st.dataframe(labels, use_container_width=True)

con.close()
