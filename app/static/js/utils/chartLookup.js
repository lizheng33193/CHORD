// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { arrayValue, stringValue, numberValue, objectValue } = window.AppUtils.normalize;

function findChart(charts, title) {
  return arrayValue(charts).find((chart) => stringValue(chart?.title) === title) || null;
}

function chartSeriesData(chart, seriesIndex = 0) {
  const series = arrayValue(chart?.series)[seriesIndex];
  return arrayValue(series?.data).map((value) => numberValue(value));
}

function chartValue(chart, index, fallback = 0) {
  const data = chartSeriesData(chart);
  return typeof data[index] === 'number' && !Number.isNaN(data[index]) ? data[index] : fallback;
}

function chartMetaLevels(chart) {
  return objectValue(objectValue(chart?.meta).levels);
}

function buildConicGradient(items, palette) {
  const safeItems = arrayValue(items);
  const safePalette = arrayValue(palette).length ? arrayValue(palette) : ['#3b82f6', '#06b6d4', '#6366f1', '#8b5cf6', '#0f172a'];
  if (!safeItems.length) {
    return 'conic-gradient(#3b82f6 0% 100%)';
  }

  let start = 0;
  const segments = safeItems.map((item, index) => {
    const share = Math.max(0, Math.min(100, numberValue(item.share, 0)));
    const end = index === safeItems.length - 1 ? 100 : Math.min(100, start + share);
    const segment = `${safePalette[index % safePalette.length]} ${start}% ${end}%`;
    start = end;
    return segment;
  });

  if (start < 100) {
    segments.push(`${safePalette[safeItems.length % safePalette.length]} ${start}% 100%`);
  }
  return `conic-gradient(${segments.join(', ')})`;
}

function findPrimaryCategoryIndex(items) {
  const safeItems = arrayValue(items);
  const candidateIndex = safeItems.findIndex((item) => stringValue(item?.label) !== '其他-待归类');
  return candidateIndex >= 0 ? candidateIndex : 0;
}

function polarToCartesian(cx, cy, radius, angleInDegrees) {
  const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
  return {
    x: cx + radius * Math.cos(angleInRadians),
    y: cy + radius * Math.sin(angleInRadians)
  };
}

function donutSegmentPath(cx, cy, outerRadius, innerRadius, startAngle, endAngle) {
  const cappedEndAngle = endAngle - 0.01;
  const outerStart = polarToCartesian(cx, cy, outerRadius, cappedEndAngle);
  const outerEnd = polarToCartesian(cx, cy, outerRadius, startAngle);
  const innerStart = polarToCartesian(cx, cy, innerRadius, cappedEndAngle);
  const innerEnd = polarToCartesian(cx, cy, innerRadius, startAngle);
  const largeArcFlag = cappedEndAngle - startAngle <= 180 ? '0' : '1';
  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerRadius} ${outerRadius} 0 ${largeArcFlag} 0 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 1 ${innerStart.x} ${innerStart.y}`,
    'Z'
  ].join(' ');
}

window.AppUtils = window.AppUtils || {};
window.AppUtils.chartLookup = {
  findChart, chartSeriesData, chartValue, chartMetaLevels,
  buildConicGradient, findPrimaryCategoryIndex, polarToCartesian, donutSegmentPath,
};
