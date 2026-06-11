const httpClient = window.AppServices.httpClient;
const authStoreForApi = window.AppState.authStore;

async function fetchAuthRuntimeConfig() {
  try {
    return await httpClient.json('/api/ui-config', {}, '获取运行时配置失败。');
  } catch (_err) {
    return { auth_enabled: true };
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
  return response;
}

async function fetchCurrentUser() {
  const user = await httpClient.json('/api/auth/me', {}, '获取当前用户失败。');
  authStoreForApi.setUser(user);
  return user;
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
    return await fetchCurrentUser();
  } catch (_err) {
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
  fetchRuntimeConfig: fetchAuthRuntimeConfig,
  restoreSession: restoreAuthSession,
  logout: logoutAuthUser,
};
