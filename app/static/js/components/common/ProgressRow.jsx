// Extracted from app/ui/live_frontend.py during UI separation Step-1.

function ProgressRow({ label, value, widthClass, barClass }) {
  return (
    <div>
      <div className="flex justify-between text-sm mb-1 text-slate-600"><span>{label}</span><span className="text-slate-800 font-bold">{value}</span></div>
      <div className="w-full bg-slate-200 rounded-full h-1.5"><div className={`${barClass} h-1.5 rounded-full ${widthClass}`}></div></div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ProgressRow = ProgressRow;
