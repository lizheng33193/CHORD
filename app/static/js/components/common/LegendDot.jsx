// Extracted from app/ui/live_frontend.py during UI separation Step-1.

function LegendDot({ color, label }) {
  return (
    <div className="flex items-center gap-2">
      <div className={`w-3 h-3 rounded-full ${color}`}></div>
      <span className="text-slate-600">{label}</span>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.LegendDot = LegendDot;
