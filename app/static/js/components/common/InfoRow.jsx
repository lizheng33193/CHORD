// Extracted from app/ui/live_frontend.py during UI separation Step-1.

function InfoRow({ label, value, valueClass }) {
  return (
    <li className="bg-white p-3 rounded shadow-sm border border-slate-100 flex justify-between gap-3">
      <span className="text-slate-600">{label}</span>
      <span className={`font-semibold text-right ${valueClass}`}>{value}</span>
    </li>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.InfoRow = InfoRow;
