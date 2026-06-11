// Extracted from app/ui/live_frontend.py during UI separation Step-1.

function TimelineItem({ time, title, sub, icon: Icon, color, isLast }) {
  return (
    <div className="relative pl-8 pb-8">
      {!isLast && <div className="absolute left-3.5 top-8 bottom-0 w-0.5 bg-slate-200"></div>}
      <div className={`absolute left-0 top-1 w-7 h-7 rounded-full flex items-center justify-center text-white shadow-md ${color} ring-4 ring-white`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-sm font-bold text-slate-700">{time}</span>
          <span className="text-sm font-medium text-slate-800">{title}</span>
        </div>
        {sub && <p className="text-xs text-slate-500 bg-slate-50 p-2 rounded-md border border-slate-100 inline-block mt-1">{sub}</p>}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.TimelineItem = TimelineItem;
