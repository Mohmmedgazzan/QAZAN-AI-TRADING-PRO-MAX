import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.ml.probability_engine import (
    MIN_REQUIRED_CLOSED_BARS,
    PROB_FEATURE_COLS,
    build_causal_probability_features,
    estimate_next_candle_probabilities_on_df,
)


def _make_ohlcv_df(n_bars: int = 320, seed: int = 19, interval_sec: int = 3600) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base_ts = 1_700_000_000
    rows = []
    price = 50000.0
    for i in range(n_bars):
        drift = 0.0012 if (i // 45) % 2 == 0 else -0.0009
        ret = drift + float(rng.normal(0.0, 0.008))
        o = price
        c = max(100.0, o * (1.0 + ret))
        wick_up = abs(float(rng.normal(0.0, 0.004))) * max(o, c)
        wick_dn = abs(float(rng.normal(0.0, 0.004))) * min(o, c)
        h = max(o, c) + wick_up
        l = min(o, c) - wick_dn
        vol = 900.0 + abs(float(rng.normal(0.0, 350.0)))
        rows.append(
            {
                "time": base_ts + i * interval_sec,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": round(vol, 2),
            }
        )
        price = c
    return pd.DataFrame(rows)


def test_refuses_prediction_when_data_insufficient():
    df_short = _make_ohlcv_df(n_bars=65)
    res = estimate_next_candle_probabilities_on_df(df_short, symbol="BTCUSDT", interval="1h")
    assert res.status == "INSUFFICIENT_DATA"
    assert res.closed_bars_analyzed < MIN_REQUIRED_CLOSED_BARS
    assert res.probabilities is None
    assert res.estimated_range is None
    assert res.confidence_pct is None
    assert res.walk_forward_metrics is None
    assert res.insufficient_reason is not None
    assert res.is_guarantee is False


def test_zero_future_leakage_in_all_nine_feature_domains():
    """
    Truncating OHLCV at bar N must produce identical causal features across
    OHLCV, RSI, ATR, Volume, VWAP, Market Structure, Liquidity, FVG, and Trend
    compared to the extended DataFrame with 40 future candles appended.
    """
    df_full = _make_ohlcv_df(n_bars=260, seed=77)
    cutoff = 200
    df_prefix = df_full.iloc[:cutoff].copy()

    feat_prefix, _ = build_causal_probability_features(df_prefix, timeframe="1h")
    feat_full, _ = build_causal_probability_features(df_full, timeframe="1h")

    for col in PROB_FEATURE_COLS:
        arr_p = feat_prefix[col].iloc[:cutoff].fillna(0.0).to_numpy(dtype=np.float64)
        arr_f = feat_full[col].iloc[:cutoff].fillna(0.0).to_numpy(dtype=np.float64)
        assert np.allclose(arr_p, arr_f, atol=1e-9), f"Look-ahead leakage detected in feature '{col}'"


def test_unclosed_candle_excluded_in_probability_engine():
    df = _make_ohlcv_df(n_bars=220, interval_sec=3600)
    last_open = int(df["time"].iloc[-1])
    res = estimate_next_candle_probabilities_on_df(
        df, symbol="ETHUSDT", interval="1h", as_of_ts=last_open + 900
    )
    assert res.unclosed_bar_excluded is True
    assert res.closed_bars_analyzed == 219


def test_walk_forward_brier_logloss_baseline_and_range_output():
    df = _make_ohlcv_df(n_bars=320, seed=123)
    res = estimate_next_candle_probabilities_on_df(df, symbol="BTCUSDT", interval="1h", persist=False)

    assert res.status == "OK"
    assert res.is_guarantee is False
    assert res.look_ahead_bias_prevented is True
    assert res.probabilities is not None
    total_p = res.probabilities.up_pct + res.probabilities.down_pct + res.probabilities.sideways_pct
    assert abs(total_p - 100.0) <= 0.05
    assert res.probabilities.dominant_outcome in {"UP", "DOWN", "SIDEWAYS"}

    assert res.estimated_range is not None
    assert res.estimated_range.lower_bound < res.estimated_range.reference_close < res.estimated_range.upper_bound
    assert res.estimated_range.central_band_low < res.estimated_range.central_band_high

    assert res.walk_forward_metrics is not None
    wf = res.walk_forward_metrics
    assert wf.folds >= 2
    assert wf.evaluated_bars >= 20
    assert 0.0 <= wf.model_brier_score <= 2.0
    assert 0.0 <= wf.baseline_brier_score <= 2.0
    assert wf.model_log_loss > 0.0
    assert wf.baseline_log_loss > 0.0

    assert res.confidence_pct is not None and 15.0 <= res.confidence_pct <= 88.0
    assert res.confidence_level in {"LOW", "MODERATE", "HIGH"}
    assert len(res.driving_factors) >= 6
    assert res.feature_snapshot is not None


def test_live_probability_api_real_data_and_insufficient_guard():
    with TestClient(app) as client:
        # 1. Real Binance historical OHLCV run
        res = client.get("/api/v1/analysis/candle-probabilities?symbol=BTCUSDT&interval=1h&limit=360")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["status"] == "OK"
        assert data["is_guarantee"] is False
        assert data["look_ahead_bias_prevented"] is True
        assert data["walk_forward_metrics"]["evaluated_bars"] >= 20
        assert data["walk_forward_metrics"]["model_brier_score"] >= 0
        assert data["walk_forward_metrics"]["baseline_brier_score"] >= 0
        assert data["run_id"] is not None

        # 2. Insufficient data refusal on live API when limit=50
        res_short = client.get(
            "/api/v1/analysis/candle-probabilities?symbol=BTCUSDT&interval=1h&limit=50&persist=false"
        )
        assert res_short.status_code == 200
        short_data = res_short.json()
        assert short_data["status"] == "INSUFFICIENT_DATA"
        assert short_data["probabilities"] is None
        assert short_data["estimated_range"] is None

        # 3. Persisted history endpoint
        hist_res = client.get("/api/v1/analysis/candle-probabilities/history?limit=5")
        assert hist_res.status_code == 200
        hist = hist_res.json()
        assert len(hist) >= 1
        assert hist[0]["symbol"] == "BTCUSDT"
