const { ShieldCheck, LockKeyhole, Database, Workflow, ArrowRight, AlertCircle } = window.LucideReact || {};

function LoginPage({
  onSubmit,
  onSwitchToRegister,
  loading = false,
  errorMessage = '',
}) {
  const [usernameOrEmail, setUsernameOrEmail] = React.useState('');
  const [password, setPassword] = React.useState('');

  function handleSubmit(event) {
    event.preventDefault();
    if (!onSubmit) return;
    onSubmit({
      username_or_email: usernameOrEmail.trim(),
      password,
    });
  }

  return (
    <div className="min-h-screen overflow-hidden bg-[#eef3f8] text-slate-900">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(30,64,175,0.16),_transparent_34%),radial-gradient(circle_at_bottom_right,_rgba(245,158,11,0.16),_transparent_26%)]" />
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage: 'linear-gradient(rgba(148,163,184,0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.12) 1px, transparent 1px)',
          backgroundSize: '32px 32px'
        }}
      />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl items-center px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid w-full gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-[2rem] border border-white/70 bg-white/78 p-6 shadow-[0_30px_80px_rgba(15,23,42,0.12)] backdrop-blur-xl sm:p-8 lg:p-10">
            <div className="mb-10 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#1e40af] text-white shadow-lg shadow-blue-700/20">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <div>
                <p className="font-['Lexend'] text-lg font-semibold tracking-tight">MAPS-LZ Harness</p>
                <p className="text-sm text-slate-500">Identity & Permission Foundation</p>
              </div>
            </div>

            <div className="max-w-2xl space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-900">
                <LockKeyhole className="h-4 w-4" />
                所有后续 Agent 行为都以真实身份和项目 scope 执行
              </div>

              <div className="space-y-4">
                <h1 className="font-['Lexend'] text-4xl font-semibold leading-tight text-slate-900 sm:text-5xl">
                  登录之后，系统才能知道
                  <span className="block text-[#1e40af]">是谁在分析、谁在审批、谁在写记忆。</span>
                </h1>
                <p className="max-w-xl text-lg leading-8 text-slate-600">
                  这一层不只是页面入口，它会把用户身份、项目边界、国家权限和审计链路统一接到
                  Orchestrator、Memory、Trace、SQL 执行与后续 LangGraph state。
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  {
                    icon: Database,
                    title: 'Project Scope',
                    desc: '同一套 Harness 下做多项目、多国家隔离',
                  },
                  {
                    icon: Workflow,
                    title: 'Agent Actor',
                    desc: 'Trace、Session、Tool Call 都带真实 actor',
                  },
                  {
                    icon: ShieldCheck,
                    title: 'Audit Ready',
                    desc: 'SQL 审核、执行、记忆写入可追踪可回放',
                  },
                ].map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.title} className="rounded-3xl border border-slate-200/80 bg-slate-50/90 p-5 shadow-sm">
                      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-[#1e40af] shadow-sm">
                        <Icon className="h-5 w-5" />
                      </div>
                      <h2 className="font-['Lexend'] text-base font-semibold text-slate-900">{item.title}</h2>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{item.desc}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          <section className="rounded-[2rem] border border-slate-200/80 bg-white p-6 shadow-[0_24px_60px_rgba(15,23,42,0.1)] sm:p-8 lg:p-10">
            <div className="mb-8">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Sign In</p>
              <h2 className="mt-3 font-['Lexend'] text-3xl font-semibold text-slate-900">进入分析工作台</h2>
              <p className="mt-3 text-sm leading-7 text-slate-500">
                使用用户名或邮箱登录。系统会自动恢复你的项目与默认国家上下文。
              </p>
            </div>

            <form className="space-y-5" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="login-identity" className="mb-2 block text-sm font-medium text-slate-700">
                  用户名或邮箱
                </label>
                <input
                  id="login-identity"
                  type="text"
                  autoComplete="username"
                  value={usernameOrEmail}
                  onChange={(event) => setUsernameOrEmail(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  placeholder="例如 admin 或 analyst@example.com"
                />
              </div>

              <div>
                <label htmlFor="login-password" className="mb-2 block text-sm font-medium text-slate-700">
                  密码
                </label>
                <input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-base text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  placeholder="请输入密码"
                />
              </div>

              {errorMessage ? (
                <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              ) : null}

              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#1e40af] px-5 py-3.5 font-medium text-white shadow-lg shadow-blue-700/20 transition hover:bg-[#1a3691] disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                <span>{loading ? '登录中...' : '登录并进入工作台'}</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>

            <div className="mt-8 rounded-3xl border border-slate-200 bg-slate-50 px-5 py-4">
              <p className="text-sm leading-7 text-slate-600">
                还没有账号？
                <button
                  type="button"
                  onClick={onSwitchToRegister}
                  className="ml-2 font-semibold text-[#1e40af] transition hover:text-[#172f80]"
                >
                  创建一个分析账号
                </button>
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.LoginPage = LoginPage;
