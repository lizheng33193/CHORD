// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: RichCreditPanel inline SVG at L1374-L1393.

function CreditGauge({ scoreValue }) {
  return (
    <svg width="100%" height="100%" viewBox="0 0 320 180">
      <path d="M 40 140 A 120 120 0 0 1 280 140" fill="none" stroke="#e2e8f0" strokeWidth="14" strokeLinecap="round" />
      <path
        d="M 40 140 A 120 120 0 0 1 280 140"
        fill="none"
        stroke="url(#creditGauge)"
        strokeWidth="14"
        strokeLinecap="round"
        strokeDasharray={`${Math.max(10, Math.min(100, Math.round((scoreValue / 900) * 100)))} 999`}
      />
      <defs>
        <linearGradient id="creditGauge" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#ef4444" />
          <stop offset="55%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#22c55e" />
        </linearGradient>
      </defs>
      <text x="160" y="108" textAnchor="middle" fontSize="58" fontWeight="700" fill="#1f2937">{scoreValue}</text>
      <text x="160" y="136" textAnchor="middle" fontSize="16" fill="#64748b">/ 900 分</text>
    </svg>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.CreditGauge = CreditGauge;
