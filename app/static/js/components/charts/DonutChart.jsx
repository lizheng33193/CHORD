// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { arrayValue, stringValue, numberValue } = window.AppUtils.normalize;
const { donutSegmentPath, polarToCartesian, findPrimaryCategoryIndex } = window.AppUtils.chartLookup;
const { colorByIndex } = window.AppUtils.displayMappers;

function InteractiveDonutChart({ items, palette, activeIndex, onHover, onLeave, onSelect, size = 180 }) {
  const safeItems = arrayValue(items);
  const safePalette = arrayValue(palette).length ? arrayValue(palette) : ['#3b82f6'];
  const center = size / 2;
  const radius = Math.max(42, Math.round(size * 0.4));
  const innerRadius = Math.max(24, Math.round(size * 0.23));
  const innerInset = Math.round(size * 0.23);
  if (!safeItems.length) {
    return (
      <div className="rounded-full bg-slate-100 flex items-center justify-center mb-6" style={{ width: `${size}px`, height: `${size}px` }}>
        <div className="text-center"><div className="text-2xl font-bold text-slate-700">0%</div><div className="text-xs text-slate-500 mt-1">暂无分类数据</div></div>
      </div>
    );
  }
  let startAngle = -90;
  return (
    <div className="relative mb-6" style={{ width: `${size}px`, height: `${size}px` }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full drop-shadow-sm">{safeItems.map((item, index) => { const share = Math.max(0, Math.min(100, numberValue(item.share, 0))); const angle = share * 3.6; const endAngle = startAngle + angle; const isActive = activeIndex === index; const path = donutSegmentPath(center, center, radius, innerRadius, startAngle, endAngle); const fill = safePalette[index % safePalette.length]; const segment = (<path key={`${item.label || 'segment'}-${index}`} d={path} fill={fill} opacity={isActive ? 1 : 0.85} stroke={isActive ? '#0f172a' : '#ffffff'} strokeWidth={isActive ? 3 : 1.5} className="transition-all duration-200 cursor-pointer" onMouseEnter={() => onHover(index)} onMouseLeave={onLeave} onClick={() => onSelect(index)} />); startAngle = endAngle; return segment; })}</svg>
      <div className="absolute rounded-full bg-white shadow-inner flex flex-col items-center justify-center text-center border border-slate-100" style={{ inset: `${innerInset}px` }}><span className="text-3xl font-bold text-slate-800">{numberValue((safeItems[activeIndex ?? 0] || {}).share, 0)}%</span><span className="text-xs text-slate-500 px-2 leading-5">{stringValue((safeItems[activeIndex ?? 0] || {}).label, '主偏好占比')}</span></div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.InteractiveDonutChart = InteractiveDonutChart;
