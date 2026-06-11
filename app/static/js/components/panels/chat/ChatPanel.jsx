const {
  ChatMessageList,
  ChatInputBox,
  ChatToolCallStream,
  ChatExecutionTraceCard,
  ChatAckCard,
  ChatBudgetBanner,
  ChatProviderFallbackBanner,
  MemoryInspector,
  chatReducer,
  chatInitialState,
} = window.AppComponents;
const { createOrchestratorSession, sendOrchestratorMessage, openOrchestratorStream, ackOrchestratorTool, cancelOrchestratorRun, resolveOrchestratorStep, fetchOrchestratorSession } = window.AppServices.api;
const { Bot, Clock3, PanelRightClose, X } = window.LucideReact || {};
const { useReducer, useState, useRef, useEffect, useCallback } = React;

const PROFILE_MODULE_ORDER = ['app', 'behavior', 'credit', 'comprehensive', 'product', 'ops'];
const PROFILE_MODULE_LABELS = {
  comprehensive: '综合画像',
  app: 'App画像',
  behavior: '行为画像',
  credit: '征信画像',
  product: '产品策略',
  ops: '运营策略',
};

function profileResultKey(toolCallId, uid, module) {
  return `${toolCallId}:${uid}:${module}`;
}

function normalizeToolStatus(status) {
  if (status === 'done' || status === 'ok') return 'ok';
  if (status === 'cancelled') return 'cancelled';
  if (status === 'error' || status === 'failed') return 'error';
  return 'pending';
}

function _restoreMessages(history) {
  return (Array.isArray(history && history.messages) ? history.messages : [])
    .filter((message) => message && (message.role === 'user' || message.role === 'assistant'))
    .map((message) => ({
      role: message.role,
      content: message.content || '',
      finalized: true,
    }));
}

function _restoreToolCalls(history) {
  return (Array.isArray(history && history.tool_calls) ? history.tool_calls : []).map((toolCall) => ({
    tool_call_id: toolCall.tool_call_id,
    tool_name: toolCall.tool_name,
    status: normalizeToolStatus(toolCall.status),
    input: toolCall.input || {},
    output: toolCall.output || null,
    progress: Array.isArray(toolCall.progress) ? toolCall.progress : [],
    startedAtMs: toolCall.started_at ? (Date.parse(toolCall.started_at) || Date.now()) : Date.now(),
    finishedAtMs: toolCall.finished_at ? (Date.parse(toolCall.finished_at) || Date.now()) : undefined,
    trace_id: toolCall.trace_id || null,
    turn_id: toolCall.turn_id || null,
    run_id: toolCall.run_id || null,
    source: 'history',
  }));
}

function _restoreExecutionTraces(history) {
  return (Array.isArray(history && history.execution_traces) ? history.execution_traces : []).map((trace) => ({
    execution_id: trace.execution_id,
    trace_id: trace.trace_id || trace.execution_id,
    turn_id: trace.turn_id || null,
    run_id: trace.run_id || null,
    request_summary: trace.request_summary || '',
    intent: trace.intent || '',
    request_understanding: trace.request_understanding || null,
    availability: trace.availability || null,
    steps: Array.isArray(trace.steps) ? trace.steps : [],
    review: trace.review || null,
  }));
}

function _restoreTurns(history) {
  const traces = _restoreExecutionTraces(history);
  const tools = _restoreToolCalls(history);
  if (Array.isArray(history && history.turns) && history.turns.length > 0) {
    return history.turns.map((turn) => ({
      turnId: turn.turn_id,
      clientTurnId: turn.client_turn_id || null,
      sessionId: turn.session_id || history.session_id || null,
      userMessage: turn.user_message ? {
        role: turn.user_message.role,
        content: turn.user_message.content || '',
        finalized: true,
      } : { role: 'user', content: '', finalized: true },
      assistantMessage: turn.assistant_message ? {
        role: turn.assistant_message.role,
        content: turn.assistant_message.content || '',
        finalized: true,
      } : null,
      runs: (Array.isArray(turn.runs) ? turn.runs : []).map((run) => ({
        review: (traces.find((trace) => (trace.trace_id || trace.execution_id) === (run.trace_id || null) || (trace.run_id && trace.run_id === run.run_id)) || {}).review || null,
        runId: run.run_id,
        traceId: run.trace_id || null,
        status: run.status || 'completed',
        completeness: run.completeness || 'none',
        summary: run.summary || null,
        trace: traces.find((trace) => (trace.trace_id || trace.execution_id) === (run.trace_id || null) || (trace.run_id && trace.run_id === run.run_id)) || null,
        toolCalls: tools.filter((tool) => (tool.run_id && tool.run_id === run.run_id) || (tool.trace_id && tool.trace_id === run.trace_id)),
        final: run.final_message ? { final_message: run.final_message } : null,
        startedAt: run.started_at || null,
        endedAt: run.ended_at || null,
        eventSeq: run.last_event_seq || 0,
        pendingAck: run.pending_ack || null,
        pendingResolution: run.pending_resolution || null,
      })),
      artifacts: Array.isArray(turn.artifacts) ? turn.artifacts : [],
      status: turn.status || 'completed',
      collapsed: turn.collapsed !== false,
      collapsePinned: !!turn.collapsePinned,
      createdAt: turn.created_at || null,
      updatedAt: turn.updated_at || null,
    }));
  }
  const messages = Array.isArray(history && history.messages) ? history.messages : [];
  const users = messages.filter((message) => message && message.role === 'user');
  const assistants = messages.filter((message) => message && message.role === 'assistant');
  return users.map((message, index) => {
    const trace = traces[index] || null;
    const turnId = (trace && trace.turn_id) || `legacy-turn-${index + 1}`;
    const runId = (trace && trace.run_id) || `legacy-run-${index + 1}`;
    const runTraceId = trace ? (trace.trace_id || trace.execution_id) : null;
    const runTools = tools.filter((tool) => {
      if (tool.turn_id && tool.turn_id === turnId) return true;
      return !tool.turn_id && index === 0;
    });
    return {
      turnId,
      clientTurnId: null,
      sessionId: history && history.session_id ? history.session_id : null,
      userMessage: { role: 'user', content: message.content || '', finalized: true },
      assistantMessage: assistants[index] ? { role: 'assistant', content: assistants[index].content || '', finalized: true } : null,
      runs: trace ? [{
        runId,
        traceId: runTraceId,
        status: trace.final_status === 'error' ? 'failed' : 'completed',
        completeness: 'complete',
        summary: trace.request_summary || null,
        trace,
        toolCalls: runTools,
        review: trace.review || null,
        final: trace.final_message ? { final_message: trace.final_message } : null,
        startedAt: trace.created_at || null,
        endedAt: trace.updated_at || null,
        eventSeq: 0,
      }] : [],
      artifacts: [],
      status: trace && trace.final_status === 'error' ? 'failed' : 'completed',
      collapsed: index < users.length - 1,
      collapsePinned: false,
      createdAt: message.timestamp || null,
      updatedAt: assistants[index] ? assistants[index].timestamp || null : message.timestamp || null,
    };
  });
}

function _findActiveRun(turns) {
  const activeStatuses = new Set(['queued', 'running', 'awaiting_user_ack', 'awaiting_resolution', 'cancel_requested', 'cancelling']);
  for (let tIdx = (turns || []).length - 1; tIdx >= 0; tIdx -= 1) {
    const turn = turns[tIdx];
    const runs = Array.isArray(turn && turn.runs) ? turn.runs : [];
    for (let rIdx = runs.length - 1; rIdx >= 0; rIdx -= 1) {
      const run = runs[rIdx];
      if (activeStatuses.has(run.status)) {
        return { turn, run };
      }
    }
  }
  return null;
}

function _buildTurnArtifacts(turn) {
  const runs = Array.isArray(turn && turn.runs) ? turn.runs : [];
  return runs.flatMap((run) => {
    const toolCalls = Array.isArray(run && run.toolCalls) ? run.toolCalls : [];
    const artifacts = [];
    toolCalls.forEach((toolCall) => {
      if (!toolCall) return;
      if (toolCall.tool_name === 'run_profile' && toolCall.output && Array.isArray(toolCall.output.results)) {
        const expectedByUid = {};
        const completedByUid = {};
        const inputUids = Array.isArray(toolCall.input && toolCall.input.uids) ? toolCall.input.uids : [];
        const inputModules = Array.isArray(toolCall.input && toolCall.input.modules) ? toolCall.input.modules : [];
        inputUids.forEach((uid) => {
          expectedByUid[uid] = inputModules.slice();
        });
        toolCall.output.results.forEach((row) => {
          if (!row || !row.uid || !row.module || !row.result || row.result.status !== 'ok' || !row.result.data) return;
          completedByUid[row.uid] = completedByUid[row.uid] || [];
          if (!completedByUid[row.uid].includes(row.module)) {
            completedByUid[row.uid].push(row.module);
          }
        });
        const uids = Array.from(new Set([
          ...Object.keys(expectedByUid),
          ...Object.keys(completedByUid),
        ]));
        if (uids.length > 0) {
          artifacts.push({
            kind: 'run_profile',
            runId: run.runId,
            traceId: run.traceId,
            status: toolCall.status,
            toolCallId: toolCall.tool_call_id,
            uids,
            expectedByUid,
            completedByUid,
          });
        }
      }
      if (toolCall.tool_name === 'run_trace' && toolCall.output) {
        const uid = toolCall.input && toolCall.input.uid;
        if (uid) {
          artifacts.push({
            kind: 'run_trace',
            runId: run.runId,
            traceId: run.traceId,
            status: toolCall.status,
            toolCallId: toolCall.tool_call_id,
            uids: [uid],
          });
        }
      }
    });
    return artifacts;
  });
}

function ChatPanel({
  layoutMode = 'dock',
  collapsed = false,
  onRequestClose,
  onToggleCollapse,
  onProfileReady,
  onProfilesPending,
  onTraceReady,
  onJumpToTab,
  externalSessionId = '',
  onSessionChange,
  workspaceSnapshot = null,
  onRestoreWorkspaceSession,
}) {
  const [state, dispatch] = useReducer(chatReducer, chatInitialState);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [clarificationDraft, setClarificationDraft] = useState({ country: 'mx', time_window: '最近 7 天', auto_profile: true });
  const [ingestedUids, setIngestedUids] = useState([]);
  const [traceUids, setTraceUids] = useState([]);
  const [profileModulesByUid, setProfileModulesByUid] = useState({});
  const [profileExpectedModulesByUid, setProfileExpectedModulesByUid] = useState({});
  const [selectedJumpUid, setSelectedJumpUid] = useState(null);
  const [now, setNow] = useState(Date.now());
  const esRef = useRef(null);
  const dispatchedToolsRef = useRef(new Set());
  const dispatchedProfileResultsRef = useRef(new Set());
  const dispatchedProgressRef = useRef(new Set());
  const pendingNotifiedRef = useRef(new Set());
  const skipRestoreSessionIdRef = useRef('');
  const lastHydratedSessionIdRef = useRef('');
  const onProfileReadyRef = useRef(onProfileReady);
  const onProfilesPendingRef = useRef(onProfilesPending);
  const onTraceReadyRef = useRef(onTraceReady);
  const onSessionChangeRef = useRef(onSessionChange);
  const onRestoreWorkspaceSessionRef = useRef(onRestoreWorkspaceSession);
  useEffect(() => { onProfileReadyRef.current = onProfileReady; }, [onProfileReady]);
  useEffect(() => { onProfilesPendingRef.current = onProfilesPending; }, [onProfilesPending]);
  useEffect(() => { onTraceReadyRef.current = onTraceReady; }, [onTraceReady]);
  useEffect(() => { onSessionChangeRef.current = onSessionChange; }, [onSessionChange]);
  useEffect(() => { onRestoreWorkspaceSessionRef.current = onRestoreWorkspaceSession; }, [onRestoreWorkspaceSession]);

  const resetSessionArtifacts = useCallback(() => {
    if (esRef.current) esRef.current.close();
    esRef.current = null;
    dispatchedToolsRef.current = new Set();
    dispatchedProfileResultsRef.current = new Set();
    dispatchedProgressRef.current = new Set();
    pendingNotifiedRef.current = new Set();
    setStreaming(false);
    setStopping(false);
    setIngestedUids([]);
    setTraceUids([]);
    setProfileModulesByUid({});
    setProfileExpectedModulesByUid({});
    setSelectedJumpUid(null);
  }, []);

  function rememberProfileUid(targetUid) {
    if (!targetUid) return;
    setIngestedUids((prev) => prev.includes(targetUid) ? prev : prev.concat([targetUid]));
  }

  function rememberExpectedModules(uids, modules) {
    const normalizedModules = Array.isArray(modules) && modules.length ? modules : ['app'];
    setProfileExpectedModulesByUid((prev) => {
      const next = { ...prev };
      (uids || []).forEach((u) => {
        if (u) next[u] = normalizedModules;
      });
      return next;
    });
  }

  function rememberCompletedModule(targetUid, moduleName) {
    if (!targetUid || !moduleName) return;
    setProfileModulesByUid((prev) => {
      const current = prev[targetUid] || {};
      if (current[moduleName]) return prev;
      return {
        ...prev,
        [targetUid]: { ...current, [moduleName]: true },
      };
    });
  }

  function dispatchProfileRow(row, resultKey) {
    if (!row || !row.uid || !row.module || !row.result) return;
    const key = resultKey || `${row.uid}:${row.module}`;
    const isOk = row.result.status === 'ok' && row.result.data;
    rememberProfileUid(row.uid);
    if (isOk) rememberCompletedModule(row.uid, row.module);
    if (dispatchedProfileResultsRef.current.has(key)) return;
    dispatchedProfileResultsRef.current.add(key);
    const cb = onProfileReadyRef.current;
    if (cb) cb({ uid: row.uid, module: row.module, payload: row.result });
  }

  useEffect(() => {
    state.toolCalls.forEach((t) => {
      if (t.source !== 'live') return;
      if (t.tool_name !== 'run_profile') return;
      if (pendingNotifiedRef.current.has(t.tool_call_id)) return;
      if (t.status !== 'pending' && t.status !== 'ok' && t.status !== 'error') return;
      const inp = t.input || {};
      const uids = Array.isArray(inp.uids) ? inp.uids : [];
      const modules = Array.isArray(inp.modules) && inp.modules.length ? inp.modules : ['app'];
      if (uids.length === 0) return;
      uids.forEach((u) => rememberProfileUid(u));
      rememberExpectedModules(uids, modules);
      const cb = onProfilesPendingRef.current;
      if (cb) cb({ uids, modules });
      pendingNotifiedRef.current.add(t.tool_call_id);
    });
  }, [state.toolCalls]);

  const activeRunPair = _findActiveRun(state.turns);
  const activeRun = activeRunPair ? activeRunPair.run : null;
  const activeTurn = activeRunPair ? activeRunPair.turn : null;

  useEffect(() => {
    state.toolCalls.forEach((t) => {
      if (t.source !== 'live') return;
      if (t.tool_name !== 'run_profile') return;
      const progress = Array.isArray(t.progress) ? t.progress : [];
      progress.forEach((p, idx) => {
        if (!p || p.progress_type !== 'profile_module_completed') return;
        const progressKey = `${t.tool_call_id}:${p.uid || ''}:${p.module || ''}:${idx}`;
        if (dispatchedProgressRef.current.has(progressKey)) return;
        dispatchedProgressRef.current.add(progressKey);
        if (p.uid && p.module && p.result) {
          dispatchProfileRow({
            uid: p.uid,
            module: p.module,
            result: p.result,
          }, profileResultKey(t.tool_call_id, p.uid, p.module));
        }
        if (window.console && typeof window.console.info === 'function') {
          window.console.info('[tool_progress]', {
            tool_call_id: t.tool_call_id,
            uid: p.uid,
            module: p.module,
            completed: p.completed,
            total: p.total,
          });
        }
      });
    });
  }, [state.toolCalls]);

  useEffect(() => {
    state.toolCalls.forEach((t) => {
      if (t.source !== 'live') return;
      if (t.status !== 'ok' || !t.output) return;
      if (dispatchedToolsRef.current.has(t.tool_call_id)) return;
      if (t.tool_name === 'run_profile' && Array.isArray(t.output.results)) {
        t.output.results.forEach((row) => {
          dispatchProfileRow(row, profileResultKey(t.tool_call_id, row && row.uid, row && row.module));
        });
        dispatchedToolsRef.current.add(t.tool_call_id);
      } else if (t.tool_name === 'run_trace' && t.output) {
        const traceUid = (t.input && t.input.uid) || null;
        const cb = onTraceReadyRef.current;
        if (traceUid && cb) {
          cb({ uid: traceUid, payload: t.output });
          setTraceUids((prev) => prev.includes(traceUid) ? prev : prev.concat([traceUid]));
        }
        dispatchedToolsRef.current.add(t.tool_call_id);
      }
    });
  }, [state.toolCalls]);

  const startStream = useCallback((sessionId) => {
    if (esRef.current) esRef.current.close();
    const es = openOrchestratorStream(sessionId, {
      onEvent: (evt) => dispatch(evt),
      onError: (err) => {
        const msg = (err && err.message)
          ? String(err.message)
          : 'SSE 连接中断（可能是服务器重启或网络抖动）。请重新发送问题。';
        dispatch({ type: 'error', error_type: 'sse', message: msg });
        setStreaming(false);
        if (esRef.current === es) esRef.current = null;
      },
      onClose: () => {
        setStreaming(false);
        if (esRef.current === es) esRef.current = null;
      },
    });
    esRef.current = es;
  }, []);

  useEffect(() => {
    const sessionId = externalSessionId;
    if (!sessionId) {
      lastHydratedSessionIdRef.current = '';
      return undefined;
    }
    if (skipRestoreSessionIdRef.current === sessionId) {
      skipRestoreSessionIdRef.current = '';
      lastHydratedSessionIdRef.current = sessionId;
      return undefined;
    }
    if (lastHydratedSessionIdRef.current === sessionId) return undefined;
    let cancelled = false;
    dispatch({ type: 'reset_session' });
    resetSessionArtifacts();
    fetchOrchestratorSession(sessionId).then((history) => {
      if (cancelled) return;
      lastHydratedSessionIdRef.current = sessionId;
      dispatch({
        type: 'restore_session',
        session_id: sessionId,
        messages: _restoreMessages(history),
        tool_calls: _restoreToolCalls(history),
        execution_traces: _restoreExecutionTraces(history),
        turns: _restoreTurns(history),
        run_events: Array.isArray(history && history.run_events) ? history.run_events : [],
        final: history && history.final_message ? {
          final_message: history.final_message,
          total_rounds: 0,
          total_tokens: history.total_tokens || 0,
          confidence: history.confidence || 1,
        } : null,
      });
    }).catch((err) => {
      if (cancelled) return;
      const msg = String((err && err.message) || err);
      const is404 = msg.includes('404');
      if (is404) {
        if (onSessionChangeRef.current) {
          onSessionChangeRef.current('');
        } else {
          const currentParams = new URLSearchParams(window.location.search);
          currentParams.delete('session');
          const next = `${window.location.pathname}${currentParams.toString() ? '?' + currentParams.toString() : ''}${window.location.hash}`;
          window.history.replaceState({}, '', next);
        }
      } else {
        dispatch({ type: 'error', error_type: 'restore', message: msg });
      }
    });
    return () => { cancelled = true; };
  }, [externalSessionId, resetSessionArtifacts]);

  useEffect(() => {
    if (!state.sessionId || onSessionChangeRef.current) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('session') !== state.sessionId || params.get('tab') !== 'chat') {
      params.set('session', state.sessionId);
      params.set('tab', 'chat');
      window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}${window.location.hash}`);
    }
  }, [state.sessionId]);

  useEffect(() => {
    const hasPending = state.toolCalls.some((t) => t.source === 'live' && t.status === 'pending');
    if (!hasPending) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [state.toolCalls]);

  const onSend = useCallback(async () => {
    const content = input.trim();
    if (!content) return;
    if (streaming || activeRun) return;
    const clientTurnId = `client-turn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setInput('');
    dispatch({ type: 'user_input', content, client_turn_id: clientTurnId });
    setStreaming(true);
    const compactWorkspaceSnapshot = workspaceSnapshot && Array.isArray(workspaceSnapshot.results) && workspaceSnapshot.results.length
      ? workspaceSnapshot
      : undefined;
    try {
      if (!state.sessionId) {
        const payload = await createOrchestratorSession(content, compactWorkspaceSnapshot, clientTurnId);
        dispatch({ type: 'session_started', session_id: payload.session_id });
        skipRestoreSessionIdRef.current = payload.session_id;
        if (onSessionChangeRef.current) onSessionChangeRef.current(payload.session_id);
        startStream(payload.session_id);
      } else {
        await sendOrchestratorMessage(state.sessionId, content, compactWorkspaceSnapshot, clientTurnId);
        if (!esRef.current || esRef.current.readyState === 2) startStream(state.sessionId);
      }
    } catch (err) {
      dispatch({ type: 'error', error_type: 'send', message: String((err && err.message) || err) });
      setStreaming(false);
    }
  }, [activeRun, input, startStream, state.sessionId, streaming, workspaceSnapshot]);

  const onStop = useCallback(async () => {
    if (!state.sessionId || !activeRun) return;
    setStopping(true);
    try {
      const payload = await cancelOrchestratorRun(state.sessionId, activeRun.runId);
      if (payload && payload.status === 'accepted') {
        dispatch({
          type: 'run_cancel_requested',
          turn_id: payload.turn_id || activeTurn?.turnId || null,
          run_id: payload.run_id || activeRun.runId,
        });
        return;
      }
      if (payload && payload.status === 'already_finished') {
        const history = await fetchOrchestratorSession(state.sessionId);
        dispatch({
          type: 'restore_session',
          session_id: state.sessionId,
          messages: _restoreMessages(history),
          tool_calls: _restoreToolCalls(history),
          execution_traces: _restoreExecutionTraces(history),
          turns: _restoreTurns(history),
          run_events: Array.isArray(history && history.run_events) ? history.run_events : [],
          final: history && history.final_message ? {
            final_message: history.final_message,
            total_rounds: 0,
            total_tokens: history.total_tokens || 0,
            confidence: history.confidence || 1,
          } : null,
        });
        return;
      }
      if (payload && payload.status === 'not_found') {
        dispatch({ type: 'error', error_type: 'cancel', message: '当前执行已不存在，请刷新状态。' });
        const history = await fetchOrchestratorSession(state.sessionId);
        dispatch({
          type: 'restore_session',
          session_id: state.sessionId,
          messages: _restoreMessages(history),
          tool_calls: _restoreToolCalls(history),
          execution_traces: _restoreExecutionTraces(history),
          turns: _restoreTurns(history),
          run_events: Array.isArray(history && history.run_events) ? history.run_events : [],
          final: history && history.final_message ? {
            final_message: history.final_message,
            total_rounds: 0,
            total_tokens: history.total_tokens || 0,
            confidence: history.confidence || 1,
          } : null,
        });
      }
    } catch (err) {
      dispatch({ type: 'error', error_type: 'cancel', message: String((err && err.message) || err) });
    } finally {
      setStopping(false);
    }
  }, [activeRun, activeTurn, state.sessionId]);

  const onApprove = useCallback(async () => {
    if (!state.pendingAck || !state.sessionId) return;
    try {
      await ackOrchestratorTool(state.sessionId, state.pendingAck.tool_call_id, 'approve');
    } catch (err) {
      dispatch({ type: 'error', error_type: 'ack', message: String((err && err.message) || err) });
    }
  }, [state.pendingAck, state.sessionId]);

  const onReject = useCallback(async () => {
    if (!state.pendingAck || !state.sessionId) return;
    try {
      await ackOrchestratorTool(state.sessionId, state.pendingAck.tool_call_id, 'reject');
    } catch (err) {
      dispatch({ type: 'error', error_type: 'ack', message: String((err && err.message) || err) });
    }
  }, [state.pendingAck, state.sessionId]);

  const onSubmitClarification = useCallback(async (answers) => {
    if (!state.pendingResolution || !state.sessionId) return;
    try {
      await resolveOrchestratorStep(state.sessionId, {
        execution_id: state.pendingResolution.execution_id,
        step_id: state.pendingResolution.step_id,
        resolution_type: state.pendingResolution.resolution_type,
        resolution_id: state.pendingResolution.resolution_id,
        answers,
      });
    } catch (err) {
      dispatch({ type: 'error', error_type: 'resolve', message: String((err && err.message) || err) });
    }
  }, [state.pendingResolution, state.sessionId]);

  const onSelectResolutionOption = useCallback(async (selectedOption) => {
    if (!state.pendingResolution || !state.sessionId) return;
    try {
      await resolveOrchestratorStep(state.sessionId, {
        execution_id: state.pendingResolution.execution_id,
        step_id: state.pendingResolution.step_id,
        resolution_type: state.pendingResolution.resolution_type,
        resolution_id: state.pendingResolution.resolution_id,
        selected_option: selectedOption,
      });
    } catch (err) {
      dispatch({ type: 'error', error_type: 'resolve', message: String((err && err.message) || err) });
    }
  }, [state.pendingResolution, state.sessionId]);

  useEffect(() => {
    if (!state.pendingAck) return undefined;
    const handler = (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        onApprove();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onReject();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.pendingAck, onApprove, onReject]);

  useEffect(() => () => {
    if (esRef.current) esRef.current.close();
  }, []);

  useEffect(() => {
    if (!state.pendingResolution || state.pendingResolution.resolution_type !== 'clarification') return;
    setClarificationDraft({
      country: (state.pendingResolution.candidate_defaults && state.pendingResolution.candidate_defaults.country) || 'mx',
      time_window: (state.pendingResolution.candidate_defaults && state.pendingResolution.candidate_defaults.time_window) || '最近 7 天',
      auto_profile: state.pendingResolution.candidate_defaults
        ? state.pendingResolution.candidate_defaults.auto_profile !== false
        : true,
    });
  }, [state.pendingResolution]);

  function onOpenMemory() {
    setMemoryOpen(true);
  }

  const onOpenSession = useCallback((sessionId) => {
    if (!sessionId) return;
    setMemoryOpen(false);
    const currentSessionId = externalSessionId || state.sessionId || '';
    if (sessionId === currentSessionId) return;
      if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setStreaming(false);
    }
    if (onSessionChangeRef.current) {
      onSessionChangeRef.current(sessionId);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    params.set('session', sessionId);
    params.set('tab', 'chat');
    window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}${window.location.hash}`);
  }, [externalSessionId, state.sessionId]);

  const onRestoreSession = useCallback(async (sessionId) => {
    if (!sessionId) return;
    const currentSessionId = externalSessionId || state.sessionId || '';
    if (sessionId !== currentSessionId) {
      onOpenSession(sessionId);
    }
    if (!onRestoreWorkspaceSessionRef.current) return;
    const history = await fetchOrchestratorSession(sessionId);
    onRestoreWorkspaceSessionRef.current(history);
    setMemoryOpen(false);
  }, [externalSessionId, onOpenSession, state.sessionId]);

  const isCollapsedDock = layoutMode === 'dock' && collapsed;
  const runStopping =
    stopping ||
    activeRun?.status === 'cancel_requested' ||
    activeRun?.status === 'cancelling';

  if (isCollapsedDock) {
    return (
      <div className="flex h-full flex-col bg-transparent">
        <header id="chat-panel-header" className="h-full bg-transparent">
          <div id="chat-panel-header-inner" className="flex h-full flex-col items-center justify-start gap-3 px-0 py-4">
            <button
              id="chat-launcher"
              type="button"
              onClick={onToggleCollapse}
              className="flex h-[52px] w-[52px] items-center justify-center rounded-full bg-blue-600 text-white shadow-[0_12px_24px_rgba(37,99,235,0.25)] transition-colors hover:bg-blue-700"
              title="展开 NL Chat"
            >
              {Bot ? <Bot className="h-5 w-5" /> : null}
            </button>
          </div>
        </header>
        <MemoryInspector
          open={memoryOpen}
          onClose={() => setMemoryOpen(false)}
          onOpenSession={onOpenSession}
          onRestoreSession={onRestoreSession}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-white/95 backdrop-blur-xl">
      <header id="chat-panel-header" className="h-14 shrink-0 border-b border-slate-100 bg-white/85 backdrop-blur">
        <div id="chat-panel-header-inner" className="flex h-full items-center justify-between gap-3 px-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <button
                id="chat-launcher"
                type="button"
                onClick={layoutMode === 'dock' && onToggleCollapse ? onToggleCollapse : undefined}
                className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-100 text-blue-600"
                title={layoutMode === 'dock' && onToggleCollapse ? '收起 NL Chat' : '自然语言助手'}
              >
                {Bot ? <Bot className="h-4 w-4" /> : null}
              </button>
              <div className="min-w-0">
                <h2 id="chat-panel-title" className="truncate text-sm font-semibold text-slate-800">自然语言助手 (NL Chat)</h2>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              id="chat-history-btn"
              type="button"
              onClick={onOpenMemory}
              className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-200"
            >
              {Clock3 ? <Clock3 className="h-3.5 w-3.5" /> : null}
              历史记忆
            </button>
            {layoutMode === 'dock' && onToggleCollapse ? (
              <button
                id="collapse-chat-btn"
                type="button"
                onClick={onToggleCollapse}
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600"
                title="折叠 NL Chat"
              >
                {PanelRightClose ? <PanelRightClose className="h-4 w-4" /> : null}
              </button>
            ) : null}
            {layoutMode === 'sheet' && onRequestClose ? (
              <button
                type="button"
                onClick={onRequestClose}
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-100"
              >
                {X ? <X className="h-4 w-4" /> : null}
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <div id="chat-panel-body" className="flex min-h-0 flex-1 flex-col">
        <div id="chat-container" className="flex-1 overflow-y-auto bg-slate-50/50 p-4 scroll-smooth">
          <div className="space-y-6">
            <ChatBudgetBanner used={state.budget && state.budget.used} limit={state.budget && state.budget.limit} />
            <ChatProviderFallbackBanner from={state.providerFallback && state.providerFallback.from} to={state.providerFallback && state.providerFallback.to} reason={state.providerFallback && state.providerFallback.reason} />
            {state.error ? <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{state.error.error_type}: {state.error.message}</div> : null}

            <div className="space-y-6">
              {Array.isArray(state.turns) && state.turns.length > 0 ? state.turns.map((turn) => (
                (() => {
                  const turnArtifacts = _buildTurnArtifacts(turn);
                  const profileArtifact = turnArtifacts.find((artifact) => artifact.kind === 'run_profile') || null;
                  const traceArtifact = turnArtifacts.find((artifact) => artifact.kind === 'run_trace') || null;
                  const turnJumpUids = profileArtifact
                    ? profileArtifact.uids
                    : (traceArtifact ? traceArtifact.uids : []);
                  const turnSelectedUid = turnJumpUids.includes(selectedJumpUid) ? selectedJumpUid : turnJumpUids[0];
                  const turnExpectedModules = (profileArtifact && turnSelectedUid && profileArtifact.expectedByUid[turnSelectedUid]) || [];
                  const turnCompletedModules = (profileArtifact && turnSelectedUid && profileArtifact.completedByUid[turnSelectedUid]) || [];
                  const turnProfileComplete = turnExpectedModules.length > 0 && turnCompletedModules.length >= turnExpectedModules.length;
                  const turnJumpTabs = profileArtifact
                    ? turnCompletedModules.map((id) => ({ id, label: PROFILE_MODULE_LABELS[id] || id }))
                    : [{ id: 'trace', label: '深度行为解析' }];

                  return (
                    <div key={turn.turnId} className="space-y-4">
                      <ChatMessageList messages={[turn.userMessage]} />
                      {(turn.runs || []).map((run) => {
                    const runToolCalls = Array.isArray(run.toolCalls) ? run.toolCalls : [];
                    const isActiveRun = activeRun && activeRun.runId === run.runId;
                    const runPendingAck = state.pendingAck?.run_id === run.runId ? state.pendingAck : null;
                    const runPendingResolution = state.pendingResolution?.run_id === run.runId ? state.pendingResolution : null;
                    const pendingProfile = runToolCalls.find((t) => t.tool_name === 'run_profile' && t.status === 'pending');
                    let label = 'AI 正在思考，可能需要 30~60 秒...';
                    if (run.status === 'cancel_requested') {
                      label = '已发送停止请求，正在等待当前步骤安全中止...';
                    } else if (run.status === 'cancelling') {
                      label = '正在停止本轮执行，已完成结果将保留在当前回合内...';
                    } else if (pendingProfile) {
                      const inp = pendingProfile.input || {};
                      const totalUids = (Array.isArray(inp.uids) ? inp.uids : []).length || 1;
                      const totalModules = (Array.isArray(inp.modules) ? inp.modules : ['app']).length;
                      const totalTasks = totalUids * totalModules;
                      const elapsedSec = Math.max(0, Math.floor((now - (pendingProfile.startedAtMs || now)) / 1000));
                      const etaSec = Math.max(0, totalTasks * 40 - elapsedSec);
                      const fmt = (value) => `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
                      label = `画像分析进行中 · ${totalUids} 位用户 × ${totalModules} 个模块（共 ${totalTasks} 个子任务）· 已用 ${fmt(elapsedSec)} / 预计还需 ~${fmt(etaSec)}`;
                    }
                    return (
                      <div key={run.runId} className="space-y-3">
                        {turn.collapsed ? (
                          <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                            <div className="flex items-center justify-between gap-3">
                              <div className="text-sm font-semibold text-slate-700">{run.summary || '历史执行回合'}</div>
                              <div className="flex items-center gap-2">
                                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                                  {run.status || turn.status || 'completed'}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => dispatch({ type: 'toggle_turn_collapse', turn_id: turn.turnId })}
                                  className="rounded-full border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                                >
                                  展开执行过程
                                </button>
                              </div>
                            </div>
                            {run.review ? (
                              <div className="mt-2 text-xs text-slate-500">
                                审核：{run.review.status}{run.completeness === 'partial' ? ' · partial' : ''}
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          <>
                            {run.trace ? <ChatExecutionTraceCard trace={run.trace} runStatus={run.status} /> : null}
                            {runToolCalls.length > 0 ? <ChatToolCallStream toolCalls={runToolCalls} now={now} /> : null}
                            {isActiveRun && streaming && !runPendingAck && !runPendingResolution ? (
                              <div className="flex items-center gap-2 text-sm text-slate-600">
                                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-blue-400" style={{ animationDelay: '0ms' }}></span>
                                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-blue-400" style={{ animationDelay: '150ms' }}></span>
                                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-blue-400" style={{ animationDelay: '300ms' }}></span>
                                <span className="ml-1">{label}</span>
                              </div>
                            ) : null}
                            {(turn.status === 'completed' || turn.status === 'cancelled' || turn.status === 'failed') ? (
                              <div className="flex justify-end">
                                <button
                                  type="button"
                                  onClick={() => dispatch({ type: 'toggle_turn_collapse', turn_id: turn.turnId })}
                                  className="rounded-full border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                                >
                                  收起执行过程
                                </button>
                              </div>
                            ) : null}
                            <ChatAckCard pending={runPendingAck} onApprove={onApprove} onReject={onReject} />
                            {runPendingResolution ? (
                              <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
                                <div className="text-sm font-semibold text-blue-800">
                                  {runPendingResolution.resolution_type === 'repair_strategy' ? '请选择本次 cohort 的补数策略' : '请先补充执行条件'}
                                </div>
                                <div className="mt-1 text-xs leading-5 text-blue-700">
                                  {runPendingResolution.prompt || '请补充完成当前执行所需的信息。'}
                                </div>
                                {runPendingResolution.resolution_type === 'clarification' ? (
                                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                                    <label className="flex flex-col gap-1 text-xs font-medium text-blue-800">
                                      国家
                                      <select
                                        value={clarificationDraft.country}
                                        onChange={(e) => setClarificationDraft((prev) => ({ ...prev, country: e.target.value }))}
                                        className="rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-400"
                                      >
                                        <option value="mx">墨西哥 (MX)</option>
                                        <option value="th">泰国 (TH)</option>
                                        <option value="co">哥伦比亚 (CO)</option>
                                        <option value="pe">秘鲁 (PE)</option>
                                        <option value="cl">智利 (CL)</option>
                                        <option value="br">巴西 (BR)</option>
                                      </select>
                                    </label>
                                    <label className="flex flex-col gap-1 text-xs font-medium text-blue-800">
                                      时间范围
                                      <select
                                        value={clarificationDraft.time_window}
                                        onChange={(e) => setClarificationDraft((prev) => ({ ...prev, time_window: e.target.value }))}
                                        className="rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-400"
                                      >
                                        <option value="最近 7 天">最近 7 天</option>
                                        <option value="最近 14 天">最近 14 天</option>
                                        <option value="最近 30 天">最近 30 天</option>
                                      </select>
                                    </label>
                                    <label className="sm:col-span-2 inline-flex items-center gap-2 text-xs font-medium text-blue-800">
                                      <input
                                        type="checkbox"
                                        checked={!!clarificationDraft.auto_profile}
                                        onChange={(e) => setClarificationDraft((prev) => ({ ...prev, auto_profile: e.target.checked }))}
                                      />
                                      自动继续画像
                                    </label>
                                    <div className="sm:col-span-2 flex flex-wrap gap-2">
                                      <button
                                        type="button"
                                        onClick={() => onSubmitClarification(clarificationDraft)}
                                        className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 transition-colors hover:bg-blue-100"
                                      >
                                        提交澄清条件
                                      </button>
                                    </div>
                                  </div>
                                ) : null}
                                {runPendingResolution.resolution_type === 'repair_strategy' ? (
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {(runPendingResolution.options || []).map((option) => (
                                      <button
                                        key={option}
                                        type="button"
                                        onClick={() => onSelectResolutionOption(option)}
                                        className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 transition-colors hover:bg-blue-100"
                                      >
                                        {option}
                                      </button>
                                    ))}
                                  </div>
                                ) : null}
                              </div>
                            ) : null}
                          </>
                        )}
                      </div>
                    );
                      })}
                      {turn.assistantMessage ? <ChatMessageList messages={[turn.assistantMessage]} /> : null}
                      {turnJumpUids.length > 0 && onJumpToTab ? (
                        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
                          <div className="text-sm font-semibold text-emerald-800">
                            {profileArtifact
                              ? `${turnProfileComplete ? '完整画像已生成' : '画像结果已就绪'}：${turnSelectedUid || turnJumpUids.length + ' 位用户'} 已完成 ${turnCompletedModules.length}/${turnExpectedModules.length} 个画像模块`
                              : `深度行为解析已生成：${turnSelectedUid || turnJumpUids.length + ' 位用户'} 可查看 trace dashboard`}
                          </div>
                          {turnJumpUids.length > 1 ? (
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <span className="text-xs text-emerald-700">目标 UID：</span>
                              {turnJumpUids.map((uid) => {
                                const active = turnSelectedUid === uid;
                                return (
                                  <button
                                    key={`${turn.turnId}-${uid}`}
                                    onClick={() => setSelectedJumpUid(uid)}
                                    className={`rounded px-2 py-1 text-xs font-mono transition-colors border ${
                                      active
                                        ? 'bg-emerald-600 text-white border-emerald-600'
                                        : 'bg-white text-emerald-700 border-emerald-300 hover:bg-emerald-100'
                                    }`}
                                  >
                                    {uid}
                                  </button>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="mt-1 text-xs font-mono text-emerald-700">{turnJumpUids[0]}</div>
                          )}
                          <div className="mt-2 flex flex-wrap gap-2">
                            {turnJumpTabs.length > 0 ? turnJumpTabs.map((tab) => (
                              <button
                                key={`${turn.turnId}-${tab.id}`}
                                onClick={() => onJumpToTab(tab.id, turnSelectedUid)}
                                className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-semibold text-emerald-700 transition-colors hover:bg-emerald-100"
                              >
                                {tab.label} →
                              </button>
                            )) : (
                              <span className="text-xs text-emerald-700">等待第一个画像模块完成...</span>
                            )}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  );
                })()
              )) : (
                <ChatMessageList messages={state.messages} />
              )}
            </div>

          </div>
        </div>
      </div>

      <div id="chat-panel-footer" className="shrink-0 border-t border-slate-100 bg-white p-4">
        <ChatInputBox
          value={input}
          onChange={setInput}
          onSend={onSend}
          onStop={onStop}
          disabled={!!state.pendingAck || !!state.pendingResolution}
          running={streaming || !!activeRun}
          stopping={runStopping}
        />
        <p className="mt-2 text-center text-[10px] text-slate-400">AI 助手可能会犯错，请结合左侧结构化结果核实。</p>
      </div>

      <MemoryInspector
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
        onOpenSession={onOpenSession}
        onRestoreSession={onRestoreSession}
      />
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatPanel = ChatPanel;
