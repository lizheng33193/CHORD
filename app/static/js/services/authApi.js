const httpClient = window.AppServices.httpClient;
const authStoreForApi = window.AppState.authStore;

function normalizeSupportedCountries(rawCountries) {
  if (!Array.isArray(rawCountries) || !rawCountries.length) return ['mx', 'th'];
  return rawCountries.map((country) => String(country).toLowerCase()).filter(Boolean);
}

async function fetchAuthRuntimeConfig() {
  try {
    const payload = await httpClient.json('/api/ui-config', {}, '获取运行时配置失败。');
    return {
      ...payload,
      supported_countries: normalizeSupportedCountries(payload && payload.supported_countries),
    };
  } catch (_err) {
    return { auth_enabled: true, supported_countries: ['mx', 'th'] };
  }
}

async function registerAuthUser(payload) {
  return await httpClient.json('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload || {})
  }, '注册失败，请稍后重试。');
}

async function loginAuthUser(payload) {
  const response = await httpClient.json('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload || {})
  }, '登录失败，请检查账号密码。');
  authStoreForApi.setSession(response.access_token, response.user);
  try {
    await fetchAuthorizedScopes();
  } catch (_err) {}
  return response;
}

async function fetchCurrentUser(options) {
  const user = await httpClient.json('/api/auth/me', options || {}, '获取当前用户失败。');
  authStoreForApi.setUser(user);
  return user;
}

async function fetchAuthorizedScopes() {
  const payload = await httpClient.json('/api/auth/my-projects', {
    skipScopeHeaders: true,
  }, '获取授权项目失败。');
  const projects = Array.isArray(payload && payload.projects) ? payload.projects : [];
  authStoreForApi.setAuthorizedScopes(projects);
  return projects;
}

async function restoreAuthSession() {
  const state = authStoreForApi.getState();
  const runtimeConfig = await fetchAuthRuntimeConfig();
  if (!runtimeConfig.auth_enabled && !state.token) {
    try {
      return await fetchCurrentUser();
    } catch (_err) {
      return null;
    }
  }
  if (!state.token) return null;
  try {
    const authorizedScopes = await fetchAuthorizedScopes();
    const resolvedScope = authStoreForApi.resolvePreferredScope(
      authorizedScopes,
      runtimeConfig.supported_countries
    );
    if (resolvedScope.projectId) {
      authStoreForApi.setPreferredProjectId(resolvedScope.projectId);
    }
    if (resolvedScope.country) {
      authStoreForApi.setPreferredCountry(resolvedScope.country);
    }
    return await fetchCurrentUser({
      skipScopeHeaders: true,
      headers: {
        ...(resolvedScope.projectId ? { 'X-Project-ID': resolvedScope.projectId } : {}),
        ...(resolvedScope.country ? { 'X-Country': resolvedScope.country } : {}),
      }
    });
  } catch (error) {
    if (error && error.status === 403) {
      authStoreForApi.clearInvalidScopeOverride();
      const fallbackState = authStoreForApi.getState();
      return await fetchCurrentUser({
        skipScopeHeaders: true,
        headers: {
          ...(fallbackState.preferredProjectId ? { 'X-Project-ID': fallbackState.preferredProjectId } : {}),
          ...(fallbackState.preferredCountry ? { 'X-Country': fallbackState.preferredCountry } : {}),
        }
      });
    }
    authStoreForApi.clearSession();
    return null;
  }
}

async function logoutAuthUser() {
  try {
    await httpClient.request('/api/auth/logout', { method: 'POST' });
  } finally {
    authStoreForApi.clearSession();
  }
}

window.AppServices = window.AppServices || {};
window.AppServices.authApi = {
  register: registerAuthUser,
  login: loginAuthUser,
  fetchMe: fetchCurrentUser,
  fetchAuthorizedScopes,
  fetchRuntimeConfig: fetchAuthRuntimeConfig,
  restoreSession: restoreAuthSession,
  logout: logoutAuthUser,
};
