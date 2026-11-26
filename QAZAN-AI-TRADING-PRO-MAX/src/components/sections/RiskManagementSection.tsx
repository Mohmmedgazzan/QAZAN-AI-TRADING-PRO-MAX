import React, { useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { ApiClientError } from '@/api/client';
import { platformClient } from '@/api/platformClient';
import { useApp } from '@/contexts/AppContext';
import type { RiskCalculateResponse } from '@/types/platform';

export function RiskManagementSection() {
  const { pt } = useApp();
  const [accountBalance, setAccountBalance] = useState(10000);
  const [riskPct, setRiskPct] = useState(1.0);
  const [entryPrice, setEntryPrice] = useState(64000);
  const [stopLoss, setStopLoss] = useState(62800);
  const [takeProfit, setTakeProfit] = useState(66400);
  const [leverage, setLeverage] = useState(5);

  const [result, setResult] = useState<RiskCalculateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const prof = await platformClient.getRiskProfile();
        setAccountBalance(prof.account_balance);
        setRiskPct(prof.risk_pct);
      } catch {
        // Use defaults
      }
    })();
  }, []);

  const handleCalculate = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setError(null);
    setSavedNotice(false);
    try {
      const res = await platformClient.calculateRisk({
        account_balance: accountBalance,
        risk_pct: riskPct,
        entry_price: entryPrice,
        stop_loss: stopLoss,
        take_profit: takeProfit,
        leverage,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    }
  };

  useEffect(() => {
    void handleCalculate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSaveProfile = async () => {
    setError(null);
    setSavedNotice(false);
    try {
      await platformClient.saveRiskProfile({
        account_balance: accountBalance,
        risk_pct: riskPct,
        default_rr: result?.risk_reward_ratio || 2.0,
        max_leverage: leverage,
        max_daily_loss_pct: Math.min(10, riskPct * 3),
      });
      setSavedNotice(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? `${err.code}: ${err.message}` : String(err));
    }
  };

  const totalScale = result ? Math.max(1, result.risk_amount_usdt + result.reward_amount_usdt) : 1;
  const riskBarPct = result ? (result.risk_amount_usdt / totalScale) * 100 : 33;

  return (
    <section className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
          {pt.sections['risk-management']}
        </h1>
        <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">{pt.riskSubtitle}</p>
      </div>

      {error && (
        <div role="alert" className="p-4 rounded-xl border border-red-500/30 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-200 text-xs font-mono">
          {error}
        </div>
      )}

      {savedNotice && (
        <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{pt.profileSaved}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <form
          onSubmit={(e) => void handleCalculate(e)}
          className="qazan-card p-5 space-y-4"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <label className="space-y-1.5">
              <span className="block text-slate-500 dark:text-slate-400">{pt.accountBalance}</span>
              <input
                type="number"
                step="any"
                value={accountBalance}
                onChange={(e) => setAccountBalance(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums"
              />
            </label>
            <label className="space-y-1.5">
              <span className="block text-slate-500 dark:text-slate-400">{pt.riskPercent}</span>
              <input
                type="number"
                step="0.1"
                value={riskPct}
                onChange={(e) => setRiskPct(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums"
              />
            </label>
            <label className="space-y-1.5">
              <span className="block text-slate-500 dark:text-slate-400">{pt.entryPrice}</span>
              <input
                type="number"
                step="any"
                value={entryPrice}
                onChange={(e) => setEntryPrice(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums"
              />
            </label>
            <label className="space-y-1.5">
              <span className="block text-slate-500 dark:text-slate-400">{pt.stopLoss}</span>
              <input
                type="number"
                step="any"
                value={stopLoss}
                onChange={(e) => setStopLoss(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums"
              />
            </label>
            <label className="space-y-1.5">
              <span className="block text-slate-500 dark:text-slate-400">{pt.takeProfit}</span>
              <input
                type="number"
                step="any"
                value={takeProfit}
                onChange={(e) => setTakeProfit(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums"
              />
            </label>
            <label className="space-y-1.5">
              <span className="block text-slate-500 dark:text-slate-400">{pt.leverage}</span>
              <input
                type="number"
                min={1}
                max={50}
                step="1"
                value={leverage}
                onChange={(e) => setLeverage(Number(e.target.value))}
                className="qazan-input font-mono tabular-nums"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2 pt-2">
            <button type="submit" className="qazan-btn-gold flex-1">
              {pt.calculateRisk}
            </button>
            <button
              type="button"
              onClick={() => void handleSaveProfile()}
              className="qazan-btn-secondary border-[#D4AF37]/40 text-[#9A7209] dark:text-[#E5C76B]"
            >
              {pt.saveRiskProfile}
            </button>
          </div>
        </form>

        {result && (
          <div className="qazan-card-gold p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <span className="text-sm font-semibold">{pt.riskRewardRatio}</span>
              <span className="font-mono font-bold text-lg text-[#9A7209] dark:text-[#E5C76B] tabular-nums">
                1 : {result.risk_reward_ratio.toFixed(2)} · {result.direction}
              </span>
            </div>

            {/* Visual Risk vs Reward Proportion Track */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-[11px] font-mono tabular-nums">
                <span className="text-red-600 dark:text-red-400">
                  {pt.riskAmount}: -${result.risk_amount_usdt.toFixed(2)}
                </span>
                <span className="text-emerald-600 dark:text-emerald-400">
                  {pt.rewardAmount}: +${result.reward_amount_usdt.toFixed(2)}
                </span>
              </div>
              <div className="h-2.5 rounded-full bg-emerald-500/80 overflow-hidden flex" dir="ltr">
                <div className="h-full bg-red-500/85" style={{ width: `${riskBarPct}%` }} />
              </div>
            </div>

            <dl className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">{pt.positionSizeUnits}</dt>
                <dd className="font-mono font-bold tabular-nums">{result.position_size_units.toFixed(6)}</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">{pt.notionalValue}</dt>
                <dd className="font-mono font-semibold tabular-nums">${result.position_notional_usdt.toLocaleString('en-US')}</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">{pt.requiredMargin}</dt>
                <dd className="font-mono font-semibold tabular-nums">${result.required_margin_usdt.toLocaleString('en-US')}</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">{pt.estLiquidation}</dt>
                <dd className="font-mono font-semibold tabular-nums">${result.est_liquidation_price.toLocaleString('en-US')}</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500 dark:text-slate-400">{pt.kellyHalf}</dt>
                <dd className="font-mono font-semibold tabular-nums text-[#9A7209] dark:text-[#E5C76B]">
                  {result.kelly_fraction_pct.toFixed(2)}%
                </dd>
              </div>
            </dl>
          </div>
        )}
      </div>
    </section>
  );
}
