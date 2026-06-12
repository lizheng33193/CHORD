// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: HomeView at L206-L331.

const { BrainCircuit, Bot, Search, ChevronRight, AlertCircle, FileUp, MessageCircle } = window.LucideReact || {};
const COUNTRY_NAMES = { mx: '墨西哥', th: '泰国' };

function formatCountryLabel(countryCode) {
  const code = String(countryCode || '').toLowerCase();
  return `${COUNTRY_NAMES[code] || code.toUpperCase()} · ${code.toUpperCase()}`;
}

function HomeView({
  uid,
  setUid,
  uidError,
  setUidError,
  applicationTime,
  setApplicationTime,
  selectedFile,
  setSelectedFile,
  onStartUid,
  onStartFile,
  onStartChat,
  errorMessage,
  currentUser = null,
  onLogout = null,
  authorizedScopes = [],
  supportedCountries = [],
  projectId = '',
  onProjectChange,
  country = 'mx',
  onCountryChange
}) {
  const displayName = currentUser && (currentUser.display_name || currentUser.username);
  const projectEntries = [];
  const seenProjects = new Set();
  (authorizedScopes || []).forEach((scope) => {
    if (!scope || seenProjects.has(scope.project_id)) return;
    seenProjects.add(scope.project_id);
    projectEntries.push(scope);
  });
  const currentProject = projectEntries.find((scope) => scope.project_id === projectId) || projectEntries[0] || null;
  const projectCode = currentProject && currentProject.project_code
    ? String(currentProject.project_code).toUpperCase()
    : (currentUser && currentUser.project_code ? String(currentUser.project_code).toUpperCase() : 'MAPS-LZ');
  const roleLabel = currentUser && Array.isArray(currentUser.roles) && currentUser.roles.length
    ? currentUser.roles[0]
    : 'analyst';
  const allowedCountries = (() => {
    const supported = Array.isArray(supportedCountries) && supportedCountries.length ? supportedCountries : ['mx', 'th'];
    if (!currentProject) return supported;
    const projectScopes = (authorizedScopes || []).filter((scope) => scope && scope.project_id === currentProject.project_id);
    if (projectScopes.some((scope) => scope.country == null)) return supported;
    return supported.filter((code) => projectScopes.some((scope) => scope.country === code));
  })();

  return (
    <div className="min-h-screen bg-[#f8fafc] flex flex-col items-center justify-center relative overflow-hidden">
      <div
        className="absolute inset-0 z-0 opacity-20 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(circle at 50% 50%, #3b82f6 2px, transparent 2px)',
          backgroundSize: '40px 40px'
        }}
      />
      <div className="absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-blue-100/70 to-transparent" />
      <div className="z-10 flex flex-col items-center w-full max-w-3xl px-6">
        {currentUser ? (
          <div className="mb-6 flex w-full flex-wrap items-center justify-between gap-3 rounded-[1.5rem] border border-white/70 bg-white/88 px-5 py-4 shadow-[0_16px_40px_rgba(15,23,42,0.08)] backdrop-blur">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                <span>{projectCode}</span>
                <span className="h-1 w-1 rounded-full bg-slate-300"></span>
                <span>{roleLabel}</span>
              </div>
              <div className="mt-2 text-lg font-semibold text-slate-900">
                {displayName || '当前已登录用户'}
              </div>
              <div className="mt-1 text-sm text-slate-500">
                当前国家 scope：{(country || 'mx').toUpperCase()}，所有后续分析、记忆和 Trace 都会沿用这个身份上下文。
              </div>
            </div>
            {onLogout ? (
              <button
                type="button"
                onClick={onLogout}
                className="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
              >
                退出登录
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="inline-flex items-center gap-2 rounded-full bg-white/80 backdrop-blur px-4 py-2 shadow-sm border border-slate-200 mb-6">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-sm text-slate-600">UID 与文件上传均已接通真实后端</span>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {projectEntries.length > 1 ? (
            <>
              <span className="text-sm text-slate-500">项目：</span>
              <select
                value={projectId}
                onChange={(e) => onProjectChange && onProjectChange(e.target.value)}
                className="text-sm border border-slate-300 rounded-md px-2 py-1 bg-white"
              >
                {projectEntries.map((scope) => (
                  <option key={scope.project_id} value={scope.project_id}>
                    {String(scope.project_code || scope.project_id).toUpperCase()}
                  </option>
                ))}
              </select>
            </>
          ) : null}
          <span className="text-sm text-slate-500">国家：</span>
          <select
            value={country}
            onChange={(e) => onCountryChange && onCountryChange(e.target.value)}
            className="text-sm border border-slate-300 rounded-md px-2 py-1 bg-white"
          >
            {allowedCountries.map((countryCode) => (
              <option key={countryCode} value={countryCode}>
                {formatCountryLabel(countryCode)}
              </option>
            ))}
          </select>
        </div>
        <h1 className="text-3xl md:text-4xl font-bold text-slate-800 mb-4 tracking-wide flex items-center gap-3 text-center">
          <BrainCircuit className="w-10 h-10 text-blue-500" />
          多智能体用户画像综合分析平台
        </h1>
        <p className="text-slate-500 text-center max-w-2xl mb-12 text-lg leading-8">
          支持单个 UID 推理，也支持上传 txt/csv 批量分析。
        </p>
        <div className="relative w-64 h-64 mb-12 flex items-center justify-center">
          <div className="absolute inset-0 bg-blue-500 rounded-full blur-3xl opacity-20 animate-pulse" />
          <div className="absolute inset-4 border border-blue-300 rounded-full animate-[spin_10s_linear_infinite]" />
          <div className="absolute inset-8 border border-dashed border-indigo-400 rounded-full animate-[spin_15s_linear_infinite_reverse]" />
          <div className="relative bg-white p-6 rounded-full shadow-2xl border border-blue-100">
            <Bot className="w-24 h-24 text-blue-600" strokeWidth={1.5} />
          </div>
        </div>

        <div className="w-full bg-white rounded-[2rem] shadow-lg border border-slate-200 p-3">
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex items-center gap-4 flex-1 rounded-full px-3 md:px-4 py-2 transition-all focus-within:ring-4 ring-blue-100 bg-slate-50">
              <Search className="w-6 h-6 text-slate-400" />
              <input
                type="text"
                className="flex-1 outline-none text-lg text-slate-700 placeholder-slate-400 bg-transparent"
                placeholder="请输入用户 UID 进行多维画像分析..."
                value={uid}
                onChange={(event) => {
                  setUid(event.target.value);
                  if (uidError) {
                    setUidError('');
                  }
                }}
                onKeyDown={(event) => event.key === 'Enter' && onStartUid()}
              />
            </div>
            <input
              type="datetime-local"
              className="outline-none text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded-full px-4 py-3 min-w-[220px]"
              value={applicationTime}
              onChange={(event) => setApplicationTime(event.target.value)}
            />
            <button
              onClick={onStartUid}
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-full font-medium transition-colors flex items-center justify-center gap-2"
            >
              开始推理
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
          {uidError ? (
            <div className="px-3 pt-3 text-sm text-red-600 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{uidError}</span>
            </div>
          ) : null}
          <p className="text-xs text-slate-500 px-3 pt-3">
            App画像会基于该申请时间计算安装时间衰减、近7天/30天借贷风险和页面时间线。
          </p>
        </div>

        <div className="w-full mt-5 bg-white/90 backdrop-blur rounded-3xl shadow-lg border border-slate-200 p-5">
          <div className="flex items-center gap-3 mb-4 text-slate-700">
            <FileUp className="w-5 h-5 text-blue-600" />
            <span className="font-semibold">批量文件上传分析</span>
          </div>
          <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-center">
            <label className="flex-1 border border-dashed border-slate-300 rounded-2xl px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors cursor-pointer">
              <input
                type="file"
                accept=".txt,.csv"
                className="hidden"
                onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
              />
              <div className="text-slate-700 font-medium">
                {selectedFile ? selectedFile.name : '选择 txt 或 csv 文件'}
              </div>
              <div className="text-sm text-slate-400 mt-1">
                支持 sample_ids.txt / 单列 uid CSV / 含 uid 列 CSV
              </div>
            </label>
            <button
              onClick={onStartFile}
              className="bg-slate-800 hover:bg-slate-900 text-white px-6 py-3 rounded-2xl font-medium transition-colors"
            >
              上传并分析
            </button>
          </div>
        </div>

        <div className="w-full mt-5 bg-gradient-to-r from-sky-50 to-indigo-50 backdrop-blur rounded-3xl shadow-lg border border-sky-200 p-5">
          <div className="flex items-center gap-3 mb-3 text-slate-700">
            {MessageCircle ? <MessageCircle className="w-5 h-5 text-sky-600" /> : null}
            <span className="font-semibold">自然语言对话分析</span>
            <span className="text-xs text-slate-500">/ NL Chat</span>
          </div>
          <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-center">
            <div className="flex-1 text-sm text-slate-600 leading-6">
              直接用中文描述你的分析需求（例如：<span className="text-slate-800">分析 G3 在墨西哥的 churn 风险</span>），由 Orchestrator Agent 自动选择工具并返回结果。
            </div>
            <button
              onClick={onStartChat}
              className="bg-sky-600 hover:bg-sky-700 text-white px-6 py-3 rounded-2xl font-medium transition-colors flex items-center justify-center gap-2 whitespace-nowrap"
            >
              {MessageCircle ? <MessageCircle className="w-4 h-4" /> : null}
              进入对话模式
            </button>
          </div>
        </div>

        {errorMessage ? (
          <div className="mt-5 w-full rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-red-700 flex items-start gap-3 shadow-sm">
            <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.HomeView = HomeView;
