const { LoginPage, RegisterPage } = window.AppComponents;
const authStoreRef = window.AppState.authStore;
const authApi = window.AppServices.authApi;

function AuthGate({ children }) {
  const authState = authStoreRef.useAuthState();
  const [mode, setMode] = React.useState('login');
  const [status, setStatus] = React.useState('checking');
  const [errorMessage, setErrorMessage] = React.useState('');
  const [successMessage, setSuccessMessage] = React.useState('');

  React.useEffect(() => {
    let cancelled = false;
    setStatus('checking');
    authApi.restoreSession().then((user) => {
      if (cancelled) return;
      if (user) {
        setStatus('authenticated');
        setErrorMessage('');
        setSuccessMessage('');
      } else {
        setStatus('unauthenticated');
      }
    }).catch(() => {
      if (cancelled) return;
      setStatus('unauthenticated');
      setErrorMessage('登录状态已失效，请重新登录。');
    });

    return () => { cancelled = true; };
  }, [authState.token]);

  React.useEffect(() => {
    function handleForcedLogout() {
      setStatus('unauthenticated');
      setMode('login');
      setErrorMessage('登录状态已过期，请重新登录。');
    }

    window.addEventListener('maps-auth-logout', handleForcedLogout);
    return () => window.removeEventListener('maps-auth-logout', handleForcedLogout);
  }, []);

  async function handleLogin(payload) {
    setStatus('submitting');
    setErrorMessage('');
    setSuccessMessage('');
    try {
      await authApi.login(payload);
      setStatus('authenticated');
    } catch (error) {
      setStatus('unauthenticated');
      setErrorMessage((error && error.message) || '登录失败，请稍后重试。');
    }
  }

  async function handleRegister(form) {
    if (form.password !== form.confirmPassword) {
      setErrorMessage('两次输入的密码不一致。');
      setSuccessMessage('');
      return;
    }
    setStatus('submitting');
    setErrorMessage('');
    setSuccessMessage('');
    try {
      await authApi.register({
        username: form.username,
        email: form.email,
        display_name: form.display_name || null,
        password: form.password,
      });
      setStatus('unauthenticated');
      setMode('login');
      setSuccessMessage('账号已创建，请使用新账号登录。');
    } catch (error) {
      setStatus('unauthenticated');
      setErrorMessage((error && error.message) || '注册失败，请稍后重试。');
    }
  }

  async function handleLogout() {
    setStatus('checking');
    try {
      await authApi.logout();
    } finally {
      setStatus('unauthenticated');
      setMode('login');
      setSuccessMessage('');
    }
  }

  if (status === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#eef3f8] px-4">
        <div className="rounded-[2rem] border border-white/80 bg-white/90 px-8 py-10 text-center shadow-[0_24px_60px_rgba(15,23,42,0.1)]">
          <div className="mx-auto mb-5 h-14 w-14 animate-pulse rounded-2xl bg-[#1e40af]/10" />
          <h1 className="font-['Lexend'] text-2xl font-semibold text-slate-900">正在校验会话</h1>
          <p className="mt-3 text-sm leading-7 text-slate-500">
            正在恢复你的身份、项目和国家上下文。
          </p>
        </div>
      </div>
    );
  }

  if (status !== 'authenticated' || !authState.user) {
    if (mode === 'register') {
      return (
        <RegisterPage
          loading={status === 'submitting'}
          errorMessage={errorMessage}
          successMessage={successMessage}
          onSubmit={handleRegister}
          onSwitchToLogin={() => {
            setMode('login');
            setErrorMessage('');
            setSuccessMessage('');
          }}
        />
      );
    }

    return (
      <LoginPage
        loading={status === 'submitting'}
        errorMessage={errorMessage}
        onSubmit={handleLogin}
        onSwitchToRegister={() => {
          setMode('register');
          setErrorMessage('');
          setSuccessMessage('');
        }}
      />
    );
  }

  if (typeof children === 'function') {
    return children({
      currentUser: authState.user,
      authState,
      onLogout: handleLogout,
      setPreferredCountry: authStoreRef.setPreferredCountry,
      setPreferredProjectId: authStoreRef.setPreferredProjectId,
    });
  }
  return children || null;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.AuthGate = AuthGate;
