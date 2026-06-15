const chatInitialState = {
  sessionId: null,
  messages: [],
  toolCalls: [],
  executionTraces: [],
  turns: [],
  pendingAck: null,
  pendingResolution: null,
  budget: null,
  providerFallback: null,
  final: null,
  error: null,
  streamEnded: false,
  seenEventIds: {},
  lastEventSeqByRun: {},
};

function _appendAssistant(messages, delta) {
  const last = messages[messages.length - 1];
  if (last && last.role === 'assistant' && !last.finalized) {
    return messages.slice(0, -1).concat([{ ...last, content: (last.content || '') + delta }]);
  }
  return messages.concat([{ role: 'assistant', content: delta, finalized: false }]);
}

function _finalizeAssistant(messages, finalMessage) {
  const last = messages[messages.length - 1];
  if (last && last.role === 'assistant' && !last.finalized) {
    return messages.slice(0, -1).concat([{ ...last, content: finalMessage, finalized: true }]);
  }
  return messages.concat([{ role: 'assistant', content: finalMessage, finalized: true }]);
}

function normalizeToolStatus(status) {
  if (status === 'ok' || status === 'done') return 'ok';
  if (status === 'cancelled') return 'cancelled';
  if (status === 'error' || status === 'failed') return 'error';
  return 'pending';
}

function _ensureTurn(turns, evt, state) {
  const turnId = evt.turn_id || evt.turnId;
  if (!turnId) return { turns, turn: null };
  let found = null;
  let mergedByClientTurn = false;
  const next = turns.map((turn) => {
    if (turn.turnId === turnId) {
      found = turn;
      return turn;
    }
    if (!found && evt.client_turn_id && turn.clientTurnId === evt.client_turn_id) {
      found = {
        ...turn,
        turnId,
        clientTurnId: evt.client_turn_id,
        sessionId: evt.session_id || turn.sessionId || state.sessionId || null,
        updatedAt: evt.timestamp || turn.updatedAt,
        optimistic: false,
      };
      mergedByClientTurn = true;
      return found;
    }
    return turn;
  });
  if (!found) {
    for (let idx = next.length - 1; idx >= 0; idx -= 1) {
      const turn = next[idx];
      if (turn && turn.optimistic && (!turn.runs || turn.runs.length === 0) && turn.status === 'queued') {
        found = {
          ...turn,
          turnId,
          sessionId: evt.session_id || turn.sessionId || state.sessionId || null,
          updatedAt: evt.timestamp || turn.updatedAt,
          optimistic: false,
        };
        next[idx] = found;
        mergedByClientTurn = true;
        break;
      }
    }
  }
  if (found) return { turns: next, turn: found };

  const lastUser = [...(state.messages || [])].reverse().find((message) => message && message.role === 'user');
  const created = {
    turnId,
    clientTurnId: evt.client_turn_id || null,
    sessionId: evt.session_id || state.sessionId || null,
    userMessage: lastUser ? { ...lastUser, finalized: true } : { role: 'user', content: '', finalized: true },
    runs: [],
    assistantMessage: null,
    artifacts: [],
    status: 'running',
    collapsed: false,
    collapsePinned: false,
    createdAt: evt.timestamp || null,
    updatedAt: evt.timestamp || null,
  };
  return { turns: mergedByClientTurn ? next : turns.concat([created]), turn: created };
}

function _ensureRun(turns, evt, state) {
  const ensuredTurn = _ensureTurn(turns, evt, state);
  const turnId = evt.turn_id || evt.turnId;
  const runId = evt.run_id || evt.runId;
  if (!turnId || !runId) return { turns: ensuredTurn.turns, turn: ensuredTurn.turn, run: null };
  let targetRun = null;
  const nextTurns = ensuredTurn.turns.map((turn) => {
    if (turn.turnId !== turnId) return turn;
    const existing = Array.isArray(turn.runs) ? turn.runs.find((run) => run.runId === runId) : null;
    if (existing) {
      targetRun = existing;
      return turn;
    }
    const createdRun = {
      runId,
      traceId: evt.trace_id || evt.traceId || evt.execution_id || evt.executionId || null,
      status: evt.type === 'run_started' ? 'running' : 'queued',
      completeness: 'none',
      summary: null,
      trace: null,
      toolCalls: [],
      review: null,
      final: null,
      startedAt: evt.timestamp || null,
      endedAt: null,
      eventSeq: evt.event_seq || 0,
    };
    targetRun = createdRun;
    return {
      ...turn,
      runs: (turn.runs || []).concat([createdRun]),
      updatedAt: evt.timestamp || turn.updatedAt,
    };
  });
  return {
    turns: nextTurns,
    turn: nextTurns.find((turn) => turn.turnId === turnId) || null,
    run: targetRun,
  };
}

function _mapTurns(turns, turnId, mapper) {
  return turns.map((turn) => turn.turnId === turnId ? mapper(turn) : turn);
}

function _mapRun(turns, turnId, runId, mapper) {
  return turns.map((turn) => {
    if (turn.turnId !== turnId) return turn;
    return {
      ...turn,
      runs: (turn.runs || []).map((run) => run.runId === runId ? mapper(run, turn) : run),
      updatedAt: turn.updatedAt,
    };
  });
}

function upsertExecutionTrace(traces, incoming) {
  const executionId = incoming && (incoming.execution_id || incoming.trace_id);
  if (!executionId) return traces;
  const idx = traces.findIndex((trace) => trace && (trace.execution_id === executionId || trace.trace_id === executionId));
  if (idx === -1) return traces.concat([incoming]);
  return traces.map((trace, traceIdx) => {
    if (traceIdx !== idx) return trace;
    return {
      ...trace,
      ...incoming,
      execution_id: incoming.execution_id || incoming.trace_id || trace.execution_id,
      trace_id: incoming.trace_id || incoming.execution_id || trace.trace_id || trace.execution_id,
      request_understanding: incoming.request_understanding !== undefined ? incoming.request_understanding : (trace.request_understanding || null),
      availability: incoming.availability !== undefined ? incoming.availability : trace.availability,
      steps: Array.isArray(incoming.steps) ? incoming.steps : (Array.isArray(trace.steps) ? trace.steps : []),
      review: incoming.review !== undefined && incoming.review !== null ? incoming.review : (trace.review || null),
    };
  });
}

function _derivePendingResolutionFromTraces(traces) {
  for (const trace of Array.isArray(traces) ? traces : []) {
    const steps = Array.isArray(trace && trace.steps) ? trace.steps : [];
    for (const step of steps) {
      if (!step || step.status !== 'awaiting_resolution') continue;
      return {
        execution_id: trace.execution_id || trace.trace_id,
        trace_id: trace.trace_id || trace.execution_id,
        turn_id: trace.turn_id || null,
        run_id: trace.run_id || null,
        step_id: step.step_id,
        resolution_type: step.resolution_type || '',
        prompt: step.resolution_prompt || '',
        required_slots: Array.isArray(step.resolution_required_slots) ? step.resolution_required_slots : [],
        candidate_defaults: step.resolution_candidate_defaults || {},
        options: Array.isArray(step.resolution_options) ? step.resolution_options : [],
        missing_bucket_counts: {},
        cohort_size: null,
        selected_option: null,
      };
    }
  }
  return null;
}

function _derivePendingStateFromTurns(turns) {
  let pendingAck = null;
  let pendingResolution = null;
  for (const turn of Array.isArray(turns) ? turns : []) {
    for (const run of Array.isArray(turn && turn.runs) ? turn.runs : []) {
      const pendingAckState = run && (run.pendingAck || run.pending_ack);
      const pendingResolutionState = run && (run.pendingResolution || run.pending_resolution);
      const turnId = turn.turnId || turn.turn_id || null;
      const runId = run.runId || run.run_id || null;
      const traceId = run.traceId || run.trace_id || null;
      if (!pendingAck && pendingAckState) {
        pendingAck = {
          turn_id: turnId,
          run_id: runId,
          ack_id: pendingAckState.ack_id,
          tool_call_id: pendingAckState.tool_call_id,
          sql_text: pendingAckState.sql_text || '',
          rows_estimated: pendingAckState.rows_estimated ?? null,
        };
      }
      if (!pendingResolution && pendingResolutionState) {
        pendingResolution = {
          turn_id: turnId,
          run_id: runId,
          execution_id: traceId,
          trace_id: traceId,
          resolution_id: pendingResolutionState.resolution_id,
          step_id: pendingResolutionState.step_id,
          resolution_type: pendingResolutionState.resolution_type,
          prompt: pendingResolutionState.message || '',
          required_slots: [],
          candidate_defaults: {},
          options: Array.isArray(pendingResolutionState.options) ? pendingResolutionState.options : [],
          missing_bucket_counts: {},
          cohort_size: null,
          selected_option: null,
        };
      }
    }
  }
  return { pendingAck, pendingResolution };
}

function _derivePendingStateFromRunEvents(runEvents, turns) {
  let pendingAck = null;
  let pendingResolution = null;
  const traceIdByRun = {};
  for (const turn of Array.isArray(turns) ? turns : []) {
    for (const run of Array.isArray(turn && turn.runs) ? turn.runs : []) {
      const runId = run && (run.runId || run.run_id);
      if (!runId) continue;
      traceIdByRun[runId] = run.traceId || run.trace_id || null;
    }
  }
  for (const event of Array.isArray(runEvents) ? runEvents : []) {
    const eventType = event && (event.event_type || event.type);
    const payload = event && event.payload ? event.payload : {};
    if (eventType === 'awaiting_user_ack') {
      pendingAck = {
        turn_id: event.turn_id || null,
        run_id: event.run_id || null,
        ack_id: payload.ack_id || null,
        tool_call_id: payload.tool_call_id || null,
        sql_text: payload.sql_text || '',
        rows_estimated: payload.rows_estimated ?? null,
      };
      continue;
    }
    if (eventType === 'awaiting_resolution') {
      const traceId = payload.trace_id || payload.execution_id || traceIdByRun[event.run_id] || null;
      pendingResolution = {
        turn_id: event.turn_id || null,
        run_id: event.run_id || null,
        execution_id: traceId,
        trace_id: traceId,
        resolution_id: payload.resolution_id || null,
        step_id: payload.step_id || null,
        resolution_type: payload.resolution_type || '',
        prompt: payload.prompt || '',
        required_slots: Array.isArray(payload.required_slots) ? payload.required_slots : [],
        candidate_defaults: payload.candidate_defaults || {},
        options: Array.isArray(payload.options) ? payload.options : [],
        missing_bucket_counts: payload.missing_bucket_counts || {},
        cohort_size: payload.cohort_size ?? null,
        selected_option: payload.selected_option ?? null,
      };
      continue;
    }
    if (['ack_received', 'ack_rejected', 'ack_cancelled', 'ack_expired', 'run_cancelled'].includes(eventType)) {
      if (pendingAck && pendingAck.run_id === event.run_id) pendingAck = null;
      continue;
    }
    if (['resolution_received', 'resolution_cancelled', 'resolution_expired', 'run_cancelled'].includes(eventType)) {
      if (pendingResolution && pendingResolution.run_id === event.run_id) pendingResolution = null;
    }
  }
  return { pendingAck, pendingResolution };
}

function _mergeTraceIntoRun(run, evt, trace) {
  return {
    ...run,
    traceId: evt.trace_id || evt.execution_id || run.traceId,
    trace: trace,
    summary: (trace && trace.request_summary) || run.summary || null,
    eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
  };
}

function _upsertToolCall(toolCalls, evt) {
  const idx = toolCalls.findIndex((item) => item.tool_call_id === evt.tool_call_id);
  if (idx === -1) {
    const status = normalizeToolStatus(evt.status);
    return toolCalls.concat([{
      tool_call_id: evt.tool_call_id,
      tool_name: evt.tool_name,
      status,
      input: evt.input || {},
      output: evt.output || null,
      progress: [],
      startedAtMs: evt.timestamp ? (Date.parse(evt.timestamp) || Date.now()) : Date.now(),
      finishedAtMs: status === 'ok' || status === 'error' || status === 'cancelled'
        ? (evt.timestamp ? (Date.parse(evt.timestamp) || Date.now()) : Date.now())
        : undefined,
      source: 'live',
      trace_id: evt.trace_id || evt.execution_id || null,
      turn_id: evt.turn_id || null,
      run_id: evt.run_id || null,
    }]);
  }
  return toolCalls.map((item, itemIdx) => {
    if (itemIdx !== idx) return item;
    const status = evt.status !== undefined ? normalizeToolStatus(evt.status) : item.status;
    return {
      ...item,
      tool_name: evt.tool_name || item.tool_name,
      status,
      input: evt.input || item.input,
      output: evt.output !== undefined ? evt.output : item.output,
      finishedAtMs: status === 'ok' || status === 'error' || status === 'cancelled'
        ? (evt.timestamp ? (Date.parse(evt.timestamp) || Date.now()) : Date.now())
        : item.finishedAtMs,
      trace_id: evt.trace_id || item.trace_id,
      turn_id: evt.turn_id || item.turn_id,
      run_id: evt.run_id || item.run_id,
    };
  });
}

function _appendToolProgress(progress, evt) {
  const nextItem = {
    progress_type: evt.progress_type,
    uid: evt.uid,
    module: evt.module,
    result: evt.result,
    status: evt.status,
    completed: evt.completed,
    total: evt.total,
  };
  const existing = Array.isArray(progress) ? progress : [];
  const existingIndex = existing.findIndex((item) => (
    item
    && item.progress_type === nextItem.progress_type
    && item.uid === nextItem.uid
    && item.module === nextItem.module
    && item.status === nextItem.status
    && item.completed === nextItem.completed
    && item.total === nextItem.total
  ));
  if (existingIndex === -1) return existing.concat([nextItem]);
  return existing.map((item, idx) => (idx === existingIndex ? { ...item, ...nextItem } : item));
}

function chatReducer(state, evt) {
  const eventId = evt && evt.event_id;
  const runId = evt && (evt.run_id || evt.runId);
  const eventSeq = typeof evt.event_seq === 'number' ? evt.event_seq : null;
  if (eventId && state.seenEventIds && state.seenEventIds[eventId]) {
    return state;
  }
  if (runId && eventSeq !== null) {
    const lastSeq = state.lastEventSeqByRun ? state.lastEventSeqByRun[runId] : undefined;
    if (typeof lastSeq === 'number' && eventSeq < lastSeq) {
      return state;
    }
  }
  const nextSeenEventIds = eventId
    ? { ...(state.seenEventIds || {}), [eventId]: true }
    : (state.seenEventIds || {});
  const nextLastEventSeqByRun = (runId && eventSeq !== null)
    ? { ...(state.lastEventSeqByRun || {}), [runId]: Math.max(state.lastEventSeqByRun && state.lastEventSeqByRun[runId] || 0, eventSeq) }
    : (state.lastEventSeqByRun || {});
  switch (evt.type) {
    case 'reset_session':
      return { ...chatInitialState };
    case 'restore_session':
      {
        const executionTraces = Array.isArray(evt.execution_traces) ? evt.execution_traces : [];
        const turns = Array.isArray(evt.turns) ? evt.turns : [];
        const derivedPending = _derivePendingStateFromTurns(turns);
        const fallbackPending = _derivePendingStateFromRunEvents(Array.isArray(evt.run_events) ? evt.run_events : [], turns);
        return {
          ...chatInitialState,
          sessionId: evt.session_id || null,
          messages: Array.isArray(evt.messages) ? evt.messages : [],
          toolCalls: Array.isArray(evt.tool_calls) ? evt.tool_calls : [],
          executionTraces,
          turns,
          pendingAck: derivedPending.pendingAck || fallbackPending.pendingAck,
          pendingResolution: derivedPending.pendingResolution || fallbackPending.pendingResolution || _derivePendingResolutionFromTraces(executionTraces),
          final: evt.final || null,
          streamEnded: true,
          seenEventIds: {},
          lastEventSeqByRun: {},
        };
      }
    case 'user_input':
      return {
        ...state,
        error: null,
        messages: state.messages.concat([{ role: 'user', content: evt.content, finalized: true }]),
        turns: state.turns.concat([{
          turnId: evt.client_turn_id || `client-turn-${Date.now()}`,
          clientTurnId: evt.client_turn_id || null,
          sessionId: state.sessionId || null,
          userMessage: { role: 'user', content: evt.content, finalized: true },
          runs: [],
          assistantMessage: null,
          artifacts: [],
          status: 'queued',
          collapsed: false,
          collapsePinned: false,
          optimistic: true,
          createdAt: evt.timestamp || null,
          updatedAt: evt.timestamp || null,
        }]),
      };
    case 'session_started':
      return { ...state, sessionId: evt.session_id };
    case 'turn_started': {
      const ensured = _ensureTurn(state.turns, evt, state);
      const turns = ensured.turns.map((turn) => (
        turn.turnId === evt.turn_id
          ? { ...turn, collapsed: false, status: 'running', optimistic: false, updatedAt: evt.timestamp || turn.updatedAt }
          : ((turn.status === 'completed' || turn.status === 'cancelled' || turn.status === 'failed')
              ? (turn.collapsePinned ? turn : { ...turn, collapsed: true })
              : turn)
      ));
      return {
        ...state,
        turns,
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    }
    case 'run_started': {
      const ensured = _ensureRun(state.turns, evt, state);
      const turns = _mapRun(ensured.turns, evt.turn_id, evt.run_id, (run, turn) => ({
        ...run,
        traceId: evt.trace_id || run.traceId,
        status: 'running',
        startedAt: evt.timestamp || run.startedAt,
        eventSeq: evt.event_seq || run.eventSeq,
      }));
      return { ...state, turns, seenEventIds: nextSeenEventIds, lastEventSeqByRun: nextLastEventSeqByRun };
    }
    case 'tool_started': {
      const toolCalls = _upsertToolCall(state.toolCalls, evt);
      const ensured = _ensureRun(state.turns, evt, state);
      const turns = _mapRun(ensured.turns, evt.turn_id, evt.run_id, (run) => ({
        ...run,
        status: 'running',
        toolCalls: _upsertToolCall(run.toolCalls || [], evt),
        eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
      }));
      return { ...state, toolCalls, turns, seenEventIds: nextSeenEventIds, lastEventSeqByRun: nextLastEventSeqByRun };
    }
    case 'tool_progress': {
      const toolCalls = state.toolCalls.map((item) => (
        item.tool_call_id === evt.tool_call_id
          ? { ...item, progress: _appendToolProgress(item.progress || [], evt) }
          : item
      ));
      const ensured = _ensureRun(state.turns, evt, state);
      const turns = _mapRun(ensured.turns, evt.turn_id, evt.run_id, (run) => ({
        ...run,
        toolCalls: (run.toolCalls || []).map((item) => (
          item.tool_call_id === evt.tool_call_id
            ? { ...item, progress: _appendToolProgress(item.progress || [], evt) }
            : item
        )),
        eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
      }));
      return { ...state, toolCalls, turns, seenEventIds: nextSeenEventIds, lastEventSeqByRun: nextLastEventSeqByRun };
    }
    case 'execution_plan': {
      const trace = {
        execution_id: evt.execution_id || evt.trace_id,
        trace_id: evt.trace_id || evt.execution_id,
        turn_id: evt.turn_id || null,
        run_id: evt.run_id || null,
        request_summary: evt.request_summary || '',
        intent: evt.intent || '',
        request_understanding: evt.request_understanding || null,
        availability: evt.availability || null,
        steps: Array.isArray(evt.steps) ? evt.steps : [],
        review: null,
      };
      const executionTraces = upsertExecutionTrace(state.executionTraces, trace);
      const ensured = _ensureRun(state.turns, evt, state);
      const turns = _mapRun(ensured.turns, evt.turn_id, evt.run_id, (run) => _mergeTraceIntoRun(run, evt, trace));
      return {
        ...state,
        executionTraces,
        turns,
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    }
    case 'plan_step_status': {
      const executionTraces = state.executionTraces.map((trace) => {
        if (!trace) return trace;
        const traceId = evt.execution_id || evt.trace_id;
        if ((trace.execution_id || trace.trace_id) !== traceId) return trace;
        const steps = Array.isArray(trace.steps) ? trace.steps : [];
        const hasStep = steps.some((step) => step && step.step_id === evt.step_id);
        const nextSteps = hasStep
          ? steps.map((step) => (
              step && step.step_id === evt.step_id
                ? { ...step, status: evt.status, result_summary: evt.result_summary, tool_call_id: evt.tool_call_id || step.tool_call_id }
                : step
            ))
          : steps.concat([{
              step_id: evt.step_id,
              title: evt.step_id,
              kind: 'dynamic',
              status: evt.status,
              result_summary: evt.result_summary,
              tool_call_id: evt.tool_call_id || null,
            }]);
        return { ...trace, steps: nextSteps };
      });
      const turns = _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => {
        const trace = run.trace || {
          execution_id: evt.execution_id || evt.trace_id,
          trace_id: evt.trace_id || evt.execution_id,
          request_summary: '',
          intent: '',
          steps: [],
          review: null,
        };
        const steps = Array.isArray(trace.steps) ? trace.steps : [];
        const hasStep = steps.some((step) => step && step.step_id === evt.step_id);
        const nextSteps = hasStep
          ? steps.map((step) => (
              step && step.step_id === evt.step_id
                ? { ...step, status: evt.status, result_summary: evt.result_summary, tool_call_id: evt.tool_call_id || step.tool_call_id }
                : step
            ))
          : steps.concat([{
              step_id: evt.step_id,
              title: evt.step_id,
              kind: 'dynamic',
              status: evt.status,
              result_summary: evt.result_summary,
              tool_call_id: evt.tool_call_id || null,
            }]);
        return {
          ...run,
          trace: { ...trace, steps: nextSteps },
          traceId: evt.trace_id || evt.execution_id || run.traceId,
          eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
          status: evt.status === 'awaiting_resolution' ? 'awaiting_resolution' : run.status,
        };
      });
      const pendingResolution = state.pendingResolution
        && state.pendingResolution.execution_id === (evt.execution_id || evt.trace_id)
        && state.pendingResolution.step_id === evt.step_id
        && evt.status !== 'awaiting_resolution'
          ? null
          : state.pendingResolution;
      return { ...state, executionTraces, turns, pendingResolution, seenEventIds: nextSeenEventIds, lastEventSeqByRun: nextLastEventSeqByRun };
    }
    case 'review_result': {
      const review = {
        status: evt.status,
        issues: Array.isArray(evt.issues) ? evt.issues : [],
        confidence_impact: evt.confidence_impact || null,
        can_answer: Boolean(evt.can_answer),
      };
      const executionTraces = state.executionTraces.map((trace) => (
        trace && (trace.execution_id || trace.trace_id) === (evt.execution_id || evt.trace_id)
          ? { ...trace, review }
          : trace
      ));
      const turns = _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({
        ...run,
        review,
        trace: run.trace ? { ...run.trace, review } : run.trace,
        eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
      }));
      return { ...state, executionTraces, turns, seenEventIds: nextSeenEventIds, lastEventSeqByRun: nextLastEventSeqByRun };
    }
    case 'awaiting_user_ack':
      return {
        ...state,
        pendingAck: {
          turn_id: evt.turn_id || null,
          run_id: evt.run_id || null,
          ack_id: evt.ack_id || null,
          tool_call_id: evt.tool_call_id,
          sql_text: evt.sql_text || '',
          rows_estimated: evt.rows_estimated ?? null,
        },
        turns: _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({ ...run, status: 'awaiting_user_ack' })),
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    case 'awaiting_resolution':
      return {
        ...state,
        pendingResolution: {
          turn_id: evt.turn_id || null,
          run_id: evt.run_id || null,
          execution_id: evt.execution_id || evt.trace_id,
          trace_id: evt.trace_id || evt.execution_id,
          resolution_id: evt.resolution_id || null,
          step_id: evt.step_id,
          resolution_type: evt.resolution_type,
          prompt: evt.prompt || '',
          required_slots: Array.isArray(evt.required_slots) ? evt.required_slots : [],
          candidate_defaults: evt.candidate_defaults || {},
          options: Array.isArray(evt.options) ? evt.options : [],
          missing_bucket_counts: evt.missing_bucket_counts || {},
          cohort_size: evt.cohort_size ?? null,
          selected_option: evt.selected_option ?? null,
        },
        turns: _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({ ...run, status: 'awaiting_resolution' })),
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    case 'tool_completed': {
      const toolCalls = state.toolCalls.map((item) => item.tool_call_id === evt.tool_call_id ? {
        ...item,
        status: normalizeToolStatus(evt.status),
        output: evt.output,
        finishedAtMs: evt.timestamp ? (Date.parse(evt.timestamp) || Date.now()) : Date.now(),
      } : item);
      const pendingAck = state.pendingAck && state.pendingAck.tool_call_id === evt.tool_call_id ? null : state.pendingAck;
      const turns = _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({
        ...run,
        toolCalls: (run.toolCalls || []).map((item) => item.tool_call_id === evt.tool_call_id ? {
          ...item,
          status: normalizeToolStatus(evt.status),
          output: evt.output,
          finishedAtMs: evt.timestamp ? (Date.parse(evt.timestamp) || Date.now()) : Date.now(),
        } : item),
        eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
      }));
      return { ...state, toolCalls, turns, pendingAck, seenEventIds: nextSeenEventIds, lastEventSeqByRun: nextLastEventSeqByRun };
    }
    case 'assistant_thinking':
      {
        let turns = state.turns;
        const currentTurn = turns.length ? turns[turns.length - 1] : null;
        if (currentTurn) {
          turns = _mapTurns(turns, currentTurn.turnId, (turn) => ({
            ...turn,
            assistantMessage: turn.assistantMessage
              ? { ...turn.assistantMessage, content: (turn.assistantMessage.content || '') + (evt.content_delta || ''), finalized: false }
              : { role: 'assistant', content: evt.content_delta || '', finalized: false },
          }));
        }
        return { ...state, messages: _appendAssistant(state.messages, evt.content_delta || ''), turns };
      }
    case 'budget_warning':
      return { ...state, budget: { used: evt.used, limit: evt.limit, percentage: evt.percentage } };
    case 'provider_fallback':
      return { ...state, providerFallback: { from: evt.from, to: evt.to, reason: evt.reason } };
    case 'run_cancel_requested':
      return {
        ...state,
        turns: _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({ ...run, status: 'cancel_requested' })),
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    case 'run_cancelling':
      return {
        ...state,
        turns: _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({ ...run, status: 'cancelling' })),
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    case 'run_cancelled':
      return {
        ...state,
        pendingAck: state.pendingAck && state.pendingAck.run_id === evt.run_id ? null : state.pendingAck,
        pendingResolution: state.pendingResolution && state.pendingResolution.run_id === evt.run_id ? null : state.pendingResolution,
        toolCalls: state.toolCalls.map((item) => (
          item.run_id === evt.run_id && ['pending', 'running'].includes(item.status)
            ? { ...item, status: 'cancelled' }
            : item
        )),
        turns: _mapRun(state.turns, evt.turn_id, evt.run_id, (run, turn) => ({
          ...run,
          status: 'cancelled',
          completeness: (evt.completeness || (evt.payload && evt.payload.completeness)) || 'partial',
          toolCalls: (run.toolCalls || []).map((item) => (
            ['pending', 'running'].includes(item.status) ? { ...item, status: 'cancelled' } : item
          )),
          endedAt: evt.timestamp || run.endedAt,
        })).map((turn) => turn.turnId === evt.turn_id ? { ...turn, status: 'cancelled', collapsed: turn.collapsePinned ? turn.collapsed : true } : turn),
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    case 'run_failed':
      return {
        ...state,
        pendingAck: state.pendingAck && state.pendingAck.run_id === evt.run_id ? null : state.pendingAck,
        pendingResolution: state.pendingResolution && state.pendingResolution.run_id === evt.run_id ? null : state.pendingResolution,
        toolCalls: state.toolCalls.map((item) => (
          item.run_id === evt.run_id && ['pending', 'running'].includes(item.status)
            ? { ...item, status: 'error' }
            : item
        )),
        turns: _mapRun(state.turns, evt.turn_id, evt.run_id, (run) => ({
          ...run,
          status: 'failed',
          completeness: run.completeness || 'partial',
          final: evt.message ? { final_message: evt.message } : (run.final || null),
          toolCalls: (run.toolCalls || []).map((item) => (
            ['pending', 'running'].includes(item.status) ? { ...item, status: 'error' } : item
          )),
          endedAt: evt.timestamp || run.endedAt,
          eventSeq: Math.max(run.eventSeq || 0, evt.event_seq || 0),
        })).map((turn) => turn.turnId === evt.turn_id ? {
          ...turn,
          status: 'failed',
          collapsed: turn.collapsePinned ? turn.collapsed : true,
        } : turn),
        seenEventIds: nextSeenEventIds,
        lastEventSeqByRun: nextLastEventSeqByRun,
      };
    case 'error':
      return {
        ...state,
        error: { error_type: evt.error_type || 'error', message: evt.message || 'unknown error' },
        turns: evt.error_type === 'send'
          ? state.turns.map((turn) => (
              turn.optimistic && turn.status === 'queued'
                ? { ...turn, status: 'failed', optimistic: false }
                : turn
            ))
          : state.turns,
      };
    case 'final':
      {
        const turns = evt.turn_id
          ? _mapTurns(state.turns, evt.turn_id, (turn) => ({
              ...turn,
              assistantMessage: { role: 'assistant', content: evt.final_message || '', finalized: true },
              artifacts: Array.isArray(evt.artifacts) ? evt.artifacts : (Array.isArray(turn.artifacts) ? turn.artifacts : []),
              status: 'completed',
              collapsed: turn.collapsePinned ? turn.collapsed : true,
            }))
          : state.turns;
        const turnsWithRun = evt.turn_id && evt.run_id
          ? _mapRun(turns, evt.turn_id, evt.run_id, (run) => ({
              ...run,
              status: 'completed',
              completeness: 'complete',
              final: {
                final_message: evt.final_message,
                total_rounds: evt.total_rounds,
                total_tokens: evt.total_tokens,
                confidence: evt.confidence,
              },
              endedAt: evt.timestamp || run.endedAt,
            }))
          : turns;
        return {
          ...state,
          final: { final_message: evt.final_message, total_rounds: evt.total_rounds, total_tokens: evt.total_tokens, confidence: evt.confidence },
          messages: _finalizeAssistant(state.messages, evt.final_message || ''),
          turns: turnsWithRun,
          seenEventIds: nextSeenEventIds,
          lastEventSeqByRun: nextLastEventSeqByRun,
        };
      }
    case 'toggle_turn_collapse':
      return {
        ...state,
        turns: state.turns.map((turn) => (
          turn.turnId === evt.turn_id
            ? { ...turn, collapsed: !turn.collapsed, collapsePinned: true }
            : turn
        )),
      };
    case 'done':
      return { ...state, streamEnded: true };
    default:
      return state;
  }
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.chatReducer = chatReducer;
window.AppComponents.chatInitialState = chatInitialState;
