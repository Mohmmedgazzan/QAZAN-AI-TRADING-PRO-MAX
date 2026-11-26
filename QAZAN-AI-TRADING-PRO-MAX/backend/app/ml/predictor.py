from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.metrics import accuracy_score, mean_absolute_error, root_mean_squared_error
from xgboost import XGBClassifier, XGBRegressor

from app.schemas.platform import (
    AIAnalysisResponse,
    CandlePredictionResponse,
    FeatureImportance,
)
from app.services.market_service import fetch_market_klines
from app.services.quant_analysis_service import candles_to_df, compute_atr, compute_rsi


FEATURE_COLS = [
    "ret_1",
    "ret_3",
    "ret_6",
    "rsi_14",
    "macd_hist",
    "atr_pct",
    "bb_pos",
    "ema_spread",
    "vol_zscore",
]


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["ret_1"] = work["close"].pct_change(1)
    work["ret_3"] = work["close"].pct_change(3)
    work["ret_6"] = work["close"].pct_change(6)
    work["rsi_14"] = compute_rsi(work["close"], 14)

    ema12 = work["close"].ewm(span=12, adjust=False).mean()
    ema26 = work["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    work["macd_hist"] = (macd - macd_signal) / work["close"].replace(0.0, np.nan)

    atr14 = compute_atr(work, 14)
    work["atr_pct"] = atr14 / work["close"].replace(0.0, np.nan)

    sma20 = work["close"].rolling(20).mean()
    std20 = work["close"].rolling(20).std().replace(0.0, np.nan)
    work["bb_pos"] = (work["close"] - (sma20 - 2 * std20)) / (4 * std20)

    ema20 = work["close"].ewm(span=20, adjust=False).mean()
    ema50 = work["close"].ewm(span=50, adjust=False).mean()
    work["ema_spread"] = (ema20 - ema50) / work["close"].replace(0.0, np.nan)

    vol_mean = work["volume"].rolling(20).mean()
    vol_std = work["volume"].rolling(20).std().replace(0.0, np.nan)
    work["vol_zscore"] = (work["volume"] - vol_mean) / vol_std

    work["next_ret"] = work["close"].pct_change(1).shift(-1)
    work["next_high_pct"] = (work["high"].shift(-1) - work["close"]) / work["close"]
    work["next_low_pct"] = (work["low"].shift(-1) - work["close"]) / work["close"]
    work["target_up"] = (work["next_ret"] > 0).astype(int)
    return work


async def run_ai_market_analysis(symbol: str, interval: str = "1h") -> AIAnalysisResponse:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=300)
    raw_df = candles_to_df(klines.candles)
    feat_df = _build_features(raw_df)

    latest_row = feat_df[FEATURE_COLS].iloc[-1:].ffill().fillna(0.0)
    trainable = feat_df.dropna(subset=FEATURE_COLS + ["target_up", "next_ret"]).reset_index(drop=True)

    X = trainable[FEATURE_COLS].to_numpy(dtype=np.float64)
    y = trainable["target_up"].to_numpy(dtype=np.int64)

    split_idx = int(len(trainable) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    rf = RandomForestClassifier(
        n_estimators=120,
        max_depth=5,
        random_state=42,
        n_jobs=1,
    )
    xgb = XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        eval_metric="logloss",
        random_state=42,
        n_jobs=1,
    )

    rf.fit(X_train, y_train)
    xgb.fit(X_train, y_train)

    rf_preds = rf.predict(X_test)
    xgb_preds = xgb.predict(X_test)
    rf_probs_test = rf.predict_proba(X_test)[:, 1]
    xgb_probs_test = xgb.predict_proba(X_test)[:, 1]
    ens_probs_test = (rf_probs_test + xgb_probs_test) / 2.0
    ens_preds = (ens_probs_test >= 0.5).astype(int)

    rf_acc = round(float(accuracy_score(y_test, rf_preds)) * 100.0, 2)
    xgb_acc = round(float(accuracy_score(y_test, xgb_preds)) * 100.0, 2)
    ens_acc = round(float(accuracy_score(y_test, ens_preds)) * 100.0, 2)

    X_live = latest_row.to_numpy(dtype=np.float64)
    live_prob_up = float((rf.predict_proba(X_live)[0, 1] + xgb.predict_proba(X_live)[0, 1]) / 2.0)
    live_prob_down = 1.0 - live_prob_up

    signal = "BULLISH" if live_prob_up >= 0.5 else "BEARISH"
    confidence = round(max(live_prob_up, live_prob_down) * 100.0, 2)

    importances = (rf.feature_importances_ + xgb.feature_importances_) / 2.0
    top_features = [
        FeatureImportance(feature=name, importance=round(float(imp), 4))
        for name, imp in sorted(
            zip(FEATURE_COLS, importances), key=lambda pair: pair[1], reverse=True
        )[:6]
    ]

    last_vals = feat_df.iloc[-1]
    return AIAnalysisResponse(
        symbol=klines.symbol,
        interval=klines.interval,
        sample_size=len(trainable),
        train_size=len(X_train),
        test_size=len(X_test),
        signal=signal,
        confidence_pct=confidence,
        prob_bullish=round(live_prob_up * 100.0, 2),
        prob_bearish=round(live_prob_down * 100.0, 2),
        rf_test_accuracy_pct=rf_acc,
        xgb_test_accuracy_pct=xgb_acc,
        ensemble_test_accuracy_pct=ens_acc,
        rsi_14=round(float(last_vals["rsi_14"]), 2),
        macd_hist=round(float(last_vals["macd_hist"]) * 100.0, 4),
        atr_pct=round(float(last_vals["atr_pct"]) * 100.0, 3),
        top_features=top_features,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


async def run_candle_prediction(symbol: str, interval: str = "1h") -> CandlePredictionResponse:
    klines = await fetch_market_klines(symbol=symbol, interval=interval, limit=300)
    raw_df = candles_to_df(klines.candles)
    feat_df = _build_features(raw_df)

    latest_row = feat_df[FEATURE_COLS].iloc[-1:].ffill().fillna(0.0)
    current_close = float(raw_df["close"].iloc[-1])

    trainable = feat_df.dropna(
        subset=FEATURE_COLS + ["next_ret", "next_high_pct", "next_low_pct"]
    ).reset_index(drop=True)

    X = trainable[FEATURE_COLS].to_numpy(dtype=np.float64)
    y_ret = trainable["next_ret"].to_numpy(dtype=np.float64)
    y_high = trainable["next_high_pct"].to_numpy(dtype=np.float64)
    y_low = trainable["next_low_pct"].to_numpy(dtype=np.float64)

    split_idx = int(len(trainable) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_ret_train, y_ret_test = y_ret[:split_idx], y_ret[split_idx:]

    xgb_reg = XGBRegressor(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.85,
        random_state=42,
        n_jobs=1,
    )
    gbr_reg = GradientBoostingRegressor(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        random_state=42,
    )
    high_reg = XGBRegressor(
        n_estimators=80, max_depth=3, learning_rate=0.05, random_state=42, n_jobs=1
    )
    low_reg = XGBRegressor(
        n_estimators=80, max_depth=3, learning_rate=0.05, random_state=42, n_jobs=1
    )

    xgb_reg.fit(X_train, y_ret_train)
    gbr_reg.fit(X_train, y_ret_train)
    high_reg.fit(X_train, y_high[:split_idx])
    low_reg.fit(X_train, y_low[:split_idx])

    xgb_val_pred = xgb_reg.predict(X_test)
    gbr_val_pred = gbr_reg.predict(X_test)

    mae_pct = round(float(mean_absolute_error(y_ret_test, xgb_val_pred)) * 100.0, 3)
    rmse_pct = round(float(root_mean_squared_error(y_ret_test, gbr_val_pred)) * 100.0, 3)

    X_live = latest_row.to_numpy(dtype=np.float64)
    pred_ret = float((xgb_reg.predict(X_live)[0] + gbr_reg.predict(X_live)[0]) / 2.0)
    pred_high_pct = max(float(high_reg.predict(X_live)[0]), max(pred_ret, 0.001))
    pred_low_pct = min(float(low_reg.predict(X_live)[0]), min(pred_ret, -0.001))

    predicted_close = current_close * (1.0 + pred_ret)
    predicted_high = max(current_close * (1.0 + pred_high_pct), predicted_close, current_close)
    predicted_low = min(current_close * (1.0 + pred_low_pct), predicted_close, current_close)

    return CandlePredictionResponse(
        symbol=klines.symbol,
        interval=klines.interval,
        current_close=round(current_close, 6),
        predicted_close=round(predicted_close, 6),
        predicted_high=round(predicted_high, 6),
        predicted_low=round(predicted_low, 6),
        expected_move_pct=round(pred_ret * 100.0, 3),
        predicted_direction="BULLISH" if predicted_close >= current_close else "BEARISH",
        xgb_val_mae_pct=mae_pct,
        gbr_val_rmse_pct=rmse_pct,
        sample_size=len(trainable),
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )
