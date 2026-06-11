// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: RichCreditPanel inline SVG at L1571-L1595.
// radarPoint is declared locally here; RichCreditPanel keeps its own copy
// for pre-computing radarPolygon (per Plan E.3 + user authorization).

function CreditRiskStructure({ radarDimensions, radarValues, radarPolygon, centerX, centerY }) {
  const radius = 92;

  function radarPoint(value, index, count) {
    const angle = (-Math.PI / 2) + (index * 2 * Math.PI / count);
    const r = radius * (value / 100);
    return {
      x: centerX + r * Math.cos(angle),
      y: centerY + r * Math.sin(angle),
      labelX: centerX + (radius + 24) * Math.cos(angle),
      labelY: centerY + (radius + 24) * Math.sin(angle)
    };
  }

  return (
    <svg width="320" height="280" viewBox="0 0 320 280">
      {[20, 40, 60, 80, 100].map((tick) => {
        const ring = radarDimensions
          .map((_, index) => {
            const p = radarPoint(tick, index, radarDimensions.length);
            return `${p.x},${p.y}`;
          })
          .join(' ');
        return <polygon key={tick} points={ring} fill="none" stroke="#dbeafe" strokeWidth="1" />;
      })}
      {radarDimensions.map((item, index) => {
        const end = radarPoint(100, index, radarDimensions.length);
        return (
          <g key={item.key}>
            <line x1={centerX} y1={centerY} x2={end.x} y2={end.y} stroke="#cbd5e1" strokeWidth="1" />
            <text x={end.labelX} y={end.labelY} textAnchor="middle" fontSize="10" fill="#475569">{item.label}</text>
          </g>
        );
      })}
      <polygon points={radarPolygon} fill="rgba(59, 130, 246, 0.18)" stroke="#2563eb" strokeWidth="2.5" />
      {radarValues.map((value, index) => {
        const point = radarPoint(value, index, radarDimensions.length);
        return <circle key={`${value}-${index}`} cx={point.x} cy={point.y} r="4" fill="#2563eb" />;
      })}
    </svg>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.CreditRiskStructure = CreditRiskStructure;
