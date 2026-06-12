const authStore = (window.AppState && window.AppState.authStore) || null;

function buildRequestHeaders(extraHeaders, body, options) {
  const headers = new Headers(extraHeaders || {});
  const opts = options || {};
  const authState = authStore ? authStore.getState() : { token: '', preferredProjectId: '', preferredCountry: 'mx' };

  if (!opts.skipAuthHeaders && authState.token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${authState.token}`);
  }
  if (!opts.skipScopeHeaders && authState.preferredCountry && !headers.has('X-Country')) {
    headers.set('X-Country', authState.preferredCountry);
  }
  if (!opts.skipScopeHeaders && authState.preferredProjectId && !headers.has('X-Project-ID')) {
    headers.set('X-Project-ID', authState.preferredProjectId);
  }
  if (!(body instanceof FormData) && body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  return headers;
}

function resolveHttpErrorMessage(payload, response, fallback) {
  if (payload && typeof payload.detail === 'string') return payload.detail;
  if (payload && payload.detail && typeof payload.detail.reason === 'string') return payload.detail.reason;
  if (payload && typeof payload.message === 'string') return payload.message;
  return fallback || `HTTP ${response.status}`;
}

async function request(url, options) {
  const opts = options || {};
  const {
    skipAuthHeaders,
    skipScopeHeaders,
    ...fetchOptions
  } = opts;
  const response = await fetch(url, {
    ...fetchOptions,
    headers: buildRequestHeaders(fetchOptions.headers, fetchOptions.body, {
      skipAuthHeaders: Boolean(skipAuthHeaders),
      skipScopeHeaders: Boolean(skipScopeHeaders),
    }),
  });

  if (response.status === 401 && authStore) {
    authStore.clearSession();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('maps-auth-logout'));
    }
  }
  return response;
}

async function json(url, options, fallbackMessage) {
  const response = await request(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(resolveHttpErrorMessage(payload, response, fallbackMessage));
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function openEventStream(url, handlers, options) {
  const controller = new AbortController();
  const signal = controller.signal;
  const opts = options || {};
  const callbacks = handlers || {};
  const streamHandle = {
    readyState: 0,
    close() {
      if (streamHandle.readyState === 2) return;
      streamHandle.readyState = 2;
      controller.abort();
    },
    ready: null,
  };

  const runner = (async () => {
    const response = await request(url, {
      method: opts.method || 'GET',
      headers: { Accept: 'text/event-stream', ...(opts.headers || {}) },
      body: opts.body,
      signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(resolveHttpErrorMessage(payload, response, `stream ${response.status}`));
    }
    if (!response.body) {
      throw new Error('stream body unavailable');
    }
    streamHandle.readyState = 1;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex = -1;
      while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        if (!block || block.startsWith(':')) continue;
        const dataLine = block.split('\n').find((line) => line.startsWith('data:'));
        if (!dataLine) continue;
        try {
          const event = JSON.parse(dataLine.slice(5).trim());
          if (callbacks.onEvent) callbacks.onEvent(event);
        } catch (err) {
          if (callbacks.onError) callbacks.onError(err);
        }
      }
    }

    streamHandle.readyState = 2;
    if (callbacks.onClose) callbacks.onClose();
  })().catch((err) => {
    if (signal.aborted) {
      streamHandle.readyState = 2;
      if (callbacks.onClose) callbacks.onClose();
      return;
    }
    streamHandle.readyState = 2;
    if (callbacks.onError) callbacks.onError(err);
    if (callbacks.onClose) callbacks.onClose();
  });

  streamHandle.ready = runner;
  return streamHandle;
}

window.AppServices = window.AppServices || {};
window.AppServices.httpClient = {
  request,
  json,
  openEventStream,
};
