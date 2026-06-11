// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: CreditPanel at L1209-L1252.

const { CreditCard, PieChart } = window.LucideReact || {};
const { objectValue, arrayValue, stringValue } = window.AppUtils.normalize;
const { findChart, chartValue, chartMetaLevels } = window.AppUtils.chartLookup;
const { scoreBandWidthClass, repaymentWidthClass, levelWidthClass } = window.AppUtils.displayMappers;
const { ProgressRow } = window.AppComponents;

function CreditPanel({ profile }) {
  const structured = profile?.structured_result || {};
  const metrics = objectValue(structured.metrics);
  const charts = arrayValue(profile?.charts);
  const riskChart = findChart(charts, 'Credit Risk Level');
  const proxyChart = findChart(charts, 'Credit Proxy Signals');
  const proxyLevels = chartMetaLevels(proxyChart);
  const riskLevel = stringValue(metrics.risk_level, 'unknown');
  const gaugeValue = chartValue(riskChart, 0, { low: 1, medium: 2, high: 3, unknown: 0 }[riskLevel] || 0);
  const riskPercentMap = { 0: 20, 1: 35, 2: 62, 3: 88 };
  const debtRatio = riskPercentMap[gaugeValue] || 20;
  const creditScoreBand = stringValue(metrics.credit_score_band, '-');
  const repaymentStatus = stringValue(metrics.repayment_status, '-');
  const debtPressureLevel = stringValue(metrics.debt_pressure_level, stringValue(proxyLevels.debt_pressure, 'unknown'));
  return (
    <div className="animate-in fade-in duration-500">
      <div className="flex items-center gap-3 mb-8 pb-4 border-b border-slate-100"><CreditCard className="w-8 h-8 text-slate-600" /><h2 className="text-2xl font-bold text-slate-800">Skill 3: 征信画像 Agent</h2></div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        <div className="border border-slate-200 rounded-xl p-6">
          <h3 className="font-bold text-slate-700 mb-4 flex items-center gap-2"><PieChart className="w-5 h-5" /> 征信风险结构</h3>
          <div className="flex items-center justify-center py-6">
            <div className="relative w-40 h-40 rounded-full border-8 border-slate-100 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full" style={{ background: `conic-gradient(#3b82f6 0 ${debtRatio}%, #cbd5e1 ${debtRatio}% 100%)` }}></div>
              <div className="absolute inset-4 rounded-full bg-white"></div>
              <div className="relative text-center"><span className="block text-2xl font-bold text-slate-700">{debtRatio}%</span><span className="text-xs text-slate-500">风险映射值</span></div>
            </div>
          </div>
          <div className="flex justify-center gap-4 text-sm mt-2">
            <span className="flex items-center gap-1"><div className="w-3 h-3 bg-blue-500 rounded-full"></div>风险强度</span>
            <span className="flex items-center gap-1"><div className="w-3 h-3 bg-slate-300 rounded-full"></div>稳定区间</span>
          </div>
        </div>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-6">
          <h3 className="font-bold text-slate-700 mb-4">征信历史指标</h3>
          <div className="space-y-5">
            <ProgressRow label="Credit Score Band" value={creditScoreBand} widthClass={scoreBandWidthClass(creditScoreBand)} barClass="bg-blue-500" />
            <ProgressRow label="Repayment Status" value={repaymentStatus} widthClass={repaymentWidthClass(repaymentStatus)} barClass="bg-green-500" />
            <ProgressRow label="Debt Pressure" value={debtPressureLevel} widthClass={levelWidthClass(debtPressureLevel)} barClass="bg-slate-600" />
          </div>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.CreditPanel = CreditPanel;
