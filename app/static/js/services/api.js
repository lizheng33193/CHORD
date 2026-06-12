// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// All fetch calls live here so future SSE / polling switches are local to this file.
// Authorization, project_id, and country headers are injected by httpClient.

const httpClient = window.AppServices.httpClient;

async function analyzeByUid(trimmedUid, normalizedApplicationTime, country) {
  return await httpClient.json('/api/analyze', {
    method: 'POST',
    body: JSON.stringify({
      uid: trimmedUid,
      application_time: normalizedApplicationTime,
      country: country || 'mx'
    })
  }, '分析请求失败，请稍后重试。');
}

async function analyzeByFile(file, country) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('country', country || 'mx');

  return await httpClient.json('/api/analyze-file', {
    method: 'POST',
    body: formData
  }, '文件分析请求失败，请检查文件内容。');
}

// SSE-aware streaming variant of analyzeByUid.
// onEvent: (evt: object) => void  — invoked once per parsed event
// signal:  AbortSignal | undefined — fetch abort support (Q6.5)
// Returns: Promise<void> — resolves when stream ends naturally; rejects on
//          network/HTTP error (NOT on stream_error events — those are
//          delivered via onEvent and the consumer decides how to react).
async function analyzeByUidStream(trimmedUid, normalizedApplicationTime, onEvent, signal, country) {
  const body = trimmedUid && trimmedUid.length === 18
    ? { uid: trimmedUid, application_time: normalizedApplicationTime, country: country || 'mx' }
    : null;
  if (!body) throw new Error('UID 格式错误');

  const response = await httpClient.request('/api/analyze-stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    },
    body: JSON.stringify(body),
    signal
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `分析请求失败 (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex;
    // Process every complete event (delimited by blank line, '\n\n').
    while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      if (!block || block.startsWith(':')) continue;  // heartbeat
      const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
      if (!dataLine) continue;
      try {
        const evt = JSON.parse(dataLine.slice(5).trim());
        onEvent(evt);
      } catch (e) {
        // Malformed event — ignore rather than tear down the whole stream.
        console.warn('SSE parse error', e, block);
      }
    }
  }
}

async function fetchTrace(uid) {
  const res = await httpClient.request(`/api/trace/${encodeURIComponent(uid)}`);
  if (res.status === 404) return { uid, status: 'data_missing' };
  if (!res.ok) throw new Error(`trace_http_${res.status}`);
  return await res.json();
}

async function fetchUiConfig() {
  const res = await httpClient.request('/api/ui-config');
  const payload = res.ok ? await res.json() : {};
  return {
    ...payload,
    supported_countries: Array.isArray(payload && payload.supported_countries)
      ? payload.supported_countries.map((country) => String(country).toLowerCase())
      : [],
  };
}

async function analyzeModule(targetUid, moduleName, normalizedApplicationTime, country) {
  const params = new URLSearchParams({
    uid: targetUid,
    module: moduleName,
    country: country || 'mx',
  });
  if (normalizedApplicationTime) {
    params.set('application_time', normalizedApplicationTime);
  }
  return await httpClient.json(
    `/api/analyze-module?${params.toString()}`,
    {},
    '模块分析请求失败，请稍后重试。'
  );
}

async function createOrchestratorSession(initialMessage, workspaceSnapshot, clientTurnId) {
  return await httpClient.json('/api/orchestrator/sessions', {
    method: 'POST',
    body: JSON.stringify({ initial_message: initialMessage, workspace_snapshot: workspaceSnapshot, client_turn_id: clientTurnId || null })
  }, '创建对话会话失败。');
}

async function sendOrchestratorMessage(sessionId, content, workspaceSnapshot, clientTurnId) {
  return await httpClient.json(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, workspace_snapshot: workspaceSnapshot, client_turn_id: clientTurnId || null })
  }, '发送消息失败。');
}

function openOrchestratorStream(sessionId, handlers) {
  let stream = null;
  stream = httpClient.openEventStream(
    `/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/stream`,
    {
      onEvent: (evt) => {
        handlers.onEvent && handlers.onEvent(evt);
        if (evt && evt.type === 'done' && stream) {
          stream.close();
        }
      },
      onError: (err) => {
        handlers.onError && handlers.onError(err);
      },
      onClose: () => {
        handlers.onClose && handlers.onClose();
      },
    }
  );
  return stream;
}

async function ackOrchestratorTool(sessionId, toolCallId, decision) {
  return await httpClient.json(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/ack`, {
    method: 'POST',
    body: JSON.stringify({ tool_call_id: toolCallId, decision })
  }, '工具审批失败。');
}

async function cancelOrchestratorRun(sessionId, runId) {
  const res = await httpClient.request(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `cancelOrchestratorRun ${res.status}`);
  return payload;
}

async function resolveOrchestratorStep(sessionId, payload) {
  const res = await httpClient.request(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/resolve`, {
    method: 'POST',
    body: JSON.stringify(payload || {})
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `resolveOrchestratorStep ${res.status}`);
  return body;
}

async function fetchOrchestratorSession(sessionId) {
  return await httpClient.json(
    `/api/orchestrator/sessions/${encodeURIComponent(sessionId)}`,
    {},
    '获取对话会话失败。'
  );
}

async function fetchOrchestratorSessions(params) {
  const res = await httpClient.request(`/api/orchestrator/sessions${memoryQueryString(params || { limit: 20 })}`);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `fetchOrchestratorSessions ${res.status}`);
  return payload;
}

async function fetchMemoryStatus() {
  return await httpClient.json('/api/orchestrator/memory/status', {}, '获取记忆状态失败。');
}

async function queryMemory(params) {
  const res = await httpClient.request('/api/orchestrator/memory/query', {
    method: 'POST',
    body: JSON.stringify(params || {})
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `queryMemory ${res.status}`);
  return payload;
}

function memoryQueryString(params) {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') sp.set(key, value);
  });
  const qs = sp.toString();
  return qs ? `?${qs}` : '';
}

async function listMemories(params) {
  const res = await httpClient.request(`/api/orchestrator/memory/list${memoryQueryString(params)}`);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `listMemories ${res.status}`);
  return payload;
}

async function createMemory(payload) {
  const res = await httpClient.request('/api/orchestrator/memory', {
    method: 'POST',
    body: JSON.stringify(payload || {})
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body.detail && body.detail.reason) || body.detail || `createMemory ${res.status}`);
  return body;
}

async function updateMemory(memoryId, payload) {
  const res = await httpClient.request(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload || {})
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body.detail && body.detail.reason) || body.detail || `updateMemory ${res.status}`);
  return body;
}

async function archiveMemory(memoryId, params) {
  const res = await httpClient.request(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}/archive${memoryQueryString(params)}`, {
    method: 'POST'
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `archiveMemory ${res.status}`);
  return body;
}

async function restoreMemory(memoryId, params) {
  const res = await httpClient.request(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}/restore${memoryQueryString(params)}`, {
    method: 'POST'
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `restoreMemory ${res.status}`);
  return body;
}

async function deleteMemory(memoryId, params) {
  const res = await httpClient.request(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}${memoryQueryString(params)}`, {
    method: 'DELETE'
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `deleteMemory ${res.status}`);
  return body;
}

async function fetchCurrentAuthUser() {
  return await httpClient.json('/api/auth/me', {}, '获取当前用户失败。');
}

window.AppServices = window.AppServices || {};
window.AppServices.api = {
  analyzeByUid, analyzeByFile, analyzeByUidStream, fetchTrace, fetchUiConfig, analyzeModule,
  createOrchestratorSession, sendOrchestratorMessage, openOrchestratorStream,
  ackOrchestratorTool, cancelOrchestratorRun, resolveOrchestratorStep, fetchOrchestratorSession, fetchOrchestratorSessions, fetchMemoryStatus, queryMemory,
  listMemories, createMemory, updateMemory, archiveMemory, restoreMemory, deleteMemory,
  fetchCurrentAuthUser
};
