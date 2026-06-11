// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// All fetch calls live here so future SSE / polling switches are local to this file.

async function analyzeByUid(trimmedUid, normalizedApplicationTime, country) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      uid: trimmedUid,
      application_time: normalizedApplicationTime,
      country: country || 'mx'
    })
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '分析请求失败，请稍后重试。');
  }

  return payload;
}

async function analyzeByFile(file, country) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('country', country || 'mx');

  const response = await fetch('/api/analyze-file', {
    method: 'POST',
    body: formData
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '文件分析请求失败，请检查文件内容。');
  }

  return payload;
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

  const response = await fetch('/api/analyze-stream', {
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
  const res = await fetch(`/api/trace/${encodeURIComponent(uid)}`);
  if (res.status === 404) return { uid, status: 'data_missing' };
  if (!res.ok) throw new Error(`trace_http_${res.status}`);
  return await res.json();
}

async function fetchUiConfig() {
  const res = await fetch('/api/ui-config');
  return res.ok ? await res.json() : {};
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
  const res = await fetch(`/api/analyze-module?${params.toString()}`);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(payload.detail || '模块分析请求失败，请稍后重试。');
  }
  return payload;
}

async function createOrchestratorSession(initialMessage, workspaceSnapshot, clientTurnId) {
  const res = await fetch('/api/orchestrator/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initial_message: initialMessage, workspace_snapshot: workspaceSnapshot, client_turn_id: clientTurnId || null })
  });
  if (!res.ok) throw new Error(`createOrchestratorSession ${res.status}`);
  return res.json();
}

async function sendOrchestratorMessage(sessionId, content, workspaceSnapshot, clientTurnId) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, workspace_snapshot: workspaceSnapshot, client_turn_id: clientTurnId || null })
  });
  if (!res.ok) throw new Error(`sendOrchestratorMessage ${res.status}`);
  return res.json();
}

function openOrchestratorStream(sessionId, handlers) {
  const es = new EventSource(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/stream`);
  // 2026-05-05 修复：es.onerror 在服务器正常 close（done 事件后）也会触发，
  // 过去会在业务跳出 onError，前端错误提示。用 closedNormally flag 区分主动 close 与真错。
  let closedNormally = false;
  const close = es.close.bind(es);
  es.close = () => { closedNormally = true; close(); };
  es.onmessage = (event) => {
    try {
      const evt = JSON.parse(event.data);
      handlers.onEvent && handlers.onEvent(evt);
      if (evt.type === 'done') {
        es.close();
        handlers.onClose && handlers.onClose();
      }
    } catch (err) {
      handlers.onError && handlers.onError(err);
    }
  };
  es.onerror = (err) => {
    if (closedNormally) return;
    // EventSource 在连接中断后会自动重试（readyState=CONNECTING，值为 0），
    // 这种是临时抖动，不该报错；只在 readyState=CLOSED (2) 才是真的断了。
    if (es.readyState !== 2) return;
    handlers.onError && handlers.onError(err);
    handlers.onClose && handlers.onClose();
  };
  return es;
}

async function ackOrchestratorTool(sessionId, toolCallId, decision) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_call_id: toolCallId, decision })
  });
  if (!res.ok) throw new Error(`ackOrchestratorTool ${res.status}`);
  return res.json();
}

async function cancelOrchestratorRun(sessionId, runId) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `cancelOrchestratorRun ${res.status}`);
  return payload;
}

async function resolveOrchestratorStep(sessionId, payload) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `resolveOrchestratorStep ${res.status}`);
  return body;
}

async function fetchOrchestratorSession(sessionId) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`fetchOrchestratorSession ${res.status}`);
  return res.json();
}

async function fetchOrchestratorSessions(params) {
  const res = await fetch(`/api/orchestrator/sessions${memoryQueryString(params || { limit: 20 })}`);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `fetchOrchestratorSessions ${res.status}`);
  return payload;
}

async function fetchMemoryStatus() {
  const res = await fetch('/api/orchestrator/memory/status');
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `fetchMemoryStatus ${res.status}`);
  return payload;
}

async function queryMemory(params) {
  const res = await fetch('/api/orchestrator/memory/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
  const res = await fetch(`/api/orchestrator/memory/list${memoryQueryString(params)}`);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.detail || `listMemories ${res.status}`);
  return payload;
}

async function createMemory(payload) {
  const res = await fetch('/api/orchestrator/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body.detail && body.detail.reason) || body.detail || `createMemory ${res.status}`);
  return body;
}

async function updateMemory(memoryId, payload) {
  const res = await fetch(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body.detail && body.detail.reason) || body.detail || `updateMemory ${res.status}`);
  return body;
}

async function archiveMemory(memoryId, params) {
  const res = await fetch(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}/archive${memoryQueryString(params)}`, {
    method: 'POST'
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `archiveMemory ${res.status}`);
  return body;
}

async function restoreMemory(memoryId, params) {
  const res = await fetch(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}/restore${memoryQueryString(params)}`, {
    method: 'POST'
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `restoreMemory ${res.status}`);
  return body;
}

async function deleteMemory(memoryId, params) {
  const res = await fetch(`/api/orchestrator/memory/${encodeURIComponent(memoryId)}${memoryQueryString(params)}`, {
    method: 'DELETE'
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `deleteMemory ${res.status}`);
  return body;
}

window.AppServices = window.AppServices || {};
window.AppServices.api = {
  analyzeByUid, analyzeByFile, analyzeByUidStream, fetchTrace, fetchUiConfig, analyzeModule,
  createOrchestratorSession, sendOrchestratorMessage, openOrchestratorStream,
  ackOrchestratorTool, cancelOrchestratorRun, resolveOrchestratorStep, fetchOrchestratorSession, fetchOrchestratorSessions, fetchMemoryStatus, queryMemory,
  listMemories, createMemory, updateMemory, archiveMemory, restoreMemory, deleteMemory
};
