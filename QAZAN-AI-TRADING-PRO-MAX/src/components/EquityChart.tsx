import { useEffect, useRef } from 'react';
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useApp } from '@/contexts/AppContext';
import type { EquityPoint } from '@/types/platform';

export function EquityChart({ points }: { points: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const { theme } = useApp();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const isDark = theme === 'dark';

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: isDark ? '#0B0F17' : '#ffffff' },
        textColor: isDark ? '#94a3b8' : '#475569',
        fontFamily: '"JetBrains Mono", monospace',
      },
      grid: {
        vertLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
        horzLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
      },
      rightPriceScale: { borderColor: isDark ? '#1e293b' : '#e2e8f0' },
      timeScale: { borderColor: isDark ? '#1e293b' : '#e2e8f0', timeVisible: true },
      width: container.clientWidth,
      height: 280,
    });

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: '#D4AF37',
      topColor: 'rgba(212, 175, 55, 0.30)',
      bottomColor: 'rgba(212, 175, 55, 0.02)',
      lineWidth: 2,
    });

    chartRef.current = chart;
    seriesRef.current = areaSeries;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          chart.applyOptions({ width: entry.contentRect.width });
        }
      }
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const isDark = theme === 'dark';
    chart.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: isDark ? '#0B0F17' : '#ffffff' },
        textColor: isDark ? '#94a3b8' : '#475569',
      },
      grid: {
        vertLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
        horzLines: { color: isDark ? '#141C2B' : '#f1f5f9' },
      },
    });
  }, [theme]);

  useEffect(() => {
    if (!seriesRef.current || points.length === 0) return;
    seriesRef.current.setData(
      points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  return (
    <div
      dir="ltr"
      ref={containerRef}
      className="w-full h-[280px] rounded-xl overflow-hidden border border-slate-200 dark:border-[#D4AF37]/20 bg-white dark:bg-[#0B0F17]"
    />
  );
}
