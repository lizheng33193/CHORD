// Top-level entry — progressive module loading.
// UID mode: fake loading animation → dashboard with per-module progressive rendering.
// File mode: fake loading animation → /api/analyze-file one-shot → dashboard.

const { useState, useRef, useEffect, useCallback } = React;
const { AuthGate, HomeView, LoadingView, DashboardView } = window.AppComponents;
const { normalizeAnalysisResult, buildEmptyAgentOutput, normalizeApplicationTime } = window.AppUtils.normalize;
const { analyzeByFile, analyzeModule, fetchUiConfig, fetchTrace } = window.AppServices.api;
const authStore = window.AppState.authStore;
// AuthGate restores the persisted access_token before rendering AppShell.
// The auth shell keeps login / logout state outside the profiling workspace.

const UID_PATTERN = /^\d{18}$/;

const DEFAULT_UID_TRANSITION_DURATION_MS = 4000;

const LOADING_TEXTS = [
  '正在唤醒多智能体系统...',
  'App画像Agent：正在提取安装列表与分类标签...',
  '行为画像Agent：正在分析埋点行为与活跃度...',
  '征信画像Agent：正在解析征信报告与风险结果...',
  '综合画像Agent：正在进行三维整合推理...'
];

const CORE_MODULES = ['app', 'behavior', 'credit'];
const MODULE_RESULT_MAP = {
  app: 'app_profile',
  behavior: 'behavior_profile',
  credit: 'credit_profile',
  comprehensive: 'comprehensive_profile',
  product: 'product_advice',
  ops: 'ops_advice'
};

const VALID_DASHBOARD_TABS = ['comprehensive', 'app', 'behavior', 'credit', 'product', 'ops', 'trace', 'knowledge', 'chat'];
const WORKSPACE_SNAPSHOT_STORAGE_KEY = 'maps-lz.workspace-snapshot.v1';

function getInitialDashboardTab() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab');
  if (VALID_DASHBOARD_TABS.includes(tab) && tab !== 'chat') return tab;
  if (params.get('session')) return 'comprehensive';
  return 'comprehensive';
}

function getInitialViewFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab');
  if (tab === 'chat' || params.get('session')) return 'dashboard';
  return 'home';
}

function getInitialChatFocusFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('tab') === 'chat' || Boolean(params.get('session'));
}

function getInitialSessionIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('session') || '';
}

function getInitialCountry() {
  const params = new URLSearchParams(window.location.search);
  const v = params.get('country');
  if (v === 'th') return 'th';
  if (v === 'mx') return 'mx';
  const authState = authStore && authStore.getState ? authStore.getState() : null;
  if (authState && authState.preferredCountry) {
    return String(authState.preferredCountry).toLowerCase();
  }
  return (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.country) || 'mx';
}

function createInitialModuleStates(status) {
  status = status || 'idle';
  return {
    app: { status: status, error: '' },
    behavior: { status: status, error: '' },
    credit: { status: status, error: '' },
    comprehensive: { status: 'idle', error: '' },
    product: { status: 'idle', error: '' },
    ops: { status: 'idle', error: '' },
    trace: { status: 'idle', error: '' }
  };
}

function buildWorkspaceSnapshotFromAppState({
  country,
  applicationTime,
  analysisResults,
  moduleStates,
  moduleStatesByUid,
  traceSeedByUid,
  selectedResultIndex,
}) {
  return {
    country: country || 'mx',
    applicationTime: applicationTime || '',
    analysisResults: Array.isArray(analysisResults) ? analysisResults : [],
    moduleStates: moduleStates && typeof moduleStates === 'object' ? moduleStates : createInitialModuleStates(),
    moduleStatesByUid: moduleStatesByUid && typeof moduleStatesByUid === 'object' ? moduleStatesByUid : {},
    traceSeedByUid: traceSeedByUid && typeof traceSeedByUid === 'object' ? traceSeedByUid : {},
    selectedResultIndex: Number.isFinite(Number(selectedResultIndex)) ? Number(selectedResultIndex) : 0,
  };
}

function buildChatWorkspaceSnapshotFromAppState({
  country,
  applicationTime,
  analysisResults,
  selectedResultIndex,
  moduleStates,
  moduleStatesByUid,
}) {
  const results = Array.isArray(analysisResults) ? analysisResults : [];
  const selected = results[selectedResultIndex] || results[0];
  if (!selected || !selected.uid) return null;
  const effectiveStates = (moduleStatesByUid && moduleStatesByUid[selected.uid]) || moduleStates || createInitialModuleStates();
  const normalizedApplicationTime = normalizeApplicationTime(applicationTime) || null;
  const compactRows = Object.entries(MODULE_RESULT_MAP)
    .filter(([moduleName]) => moduleName !== 'trace')
    .map(([moduleName, resultKey]) => {
      const moduleState = effectiveStates[moduleName] || {};
      const agentOutput = selected[resultKey];
      if (moduleState.status !== 'success' || !agentOutput) return null;
      return {
        uid: selected.uid,
        module: moduleName,
        summary: agentOutput.summary || '',
        structured_result: (agentOutput.structured_result && typeof agentOutput.structured_result === 'object') ? agentOutput.structured_result : {},
        country: country || 'mx',
        applicationTime: normalizedApplicationTime,
      };
    })
    .filter(Boolean);
  if (!compactRows.length) return null;
  return {
    country: country || 'mx',
    applicationTime: normalizedApplicationTime,
    results: compactRows,
  };
}

function _readWorkspaceSnapshotFromSessionStorage() {
  if (typeof window === 'undefined' || !window.sessionStorage) return null;
  try {
    const raw = window.sessionStorage.getItem(WORKSPACE_SNAPSHOT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_err) {
    return null;
  }
}

function _applyProfileResultRowToWorkspace(resultsByUid, moduleStatesByUid, row) {
  if (!row || !row.uid || !row.module) return;
  const resultKey = MODULE_RESULT_MAP[row.module];
  if (!resultKey) return;
  const targetUid = row.uid;
  if (!resultsByUid[targetUid]) {
    resultsByUid[targetUid] = normalizeAnalysisResult({ uid: targetUid }, targetUid);
  }
  if (!moduleStatesByUid[targetUid]) {
    moduleStatesByUid[targetUid] = createInitialModuleStates();
  }
  const payload = row.payload || {};
  resultsByUid[targetUid] = {
    ...resultsByUid[targetUid],
    uid: targetUid,
    [resultKey]: {
      summary: payload.summary || '',
      structured_result: (payload.structured_result && typeof payload.structured_result === 'object') ? payload.structured_result : {},
      charts: Array.isArray(payload.charts) ? payload.charts : [],
      report_markdown: payload.report_markdown || '',
    },
  };
  moduleStatesByUid[targetUid] = {
    ...moduleStatesByUid[targetUid],
    [row.module]: { status: row.status === 'error' ? 'error' : 'success', error: row.error || '' },
  };
}

function restoreWorkspaceSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return null;
  const analysisResults = Array.isArray(snapshot.analysisResults)
    ? snapshot.analysisResults.map((item, index) => normalizeAnalysisResult(item, (item && item.uid) || `restored_${index + 1}`))
    : [];
  const moduleStates = snapshot.moduleStates && typeof snapshot.moduleStates === 'object'
    ? snapshot.moduleStates
    : createInitialModuleStates();
  const moduleStatesByUid = snapshot.moduleStatesByUid && typeof snapshot.moduleStatesByUid === 'object'
    ? snapshot.moduleStatesByUid
    : {};
  const traceSeedByUid = snapshot.traceSeedByUid && typeof snapshot.traceSeedByUid === 'object'
    ? snapshot.traceSeedByUid
    : {};
  const maxIndex = Math.max(0, analysisResults.length - 1);
  const selectedResultIndex = Math.min(maxIndex, Math.max(0, Number(snapshot.selectedResultIndex) || 0));
  return {
    country: snapshot.country === 'th' ? 'th' : 'mx',
    applicationTime: snapshot.applicationTime || '2026-04-15T12:00',
    analysisResults,
    moduleStates,
    moduleStatesByUid,
    traceSeedByUid,
    selectedResultIndex,
  };
}

function restoreWorkspaceFromSession(sessionPayload) {
  if (!sessionPayload || typeof sessionPayload !== 'object') return null;
  const resultsByUid = {};
  const moduleStatesByUid = {};
  const traceSeedByUid = {};
  const restoredUidOrder = [];
  let firstSuccessUid = '';
  let restoredApplicationTime = '';

  function rememberUid(targetUid) {
    if (!targetUid || restoredUidOrder.includes(targetUid)) return;
    restoredUidOrder.push(targetUid);
  }

  function applyRow(uidValue, moduleName, payload, status, error) {
    if (!uidValue || !moduleName || !payload) return;
    rememberUid(uidValue);
    _applyProfileResultRowToWorkspace(resultsByUid, moduleStatesByUid, {
      uid: uidValue,
      module: moduleName,
      payload,
      status,
      error,
    });
    if (!firstSuccessUid && status !== 'error') firstSuccessUid = uidValue;
  }

  const toolCalls = Array.isArray(sessionPayload.tool_calls) ? sessionPayload.tool_calls : [];
  toolCalls.forEach((record) => {
    if (!record || typeof record !== 'object') return;
    if (record.tool_name === 'run_profile' && record.output && Array.isArray(record.output.results)) {
      if (!restoredApplicationTime && record.input && typeof record.input.app_time === 'string' && record.input.app_time) {
        restoredApplicationTime = record.input.app_time;
      }
      record.output.results.forEach((row) => {
        if (!row || typeof row !== 'object') return;
        const payload = row.result && row.result.data;
        const status = row.result && row.result.status;
        if (status === 'ok' && payload) {
          applyRow(row.uid, row.module, payload, 'success', '');
        } else if (row.uid && row.module) {
          rememberUid(row.uid);
          moduleStatesByUid[row.uid] = moduleStatesByUid[row.uid] || createInitialModuleStates();
          moduleStatesByUid[row.uid] = {
            ...moduleStatesByUid[row.uid],
            [row.module]: { status: 'error', error: (row.result && row.result.error && row.result.error.message) || '该模块分析失败' },
          };
        }
      });
    }
    if (record.tool_name === 'run_trace' && record.status === 'done' && record.output && record.input && record.input.uid) {
      const traceUid = record.input.uid;
      rememberUid(traceUid);
      traceSeedByUid[traceUid] = { requestStatus: 'success', response: record.output };
      if (!resultsByUid[traceUid]) {
        resultsByUid[traceUid] = normalizeAnalysisResult({ uid: traceUid }, traceUid);
      }
      moduleStatesByUid[traceUid] = moduleStatesByUid[traceUid] || createInitialModuleStates();
      moduleStatesByUid[traceUid] = {
        ...moduleStatesByUid[traceUid],
        trace: { status: 'success', error: '' },
      };
    }
  });

  const workspaceSnapshot = sessionPayload.active_entities && sessionPayload.active_entities.workspace_snapshot;
  if (workspaceSnapshot && typeof workspaceSnapshot === 'object' && Array.isArray(workspaceSnapshot.results)) {
    if (!restoredApplicationTime && workspaceSnapshot.applicationTime) {
      restoredApplicationTime = workspaceSnapshot.applicationTime;
    }
    workspaceSnapshot.results.forEach((row) => {
      if (!row || typeof row !== 'object') return;
      const existingState = moduleStatesByUid[row.uid] && moduleStatesByUid[row.uid][row.module];
      if (existingState && existingState.status === 'success') return;
      applyRow(row.uid, row.module, {
        summary: row.summary || '',
        structured_result: (row.structured_result && typeof row.structured_result === 'object') ? row.structured_result : {},
        charts: [],
        report_markdown: '',
      }, 'success', '');
    });
  }

  const orderedResults = restoredUidOrder.map((targetUid) => resultsByUid[targetUid]).filter(Boolean);
  const selectedUid = firstSuccessUid || (orderedResults[0] && orderedResults[0].uid) || '';
  const selectedResultIndex = orderedResults.findIndex((item) => item && item.uid === selectedUid);
  return {
    country: sessionPayload.country === 'th' ? 'th' : 'mx',
    applicationTime: restoredApplicationTime || '2026-04-15T12:00',
    analysisResults: orderedResults,
    moduleStates: (selectedUid && moduleStatesByUid[selectedUid]) || createInitialModuleStates(),
    moduleStatesByUid,
    traceSeedByUid,
    selectedResultIndex: selectedResultIndex >= 0 ? selectedResultIndex : 0,
  };
}

const INITIAL_WORKSPACE_STATE = restoreWorkspaceSnapshot(_readWorkspaceSnapshotFromSessionStorage()) || null;

function AppShell({ currentUser, onLogout, setPreferredCountry, setPreferredProjectId }) {
  const authState = authStore.useAuthState();
  const [view, setView] = useState(getInitialViewFromUrl);
  const [uid, setUid] = useState('');
  const [uidError, setUidError] = useState('');
  const [applicationTime, setApplicationTime] = useState(() => (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.applicationTime) || '2026-04-15T12:00');
  const [activeTab, setActiveTab] = useState(getInitialDashboardTab);
  const [analysisResults, setAnalysisResults] = useState(() => (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.analysisResults) || []);
  const [selectedResultIndex, setSelectedResultIndex] = useState(() => (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.selectedResultIndex) || 0);
  const [errorMessage, setErrorMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [moduleStates, setModuleStates] = useState(() => (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.moduleStates) || createInitialModuleStates());
  // 2026-05-04 方案 A v2：按 UID 隔离的模块状态。NL Chat 多 UID 跑批不再互相覆盖。
  // DashboardView 根据 selectedResult.uid 优先读这里，找不到再回退到全局 moduleStates。
  const [moduleStatesByUid, setModuleStatesByUid] = useState(() => (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.moduleStatesByUid) || {});
  const [uidTransitionDurationMs, setUidTransitionDurationMs] = useState(DEFAULT_UID_TRANSITION_DURATION_MS);
  const [chatFocusRequested, setChatFocusRequested] = useState(getInitialChatFocusFromUrl);
  const [chatSessionId, setChatSessionId] = useState(getInitialSessionIdFromUrl);
  // 2026-05-04 方案 A：NL Chat 跑过的 trace 结果种子，注入 DashboardView 的 traceCacheByUid，
  // 避免用户跳到 trace tab 时再发一次 /api/trace 请求（trace 同样会跑 LLM）。
  const [traceSeedByUid, setTraceSeedByUid] = useState(() => (INITIAL_WORKSPACE_STATE && INITIAL_WORKSPACE_STATE.traceSeedByUid) || {});
  const userPermissions = Array.isArray(currentUser && currentUser.permissions) ? currentUser.permissions : [];
  const [supportedCountries, setSupportedCountries] = useState(['mx', 'th']);

  const [country, setCountry] = useState(getInitialCountry);
  const authorizedScopes = Array.isArray(authState && authState.authorizedScopes) ? authState.authorizedScopes : [];
  const preferredProjectId = authState && authState.preferredProjectId ? String(authState.preferredProjectId) : '';
  const canManageProject = !currentUser || currentUser.is_superuser || userPermissions.includes('project:manage');

  function getProjectEntries(scopes) {
    const entries = [];
    const seen = new Set();
    (scopes || []).forEach((scope) => {
      if (!scope || seen.has(scope.project_id)) return;
      seen.add(scope.project_id);
      entries.push(scope);
    });
    return entries;
  }

  function getAllowedCountries(scopes, projectId, backendSupportedCountries) {
    const supported = Array.isArray(backendSupportedCountries) && backendSupportedCountries.length
      ? backendSupportedCountries
      : ['mx', 'th'];
    const projectScopes = (scopes || []).filter((scope) => !projectId || scope.project_id === projectId);
    if (!projectScopes.length) return supported;
    if (projectScopes.some((scope) => scope.country == null)) return supported;
    return supported.filter((code) => projectScopes.some((scope) => scope.country === code));
  }

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set('country', country);
    window.history.replaceState({}, '', url.toString());
  }, [country]);

  useEffect(() => {
    if (setPreferredCountry) {
      setPreferredCountry(country);
    }
  }, [country, setPreferredCountry]);

  useEffect(() => {
    if (!currentUser || !setPreferredProjectId || !currentUser.default_project_id) return;
    if (!preferredProjectId) {
      setPreferredProjectId(currentUser.default_project_id);
    }
  }, [currentUser, preferredProjectId, setPreferredProjectId]);

  useEffect(() => {
    const projectEntries = getProjectEntries(authorizedScopes);
    if (!projectEntries.length) return;
    const activeProjectId = preferredProjectId || projectEntries[0].project_id;
    const projectStillAllowed = projectEntries.some((scope) => scope.project_id === activeProjectId);
    if (!projectStillAllowed && setPreferredProjectId) {
      setPreferredProjectId(projectEntries[0].project_id);
      return;
    }
    const allowedCountries = getAllowedCountries(authorizedScopes, activeProjectId, supportedCountries);
    if (!allowedCountries.includes(country)) {
      setCountry(allowedCountries[0] || 'mx');
    }
  }, [authorizedScopes, preferredProjectId, supportedCountries, country, setPreferredProjectId]);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.sessionStorage) return;
    try {
      const snapshot = buildWorkspaceSnapshotFromAppState({
        country,
        applicationTime,
        analysisResults,
        moduleStates,
        moduleStatesByUid,
        traceSeedByUid,
        selectedResultIndex,
      });
      window.sessionStorage.setItem(WORKSPACE_SNAPSHOT_STORAGE_KEY, JSON.stringify(snapshot));
    } catch (_err) {}
  }, [country, applicationTime, analysisResults, moduleStates, moduleStatesByUid, traceSeedByUid, selectedResultIndex]);

  function resetAnalysisStateForCountry() {
    setAnalysisResults([]);
    setSelectedResultIndex(0);
    setModuleStates(createInitialModuleStates());
    setModuleStatesByUid({});
    setErrorMessage('');
    setTraceSeedByUid({});
    setChatSessionId('');
  }

  function handleCountryChange(next) {
    if (next === country) return;
    if (!window.confirm('切换国家会清空当前分析结果，是否继续？')) return;
    resetAnalysisStateForCountry();
    setCountry(next);
  }

  function handleProjectChange(nextProjectId) {
    if (!nextProjectId || nextProjectId === preferredProjectId) return;
    if (!window.confirm('切换项目会清空当前分析结果，是否继续？')) return;
    resetAnalysisStateForCountry();
    if (setPreferredProjectId) {
      setPreferredProjectId(nextProjectId);
    }
    const nextAllowedCountries = getAllowedCountries(authorizedScopes, nextProjectId, supportedCountries);
    setCountry(nextAllowedCountries[0] || 'mx');
  }

  const handleChatSessionChange = useCallback((nextSessionId) => {
    setChatSessionId(nextSessionId || '');
    if (nextSessionId) {
      setChatFocusRequested(true);
      setView('dashboard');
    }
  }, []);

  const handleRestoreWorkspaceSession = useCallback((sessionPayload) => {
    const restored = restoreWorkspaceFromSession(sessionPayload);
    if (!restored) return;
    setAnalysisResults(restored.analysisResults);
    setSelectedResultIndex(restored.selectedResultIndex);
    setModuleStates(restored.moduleStates);
    setModuleStatesByUid(restored.moduleStatesByUid);
    setTraceSeedByUid(restored.traceSeedByUid);
    setApplicationTime(restored.applicationTime);
    setCountry(restored.country);
    setActiveTab('comprehensive');
    setView('dashboard');
  }, []);

  // Fetch backend-configurable transition duration once on mount.
  useEffect(() => {
    let isMounted = true;
    fetchUiConfig()
      .then((config) => {
        const d = Number(config && config.uid_transition_duration_ms);
        if (isMounted && Number.isFinite(d) && d >= 0) {
          setUidTransitionDurationMs(d);
        }
        const backendSupportedCountries = Array.isArray(config && config.supported_countries)
          ? config.supported_countries.map((countryCode) => String(countryCode).toLowerCase())
          : [];
        if (isMounted && backendSupportedCountries.length) {
          setSupportedCountries(backendSupportedCountries);
        }
      })
      .catch(() => {});
    return () => { isMounted = false; };
  }, []);

  useEffect(() => {
    if (view !== 'dashboard') return;
    if (activeTab === 'knowledge' && !canManageProject) {
      setActiveTab('comprehensive');
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const tabTarget = (chatSessionId || chatFocusRequested) ? 'chat' : activeTab;
    if (params.get('tab') === 'knowledge' && !canManageProject) {
      params.set('tab', 'comprehensive');
    }
    if (chatSessionId) {
      params.set('session', chatSessionId);
    } else {
      params.delete('session');
    }
    if (params.get('tab') !== tabTarget) {
      params.set('tab', tabTarget);
    }
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
    window.history.replaceState({}, '', nextUrl);
  }, [view, activeTab, chatFocusRequested, chatSessionId, canManageProject]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab === 'knowledge' && !canManageProject) {
      setActiveTab('comprehensive');
    }
  }, [canManageProject]);

  function playLoadingSequence() {
    return new Promise((resolve) => {
      const durationMs = Math.max(0, Number(uidTransitionDurationMs) || 0);
      resolve();  // resolve immediately — caller awaits this then switches to dashboard
      // The LoadingView component handles its own text cycling internally
    });
  }

  function _updateModuleResult(targetUid, moduleName, moduleResult) {
    const resultKey = MODULE_RESULT_MAP[moduleName];
    if (!resultKey) return;
    setAnalysisResults((prev) => {
      // 2026-05-04 方案 A：支持 chat 路径多 UID 写入。先按 uid 查找已存在条目，
      // 找不到再追加新条目（保留旧 UID 模式：prev 为空时创建第 0 条）。
      const next = prev.length ? [...prev] : [];
      let idx = next.findIndex((r) => r && r.uid === targetUid);
      if (idx < 0) {
        next.push(normalizeAnalysisResult({ uid: targetUid }, targetUid));
        idx = next.length - 1;
      }
      const current = next[idx];
      const normalized = moduleResult || {};
      next[idx] = {
        ...current,
        uid: targetUid,
        [resultKey]: {
          summary: (normalized.summary != null ? normalized.summary : '') || '',
          structured_result: (normalized.structured_result && typeof normalized.structured_result === 'object') ? normalized.structured_result : {},
          charts: Array.isArray(normalized.charts) ? normalized.charts : [],
          report_markdown: (normalized.report_markdown != null ? normalized.report_markdown : '') || ''
        }
      };
      return next;
    });
  }

  // 2026-05-04 方案 A v2：NL Chat 跑完 run_profile 后回写 analysisResults +
  // moduleStatesByUid（按 UID 隔离，多 UID 跑批不会互相覆盖）。
  function ingestProfileFromChat({ uid: targetUid, module, payload }) {
    if (!targetUid || !module || !payload) return;
    const isOk = payload.status === 'ok' && payload.data;
    if (isOk) {
      _updateModuleResult(targetUid, module, payload.data);
    }
    const errMsg = isOk ? '' : ((payload.error && payload.error.message) || '该模块分析失败');
    setModuleStatesByUid((prev) => {
      const cur = prev[targetUid] || createInitialModuleStates();
      return {
        ...prev,
        [targetUid]: {
          ...cur,
          [module]: { status: isOk ? 'success' : 'error', error: errMsg }
        }
      };
    });
  }

  // 2026-05-04 方案 A v3：tool_started(run_profile) 时，前端预派发 (uids × modules) loading 状态，
  // 让 6 个 Tab 卡片在长时间 LLM 跑批期间立即显示"分析中..."动画，避免 UI 看起来卡死。
  function ingestProfilesPending({ uids, modules }) {
    if (!Array.isArray(uids) || !Array.isArray(modules)) return;
    if (uids.length === 0 || modules.length === 0) return;
    // 1) 给每个 uid 在 analysisResults 里建壳（如果不存在），让 dashboard 顶部 UID 切换器立刻列出来
    setAnalysisResults((prev) => {
      let next = prev;
      let mutated = false;
      uids.forEach((u) => {
        if (!next.find((r) => r && r.uid === u)) {
          if (!mutated) { next = [...prev]; mutated = true; }
          next.push(normalizeAnalysisResult({ uid: u }, u));
        }
      });
      return mutated ? next : prev;
    });
    // 2) 把 (uid × module) 全置 loading，dashboard Tab 卡片立即出现"分析中..."
    setModuleStatesByUid((prev) => {
      const next = { ...prev };
      uids.forEach((u) => {
        const cur = next[u] || createInitialModuleStates();
        const merged = { ...cur };
        modules.forEach((m) => {
          if (!merged[m] || merged[m].status !== 'success') {
            merged[m] = { status: 'loading', error: '' };
          }
        });
        next[u] = merged;
      });
      return next;
    });
  }

  // 2026-05-04 方案 A：NL Chat 跑过的 trace 结果，缓存到 traceSeedByUid，
  // DashboardView 接管时优先读种子，避免重复 fetch 重复 LLM。
  function ingestTraceFromChat({ uid: targetUid, payload }) {
    if (!targetUid || !payload) return;
    setTraceSeedByUid((prev) => ({
      ...prev,
      [targetUid]: { requestStatus: 'success', response: payload }
    }));
    // trace uid 之前未出现在 analysisResults 时，也建一个壳条目（让 dashboard 切换面板可用）
    setAnalysisResults((prev) => {
      const idx = prev.findIndex((r) => r && r.uid === targetUid);
      if (idx >= 0) return prev;
      return prev.concat([normalizeAnalysisResult({ uid: targetUid }, targetUid)]);
    });
  }

  async function loadModuleForUid(targetUid, moduleName, normalizedApplicationTime) {
    setModuleStates((prev) => ({
      ...prev,
      [moduleName]: { status: 'loading', error: '' }
    }));
    try {
      if (moduleName === 'trace') {
        const traceResult = await fetchTrace(targetUid);
        setAnalysisResults((prev) => {
          const next = prev.length ? [...prev] : [normalizeAnalysisResult({uid: targetUid}, targetUid)];
          next[0] = { ...next[0], _trace: traceResult };
          return next;
        });
        setModuleStates((prev) => ({ ...prev, trace: { status: 'success', error: '' } }));
        return true;
      }
      const payload = await analyzeModule(targetUid, moduleName, normalizedApplicationTime, country);
      if ((payload && payload.status) !== 'ok' || !(payload && payload.data)) {
        const backendError = (payload && payload.error && typeof payload.error === 'object') ? payload.error : {};
        throw new Error(backendError.message || '该模块分析失败，请稍后重试。');
      }
      _updateModuleResult(targetUid, moduleName, payload.data);
      setModuleStates((prev) => ({
        ...prev,
        [moduleName]: { status: 'success', error: '' }
      }));
      return true;
    } catch (error) {
      setModuleStates((prev) => ({
        ...prev,
        [moduleName]: { status: 'error', error: error.message || '该模块分析失败，请稍后重试。' }
      }));
      return false;
    }
  }

  function preloadModulesForUid(targetUid, normalizedApplicationTime) {
    // Fire core modules in parallel
    Promise.all(
      CORE_MODULES.map((m) => loadModuleForUid(targetUid, m, normalizedApplicationTime))
    ).then((coreStatuses) => {
      if (coreStatuses.every(Boolean)) {
        // All 3 core modules succeeded → request comprehensive
        loadModuleForUid(targetUid, 'comprehensive', normalizedApplicationTime).then((compOk) => {
          if (compOk) {
            // comprehensive succeeded → request product + ops in parallel
            loadModuleForUid(targetUid, 'product', normalizedApplicationTime);
            loadModuleForUid(targetUid, 'ops', normalizedApplicationTime);
          } else {
            // comprehensive failed → product/ops cannot run
            setModuleStates((prev) => ({
              ...prev,
              product: { status: 'error', error: '产品策略依赖综合画像，综合画像分析失败。' },
              ops: { status: 'error', error: '运营策略依赖综合画像，综合画像分析失败。' }
            }));
          }
        });
        return;
      }
      // At least one core module failed — comprehensive cannot run
      setModuleStates((prev) => ({
        ...prev,
        comprehensive: { status: 'error', error: '综合画像依赖 App / Behavior / Credit，需等待三个基础模块全部成功。' },
        product: { status: 'error', error: '产品策略依赖综合画像，综合画像未完成。' },
        ops: { status: 'error', error: '运营策略依赖综合画像，综合画像未完成。' }
      }));
    });
  }

  function retryModule(moduleName) {
    const selectedResult = analysisResults[selectedResultIndex] || {};
    const targetUid = (selectedResult.uid || uid.trim() || '');
    const normalizedApplicationTime = normalizeApplicationTime(applicationTime);
    if (!targetUid || !moduleName) return;
    if (moduleName === 'comprehensive') {
      const coreReady = CORE_MODULES.every((name) => (moduleStates[name] && moduleStates[name].status) === 'success');
      if (!coreReady) {
        setModuleStates((prev) => ({
          ...prev,
          comprehensive: { status: 'error', error: '综合画像依赖 App / Behavior / Credit，需等待三个基础模块全部成功。' }
        }));
        return;
      }
    }
    loadModuleForUid(targetUid, moduleName, normalizedApplicationTime);
  }

  async function handleAnalyze({ mode }) {
    const trimmedUid = uid.trim();
    const normalizedApplicationTime = normalizeApplicationTime(applicationTime);

    if (mode === 'uid' && !trimmedUid) {
      setUidError('请输入 18 位纯数字 UID。');
      return;
    }
    if (mode === 'uid' && !UID_PATTERN.test(trimmedUid)) {
      setUidError('UID 格式错误：仅支持 18 位纯数字。');
      return;
    }
    if (mode === 'uid' && !normalizedApplicationTime) {
      window.alert('请输入申请时间');
      return;
    }
    if (mode === 'file' && !selectedFile) {
      window.alert('请先选择 txt 或 csv 文件');
      return;
    }

    setErrorMessage('');
    setUidError('');
    setChatFocusRequested(false);
    setChatSessionId('');
    setView('loading');

    try {
      if (mode === 'uid') {
        // Initialize empty result + module states
        setAnalysisResults([normalizeAnalysisResult({ uid: trimmedUid }, trimmedUid)]);
        setSelectedResultIndex(0);
        setActiveTab('comprehensive');
        setModuleStates(createInitialModuleStates('loading'));

        // Start loading modules in background (non-blocking)
        preloadModulesForUid(trimmedUid, normalizedApplicationTime);

        // Wait for transition animation, then switch to dashboard
        await new Promise((resolve) => {
          window.setTimeout(resolve, Math.max(0, Number(uidTransitionDurationMs) || 0));
        });
        setView('dashboard');
        return;
      }

      // File mode — one-shot with loading animation
      const dataPromise = analyzeByFile(selectedFile, country);
      const [payload] = await Promise.all([
        dataPromise,
        new Promise((resolve) => {
          window.setTimeout(resolve, Math.max(0, Number(uidTransitionDurationMs) || 0));
        })
      ]);
      const rawResults = Array.isArray(payload && payload.results) ? payload.results : [];
      if (!rawResults.length) {
        throw new Error('后端未返回有效画像结果。');
      }
      const normalizedResults = rawResults.map((item, index) =>
        normalizeAnalysisResult(item, (item && item.uid) || trimmedUid || `user_${index + 1}`)
      );
      setAnalysisResults(normalizedResults);
      setModuleStates(createInitialModuleStates('success'));
      setSelectedResultIndex(0);
      setActiveTab('comprehensive');
      setView('dashboard');
    } catch (error) {
      setErrorMessage(error.message || '请求失败，请检查服务是否已启动。');
      setView('home');
    }
  }

  if (view === 'home') {
    return (
      <HomeView
        uid={uid}
        setUid={setUid}
        uidError={uidError}
        setUidError={setUidError}
        applicationTime={applicationTime}
        setApplicationTime={setApplicationTime}
        selectedFile={selectedFile}
        setSelectedFile={setSelectedFile}
        onStartUid={() => handleAnalyze({ mode: 'uid' })}
        onStartFile={() => handleAnalyze({ mode: 'file' })}
        onStartChat={() => { setActiveTab('comprehensive'); setChatFocusRequested(true); setView('dashboard'); }}
        errorMessage={errorMessage}
        currentUser={currentUser}
        onLogout={onLogout}
        authorizedScopes={authorizedScopes}
        supportedCountries={supportedCountries}
        projectId={preferredProjectId}
        onProjectChange={handleProjectChange}
        country={country}
        onCountryChange={handleCountryChange}
      />
    );
  }

  if (view === 'loading') {
    return <LoadingView loadingTexts={LOADING_TEXTS} durationMs={uidTransitionDurationMs} />;
  }

  return (
    <DashboardView
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      analysisResults={analysisResults}
      selectedResultIndex={selectedResultIndex}
      setSelectedResultIndex={setSelectedResultIndex}
      moduleStates={moduleStates}
      onRetryModule={retryModule}
      onBack={() => { setChatFocusRequested(false); setView('home'); }}
      onChatProfileReady={ingestProfileFromChat}
      onChatProfilesPending={ingestProfilesPending}
      onChatTraceReady={ingestTraceFromChat}
      traceSeedByUid={traceSeedByUid}
      moduleStatesByUid={moduleStatesByUid}
      currentUser={currentUser}
      permissions={userPermissions}
      onLogout={onLogout}
      authorizedScopes={authorizedScopes}
      supportedCountries={supportedCountries}
      projectId={preferredProjectId}
      onProjectChange={handleProjectChange}
      country={country}
      onCountryChange={handleCountryChange}
      chatFocusRequested={chatFocusRequested}
      onChatFocusChange={setChatFocusRequested}
      chatSessionId={chatSessionId}
      onChatSessionChange={handleChatSessionChange}
      chatWorkspaceSnapshot={buildChatWorkspaceSnapshotFromAppState({
        country,
        applicationTime,
        analysisResults,
        selectedResultIndex,
        moduleStates,
        moduleStatesByUid,
      })}
      onRestoreWorkspaceSession={handleRestoreWorkspaceSession}
    />
  );
}

function App() {
  return (
    <AuthGate>
      {({ currentUser, onLogout, setPreferredCountry, setPreferredProjectId }) => (
        <AppShell
          currentUser={currentUser}
          onLogout={onLogout}
          setPreferredCountry={setPreferredCountry}
          setPreferredProjectId={setPreferredProjectId}
        />
      )}
    </AuthGate>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
