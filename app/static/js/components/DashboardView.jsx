// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Source: DashboardView at L349-L438.
// Renamed JSX call: <ComprehensivePanelV2> -> <ComprehensivePanel>
// (legacy V2 alias dropped per Phase F.5 user direction).

const { ChevronRight, Bot, Network, Smartphone, Activity, CreditCard, Package, Headphones, Search, Settings } = window.LucideReact || {};
const {
  AppPanel,
  BehaviorPanel,
  RichCreditPanel,
  ComprehensivePanel,
  ProductAdvicePanel,
  OpsAdvicePanel,
  LabelsOverviewCard,
  TracePanel,
  ModuleStatusPanel,
  ChatPanel,
  KnowledgeBaseConsole,
} = window.AppComponents;

const FALLBACK_RESULT_DASHBOARD = {
  uid: '',
  app_profile: window.AppUtils.normalize.buildEmptyAgentOutput('暂无 App 画像结果'),
  behavior_profile: window.AppUtils.normalize.buildEmptyAgentOutput('暂无行为画像结果'),
  credit_profile: window.AppUtils.normalize.buildEmptyAgentOutput('暂无征信画像结果'),
  comprehensive_profile: window.AppUtils.normalize.buildEmptyAgentOutput('暂无综合画像结果'),
  product_advice: null,
  ops_advice: null,
  standardized_labels: null
};

const SEGMENT_KEYS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'];
const MIN_CHAT_WIDTH = 320;
const MAX_CHAT_WIDTH = 760;
const DEFAULT_CHAT_WIDTH = 440;
const DESKTOP_COLLAPSED_CHAT_WIDTH = 76;
const SAFE_LEFT_WIDTH = 800;
const CHAT_AUTO_COLLAPSE_BREAKPOINT = 1280;
const COUNTRY_NAMES = { mx: '墨西哥', th: '泰国' };
const DASHBOARD_LAYOUT_STYLES = `
  #workspace {
    display: flex;
    flex: 1 1 auto;
    min-height: 0;
    overflow: hidden;
    background: #f4f7f9;
  }

  #left-panel {
    flex: 1 1 auto;
    min-width: 420px;
    min-height: 0;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-gutter: stable;
  }

  #left-panel::-webkit-scrollbar,
  .dashboard-chat-column::-webkit-scrollbar,
  #chat-container::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }

  #left-panel::-webkit-scrollbar-track,
  .dashboard-chat-column::-webkit-scrollbar-track,
  #chat-container::-webkit-scrollbar-track {
    background: transparent;
  }

  #left-panel::-webkit-scrollbar-thumb,
  .dashboard-chat-column::-webkit-scrollbar-thumb,
  #chat-container::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 999px;
  }

  .dashboard-left-inner {
    min-height: 100%;
  }

  .module-grid-shell {
    overflow-x: auto;
    padding-bottom: 0.25rem;
  }

  .detail-scroll-shell {
    width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 0.25rem;
  }

  .dashboard-module-card {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
    min-height: 150px;
    border-radius: 1rem;
    border: 1px solid rgba(226, 232, 240, 0.8);
    background: #ffffff;
    padding: 1.25rem;
    text-align: left;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
    transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
  }

  .dashboard-module-card::before {
    content: '';
    position: absolute;
    right: -1rem;
    bottom: -1rem;
    width: 5rem;
    height: 5rem;
    border-radius: 999px;
    background: #f8fafc;
    opacity: 0.5;
    transition: transform 300ms ease, background-color 180ms ease, opacity 180ms ease;
  }

  .dashboard-module-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
    border-color: var(--module-hover-border, rgba(191, 219, 254, 1));
  }

  .dashboard-module-card--active {
    border-color: transparent;
    background-image: linear-gradient(135deg, var(--module-bg-start), var(--module-bg-end));
    box-shadow: 0 12px 24px var(--module-shadow);
    transform: scale(1.02);
  }

  .dashboard-module-card--active::before {
    background: rgba(255, 255, 255, 0.12);
    opacity: 1;
  }

  .dashboard-module-card__title {
    color: #1e293b;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.375;
  }

  .dashboard-module-card__subtitle {
    margin-top: 0.125rem;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .dashboard-module-card__status {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    color: #64748b;
    font-size: 12px;
    font-weight: 500;
  }

  .dashboard-module-card__dot {
    width: 8px;
    height: 8px;
    flex: 0 0 auto;
    border-radius: 999px;
    background: #cbd5e1;
  }

  .dashboard-module-card__icon {
    color: var(--module-icon);
  }

  .dashboard-module-card--active .dashboard-module-card__title,
  .dashboard-module-card--active .dashboard-module-card__subtitle,
  .dashboard-module-card--active .dashboard-module-card__status,
  .dashboard-module-card--active .dashboard-module-card__icon {
    color: white;
  }

  .dashboard-module-card--active .dashboard-module-card__dot {
    background: white;
  }

  .dashboard-module-card--active .dashboard-module-card__subtitle {
    color: rgba(255, 255, 255, 0.82);
  }

  .dashboard-detail-content {
    min-width: 0;
    width: 100%;
    overflow: visible;
  }

  .dashboard-detail-content > * {
    min-width: 0;
  }

  .dashboard-secondary-stack {
    display: grid;
    gap: 1rem;
  }

  .dashboard-resize-rail {
    position: relative;
    width: 10px;
    flex: 0 0 10px;
    cursor: col-resize;
    background: linear-gradient(to right, transparent 0, transparent 3px, rgba(203, 213, 225, 0.85) 3px, rgba(203, 213, 225, 0.85) 7px, transparent 7px, transparent 100%);
  }

  .dashboard-resize-handle {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 36px;
    height: 92px;
    transform: translate(-50%, -50%);
    border-radius: 999px;
    background: rgba(203, 213, 225, 0.65);
    box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
    transition: background-color 180ms ease, box-shadow 180ms ease;
  }

  .dashboard-resize-rail:hover .dashboard-resize-handle,
  .dashboard-resize-rail.is-active .dashboard-resize-handle {
    background: rgba(96, 165, 250, 0.95);
    box-shadow: 0 18px 30px rgba(59, 130, 246, 0.22);
  }

  .dashboard-resize-rail--collapsed {
    cursor: default;
  }

  .dashboard-resize-rail--collapsed .dashboard-resize-handle {
    width: 24px;
    height: 56px;
    background: rgba(203, 213, 225, 0.45);
  }

  .dashboard-chat-column {
    position: relative;
    flex: 0 0 auto;
    height: 100%;
    min-width: 76px;
    overflow: hidden;
    border-left: 1px solid rgba(226, 232, 240, 0.6);
    background: rgba(255, 255, 255, 0.96);
    box-shadow: -8px 0 30px -10px rgba(0, 0, 0, 0.05);
    transition: width 220ms ease, min-width 220ms ease, box-shadow 220ms ease;
  }

  .dashboard-chat-column--collapsed {
    box-shadow: none;
  }

  .dashboard-chat-backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(15, 23, 42, 0.32);
    opacity: 0;
    pointer-events: none;
    transition: opacity 180ms ease;
  }

  .dashboard-chat-backdrop.is-open {
    opacity: 1;
    pointer-events: auto;
  }

  .dashboard-chat-sheet {
    position: fixed;
    top: 3.5rem;
    right: 0;
    bottom: 0;
    z-index: 70;
    width: min(92vw, 560px);
    transform: translateX(100%);
    transition: transform 220ms ease;
    border-left: 1px solid rgba(226, 232, 240, 0.6);
    background: rgba(255, 255, 255, 0.98);
    box-shadow: -16px 0 36px rgba(15, 23, 42, 0.12);
  }

  .dashboard-chat-sheet.is-open {
    transform: translateX(0);
  }

  .dashboard-chat-launcher {
    position: fixed;
    right: 1rem;
    bottom: 1rem;
    z-index: 55;
    box-shadow: 0 18px 34px rgba(37, 99, 235, 0.28);
  }

  @media (max-width: 1279px) {
    #workspace {
      display: block;
    }

    .dashboard-resize-rail,
    .dashboard-chat-column {
      display: none;
    }
  }
`;

function computeSegmentDistribution(results) {
  const counts = { S1: 0, S2: 0, S3: 0, S4: 0, S5: 0, S6: 0 };
  let total = 0;
  results.forEach((r) => {
    const seg = r?.comprehensive_profile?.structured_result?.metrics?.segment;
    if (typeof seg === 'string' && counts.hasOwnProperty(seg)) {
      counts[seg] += 1;
      total += 1;
    }
  });
  return { counts, total };
}

function SegmentDistributionCard({ results }) {
  if (!results || results.length <= 1) {
    return null;
  }
  const { counts, total } = computeSegmentDistribution(results);
  if (total === 0) {
    return null;
  }
  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <h3 className="text-base font-bold text-slate-800 mb-4">批量分析 · 客群分层分布 (S1-S6)</h3>
      <div className="space-y-2">
        {SEGMENT_KEYS.map((key) => {
          const c = counts[key];
          const pct = total > 0 ? (c / total) * 100 : 0;
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="w-8 text-xs font-semibold text-slate-600">{key}</span>
              <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-12 text-xs text-slate-500 text-right">{c} 人</span>
            </div>
          );
        })}
        <p className="text-xs text-slate-400 mt-2">合计 {total} 个有效分层结果（共 {results.length} 条）</p>
      </div>
    </div>
  );
}

function clampChatWidth(width, viewportWidth) {
  const viewWidth = Number(viewportWidth) || (typeof window !== 'undefined' ? window.innerWidth : MAX_CHAT_WIDTH + SAFE_LEFT_WIDTH);
  const safeMax = Math.min(MAX_CHAT_WIDTH, Math.max(MIN_CHAT_WIDTH, viewWidth - SAFE_LEFT_WIDTH - 24));
  return Math.min(safeMax, Math.max(MIN_CHAT_WIDTH, width));
}

function formatCountryLabel(countryCode) {
  const code = String(countryCode || '').toLowerCase();
  return `${COUNTRY_NAMES[code] || code.toUpperCase()} · ${code.toUpperCase()}`;
}

function DashboardView({
  activeTab,
  setActiveTab,
  analysisResults,
  selectedResultIndex,
  setSelectedResultIndex,
  moduleStates,
  onRetryModule,
  onBack,
  onChatProfileReady,
  onChatProfilesPending,
  onChatTraceReady,
  traceSeedByUid,
  moduleStatesByUid,
  currentUser = null,
  permissions = [],
  onLogout = null,
  authorizedScopes = [],
  supportedCountries = [],
  projectId = '',
  onProjectChange,
  country = 'mx',
  onCountryChange,
  chatFocusRequested = false,
  onChatFocusChange,
  chatSessionId = '',
  onChatSessionChange,
  chatWorkspaceSnapshot = null,
  onRestoreWorkspaceSession,
}) {
  const selectedResult = analysisResults[selectedResultIndex] || FALLBACK_RESULT_DASHBOARD;
  const uid = selectedResult.uid || 'unknown_user';
  const effectiveModuleStates = (moduleStatesByUid && moduleStatesByUid[uid]) || moduleStates;
  const behaviorStructured = (selectedResult
    && selectedResult.behavior_profile
    && selectedResult.behavior_profile.structured_result) || {};
  const behaviorDataMissing = behaviorStructured.status === 'data_missing';
  const [traceCacheByUid, setTraceCacheByUid] = React.useState({});
  const [chatPanelWidth, setChatPanelWidth] = React.useState(DEFAULT_CHAT_WIDTH);
  const [isResizingChat, setIsResizingChat] = React.useState(false);
  const [desktopChatCollapsed, setDesktopChatCollapsed] = React.useState(false);
  const [compactChatMode, setCompactChatMode] = React.useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < CHAT_AUTO_COLLAPSE_BREAKPOINT : false
  );
  const [floatingChatOpen, setFloatingChatOpen] = React.useState(() =>
    typeof window !== 'undefined'
      ? (window.innerWidth < CHAT_AUTO_COLLAPSE_BREAKPOINT ? Boolean(chatFocusRequested) : true)
      : Boolean(chatFocusRequested)
  );
  const permissionSet = React.useMemo(() => new Set(Array.isArray(permissions) ? permissions : []), [permissions]);
  const canAccessTrace = !currentUser || currentUser.is_superuser || permissionSet.has('trace:run') || permissionSet.has('trace:view');
  const canManageProject = !currentUser || currentUser.is_superuser || permissionSet.has('project:manage');
  const dashboardTabs = [
    { id: 'comprehensive', title: '综合画像', sub: 'COMPREHENSIVE', icon: Network, iconColor: '#f97316', bgStart: '#f5bf48', bgEnd: '#b04ed3', shadow: 'rgba(212, 106, 25, 0.28)' },
    { id: 'app', title: 'App画像', sub: 'APP USAGE', icon: Smartphone, iconColor: '#3b82f6', bgStart: '#5db7f0', bgEnd: '#2c59d6', shadow: 'rgba(37, 99, 235, 0.28)' },
    { id: 'behavior', title: '行为画像', sub: 'BEHAVIORAL', icon: Activity, iconColor: '#ef4444', bgStart: '#f49a59', bgEnd: '#d47167', shadow: 'rgba(234, 88, 12, 0.24)' },
    { id: 'credit', title: '征信画像', sub: 'CREDIT REPORT', icon: CreditCard, iconColor: '#64748b', bgStart: '#8894a6', bgEnd: '#667182', shadow: 'rgba(71, 85, 105, 0.28)' },
    { id: 'product', title: '产品策略', sub: 'PRODUCT ADVICE', icon: Package, iconColor: '#14b8a6', bgStart: '#8bd8a6', bgEnd: '#68bebd', shadow: 'rgba(20, 184, 166, 0.22)' },
    { id: 'ops', title: '运营策略', sub: 'OPERATIONS', icon: Headphones, iconColor: '#8b5cf6', bgStart: '#b28ef4', bgEnd: '#8d72ea', shadow: 'rgba(139, 92, 246, 0.22)' },
    { id: 'trace', title: '深度行为解析', sub: 'TRACE ANALYSIS', icon: Search, iconColor: '#a855f7', bgStart: '#d59dff', bgEnd: '#a855f7', shadow: 'rgba(168, 85, 247, 0.22)' },
    { id: 'knowledge', title: '知识库管理', sub: 'RISK KNOWLEDGE', icon: Settings, iconColor: '#0891b2', bgStart: '#6ee7f9', bgEnd: '#0284c7', shadow: 'rgba(8, 145, 178, 0.24)' },
  ].filter((tab) => {
    if (tab.id === 'trace') return canAccessTrace;
    if (tab.id === 'knowledge') return canManageProject;
    return true;
  });
  const hasVisibleTab = dashboardTabs.some((tab) => tab.id === activeTab);
  const visibleActiveTab = hasVisibleTab ? activeTab : 'comprehensive';
  const activeTabMeta = dashboardTabs.find((tab) => tab.id === visibleActiveTab) || dashboardTabs[0];
  const activeModuleState = visibleActiveTab === 'trace'
    ? { status: 'success', error: '' }
    : (effectiveModuleStates && effectiveModuleStates[visibleActiveTab]) || { status: 'success', error: '' };
  const detailPanelMinWidthClass = {
    app: 'min-w-[1140px]',
    behavior: 'min-w-[1100px]',
    credit: 'min-w-[1160px]',
    comprehensive: 'min-w-[980px]',
    product: 'min-w-[960px]',
    ops: 'min-w-[960px]',
    trace: 'min-w-[960px]',
    knowledge: 'min-w-[1080px]',
  }[visibleActiveTab] || 'min-w-full';

  React.useEffect(() => {
    if (!traceSeedByUid) return;
    setTraceCacheByUid((prev) => {
      let changed = false;
      const next = { ...prev };
      Object.keys(traceSeedByUid).forEach((seedUid) => {
        if (!next[seedUid]) {
          next[seedUid] = traceSeedByUid[seedUid];
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [traceSeedByUid]);

  React.useEffect(() => {
    if (visibleActiveTab !== 'trace') return;
    if (!uid || uid === 'unknown_user') return;
    if (traceCacheByUid[uid]) return;
    if (behaviorDataMissing) {
      setTraceCacheByUid((prev) => ({
        ...prev,
        [uid]: {
          requestStatus: 'success',
          response: { uid, status: 'data_missing', errors: ['behavior_data_missing'] }
        }
      }));
      return;
    }
    setTraceCacheByUid((prev) => ({
      ...prev,
      [uid]: { requestStatus: 'loading' }
    }));
    window.AppServices.api.fetchTrace(uid).then((response) => {
      setTraceCacheByUid((prev) => ({
        ...prev,
        [uid]: { requestStatus: 'success', response }
      }));
    }).catch((err) => {
      setTraceCacheByUid((prev) => ({
        ...prev,
        [uid]: { requestStatus: 'error', errorMessage: (err && err.message) || '请求失败' }
      }));
    });
  }, [visibleActiveTab, uid, behaviorDataMissing]);

  React.useEffect(() => {
    function syncChatViewportState() {
      const compact = window.innerWidth < CHAT_AUTO_COLLAPSE_BREAKPOINT;
      setCompactChatMode(compact);
      setChatPanelWidth((current) => clampChatWidth(current, window.innerWidth));
    }

    syncChatViewportState();
    window.addEventListener('resize', syncChatViewportState);
    return () => window.removeEventListener('resize', syncChatViewportState);
  }, []);

  React.useEffect(() => {
    if (compactChatMode) {
      setFloatingChatOpen(Boolean(chatFocusRequested));
      return;
    }
    if (chatFocusRequested) {
      setDesktopChatCollapsed(false);
    }
    setFloatingChatOpen(false);
  }, [chatFocusRequested, compactChatMode]);

  React.useEffect(() => {
    if (!isResizingChat || compactChatMode) return undefined;

    function handlePointerMove(event) {
      const nextWidth = window.innerWidth - event.clientX - 32;
      setChatPanelWidth(clampChatWidth(nextWidth, window.innerWidth));
    }

    function handlePointerUp() {
      setIsResizingChat(false);
      document.body.style.userSelect = '';
    }

    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', handlePointerMove);
    window.addEventListener('mouseup', handlePointerUp);
    return () => {
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handlePointerMove);
      window.removeEventListener('mouseup', handlePointerUp);
    };
  }, [compactChatMode, isResizingChat]);

  function handleTraceRetry(targetUid) {
    setTraceCacheByUid((prev) => {
      const next = { ...prev };
      delete next[targetUid];
      return next;
    });
  }

  function handleOpenFloatingChat() {
    setFloatingChatOpen(true);
    if (onChatFocusChange) onChatFocusChange(true);
  }

  function handleCloseFloatingChat() {
    setFloatingChatOpen(false);
    if (onChatFocusChange) onChatFocusChange(false);
  }

  function handleToggleDesktopChat() {
    setDesktopChatCollapsed((prev) => {
      const next = !prev;
      if (onChatFocusChange) onChatFocusChange(!next);
      return next;
    });
  }

  function renderActivePanel() {
    if (visibleActiveTab === 'trace') {
      return <TracePanel uid={uid} cacheEntry={traceCacheByUid[uid]} onRetry={() => handleTraceRetry(uid)} />;
    }
    if (visibleActiveTab === 'knowledge') {
      return <KnowledgeBaseConsole activeTab={visibleActiveTab} currentUser={currentUser} />;
    }
    return (
      <ModuleStatusPanel state={activeModuleState} onRetry={() => onRetryModule && onRetryModule(visibleActiveTab)}>
        {visibleActiveTab === 'comprehensive' && <ComprehensivePanel profile={selectedResult.comprehensive_profile} />}
        {visibleActiveTab === 'app' && <AppPanel profile={selectedResult.app_profile} />}
        {visibleActiveTab === 'behavior' && <BehaviorPanel profile={selectedResult.behavior_profile} />}
        {visibleActiveTab === 'credit' && <RichCreditPanel profile={selectedResult.credit_profile} />}
        {visibleActiveTab === 'product' && <ProductAdvicePanel profile={selectedResult.product_advice} />}
        {visibleActiveTab === 'ops' && <OpsAdvicePanel profile={selectedResult.ops_advice} />}
      </ModuleStatusPanel>
    );
  }

  const ActiveDetailIcon = activeTabMeta.icon || Activity;
  const hasMultipleResults = analysisResults.length > 1;
  const showSecondaryStack = Boolean(selectedResult.standardized_labels) || hasMultipleResults;
  const userDisplayName = currentUser && (currentUser.display_name || currentUser.username) ? (currentUser.display_name || currentUser.username) : '当前用户';
  const userRoleLabel = currentUser && Array.isArray(currentUser.roles) && currentUser.roles.length ? currentUser.roles[0] : 'analyst';
  const projectEntries = [];
  const seenProjects = new Set();
  (authorizedScopes || []).forEach((scope) => {
    if (!scope || seenProjects.has(scope.project_id)) return;
    seenProjects.add(scope.project_id);
    projectEntries.push(scope);
  });
  const currentProject = projectEntries.find((scope) => scope.project_id === projectId) || projectEntries[0] || null;
  const projectLabel = currentProject && currentProject.project_code
    ? String(currentProject.project_code).toUpperCase()
    : (currentUser && currentUser.project_code ? String(currentUser.project_code).toUpperCase() : 'MAPS-LZ');
  const allowedCountries = (() => {
    const supported = Array.isArray(supportedCountries) && supportedCountries.length ? supportedCountries : ['mx', 'th'];
    if (!currentProject) return supported;
    const projectScopes = (authorizedScopes || []).filter((scope) => scope && scope.project_id === currentProject.project_id);
    if (projectScopes.some((scope) => scope.country == null)) return supported;
    return supported.filter((code) => projectScopes.some((scope) => scope.country === code));
  })();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F4F7F9] font-sans text-slate-800">
      <style>{DASHBOARD_LAYOUT_STYLES}</style>
      <header className="relative z-20 flex h-14 shrink-0 items-center justify-between border-b border-slate-200/70 bg-white/90 px-6 shadow-sm backdrop-blur-md">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="rounded-full p-2 text-slate-400 transition-colors hover:text-slate-700">
            <ChevronRight className="h-5 w-5 rotate-180" />
          </button>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 shadow-sm">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold leading-tight text-slate-800">Multi-Agent Profiling System</h1>
            <p className="text-xs text-slate-400">当前用户 UID: {uid}</p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-sm">
          {projectEntries.length > 1 ? (
            <select
              value={projectId}
              onChange={(e) => onProjectChange && onProjectChange(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700"
              title="切换项目"
            >
              {projectEntries.map((scope) => (
                <option key={scope.project_id} value={scope.project_id}>
                  {String(scope.project_code || scope.project_id).toUpperCase()}
                </option>
              ))}
            </select>
          ) : null}
          <select
            value={country}
            onChange={(e) => onCountryChange && onCountryChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700"
            title="切换国家"
          >
            {allowedCountries.map((countryCode) => (
              <option key={countryCode} value={countryCode}>
                {formatCountryLabel(countryCode)}
              </option>
            ))}
          </select>
          <div className="h-4 w-px bg-slate-200"></div>
          <span className="text-slate-500">当前模式: <span className="font-medium text-slate-700">api-live</span></span>
          <div className="h-4 w-px bg-slate-200"></div>
          <span className="text-slate-500">返回结果数: <span className="font-medium text-blue-600">{analysisResults.length}</span></span>
          {currentUser ? (
            <>
              <div className="h-4 w-px bg-slate-200"></div>
              <div className="hidden items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 md:flex">
                <div>
                  <div className="text-sm font-semibold text-slate-800">{userDisplayName}</div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {projectLabel} · {userRoleLabel} · {(country || 'mx').toUpperCase()}
                  </div>
                </div>
              </div>
            </>
          ) : null}
          {onLogout ? (
            <button
              type="button"
              onClick={onLogout}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
            >
              退出登录
            </button>
          ) : null}
        </div>
      </header>

      <main id="workspace" className="flex-1 flex overflow-hidden">
        <section id="left-panel" className="flex-1 h-full overflow-y-auto">
          <div className="px-6 pt-6 lg:px-8 lg:pt-8">
            <div className="dashboard-left-inner max-w-5xl mx-auto w-full">
              <section className="mb-8">
                <div className="space-y-4">
                  <h2 className="text-lg font-semibold text-slate-800 mb-4">用户结果切换</h2>
                  <div className="space-y-3">
                    {hasMultipleResults ? (
                      <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm">
                        <div className="flex gap-2 overflow-x-auto pb-1">
                          {analysisResults.map((item, index) => {
                            const isActive = selectedResultIndex === index;
                            const label = item.uid || `user_${index + 1}`;
                            return (
                              <button
                                key={`${label}-${index}`}
                                onClick={() => setSelectedResultIndex(index)}
                                className={`whitespace-nowrap rounded-2xl border px-4 py-2 text-sm font-semibold transition-colors ${
                                  isActive
                                    ? 'border-blue-600 bg-blue-600 text-white shadow-sm'
                                    : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
                                }`}
                              >
                                {label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="module-grid-shell overflow-x-auto pb-1">
                    <div id="module-grid" className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 xl:min-w-[980px]">
                      {dashboardTabs.map((tab) => {
                        const isActive = visibleActiveTab === tab.id;
                        const Icon = tab.icon;
                        let tabModuleState;
                        if (tab.id === 'trace') {
                          const traceEntry = traceCacheByUid[uid];
                          if (traceEntry) {
                            if (traceEntry.requestStatus === 'success') {
                              const respStatus = traceEntry.response && traceEntry.response.status;
                              tabModuleState = { status: (respStatus === 'data_missing' || respStatus === 'insufficient_events') ? 'no_data' : 'success' };
                            } else if (traceEntry.requestStatus === 'error') {
                              tabModuleState = { status: 'error' };
                            } else {
                              tabModuleState = { status: 'loading' };
                            }
                          } else if (behaviorDataMissing) {
                            tabModuleState = { status: 'no_data' };
                          } else {
                            tabModuleState = { status: 'idle' };
                          }
                        } else {
                          tabModuleState = effectiveModuleStates && effectiveModuleStates[tab.id];
                        }

                        const tabStatus = tabModuleState && tabModuleState.status;
                        const statusLabel = tabStatus === 'success' ? '已完成'
                          : tabStatus === 'loading' ? '分析中...'
                          : tabStatus === 'error' ? '模块报错'
                          : tabStatus === 'no_data' ? '暂无可用数据'
                          : '等待依赖';

                        return (
                          <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`dashboard-module-card ${isActive ? 'dashboard-module-card--active' : ''}`}
                            style={{
                              '--module-bg-start': tab.bgStart,
                              '--module-bg-end': tab.bgEnd,
                              '--module-shadow': tab.shadow,
                              '--module-icon': tab.iconColor,
                              '--module-hover-border': `${tab.iconColor}4d`,
                            }}
                          >
                            <div className="relative z-10 mb-3 flex items-start justify-between gap-4">
                              <div className="min-w-0">
                                <h3 className="dashboard-module-card__title">{tab.title}</h3>
                                <p className="dashboard-module-card__subtitle">{tab.sub}</p>
                              </div>
                              {Icon ? <Icon className="dashboard-module-card__icon h-5 w-5 shrink-0" /> : null}
                            </div>

                            <div className="relative z-10 mt-5">
                              <div className="dashboard-module-card__status">
                                <span className="dashboard-module-card__dot"></span>
                                <span>{statusLabel}</span>
                              </div>
                              {tabStatus === 'loading' ? (
                                <div className="skeleton-shimmer mt-4 space-y-2" aria-label="module loading skeleton">
                                  <div className={`h-1.5 w-28 overflow-hidden rounded-full ${isActive ? 'bg-white/25' : 'bg-slate-200'}`}>
                                    <div className={`loading-progress-bar h-full w-2/3 animate-pulse rounded-full ${isActive ? 'bg-white/80' : 'bg-slate-400'}`}></div>
                                  </div>
                                  <div className={`h-1.5 w-20 rounded-full ${isActive ? 'bg-white/20' : 'bg-slate-100'}`}></div>
                                </div>
                              ) : null}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>

          <div className="px-6 pb-8 lg:px-8">
            <div className="space-y-8">
              <section className="rounded-2xl border border-slate-200/60 bg-white/80 p-6 shadow-sm backdrop-blur-md min-h-[400px]">
                <div className="mb-6 flex items-center justify-between gap-4 border-b border-slate-100 pb-4">
                  <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-800">
                    {ActiveDetailIcon ? <ActiveDetailIcon className="h-5 w-5 text-blue-600" /> : null}
                    <span id="detail-title">{activeTabMeta.title}</span> 数据详情
                  </h2>
                  <button className="text-sm text-slate-500 hover:text-blue-600 flex items-center gap-1">
                    {Settings ? <Settings className="h-4 w-4" /> : null}
                    配置项
                  </button>
                </div>

                <div id="detail-content" className="text-slate-600">
                  <div className="detail-scroll-shell">
                    <div className="dashboard-detail-content">
                      <div className={detailPanelMinWidthClass}>
                        {renderActivePanel()}
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              {showSecondaryStack ? (
                <section className="dashboard-secondary-stack">
                  {selectedResult.standardized_labels ? (
                    <div className="detail-scroll-shell">
                      <div className="min-w-[960px]">
                        <LabelsOverviewCard labels={selectedResult.standardized_labels} />
                      </div>
                    </div>
                  ) : null}
                  {hasMultipleResults ? (
                    <div className="detail-scroll-shell">
                      <div className="min-w-[960px]">
                        <SegmentDistributionCard results={analysisResults} />
                      </div>
                    </div>
                  ) : null}
                </section>
              ) : null}
            </div>
          </div>
        </section>

        {!compactChatMode ? (
          <div
            id="resize-handle"
            className={`dashboard-resize-rail ${isResizingChat ? 'is-active' : ''} ${desktopChatCollapsed ? 'dashboard-resize-rail--collapsed' : ''}`}
            onMouseDown={() => {
              if (!desktopChatCollapsed) setIsResizingChat(true);
            }}
            aria-hidden="true"
          >
            <div className="dashboard-resize-handle"></div>
          </div>
        ) : null}

        <div
          className={`dashboard-chat-backdrop ${compactChatMode && floatingChatOpen ? 'is-open' : ''}`}
          onClick={handleCloseFloatingChat}
        />

        <aside
          id="chat-panel"
          className={
            compactChatMode
              ? `dashboard-chat-sheet ${floatingChatOpen ? 'is-open' : ''}`
              : `dashboard-chat-column ${desktopChatCollapsed ? 'dashboard-chat-column--collapsed' : ''}`
          }
          style={
            compactChatMode
              ? undefined
              : { width: desktopChatCollapsed ? DESKTOP_COLLAPSED_CHAT_WIDTH : chatPanelWidth }
          }
        >
          <ChatPanel
            layoutMode={compactChatMode ? 'sheet' : 'dock'}
            collapsed={!compactChatMode && desktopChatCollapsed}
            onToggleCollapse={!compactChatMode ? handleToggleDesktopChat : null}
            onRequestClose={compactChatMode ? handleCloseFloatingChat : null}
            onProfileReady={onChatProfileReady}
            onProfilesPending={onChatProfilesPending}
            onTraceReady={onChatTraceReady}
            externalSessionId={chatSessionId}
            onSessionChange={onChatSessionChange}
            workspaceSnapshot={chatWorkspaceSnapshot}
            onRestoreWorkspaceSession={onRestoreWorkspaceSession}
            currentUser={currentUser}
            currentCountry={country}
            onJumpToTab={(tabId, targetUid) => {
              setActiveTab(tabId);
              if (targetUid) {
                const idx = analysisResults.findIndex((r) => r && r.uid === targetUid);
                if (idx >= 0) setSelectedResultIndex(idx);
              }
            }}
          />
        </aside>

        {compactChatMode ? (
          <button
            type="button"
            onClick={handleOpenFloatingChat}
            className="dashboard-chat-launcher inline-flex items-center gap-2 rounded-full bg-blue-600 px-4 py-3 text-sm font-semibold text-white"
          >
            <Bot className="h-4 w-4" />
            自然语言助手
          </button>
        ) : null}
      </main>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.DashboardView = DashboardView;
