import argparse
import asyncio
import json

from app.db.database import init_db
from app.engine.backtester import run_causal_historical_backtest
from app.engine.models import CausalBacktestRequest
from app.engine.technical_engine import analyze_multi_timeframe


async def _run(args: argparse.Namespace) -> None:
    init_db()
    analysis = await analyze_multi_timeframe(
        symbol=args.symbol,
        ltf_interval=args.ltf,
        persist=not args.no_save,
    )
    output: dict = {"analysis": analysis.model_dump()}

    if args.backtest:
        bt = await run_causal_historical_backtest(
            CausalBacktestRequest(
                symbol=args.symbol,
                timeframe=args.backtest_tf,
                lookback_bars=args.bars,
            ),
            persist=not args.no_save,
        )
        output["historical_backtest"] = bt.model_dump()

    print(json.dumps(output, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="QAZAN Institutional Multi-Timeframe Technical Analysis Engine (1W / 1D / 4H + LTF)"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair symbol (e.g. BTCUSDT)")
    parser.add_argument("--ltf", default="1h", choices=["15m", "1h"], help="LTF confirmation interval")
    parser.add_argument("--backtest", action="store_true", help="Include causal historical backtest")
    parser.add_argument("--backtest-tf", default="4h", choices=["1h", "4h", "1d"], help="Backtest timeframe")
    parser.add_argument("--bars", type=int, default=300, help="Historical OHLCV bars to backtest")
    parser.add_argument("--no-save", action="store_true", help="Skip SQLite persistence")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
