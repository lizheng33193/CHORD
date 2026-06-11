// ModuleStatusPanel — four-state wrapper for progressive module loading.
// States: loading | error | idle | success (renders children).

function ModuleStatusPanel({ state, onRetry, children }) {
  const status = (state && state.status) || 'idle';
  const error = (state && state.error) || '';

  if (status === 'loading') {
    return (
      <div className="h-full min-h-[360px] flex flex-col items-center justify-center text-center">
        <div className="sr-only">模块分析骨架屏</div>
        <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin mb-4" />
        <div className="text-lg font-semibold text-slate-800">正在分析该模块</div>
        <div className="text-sm text-slate-500 mt-2">后端完成后会自动渲染，其他已完成模块可先查看。</div>
        <div className="skeleton-shimmer mt-6 w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm">
          <div className="h-4 w-44 animate-pulse rounded-full bg-slate-200"></div>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <div className="h-20 animate-pulse rounded-xl bg-slate-100"></div>
            <div className="h-20 animate-pulse rounded-xl bg-slate-100"></div>
            <div className="h-20 animate-pulse rounded-xl bg-slate-100"></div>
          </div>
          <div className="mt-5 space-y-3">
            <div className="h-3 w-full animate-pulse rounded-full bg-slate-100"></div>
            <div className="h-3 w-11/12 animate-pulse rounded-full bg-slate-100"></div>
            <div className="h-3 w-8/12 animate-pulse rounded-full bg-slate-100"></div>
          </div>
        </div>
        {error && <div className="mt-3 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-4 py-1.5">{error}</div>}
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className="h-full min-h-[360px] flex flex-col items-center justify-center text-center">
        <div className="w-full max-w-2xl rounded-2xl border border-red-200 bg-red-50 px-5 py-5 text-red-700">
          <div className="font-semibold text-lg mb-2">该子页面分析失败</div>
          <div className="text-sm break-words">{error || '未知错误'}</div>
          <button onClick={onRetry} className="mt-4 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm">
            重试当前子页面
          </button>
        </div>
      </div>
    );
  }
  if (status === 'idle') {
    return (
      <div className="h-full min-h-[360px] flex flex-col items-center justify-center text-center">
        <div className="text-lg font-semibold text-slate-800">该子页面尚未分析</div>
        <div className="text-sm text-slate-500 mt-2">请点击重试触发该模块分析。</div>
        <button onClick={onRetry} className="mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm">
          开始分析
        </button>
      </div>
    );
  }
  return children;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ModuleStatusPanel = ModuleStatusPanel;
