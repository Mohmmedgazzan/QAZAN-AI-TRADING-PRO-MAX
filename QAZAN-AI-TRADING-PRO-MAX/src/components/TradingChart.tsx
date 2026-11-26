import { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useApp } from '@/contexts/AppContext';
import type { CandlePoint } from '@/types/api';
import type { IndicatorPoint, StructureEvent, StructureSwingPoint } from '@/types/platform';

interface TradingChartProps {
  candles: CandlePoint[];
  ema20?: IndicatorPoint[];
  ema50?: IndicatorPoint[];
  swings?: StructureSwingPoint[];
  events?: StructureEvent[];
  showEma20?: boolean;
  showEma50?: boolean;
  showStructure?: boolean;
  heightClass?: string;
}

export function TradingChart({
  candles,
  ema20 = [],
  ema50 = [],
  swings = [],
  events = [],
  showEma20 = false,
  showEma50 = false,
  showStructure = false,
  heightClass = 'h-[340px] sm:h-[420px] lg:h-[490px]',
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ema20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const { theme } = useApp();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const isDark = theme === 'dark';

    const chart = createChart(container, {
      layout: {
        background: {
          type: ColorType.Solid,
          color: isDark ? '#0B0F17' : '#ffffff',
        },
        textColor: isDark ? '#94a3b8' : '#475569',
        fontFamily: '"JetBrains Mono", monospace',
      },
      grid: {
        vertLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
        horzLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
      },
      crosshair: {
        vertLine: { color: '#D4AF37', labelBackgroundColor: '#9A7209' },
        horzLine: { color: '#D4AF37', labelBackgroundColor: '#9A7209' },
      },
      rightPriceScale: {
        borderColor: isDark ? '#1e293b' : '#e2e8f0',
      },
      timeScale: {
        borderColor: isDark ? '#1e293b' : '#e2e8f0',
        timeVisible: true,
        secondsVisible: false,
      },
      width: container.clientWidth,
      height: container.clientHeight || 380,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10B981',
      downColor: '#EF4444',
      borderVisible: false,
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444',
    });

    const markersPlugin = createSeriesMarkers(candleSeries, []);

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.82,
        bottom: 0,
      },
    });

    const ema20Series = chart.addSeries(LineSeries, {
      color: '#D4AF37',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const ema50Series = chart.addSeries(LineSeries, {
      color: '#38BDF8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    markersPluginRef.current = markersPlugin;
    volumeSeriesRef.current = volumeSeries;
    ema20SeriesRef.current = ema20Series;
    ema50SeriesRef.current = ema50Series;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          chart.applyOptions({ width, height });
        }
      }
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      markersPlugin.detach();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      markersPluginRef.current = null;
      volumeSeriesRef.current = null;
      ema20SeriesRef.current = null;
      ema50SeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const isDark = theme === 'dark';
    chart.applyOptions({
      layout: {
        background: {
          type: ColorType.Solid,
          color: isDark ? '#0B0F17' : '#ffffff',
        },
        textColor: isDark ? '#94a3b8' : '#475569',
      },
      grid: {
        vertLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
        horzLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
      },
      rightPriceScale: {
        borderColor: isDark ? '#1e293b' : '#e2e8f0',
      },
      timeScale: {
        borderColor: isDark ? '#1e293b' : '#e2e8f0',
      },
    });
  }, [theme]);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || candles.length === 0) {
      return;
    }

    const formattedCandles = candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const formattedVolumes = candles.map((c) => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(16, 185, 129, 0.30)' : 'rgba(239, 68, 68, 0.30)',
    }));

    candleSeriesRef.current.setData(formattedCandles);
    volumeSeriesRef.current.setData(formattedVolumes);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    if (!ema20SeriesRef.current) return;
    if (showEma20 && ema20.length > 0) {
      ema20SeriesRef.current.setData(
        ema20.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
      );
    } else {
      ema20SeriesRef.current.setData([]);
    }
  }, [ema20, showEma20]);

  useEffect(() => {
    if (!ema50SeriesRef.current) return;
    if (showEma50 && ema50.length > 0) {
      ema50SeriesRef.current.setData(
        ema50.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
      );
    } else {
      ema50SeriesRef.current.setData([]);
    }
  }, [ema50, showEma50]);

  useEffect(() => {
    if (!markersPluginRef.current) return;
    if (!showStructure || (swings.length === 0 && events.length === 0)) {
      markersPluginRef.current.setMarkers([]);
      return;
    }

    const markers: Array<SeriesMarker<Time>> = [];
    for (const sw of swings) {
      const isHigh = sw.kind === 'HIGH';
      markers.push({
        time: sw.time as UTCTimestamp,
        position: isHigh ? 'aboveBar' : 'belowBar',
        color: sw.label === 'HH' || sw.label === 'HL' ? '#10B981' : '#EF4444',
        shape: isHigh ? 'arrowDown' : 'arrowUp',
        text: sw.label,
      });
    }
    for (const ev of events) {
      const isBull = ev.direction === 'BULLISH';
      markers.push({
        time: ev.time as UTCTimestamp,
        position: isBull ? 'belowBar' : 'aboveBar',
        color: '#D4AF37',
        shape: 'circle',
        text: ev.event_type,
      });
    }
    markers.sort((a, b) => Number(a.time) - Number(b.time));
    markersPluginRef.current.setMarkers(markers);
  }, [swings, events, showStructure]);

  return (
    <div
      dir="ltr"
      ref={containerRef}
      className={`w-full ${heightClass} rounded-xl overflow-hidden border border-slate-200 dark:border-[#D4AF37]/20 bg-white dark:bg-[#0B0F17]`}
    />
  );
}
