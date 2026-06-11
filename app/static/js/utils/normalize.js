// Extracted from app/ui/live_frontend.py during UI separation Step-1.

function normalizeAnalysisResult(result, fallbackUid) {
  return {
    uid: stringValue(result?.uid, fallbackUid),
    app_profile: normalizeAgentOutput(result?.app_profile, '暂无 App 画像结果'),
    behavior_profile: normalizeAgentOutput(result?.behavior_profile, '暂无行为画像结果'),
    credit_profile: normalizeAgentOutput(result?.credit_profile, '暂无征信画像结果'),
    comprehensive_profile: normalizeAgentOutput(result?.comprehensive_profile, '暂无综合画像结果'),
    product_advice: result?.product_advice ? normalizeAgentOutput(result.product_advice, '暂无产品策略结果') : null,
    ops_advice: result?.ops_advice ? normalizeAgentOutput(result.ops_advice, '暂无运营策略结果') : null,
    standardized_labels: result?.standardized_labels || null
  };
}

function normalizeAgentOutput(agentOutput, fallbackSummary) {
  const safeOutput = agentOutput || {};
  return {
    summary: stringValue(safeOutput.summary, fallbackSummary),
    structured_result: objectValue(safeOutput.structured_result),
    charts: arrayValue(safeOutput.charts),
    report_markdown: stringValue(safeOutput.report_markdown, '')
  };
}

function buildEmptyAgentOutput(summary) {
  return {
    summary,
    structured_result: {},
    charts: [],
    report_markdown: ''
  };
}

function normalizeApplicationTime(value) {
  if (typeof value !== 'string' || !value.trim()) {
    return '';
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString();
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function arrayValue(value) {
  return Array.isArray(value) ? value : [];
}

function stringValue(value, fallback = '') {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function numberValue(value, fallback = 0) {
  if (typeof value === 'number' && !Number.isNaN(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function parsePercent(value) {
  const text = stringValue(value, '').replace('%', '').trim();
  const num = Number(text);
  return Number.isFinite(num) ? num : 0;
}

window.AppUtils = window.AppUtils || {};
window.AppUtils.normalize = {
  normalizeAnalysisResult,
  normalizeAgentOutput,
  buildEmptyAgentOutput,
  normalizeApplicationTime,
  objectValue,
  arrayValue,
  stringValue,
  numberValue,
  parsePercent,
};
