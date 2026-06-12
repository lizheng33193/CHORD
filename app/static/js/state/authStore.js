const AUTH_STORAGE_KEY = 'maps-lz.auth.session.v1';

function readStoredAuthState() {
  if (typeof window === 'undefined' || !window.localStorage) {
    return {
      token: '',
      user: null,
      authorizedScopes: [],
      preferredProjectId: '',
      preferredCountry: 'mx'
    };
  }
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) {
      return {
        token: '',
        user: null,
        authorizedScopes: [],
        preferredProjectId: '',
        preferredCountry: 'mx'
      };
    }
    const parsed = JSON.parse(raw);
    return {
      token: parsed && typeof parsed.token === 'string' ? parsed.token : '',
      user: parsed && parsed.user && typeof parsed.user === 'object' ? parsed.user : null,
      authorizedScopes: parsed && Array.isArray(parsed.authorizedScopes) ? parsed.authorizedScopes : [],
      preferredProjectId: parsed && parsed.preferredProjectId ? String(parsed.preferredProjectId) : '',
      preferredCountry: parsed && parsed.preferredCountry ? String(parsed.preferredCountry).toLowerCase() : 'mx'
    };
  } catch (_err) {
    return {
      token: '',
      user: null,
      authorizedScopes: [],
      preferredProjectId: '',
      preferredCountry: 'mx'
    };
  }
}

const authStoreListeners = new Set();
const authStoreState = readStoredAuthState();

function persistAuthState() {
  if (typeof window === 'undefined' || !window.localStorage) return;
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authStoreState));
}

function notifyAuthStore() {
  authStoreListeners.forEach((listener) => {
    try {
      listener(authStoreState);
    } catch (_err) {}
  });
}

function getAuthState() {
  return {
    token: authStoreState.token,
    user: authStoreState.user,
    authorizedScopes: Array.isArray(authStoreState.authorizedScopes) ? [...authStoreState.authorizedScopes] : [],
    preferredProjectId: authStoreState.preferredProjectId,
    preferredCountry: authStoreState.preferredCountry,
  };
}

function setAuthState(patch) {
  Object.assign(authStoreState, patch || {});
  if (!authStoreState.preferredCountry) {
    authStoreState.preferredCountry = 'mx';
  }
  persistAuthState();
  notifyAuthStore();
}

function setSession(token, user) {
  setAuthState({
    token: token || '',
    user: user || null,
    authorizedScopes: authStoreState.authorizedScopes,
    preferredProjectId: user && user.default_project_id ? String(user.default_project_id) : (authStoreState.preferredProjectId || ''),
    preferredCountry: (user && user.default_country) ? String(user.default_country).toLowerCase() : (authStoreState.preferredCountry || 'mx')
  });
}

function setUser(user) {
  setAuthState({
    user: user || null,
    authorizedScopes: authStoreState.authorizedScopes,
    preferredProjectId: user && user.default_project_id ? String(user.default_project_id) : authStoreState.preferredProjectId,
    preferredCountry: (user && user.default_country) ? String(user.default_country).toLowerCase() : authStoreState.preferredCountry
  });
}

function normalizeScopeEntry(scope) {
  if (!scope || typeof scope !== 'object') return null;
  const projectId = scope.project_id != null ? String(scope.project_id) : '';
  if (!projectId) return null;
  return {
    project_id: projectId,
    project_code: scope.project_code ? String(scope.project_code) : '',
    access_level: scope.access_level ? String(scope.access_level) : 'member',
    country: scope.country ? String(scope.country).toLowerCase() : null,
  };
}

function setAuthorizedScopes(scopes) {
  const normalized = Array.isArray(scopes)
    ? scopes.map(normalizeScopeEntry).filter(Boolean)
    : [];
  setAuthState({ authorizedScopes: normalized });
}

function getAuthorizedProjects() {
  const seen = new Set();
  return (authStoreState.authorizedScopes || []).filter((scope) => {
    if (!scope || seen.has(scope.project_id)) return false;
    seen.add(scope.project_id);
    return true;
  });
}

function getAuthorizedCountries(projectId, supportedCountries) {
  const projectKey = projectId ? String(projectId) : '';
  const scopes = (authStoreState.authorizedScopes || []).filter((scope) => !projectKey || scope.project_id === projectKey);
  const supported = Array.isArray(supportedCountries) && supportedCountries.length
    ? supportedCountries.map((country) => String(country).toLowerCase())
    : ['mx', 'th'];
  if (!scopes.length) return supported;
  const allowAll = scopes.some((scope) => scope.country == null);
  if (allowAll) return supported;
  return supported.filter((country) => scopes.some((scope) => scope.country === country));
}

function resolvePreferredScope(scopes, supportedCountries) {
  const normalizedScopes = Array.isArray(scopes)
    ? scopes.map(normalizeScopeEntry).filter(Boolean)
    : (authStoreState.authorizedScopes || []);
  const supported = Array.isArray(supportedCountries) && supportedCountries.length
    ? supportedCountries.map((country) => String(country).toLowerCase())
    : ['mx', 'th'];
  const projects = [];
  const seen = new Set();
  normalizedScopes.forEach((scope) => {
    if (!seen.has(scope.project_id)) {
      seen.add(scope.project_id);
      projects.push(scope);
    }
  });
  const preferredProjectId = authStoreState.preferredProjectId;
  const project = projects.find((scope) => scope.project_id === preferredProjectId) || projects[0] || null;
  const projectId = project ? project.project_id : '';
  const countries = getAuthorizedCountries(projectId, supported);
  const preferredCountry = (authStoreState.preferredCountry || '').toLowerCase();
  const country = (countries.includes(preferredCountry) ? preferredCountry : (countries[0] || 'mx'));
  return { projectId, country };
}

function clearSession() {
  authStoreState.token = '';
  authStoreState.user = null;
  authStoreState.authorizedScopes = [];
  authStoreState.preferredProjectId = '';
  authStoreState.preferredCountry = 'mx';
  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  notifyAuthStore();
}

function clearInvalidScopeOverride() {
  const resolved = resolvePreferredScope(authStoreState.authorizedScopes, ['mx', 'th']);
  setAuthState({
    preferredProjectId: resolved.projectId,
    preferredCountry: resolved.country,
  });
}

function setPreferredCountry(country) {
  setAuthState({ preferredCountry: (country || 'mx').toLowerCase() });
}

function setPreferredProjectId(projectId) {
  setAuthState({ preferredProjectId: projectId ? String(projectId) : '' });
}

function subscribeAuthStore(listener) {
  authStoreListeners.add(listener);
  return () => authStoreListeners.delete(listener);
}

function hasPermission(permission) {
  const permissions = (authStoreState.user && Array.isArray(authStoreState.user.permissions))
    ? authStoreState.user.permissions
    : [];
  return permissions.includes(permission);
}

function hasAnyPermission(permissionCodes) {
  return (permissionCodes || []).some((permission) => hasPermission(permission));
}

function useAuthState() {
  const [snapshot, setSnapshot] = React.useState(getAuthState);

  React.useEffect(() => subscribeAuthStore(() => setSnapshot(getAuthState())), []);
  return snapshot;
}

const authStore = {
  getState: getAuthState,
  setSession,
  setUser,
  setAuthorizedScopes,
  clearSession,
  clearInvalidScopeOverride,
  resolvePreferredScope,
  getAuthorizedProjects,
  getAuthorizedCountries,
  setPreferredCountry,
  setPreferredProjectId,
  subscribe: subscribeAuthStore,
  hasPermission,
  hasAnyPermission,
  useAuthState,
};

window.AppState = window.AppState || {};
window.AppState.authStore = authStore;
