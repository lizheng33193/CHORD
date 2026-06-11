// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { numberValue } = window.AppUtils.normalize;

function CreditProgressRow({ label, levelLabel = '', value, widthPercent = 0, barClass, note = '', levelClass = 'text-slate-700' }) {
  const safeWidth = Math.max(0, Math.min(100, numberValue(widthPercent, 0)));
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm text-slate-700">
        <span className="font-semibold">{label}</span>
        <span className={`font-bold ${levelClass}`}>{levelLabel}</span>
      </div>
      <div className="w-full bg-slate-200 rounded-full h-2">
        <div className={`${barClass} h-2 rounded-full`} style={{ width: `${safeWidth}%` }}></div>
      </div>
      <div className="flex justify-between gap-3 text-xs text-slate-500">
        <span className="leading-5">{note}</span>
        <span className="font-semibold text-slate-700 shrink-0">{value}</span>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.CreditProgressRow = CreditProgressRow;
