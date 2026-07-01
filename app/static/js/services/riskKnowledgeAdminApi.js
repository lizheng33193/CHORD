const riskKnowledgeHttpClient = window.AppServices.httpClient;

function riskKnowledgeResolveErrorMessage(payload, response, fallbackMessage) {
  if (payload && payload.detail && typeof payload.detail.message === 'string' && payload.detail.message) return payload.detail.message;
  if (payload && payload.detail && typeof payload.detail.code === 'string' && payload.detail.code) return payload.detail.code;
  if (payload && typeof payload.message === 'string' && payload.message) return payload.message;
  return fallbackMessage || `HTTP ${response.status}`;
}

async function riskKnowledgeJson(url, options, fallbackMessage) {
  const response = await riskKnowledgeHttpClient.request(url, options || {});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(riskKnowledgeResolveErrorMessage(payload, response, fallbackMessage));
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function buildRiskKnowledgeQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

async function listKnowledgeBases() {
  return await riskKnowledgeJson('/api/risk-knowledge/admin/kbs', {}, '获取知识库列表失败。');
}

async function createKnowledgeBase(payload) {
  return await riskKnowledgeJson('/api/risk-knowledge/admin/kbs', {
    method: 'POST',
    body: JSON.stringify(payload || {})
  }, '创建知识库失败。');
}

async function getKnowledgeBase(kbId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/kbs/${encodeURIComponent(kbId)}`, {}, '获取知识库详情失败。');
}

async function listKnowledgeDocuments(kbId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/kbs/${encodeURIComponent(kbId)}/documents`, {}, '获取文档列表失败。');
}

async function createKnowledgeDocument(kbId, payload) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/kbs/${encodeURIComponent(kbId)}/documents`, {
    method: 'POST',
    body: JSON.stringify(payload || {})
  }, '创建文档失败。');
}

async function getKnowledgeDocument(documentId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/documents/${encodeURIComponent(documentId)}`, {}, '获取文档详情失败。');
}

async function listKnowledgeVersions(documentId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/documents/${encodeURIComponent(documentId)}/versions`, {}, '获取版本列表失败。');
}

async function getKnowledgeVersion(versionId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/versions/${encodeURIComponent(versionId)}`, {}, '获取版本详情失败。');
}

async function uploadKnowledgeVersion(documentId, payload) {
  const formData = new FormData();
  formData.append('file', payload.file);
  if (payload.version_label) formData.append('version_label', payload.version_label);
  formData.append('auto_index', payload.auto_index ? 'true' : 'false');
  if (payload.metadata) formData.append('metadata', payload.metadata);
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/documents/${encodeURIComponent(documentId)}/versions:upload`, {
    method: 'POST',
    body: formData
  }, '上传文档版本失败。');
}

async function indexKnowledgeVersion(versionId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/versions/${encodeURIComponent(versionId)}:index`, {
    method: 'POST'
  }, '触发索引失败。');
}

async function rebuildKnowledgeVersion(versionId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/versions/${encodeURIComponent(versionId)}:rebuild`, {
    method: 'POST'
  }, '触发重建失败。');
}

async function activateKnowledgeVersion(versionId, payload) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/versions/${encodeURIComponent(versionId)}:activate`, {
    method: 'POST',
    body: JSON.stringify(payload || {})
  }, '激活版本失败。');
}

async function listKnowledgeJobs(params) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/indexing-jobs${buildRiskKnowledgeQuery(params)}`, {}, '获取索引任务失败。');
}

async function getKnowledgeJob(jobId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/indexing-jobs/${encodeURIComponent(jobId)}`, {}, '获取索引任务详情失败。');
}

async function retryKnowledgeJob(jobId) {
  return await riskKnowledgeJson(`/api/risk-knowledge/admin/indexing-jobs/${encodeURIComponent(jobId)}:retry`, {
    method: 'POST'
  }, '重试索引任务失败。');
}

async function debugKnowledgeRetrieve(payload) {
  return await riskKnowledgeJson('/api/risk-knowledge/admin/debug/retrieve', {
    method: 'POST',
    body: JSON.stringify(payload || {})
  }, '检索调试失败。');
}

window.AppServices = window.AppServices || {};
window.AppServices.riskKnowledgeAdminApi = {
  listKnowledgeBases,
  createKnowledgeBase,
  getKnowledgeBase,
  listKnowledgeDocuments,
  createKnowledgeDocument,
  getKnowledgeDocument,
  listKnowledgeVersions,
  getKnowledgeVersion,
  uploadKnowledgeVersion,
  indexKnowledgeVersion,
  rebuildKnowledgeVersion,
  activateKnowledgeVersion,
  listKnowledgeJobs,
  getKnowledgeJob,
  retryKnowledgeJob,
  debugKnowledgeRetrieve,
};
