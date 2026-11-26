import asyncio
from collections import deque
from datetime import datetime, timezone
import json
from typing import Any
from fastapi import WebSocket
import websockets

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.ingestion import LiquidationEventItem, WebSocketStreamStatus
from app.services.symbol_registry import get_tracked_symbol_names

logger = get_logger("qazan.ws")


class MarketWebSocketHub:
    """
    Server-authoritative real-time WebSocket ingestion & broadcast hub.
    - Subscribes to Binance Spot public combined stream (@ticker + @aggTrade)
    - Subscribes to Binance Futures public force liquidation stream (!forceOrder@arr)
    - Relays snapshots and live delta events to connected frontend clients
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._clients_lock = asyncio.Lock()

        self._spot_task: asyncio.Task | None = None
        self._futures_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._running: bool = False
        self._resubscribe_event = asyncio.Event()

        self.spot_connected: bool = False
        self.futures_liquidations_connected: bool = False
        self.spot_messages_received: int = 0
        self.liquidation_events_captured: int = 0
        self.last_spot_tick_at: str | None = None
        self.last_liquidation_at: str | None = None

        self.latest_tickers: dict[str, dict[str, Any]] = {}
        self.live_cvd_delta: dict[str, dict[str, Any]] = {}
        self.liquidations_buffer: deque[LiquidationEventItem] = deque(maxlen=250)

    def start(self) -> None:
        settings = get_settings()
        if not settings.ENABLE_BACKGROUND_WS or self._running:
            return
        self._running = True
        self._spot_task = asyncio.create_task(self._run_spot_stream_loop(), name="qazan-ws-spot")
        self._futures_task = asyncio.create_task(
            self._run_futures_liq_loop(), name="qazan-ws-futures-liq"
        )
        self._heartbeat_task = asyncio.create_task(
            self._run_heartbeat_loop(), name="qazan-ws-heartbeat"
        )
        logger.info("MarketWebSocketHub background streams started.")

    async def stop(self) -> None:
        self._running = False
        self._resubscribe_event.set()
        for task in (self._spot_task, self._futures_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        self._spot_task = None
        self._futures_task = None
        self._heartbeat_task = None
        self.spot_connected = False
        self.futures_liquidations_connected = False
        logger.info("MarketWebSocketHub background streams stopped.")

    def trigger_resubscribe(self) -> None:
        self._resubscribe_event.set()

    def status(self) -> WebSocketStreamStatus:
        return WebSocketStreamStatus(
            spot_connected=self.spot_connected,
            futures_liquidations_connected=self.futures_liquidations_connected,
            active_clients=len(self._clients),
            spot_messages_received=self.spot_messages_received,
            liquidation_events_captured=self.liquidation_events_captured,
            last_spot_tick_at=self.last_spot_tick_at,
            last_liquidation_at=self.last_liquidation_at,
        )

    def get_recent_liquidations(self, symbol: str | None = None, limit: int = 25) -> list[LiquidationEventItem]:
        items = list(self.liquidations_buffer)
        if symbol:
            norm = symbol.strip().upper()
            filtered = [item for item in items if item.symbol == norm]
            return filtered[:limit]
        return items[:limit]

    def build_snapshot(self, symbol: str | None = None) -> dict[str, Any]:
        norm = symbol.strip().upper() if symbol else None
        return {
            "type": "snapshot",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ws_status": self.status().model_dump(),
            "tickers": self.latest_tickers,
            "live_cvd_delta": self.live_cvd_delta,
            "recent_liquidations": [
                item.model_dump() for item in self.get_recent_liquidations(symbol=norm, limit=20)
            ],
        }

    async def connect_client(self, ws: WebSocket, symbol: str | None = None) -> None:
        await ws.accept()
        async with self._clients_lock:
            self._clients.add(ws)
        try:
            await ws.send_json(self.build_snapshot(symbol=symbol))
        except Exception:
            await self.disconnect_client(ws)

    async def disconnect_client(self, ws: WebSocket) -> None:
        async with self._clients_lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._clients_lock:
            clients = list(self._clients)
        if not clients:
            return
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._clients_lock:
                for ws in dead:
                    self._clients.discard(ws)

    async def _run_heartbeat_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(10.0)
                if not self._running:
                    break
                if self._clients:
                    await self.broadcast(
                        {
                            "type": "heartbeat",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "ws_status": self.status().model_dump(),
                        }
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("WS heartbeat error: %s", str(exc))

    async def _run_spot_stream_loop(self) -> None:
        settings = get_settings()
        backoff = 1.0
        while self._running:
            self._resubscribe_event.clear()
            try:
                symbols = get_tracked_symbol_names()[:12]
                streams: list[str] = []
                for sym in symbols:
                    low = sym.lower()
                    streams.append(f"{low}@ticker")
                    streams.append(f"{low}@aggTrade")
                ws_url = f"{settings.BINANCE_SPOT_WS_URL}?streams={'/'.join(streams)}"

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.spot_connected = True
                    backoff = 1.0
                    logger.info("Connected Binance Spot WebSocket (%d streams)", len(streams))
                    last_broadcast_at: dict[str, float] = {}

                    while self._running and not self._resubscribe_event.is_set():
                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=1.5)
                        except asyncio.TimeoutError:
                            continue

                        envelope = json.loads(raw_msg)
                        stream_name = str(envelope.get("stream", ""))
                        data = envelope.get("data", {})
                        if not isinstance(data, dict):
                            continue

                        now_iso = datetime.now(timezone.utc).isoformat()
                        self.spot_messages_received += 1
                        self.last_spot_tick_at = now_iso

                        if stream_name.endswith("@ticker"):
                            sym = str(data.get("s", "")).upper()
                            if not sym:
                                continue
                            ticker_obj = {
                                "symbol": sym,
                                "last_price": float(data.get("c", 0.0)),
                                "price_change_pct": float(data.get("P", 0.0)),
                                "high_24h": float(data.get("h", 0.0)),
                                "low_24h": float(data.get("l", 0.0)),
                                "volume_24h": float(data.get("v", 0.0)),
                                "quote_volume_24h": float(data.get("q", 0.0)),
                                "updated_at": now_iso,
                                "source": "Binance Spot WebSocket (@ticker)",
                            }
                            self.latest_tickers[sym] = ticker_obj
                            now_loop = asyncio.get_running_loop().time()
                            if now_loop - last_broadcast_at.get(sym, 0.0) >= 0.65:
                                last_broadcast_at[sym] = now_loop
                                await self.broadcast(
                                    {
                                        "type": "tick",
                                        "symbol": sym,
                                        "ticker": ticker_obj,
                                        "live_cvd": self.live_cvd_delta.get(sym),
                                        "ws_status": self.status().model_dump(),
                                    }
                                )

                        elif stream_name.endswith("@aggTrade"):
                            sym = str(data.get("s", "")).upper()
                            if not sym:
                                continue
                            qty = float(data.get("q", 0.0))
                            price = float(data.get("p", 0.0))
                            is_buyer_maker = bool(data.get("m", False))
                            # Buyer maker => aggressive seller initiated => negative delta
                            signed_delta = -qty if is_buyer_maker else qty
                            entry = self.live_cvd_delta.setdefault(
                                sym,
                                {
                                    "symbol": sym,
                                    "cumulative_delta_base": 0.0,
                                    "cumulative_delta_usd": 0.0,
                                    "buy_volume_base": 0.0,
                                    "sell_volume_base": 0.0,
                                    "trades_count": 0,
                                    "started_at": now_iso,
                                    "updated_at": now_iso,
                                    "source": "Binance Spot WebSocket (@aggTrade)",
                                },
                            )
                            entry["cumulative_delta_base"] += signed_delta
                            entry["cumulative_delta_usd"] += signed_delta * price
                            if signed_delta >= 0:
                                entry["buy_volume_base"] += qty
                            else:
                                entry["sell_volume_base"] += qty
                            entry["trades_count"] += 1
                            entry["updated_at"] = now_iso

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.spot_connected = False
                logger.warning("Binance Spot WS disconnected (%s); reconnecting in %.1fs", str(exc), backoff)
                await asyncio.sleep(backoff)
                backoff = min(20.0, backoff * 1.8)
            finally:
                self.spot_connected = False

    async def _run_futures_liq_loop(self) -> None:
        settings = get_settings()
        backoff = 1.5
        while self._running:
            try:
                async with websockets.connect(
                    settings.BINANCE_FUTURES_WS_URL,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.futures_liquidations_connected = True
                    backoff = 1.5
                    logger.info("Connected Binance Futures Liquidation WebSocket (!forceOrder@arr)")

                    while self._running:
                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        except asyncio.TimeoutError:
                            continue

                        payload = json.loads(raw_msg)
                        order = payload.get("o") if isinstance(payload, dict) else None
                        if not isinstance(order, dict):
                            continue

                        sym = str(order.get("s", "")).upper()
                        price = float(order.get("ap") or order.get("p") or 0.0)
                        qty = float(order.get("z") or order.get("q") or 0.0)
                        notional_usd = round(price * qty, 2)
                        now_iso = datetime.now(timezone.utc).isoformat()
                        item = LiquidationEventItem(
                            symbol=sym,
                            side=str(order.get("S", "UNKNOWN")),
                            order_type=str(order.get("o", "LIMIT")),
                            price=price,
                            quantity=qty,
                            notional_usd=notional_usd,
                            event_time=int(order.get("T") or payload.get("E") or 0) // 1000,
                            received_at=now_iso,
                            source="Binance Futures WebSocket (!forceOrder@arr)",
                        )
                        self.liquidations_buffer.appendleft(item)
                        self.liquidation_events_captured += 1
                        self.last_liquidation_at = now_iso

                        await self.broadcast(
                            {
                                "type": "liquidation",
                                "event": item.model_dump(),
                                "ws_status": self.status().model_dump(),
                            }
                        )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.futures_liquidations_connected = False
                logger.warning(
                    "Binance Futures Liquidation WS disconnected (%s); reconnecting in %.1fs",
                    str(exc),
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(25.0, backoff * 1.8)
            finally:
                self.futures_liquidations_connected = False


ws_market_hub = MarketWebSocketHub()
