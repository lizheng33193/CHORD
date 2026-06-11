const AUTH_STORAGE_KEY = 'maps-lz.auth.session.v1';

function readStoredAuthState() {
  if (typeof window === 'undefined' || !window.localStorage) {
    return {
      token: '',
      user: null,
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
        preferredProjectId: '',
        preferredCountry: 'mx'
      };
    }
    const parsed = JSON.parse(raw);
    return {
      token: parsed && typeof parsed.token === 'string' ? parsed.token : '',
      user: parsed && parsed.user && typeof parsed.user === 'object' ? parsed.user : null,
      preferredProjectId: parsed && parsed.preferredProjectId ? String(parsed.preferredProjectId) : '',
      preferredCountry: parsed && parsed.preferredCountry ? String(parsed.preferredCountry).toLowerCase() : 'mx'
    };
  } catch (_err) {
    return {
      token: '',
      user: null,
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
    preferredProjectId: user && user.default_project_id ? String(user.default_project_id) : (authStoreState.preferredProjectId || ''),
    preferredCountry: (user && user.default_country) ? String(user.default_country).toLowerCase() : (authStoreState.preferredCountry || 'mx')
  });
}

function setUser(user) {
  setAuthState({
    user: user || null,
    preferredProjectId: user && user.default_project_id ? String(user.default_project_id) : authStoreState.preferredProjectId,
    preferredCountry: (user && user.default_country) ? String(user.default_country).toLowerCase() : authStoreState.preferredCountry
  });
}

function clearSession() {
  authStoreState.token = '';
  authStoreState.user = null;
  authStoreState.preferredProjectId = '';
  authStoreState.preferredCountry = 'mx';
  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  notifyAuthStore();
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
  clearSession,
  setPreferredCountry,
  setPreferredProjectId,
  subscribe: subscribeAuthStore,
  hasPermission,
  hasAnyPermission,
  useAuthState,
};

window.AppState = window.AppState || {};
window.AppState.authStore = authStore;
