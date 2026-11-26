from __future__ import annotations

from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from app.core.logging import get_logger
from app.db.database import get_db_connection
from app.engine.technical_engine import (
    _compute_adx_series,
    _compute_atr_series,
    _compute_rsi_series,
    filter_closed_candles,
)
from app.schemas.platform import (
    CandleProbabilityFactor,
    CandleProbabilityResponse,
    EstimatedPriceRange,
    FeatureSnapshotSummary,
    NextCandleProbabilities,
    ProbabilityForecastHistoryItem,
    WalkForwardValidationMetrics,
)
from app.services.market_service import fetch_market_klines
from app.services.quant_analysis_service import candles_to_df

logger = get_logger("qazan.probability")

MIN_REQUIRED_CLOSED_BARS = 140
MIN_LABELED_ROWS = 100

CLASS_DOWN = 0
CLASS_SIDEWAYS = 1
CLASS_UP = 2
CLASS_NAMES = {
    CLASS_DOWN: "DOWN",
    CLASS_SIDEWAYS: "SIDEWAYS",
    CLASS_UP: "UP",
}

FEATURE_SPEC: list[tuple[str, str, str]] = [
    ("ret_1", "OHLCV", "Last closed candle return"),
    ("ret_3", "OHLCV", "3-bar cumulative price momentum"),
    ("body_ratio", "OHLCV", "Candle body-to-range conviction ratio"),
    ("close_pos", "OHLCV", "Close location inside high-low range"),
    ("rsi_14", "RSI", "RSI(14) momentum oscillator"),
    ("rsi_slope_3", "RSI", "3-bar RSI(14) rate of change"),
    ("atr_pct", "ATR", "ATR(14) normalized volatility %"),
    ("atr_expansion", "ATR", "ATR(14) relative to 20-bar baseline"),
    ("vol_zscore", "VOLUME", "20-bar volume Z-score anomaly"),
    ("obv_slope_5", "VOLUME", "5-bar OBV accumulation/distribution slope"),
    ("vwap_dist_atr", "VWAP", "Close distance from 24-bar rolling VWAP (ATR units)"),
    ("structure_bias_num", "MARKET_STRUCTURE", "Causal BOS/CHoCH structural bias (+1 Bull / -1 Bear)"),
    ("swing_seq_score", "MARKET_STRUCTURE", "Latest causal HH/HL vs LH/LL pivot state"),
    ("liq_imbalance_atr", "LIQUIDITY", "Causal BSL vs SSL proximity & sweep pressure"),
    ("recent_sweep_dir", "LIQUIDITY", "Recent causal SSL (+1) vs BSL (-1) wick sweep"),
    ("fvg_net_balance", "FVG", "Active causal Bullish vs Bearish FVG imbalance"),
    ("in_fvg_signal", "FVG", "Price inside active unmitigated FVG (+1 Bull / -1 Bear)"),
    ("ema_spread_atr", "TREND", "EMA(20) - EMA(50) trend spread in ATR units"),
    ("adx_14", "TREND", "ADX(14) trend strength"),
]

PROB_FEATURE_COLS = [item[0] for item in FEATURE_SPEC]


def _align_proba(model_classes: np.ndarray, raw_probs: np.ndarray) -> np.ndarray:
    """Map model output columns safely onto [CLASS_DOWN=0, CLASS_SIDEWAYS=1, CLASS_UP=2]."""
    aligned = np.full((raw_probs.shape[0], 3), 1e-4, dtype=np.float64)
    for col_idx, cls_val in enumerate(model_classes):
        c_int = int(cls_val)
        if 0 <= c_int <= 2:
            aligned[:, c_int] = raw_probs[:, col_idx]
    row_sums = aligned.sum(axis=1, keepdims=True)
    return aligned / np.maximum(row_sums, 1e-12)


def _multiclass_brier_and_logloss(y_true: np.ndarray, probs: np.ndarray) -> tuple[float, float]:
    n = len(y_true)
    if n == 0:
        return 0.0, 0.0
    clipped = np.clip(probs, 1e-6, 1.0)
    clipped = clipped / clipped.sum(axis=1, keepdims=True)
    one_hot = np.zeros((n, 3), dtype=np.float64)
    one_hot[np.arange(n), y_true] = 1.0
    brier = float(np.mean(np.sum((clipped - one_hot) ** 2, axis=1)))
    log_loss = float(-np.mean(np.log(clipped[np.arange(n), y_true])))
    return brier, log_loss


def build_causal_probability_features(
    df: pd.DataFrame,
    timeframe: str = "1h",
    as_of_ts: int | None = None,
) -> tuple[pd.DataFrame, bool]:
    """
    Build strictly causal features from closed bars <= t across all 9 domains:
    OHLCV, RSI, ATR, Volume, VWAP, Market Structure, Liquidity, FVG, Trend.
    Zero future leakage guaranteed.
    """
    closed_df, unclosed_excluded = filter_closed_candles(df, timeframe=timeframe, as_of_ts=as_of_ts)
    work = closed_df.reset_index(drop=True).copy()
    n = len(work)
    if n == 0:
        return work, unclosed_excluded

    opens = work["open"].to_numpy(dtype=np.float64)
    highs = work["high"].to_numpy(dtype=np.float64)
    lows = work["low"].to_numpy(dtype=np.float64)
    closes = work["close"].to_numpy(dtype=np.float64)
    volumes = work["volume"].to_numpy(dtype=np.float64)

    atr_arr = _compute_atr_series(work, 14)
    rsi_arr = _compute_rsi_series(work["close"], 14)
    adx_arr = _compute_adx_series(work, 14)

    ema20 = work["close"].ewm(span=20, adjust=False).mean().to_numpy(dtype=np.float64)
    ema50 = work["close"].ewm(span=50, adjust=False).mean().to_numpy(dtype=np.float64)

    # 1. OHLCV causal metrics
    bar_range = np.maximum(highs - lows, closes * 1e-6)
    work["ret_1"] = work["close"].pct_change(1)
    work["ret_3"] = work["close"].pct_change(3)
    work["body_ratio"] = (closes - opens) / bar_range
    work["close_pos"] = (closes - lows) / bar_range

    # 2. RSI causal metrics
    work["rsi_14"] = rsi_arr
    work["rsi_slope_3"] = pd.Series(rsi_arr).diff(3).fillna(0.0).to_numpy()

    # 3. ATR causal metrics
    safe_atr = np.maximum(atr_arr, closes * 1e-4)
    atr_sma20 = pd.Series(safe_atr).rolling(20, min_periods=5).mean().bfill().to_numpy()
    work["atr_14"] = safe_atr
    work["atr_pct"] = safe_atr / np.maximum(closes, 1e-8)
    work["atr_expansion"] = safe_atr / np.maximum(atr_sma20, 1e-8)

    # 4. Volume & OBV causal metrics
    vol_mean = pd.Series(volumes).rolling(20, min_periods=5).mean()
    vol_std = pd.Series(volumes).rolling(20, min_periods=5).std().replace(0.0, np.nan)
    work["vol_zscore"] = ((pd.Series(volumes) - vol_mean) / vol_std).fillna(0.0).to_numpy()
    work["vol_ratio_20"] = (pd.Series(volumes) / vol_mean.replace(0.0, np.nan)).fillna(1.0).to_numpy()

    direction_sign = np.sign(pd.Series(closes).diff().fillna(0.0).to_numpy())
    obv = np.cumsum(direction_sign * volumes)
    obv_delta_5 = pd.Series(obv).diff(5).fillna(0.0).to_numpy()
    obv_scale = pd.Series(volumes).rolling(20, min_periods=5).sum().bfill().to_numpy()
    work["obv_slope_5"] = obv_delta_5 / np.maximum(obv_scale, 1e-8)

    # 5. Rolling Session VWAP (24 bars)
    typical = (highs + lows + closes) / 3.0
    tp_vol = pd.Series(typical * volumes).rolling(24, min_periods=1).sum()
    vol_24 = pd.Series(volumes).rolling(24, min_periods=1).sum().replace(0.0, np.nan)
    vwap_arr = (tp_vol / vol_24).fillna(pd.Series(closes)).to_numpy(dtype=np.float64)
    work["vwap"] = vwap_arr
    work["vwap_dist_atr"] = (closes - vwap_arr) / safe_atr

    # 6. Trend metrics
    work["ema_spread_atr"] = (ema20 - ema50) / safe_atr
    work["adx_14"] = adx_arr

    # 7, 8, 9: Strictly Causal Market Structure, Liquidity & FVG loop (t = 0 .. n-1)
    swing_left = 3
    swing_right = 3
    structure_bias_arr = np.zeros(n, dtype=np.float64)
    swing_seq_arr = np.zeros(n, dtype=np.float64)
    liq_imbalance_arr = np.zeros(n, dtype=np.float64)
    recent_sweep_arr = np.zeros(n, dtype=np.float64)
    fvg_net_arr = np.zeros(n, dtype=np.float64)
    in_fvg_arr = np.zeros(n, dtype=np.float64)

    last_sh_price: float | None = None
    last_sl_price: float | None = None
    active_sh: float | None = None
    active_sl: float | None = None
    sh_pool: list[dict] = []
    sl_pool: list[dict] = []
    fvgs: list[dict] = []

    curr_bias = 0.0
    curr_swing_score = 0.0
    last_sweep_bar = -999
    last_sweep_dir = 0.0

    for t in range(n):
        h = float(highs[t])
        l = float(lows[t])
        c = float(closes[t])
        atr_t = float(safe_atr[t])

        # Causal pivot confirmation at t = p + swing_right
        p = t - swing_right
        if p >= swing_left:
            if highs[p] > np.max(highs[p - swing_left : p]) and highs[p] >= np.max(highs[p + 1 : t + 1]):
                p_val = float(highs[p])
                curr_swing_score = 1.0 if (last_sh_price is None or p_val >= last_sh_price) else -1.0
                last_sh_price = p_val
                active_sh = p_val
                sh_pool.append({"price": p_val, "swept": False})
            if lows[p] < np.min(lows[p - swing_left : p]) and lows[p] <= np.min(lows[p + 1 : t + 1]):
                p_val = float(lows[p])
                curr_swing_score = 1.0 if (last_sl_price is None or p_val >= last_sl_price) else -1.0
                last_sl_price = p_val
                active_sl = p_val
                sl_pool.append({"price": p_val, "swept": False})

        # Causal sweeps & breaks on current closed bar t
        for pool_item in sh_pool[-12:]:
            if not pool_item["swept"]:
                if h > pool_item["price"] and c <= pool_item["price"]:
                    pool_item["swept"] = True
                    last_sweep_bar = t
                    last_sweep_dir = -1.0  # BSL swept -> bearish sweep signal
                elif c > pool_item["price"]:
                    pool_item["swept"] = True

        for pool_item in sl_pool[-12:]:
            if not pool_item["swept"]:
                if l < pool_item["price"] and c >= pool_item["price"]:
                    pool_item["swept"] = True
                    last_sweep_bar = t
                    last_sweep_dir = 1.0  # SSL swept -> bullish sweep signal
                elif c < pool_item["price"]:
                    pool_item["swept"] = True

        if active_sh is not None and c > active_sh:
            curr_bias = 1.0
            active_sh = None
        elif active_sl is not None and c < active_sl:
            curr_bias = -1.0
            active_sl = None

        # Causal FVG mitigation & detection
        for fg in fvgs:
            if fg["mitigated"]:
                continue
            if fg["dir"] == 1 and l <= fg["bottom"]:
                fg["mitigated"] = True
            elif fg["dir"] == -1 and h >= fg["top"]:
                fg["mitigated"] = True

        if t >= 2:
            if lows[t] > highs[t - 2]:
                fvgs.append({"dir": 1, "bottom": float(highs[t - 2]), "top": float(lows[t]), "mitigated": False})
            elif highs[t] < lows[t - 2]:
                fvgs.append({"dir": -1, "bottom": float(highs[t]), "top": float(lows[t - 2]), "mitigated": False})

        # Liquidity distance imbalance: closer SSL below vs closer BSL above
        untapped_bsl = [x["price"] for x in sh_pool[-15:] if not x["swept"] and x["price"] > c]
        untapped_ssl = [x["price"] for x in sl_pool[-15:] if not x["swept"] and x["price"] < c]
        bsl_dist = ((min(untapped_bsl) - c) / atr_t) if untapped_bsl else 3.0
        ssl_dist = ((c - max(untapped_ssl)) / atr_t) if untapped_ssl else 3.0
        liq_imbalance_arr[t] = float(np.clip(ssl_dist - bsl_dist, -4.0, 4.0))

        recent_sweep_arr[t] = last_sweep_dir if (t - last_sweep_bar) <= 3 else 0.0
        structure_bias_arr[t] = curr_bias
        swing_seq_arr[t] = curr_swing_score

        active_fvgs = [fg for fg in fvgs[-25:] if not fg["mitigated"]]
        bull_cnt = sum(1 for fg in active_fvgs if fg["dir"] == 1)
        bear_cnt = sum(1 for fg in active_fvgs if fg["dir"] == -1)
        fvg_net_arr[t] = float(np.clip(bull_cnt - bear_cnt, -5, 5))

        in_sig = 0.0
        for fg in active_fvgs:
            if fg["bottom"] <= c <= fg["top"]:
                in_sig = float(fg["dir"])
                break
        in_fvg_arr[t] = in_sig

    work["structure_bias_num"] = structure_bias_arr
    work["swing_seq_score"] = swing_seq_arr
    work["liq_imbalance_atr"] = liq_imbalance_arr
    work["recent_sweep_dir"] = recent_sweep_arr
    work["fvg_net_balance"] = fvg_net_arr
    work["in_fvg_signal"] = in_fvg_arr

    # Next-candle realized return & volatility-scaled 3-state label (for past closed bars only!)
    work["next_ret"] = work["close"].pct_change(1).shift(-1)
    work["next_high_atr"] = (work["high"].shift(-1) - work["close"]) / safe_atr
    work["next_low_atr"] = (work["low"].shift(-1) - work["close"]) / safe_atr
    work["sideways_thresh"] = np.maximum(0.25 * work["atr_pct"], 0.0005)

    y_class = np.full(n, np.nan)
    for t in range(n - 1):
        nr = work["next_ret"].iloc[t]
        th = work["sideways_thresh"].iloc[t]
        if pd.isna(nr):
            continue
        if nr > th:
            y_class[t] = CLASS_UP
        elif nr < -th:
            y_class[t] = CLASS_DOWN
        else:
            y_class[t] = CLASS_SIDEWAYS

    work["target_class"] = y_class
    work["prev_class"] = pd.Series(y_class).shift(1)
    return work, unclosed_excluded


def _fit_and_predict_fold(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
) -> tuple[np.ndarray, LogisticRegression, np.ndarray]:
    """Train regularized multi-class probability ensemble strictly on past fold."""
    lr = LogisticRegression(C=0.12, max_iter=600, random_state=42)
    pipe = Pipeline([("scaler", StandardScaler()), ("lr", lr)])
    rf = RandomForestClassifier(
        n_estimators=120,
        max_depth=3,
        min_samples_leaf=12,
        random_state=42,
        n_jobs=1,
    )

    pipe.fit(X_train, y_train)
    rf.fit(X_train, y_train)

    p_lr = _align_proba(pipe.named_steps["lr"].classes_, pipe.predict_proba(X_test))
    p_rf = _align_proba(rf.classes_, rf.predict_proba(X_test))

    unique_classes = np.unique(y_train)
    if len(unique_classes) == 3 and set(unique_classes.tolist()) == {0, 1, 2}:
        xgb = XGBClassifier(
            n_estimators=70,
            max_depth=2,
            learning_rate=0.03,
            reg_lambda=10.0,
            subsample=0.80,
            colsample_bytree=0.80,
            min_child_weight=8,
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=1,
        )
        xgb.fit(X_train, y_train)
        p_xgb = _align_proba(xgb.classes_, xgb.predict_proba(X_test))
        blended = 0.40 * p_lr + 0.30 * p_rf + 0.30 * p_xgb
        importances = 0.5 * rf.feature_importances_ + 0.5 * xgb.feature_importances_
    else:
        blended = 0.55 * p_lr + 0.45 * p_rf
        importances = rf.feature_importances_

    blended = blended / np.maximum(blended.sum(axis=1, keepdims=True), 1e-12)
    return blended, pipe.named_steps["lr"], importances


def _calibrate_shrinkage_weight(
    X_train: np.ndarray,
    y_train: np.ndarray,
    prev_train: np.ndarray,
) -> float:
    """
    Strictly causal inner temporal check on the training fold to choose optimal
    Bayesian shrinkage weight between ML ensemble and statistical baseline.
    """
    if len(y_train) < 70:
        return 0.35
    cut = int(len(y_train) * 0.72)
    if len(np.unique(y_train[:cut])) < 2 or len(y_train[cut:]) < 15:
        return 0.35
    p_ml_val, _, _ = _fit_and_predict_fold(X_train[:cut], y_train[:cut], X_train[cut:])
    p_base_val = _baseline_markov_prior_probs(y_train[:cut], prev_train[cut:])
    y_val = y_train[cut:]

    best_w = 0.25
    best_ll = float("inf")
    for w in (0.15, 0.25, 0.40, 0.60, 0.75):
        cand = w * p_ml_val + (1.0 - w) * p_base_val
        _, ll = _multiclass_brier_and_logloss(y_val, cand)
        if ll < best_ll:
            best_ll = ll
            best_w = w
    return best_w


def _baseline_markov_prior_probs(
    y_train: np.ndarray,
    prev_classes_test: np.ndarray,
    alpha: float = 2.0,
) -> np.ndarray:
    """
    Strictly causal statistical baseline:
    Blends Laplace-smoothed empirical class priors and 1-step Markov state transitions
    learned solely on the training fold.
    """
    counts = np.bincount(y_train.astype(int), minlength=3).astype(np.float64) + alpha
    prior = counts / counts.sum()

    trans = np.full((3, 3), alpha, dtype=np.float64)
    for idx in range(1, len(y_train)):
        prev_c = int(y_train[idx - 1])
        curr_c = int(y_train[idx])
        trans[prev_c, curr_c] += 1.0
    trans = trans / trans.sum(axis=1, keepdims=True)

    out = np.zeros((len(prev_classes_test), 3), dtype=np.float64)
    for i, prev_val in enumerate(prev_classes_test):
        if np.isnan(prev_val):
            out[i] = prior
        else:
            p_idx = int(prev_val)
            out[i] = 0.60 * trans[p_idx] + 0.40 * prior
    out = out / np.maximum(out.sum(axis=1, keepdims=True), 1e-12)
    return out


def _persist_probability_forecast(resp: CandleProbabilityResponse) -> int | None:
    try:
        with get_db_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO probability_forecasts
                    (symbol, interval, status, prob_up, prob_down, prob_sideways, confidence_pct,
                     model_brier_score, baseline_brier_score, model_log_loss, baseline_log_loss,
                     payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resp.symbol,
                    resp.interval,
                    resp.status,
                    resp.probabilities.up_pct if resp.probabilities else None,
                    resp.probabilities.down_pct if resp.probabilities else None,
                    resp.probabilities.sideways_pct if resp.probabilities else None,
                    resp.confidence_pct,
                    resp.walk_forward_metrics.model_brier_score if resp.walk_forward_metrics else None,
                    resp.walk_forward_metrics.baseline_brier_score if resp.walk_forward_metrics else None,
                    resp.walk_forward_metrics.model_log_loss if resp.walk_forward_metrics else None,
                    resp.walk_forward_metrics.baseline_log_loss if resp.walk_forward_metrics else None,
                    resp.model_dump_json(),
                    resp.analyzed_at,
                ),
            )
            return int(cur.lastrowid) if cur.lastrowid else None
    except Exception as exc:
        logger.warning("Failed to persist probability forecast: %s", exc)
        return None


def get_probability_forecast_history(limit: int = 10) -> list[ProbabilityForecastHistoryItem]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, interval, status, prob_up, prob_down, prob_sideways, confidence_pct,
                   model_brier_score, baseline_brier_score, model_log_loss, baseline_log_loss, created_at
            FROM probability_forecasts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [ProbabilityForecastHistoryItem(**dict(r)) for r in rows]


def estimate_next_candle_probabilities_on_df(
    df: pd.DataFrame,
    symbol: str,
    interval: str = "1h",
    as_of_ts: int | None = None,
    persist: bool = False,
) -> CandleProbabilityResponse:
    """
    Core strictly causal Walk-Forward statistical + ML probability estimator.
    Never predicts an exact future close; outputs calibrated UP/DOWN/SIDEWAYS probabilities,
    ATR-quantile price range, Walk-Forward Brier Score & Log Loss vs causal baseline,
    driving factors across all 9 domains, and strict INSUFFICIENT_DATA refusal.
    """
    analyzed_at = datetime.now(timezone.utc).isoformat()
    disclaimer = (
        "Statistical probability estimates and estimated ranges are derived solely from historical closed candles; "
        "they are NOT guarantees and the exact closing price of the next candle cannot be known."
    )

    feat_df, unclosed_excluded = build_causal_probability_features(df, timeframe=interval, as_of_ts=as_of_ts)
    closed_bars = len(feat_df)

    if closed_bars < MIN_REQUIRED_CLOSED_BARS:
        resp = CandleProbabilityResponse(
            symbol=symbol.upper(),
            interval=interval.lower(),
            status="INSUFFICIENT_DATA",
            insufficient_reason=(
                f"Only {closed_bars} closed candles available; minimum {MIN_REQUIRED_CLOSED_BARS} closed candles "
                "are required for Walk-Forward validation and calibrated probability estimation."
            ),
            closed_bars_analyzed=closed_bars,
            minimum_required_bars=MIN_REQUIRED_CLOSED_BARS,
            unclosed_bar_excluded=unclosed_excluded,
            disclaimer=disclaimer,
            analyzed_at=analyzed_at,
        )
        if persist:
            resp.run_id = _persist_probability_forecast(resp)
        return resp

    # Prepare strictly labeled historical rows (excluding the final live bar n-1 whose next bar isn't realized)
    historical = feat_df.iloc[:-1].copy()
    trainable = historical.dropna(subset=PROB_FEATURE_COLS + ["target_class", "prev_class"]).reset_index(drop=True)

    if len(trainable) < MIN_LABELED_ROWS or len(trainable["target_class"].unique()) < 2:
        resp = CandleProbabilityResponse(
            symbol=symbol.upper(),
            interval=interval.lower(),
            status="INSUFFICIENT_DATA",
            insufficient_reason=(
                f"Insufficient labeled samples ({len(trainable)} valid rows, minimum {MIN_LABELED_ROWS}) "
                "or degenerate single-class price series; refusing to emit synthetic probabilities."
            ),
            closed_bars_analyzed=closed_bars,
            minimum_required_bars=MIN_REQUIRED_CLOSED_BARS,
            unclosed_bar_excluded=unclosed_excluded,
            disclaimer=disclaimer,
            analyzed_at=analyzed_at,
        )
        if persist:
            resp.run_id = _persist_probability_forecast(resp)
        return resp

    X_all = trainable[PROB_FEATURE_COLS].to_numpy(dtype=np.float64)
    y_all = trainable["target_class"].to_numpy(dtype=np.int64)
    prev_all = trainable["prev_class"].to_numpy(dtype=np.float64)

    # Expanding Walk-Forward Validation
    n_train_total = len(trainable)
    init_train = max(60, int(n_train_total * 0.55))
    oos_span = n_train_total - init_train
    if oos_span < 20:
        resp = CandleProbabilityResponse(
            symbol=symbol.upper(),
            interval=interval.lower(),
            status="INSUFFICIENT_DATA",
            insufficient_reason="Insufficient out-of-sample Walk-Forward span (< 20 bars).",
            closed_bars_analyzed=closed_bars,
            minimum_required_bars=MIN_REQUIRED_CLOSED_BARS,
            unclosed_bar_excluded=unclosed_excluded,
            disclaimer=disclaimer,
            analyzed_at=analyzed_at,
        )
        if persist:
            resp.run_id = _persist_probability_forecast(resp)
        return resp

    step = max(8, oos_span // 5)
    oos_y_true: list[int] = []
    oos_model_probs: list[np.ndarray] = []
    oos_base_probs: list[np.ndarray] = []
    folds = 0

    for fold_start in range(init_train, n_train_total, step):
        fold_end = min(fold_start + step, n_train_total)
        X_tr, y_tr = X_all[:fold_start], y_all[:fold_start]
        prev_tr = prev_all[:fold_start]
        X_te, y_te = X_all[fold_start:fold_end], y_all[fold_start:fold_end]
        prev_te = prev_all[fold_start:fold_end]

        if len(np.unique(y_tr)) < 2:
            continue

        w_ml = _calibrate_shrinkage_weight(X_tr, y_tr, prev_tr)
        raw_ml_p, _, _ = _fit_and_predict_fold(X_tr, y_tr, X_te)
        fold_base_p = _baseline_markov_prior_probs(y_tr, prev_te)
        fold_model_p = w_ml * raw_ml_p + (1.0 - w_ml) * fold_base_p
        fold_model_p = fold_model_p / np.maximum(fold_model_p.sum(axis=1, keepdims=True), 1e-12)

        oos_y_true.extend(y_te.tolist())
        oos_model_probs.append(fold_model_p)
        oos_base_probs.append(fold_base_p)
        folds += 1

    if not oos_y_true:
        resp = CandleProbabilityResponse(
            symbol=symbol.upper(),
            interval=interval.lower(),
            status="INSUFFICIENT_DATA",
            insufficient_reason="Walk-Forward validation produced zero valid folds.",
            closed_bars_analyzed=closed_bars,
            minimum_required_bars=MIN_REQUIRED_CLOSED_BARS,
            unclosed_bar_excluded=unclosed_excluded,
            disclaimer=disclaimer,
            analyzed_at=analyzed_at,
        )
        if persist:
            resp.run_id = _persist_probability_forecast(resp)
        return resp

    y_eval = np.array(oos_y_true, dtype=np.int64)
    p_model_eval = np.vstack(oos_model_probs)
    p_base_eval = np.vstack(oos_base_probs)

    m_brier, m_ll = _multiclass_brier_and_logloss(y_eval, p_model_eval)
    b_brier, b_ll = _multiclass_brier_and_logloss(y_eval, p_base_eval)

    brier_skill = ((b_brier - m_brier) / max(b_brier, 1e-8)) * 100.0
    ll_skill = ((b_ll - m_ll) / max(b_ll, 1e-8)) * 100.0
    m_acc = float(np.mean(np.argmax(p_model_eval, axis=1) == y_eval)) * 100.0
    b_acc = float(np.mean(np.argmax(p_base_eval, axis=1) == y_eval)) * 100.0

    wf_metrics = WalkForwardValidationMetrics(
        folds=folds,
        evaluated_bars=len(y_eval),
        model_brier_score=round(m_brier, 4),
        baseline_brier_score=round(b_brier, 4),
        brier_skill_vs_baseline_pct=round(brier_skill, 2),
        model_log_loss=round(m_ll, 4),
        baseline_log_loss=round(b_ll, 4),
        log_loss_skill_vs_baseline_pct=round(ll_skill, 2),
        model_accuracy_pct=round(m_acc, 2),
        baseline_accuracy_pct=round(b_acc, 2),
        outperforms_baseline=(m_brier <= b_brier and m_ll <= b_ll),
    )

    # Final causal model fit on ALL closed labeled rows (0 .. n-2) -> predict probabilities on live bar n-1
    live_row = feat_df.iloc[-1:]
    X_live = live_row[PROB_FEATURE_COLS].fillna(0.0).to_numpy(dtype=np.float64)
    w_live = _calibrate_shrinkage_weight(X_all, y_all, prev_all)
    raw_live_probs, lr_model, feat_importances = _fit_and_predict_fold(X_all, y_all, X_live)
    live_base_probs = _baseline_markov_prior_probs(y_all, live_row["prev_class"].to_numpy(dtype=np.float64))
    live_probs = w_live * raw_live_probs + (1.0 - w_live) * live_base_probs
    live_probs = live_probs / np.maximum(live_probs.sum(axis=1, keepdims=True), 1e-12)
    p_down, p_sideways, p_up = float(live_probs[0, 0]), float(live_probs[0, 1]), float(live_probs[0, 2])

    # Normalize cleanly to exact 100.00% sum
    up_pct = round(p_up * 100.0, 2)
    down_pct = round(p_down * 100.0, 2)
    sideways_pct = round(max(0.0, 100.0 - up_pct - down_pct), 2)

    dom_idx = int(np.argmax([p_down, p_sideways, p_up]))
    dominant_outcome = CLASS_NAMES[dom_idx]

    # Confidence from Shannon entropy reduction + Walk-Forward calibration skill (capped realistically)
    probs_vec = np.clip(np.array([p_down, p_sideways, p_up]), 1e-6, 1.0)
    entropy = float(-np.sum(probs_vec * np.log(probs_vec)))
    entropy_certainty = max(0.0, 1.0 - entropy / np.log(3.0))
    raw_conf = 28.0 + entropy_certainty * 52.0 + float(np.clip(brier_skill, -15.0, 15.0)) * 0.5
    confidence_pct = round(float(np.clip(raw_conf, 15.0, 88.0)), 2)
    confidence_level = "HIGH" if confidence_pct >= 62.0 else "MODERATE" if confidence_pct >= 42.0 else "LOW"

    # Estimated Price Range from empirical historical ATR excursions (NEVER claiming exact close price)
    last_bar = feat_df.iloc[-1]
    ref_close = float(last_bar["close"])
    atr_14 = float(last_bar["atr_14"])
    sw_thresh_pct = float(last_bar["sideways_thresh"]) * 100.0

    hist_high_atrs = trainable["next_high_atr"].dropna().to_numpy(dtype=np.float64)
    hist_low_atrs = trainable["next_low_atr"].dropna().to_numpy(dtype=np.float64)
    q_up_outer = float(np.quantile(hist_high_atrs, 0.85)) if len(hist_high_atrs) else 1.15
    q_low_outer = float(np.quantile(hist_low_atrs, 0.15)) if len(hist_low_atrs) else -1.15

    # Shift probability asymmetry subtly inside empirical ATR envelope without pretending point forecast
    directional_tilt = (p_up - p_down) * 0.25 * atr_14
    lower_bound = max(1e-8, ref_close + min(q_low_outer, -0.35) * atr_14 + directional_tilt * 0.4)
    upper_bound = max(lower_bound * 1.0002, ref_close + max(q_up_outer, 0.35) * atr_14 + directional_tilt * 0.4)
    central_low = ref_close * (1.0 - sw_thresh_pct / 100.0)
    central_high = ref_close * (1.0 + sw_thresh_pct / 100.0)
    width_pct = ((upper_bound - lower_bound) / max(ref_close, 1e-8)) * 100.0

    est_range = EstimatedPriceRange(
        reference_close=round(ref_close, 6),
        lower_bound=round(lower_bound, 6),
        upper_bound=round(upper_bound, 6),
        central_band_low=round(central_low, 6),
        central_band_high=round(central_high, 6),
        atr_14=round(atr_14, 6),
        sideways_threshold_pct=round(sw_thresh_pct, 3),
        estimated_range_width_pct=round(width_pct, 3),
        note=(
            "15th–85th percentile empirical ATR volatility envelope anchored at last closed price "
            "(central band marks the sideways consolidation threshold)."
        ),
    )

    # Compute transparent driving factors across all 9 domains
    means = np.mean(X_all, axis=0)
    stds = np.maximum(np.std(X_all, axis=0), 1e-6)
    z_live = (X_live[0] - means) / stds

    # Map logistic regression net bullish-vs-bearish directional sensitivity per feature
    lr_classes = lr_model.classes_.tolist()
    up_row = lr_model.coef_[lr_classes.index(CLASS_UP)] if CLASS_UP in lr_classes else np.zeros(len(PROB_FEATURE_COLS))
    down_row = (
        lr_model.coef_[lr_classes.index(CLASS_DOWN)] if CLASS_DOWN in lr_classes else np.zeros(len(PROB_FEATURE_COLS))
    )
    sw_row = (
        lr_model.coef_[lr_classes.index(CLASS_SIDEWAYS)]
        if CLASS_SIDEWAYS in lr_classes
        else np.zeros(len(PROB_FEATURE_COLS))
    )

    total_imp = max(float(np.sum(feat_importances)), 1e-8)
    raw_factors: list[CandleProbabilityFactor] = []
    for idx, (feat_name, domain, desc) in enumerate(FEATURE_SPEC):
        val = float(X_live[0, idx])
        z_v = float(np.clip(z_live[idx], -3.0, 3.0))
        score_up = float(up_row[idx] * z_v)
        score_down = float(down_row[idx] * z_v)
        score_sw = float(sw_row[idx] * z_v)

        best_score = max(score_up, score_down, score_sw)
        if abs(score_up - score_down) < 0.03 and score_sw < best_score:
            dir_eff = "NEUTRAL"
        elif best_score == score_up and score_up > 0.02:
            dir_eff = "UP"
        elif best_score == score_down and score_down > 0.02:
            dir_eff = "DOWN"
        elif best_score == score_sw and score_sw > 0.02:
            dir_eff = "SIDEWAYS"
        else:
            dir_eff = "NEUTRAL"

        weight = round((float(feat_importances[idx]) / total_imp) * 100.0, 2)
        raw_factors.append(
            CandleProbabilityFactor(
                domain=domain,
                feature=feat_name,
                current_value=round(val, 4),
                direction_effect=dir_eff,
                weight_pct=weight,
                explanation=desc,
            )
        )

    # Sort by importance weight while ensuring top representative factors across domains
    driving_factors = sorted(raw_factors, key=lambda x: x.weight_pct, reverse=True)[:12]

    struct_num = float(last_bar["structure_bias_num"])
    liq_sweep_num = float(last_bar["recent_sweep_dir"])
    in_fvg_num = float(last_bar["in_fvg_signal"])
    fvg_bal = float(last_bar["fvg_net_balance"])
    ema_sp = float(last_bar["ema_spread_atr"])
    adx_val = float(last_bar["adx_14"])

    snapshot = FeatureSnapshotSummary(
        close=round(ref_close, 6),
        rsi_14=round(float(last_bar["rsi_14"]), 2),
        atr_14=round(atr_14, 6),
        atr_pct=round(float(last_bar["atr_pct"]) * 100.0, 3),
        volume_ratio_20=round(float(last_bar["vol_ratio_20"]), 2),
        vwap=round(float(last_bar["vwap"]), 6),
        vwap_distance_atr=round(float(last_bar["vwap_dist_atr"]), 2),
        structure_bias="BULLISH" if struct_num > 0 else "BEARISH" if struct_num < 0 else "NEUTRAL",
        liquidity_bias=(
            "SSL_SWEPT_BULLISH"
            if liq_sweep_num > 0
            else "BSL_SWEPT_BEARISH"
            if liq_sweep_num < 0
            else ("BSL_CLOSER" if float(last_bar["liq_imbalance_atr"]) > 0.25 else "BALANCED")
        ),
        fvg_context=(
            "INSIDE_BULLISH_FVG"
            if in_fvg_num > 0
            else "INSIDE_BEARISH_FVG"
            if in_fvg_num < 0
            else f"NET_ACTIVE_{int(fvg_bal):+d}"
        ),
        trend_regime=(
            "STRONG_UPTREND"
            if ema_sp > 0.3 and adx_val >= 20
            else "STRONG_DOWNTREND"
            if ema_sp < -0.3 and adx_val >= 20
            else "RANGE_TRANSITION"
        ),
    )

    resp = CandleProbabilityResponse(
        symbol=symbol.upper(),
        interval=interval.lower(),
        status="OK",
        closed_bars_analyzed=closed_bars,
        minimum_required_bars=MIN_REQUIRED_CLOSED_BARS,
        unclosed_bar_excluded=unclosed_excluded,
        disclaimer=disclaimer,
        probabilities=NextCandleProbabilities(
            up_pct=up_pct,
            down_pct=down_pct,
            sideways_pct=sideways_pct,
            dominant_outcome=dominant_outcome,
        ),
        estimated_range=est_range,
        confidence_pct=confidence_pct,
        confidence_level=confidence_level,
        walk_forward_metrics=wf_metrics,
        driving_factors=driving_factors,
        feature_snapshot=snapshot,
        analyzed_at=analyzed_at,
    )
    if persist:
        resp.run_id = _persist_probability_forecast(resp)
    return resp


async def run_next_candle_probability_engine(
    symbol: str,
    interval: str = "1h",
    limit: int = 360,
    persist: bool = True,
) -> CandleProbabilityResponse:
    safe_limit = max(30, min(500, limit))
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=safe_limit)
    raw_df = candles_to_df(klines.candles)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return estimate_next_candle_probabilities_on_df(
        raw_df,
        symbol=klines.symbol,
        interval=klines.interval,
        as_of_ts=now_ts,
        persist=persist,
    )
