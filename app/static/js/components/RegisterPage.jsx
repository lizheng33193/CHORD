const { UserPlus, Shield, Mail, KeyRound, ArrowLeft, AlertCircle: RegisterAlertCircle } = window.LucideReact || {};

function RegisterPage({
  onSubmit,
  onSwitchToLogin,
  loading = false,
  errorMessage = '',
  successMessage = '',
}) {
  const [form, setForm] = React.useState({
    username: '',
    email: '',
    display_name: '',
    password: '',
    confirmPassword: '',
  });

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!onSubmit) return;
    onSubmit(form);
  }

  return (
    <div className="min-h-screen bg-[#eef3f8] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-6xl items-stretch gap-8 lg:grid-cols-[0.88fr_1.12fr]">
        <section className="rounded-[2rem] border border-white/70 bg-[linear-gradient(160deg,_#153182,_#1e40af_52%,_#2e6de4)] p-6 text-white shadow-[0_30px_80px_rgba(15,23,42,0.14)] sm:p-8 lg:p-10">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="mb-10 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/14">
                <UserPlus className="h-6 w-6" />
              </div>
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-blue-100/85">Register</p>
              <h1 className="mt-4 font-['Lexend'] text-4xl font-semibold leading-tight">
                建一个真实身份，
                <span className="block text-blue-100">让后续每一次 Agent 行为都有归属。</span>
              </h1>
              <p className="mt-5 max-w-md text-base leading-8 text-blue-100/90">
                新账号默认加入 `MAPS-LZ` 项目，并获得基础分析能力。你可以先从画像、Trace 和 Memory 入口开始使用系统。
              </p>
            </div>

            <div className="mt-8 space-y-4 rounded-[1.75rem] border border-white/12 bg-white/10 p-5">
              {[
                '默认分配到项目级 scope，避免匿名会话混入历史。',
                '登录后请求会自动携带 Bearer token、项目和国家上下文。',
                '后续 SQL 审核、Memory、Trace 都会沿用同一身份基线。',
              ].map((line) => (
                <div key={line} className="flex items-start gap-3 text-sm leading-7 text-blue-50/95">
                  <Shield className="mt-1 h-4 w-4 shrink-0" />
                  <span>{line}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="rounded-[2rem] border border-slate-200/80 bg-white p-6 shadow-[0_24px_60px_rgba(15,23,42,0.1)] sm:p-8 lg:p-10">
          <div className="mb-8 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Create Account</p>
              <h2 className="mt-3 font-['Lexend'] text-3xl font-semibold text-slate-900">注册新的分析身份</h2>
            </div>
            <button
              type="button"
              onClick={onSwitchToLogin}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
            >
              <ArrowLeft className="h-4 w-4" />
              返回登录
            </button>
          </div>

          <form className="grid gap-5 sm:grid-cols-2" onSubmit={handleSubmit}>
            <div className="sm:col-span-2">
              <label htmlFor="register-username" className="mb-2 block text-sm font-medium text-slate-700">
                用户名
              </label>
              <div className="relative">
                <UserPlus className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="register-username"
                  type="text"
                  autoComplete="username"
                  value={form.username}
                  onChange={(event) => updateField('username', event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  placeholder="3-64 位，后续可作为登录名"
                />
              </div>
            </div>

            <div className="sm:col-span-2">
              <label htmlFor="register-email" className="mb-2 block text-sm font-medium text-slate-700">
                邮箱
              </label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="register-email"
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  onChange={(event) => updateField('email', event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  placeholder="用于登录和审计识别"
                />
              </div>
            </div>

            <div className="sm:col-span-2">
              <label htmlFor="register-display-name" className="mb-2 block text-sm font-medium text-slate-700">
                显示名称
              </label>
              <input
                id="register-display-name"
                type="text"
                autoComplete="name"
                value={form.display_name}
                onChange={(event) => updateField('display_name', event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                placeholder="用于界面展示和审计描述"
              />
            </div>

            <div>
              <label htmlFor="register-password" className="mb-2 block text-sm font-medium text-slate-700">
                密码
              </label>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="register-password"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(event) => updateField('password', event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  placeholder="至少 8 位"
                />
              </div>
            </div>

            <div>
              <label htmlFor="register-confirm-password" className="mb-2 block text-sm font-medium text-slate-700">
                确认密码
              </label>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="register-confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={form.confirmPassword}
                  onChange={(event) => updateField('confirmPassword', event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  placeholder="再次输入密码"
                />
              </div>
            </div>

            {errorMessage ? (
              <div className="sm:col-span-2 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                <RegisterAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            ) : null}

            {successMessage ? (
              <div className="sm:col-span-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {successMessage}
              </div>
            ) : null}

            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-2xl bg-[#1e40af] px-5 py-3.5 font-medium text-white shadow-lg shadow-blue-700/20 transition hover:bg-[#173689] disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {loading ? '创建中...' : '创建账号'}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.RegisterPage = RegisterPage;
