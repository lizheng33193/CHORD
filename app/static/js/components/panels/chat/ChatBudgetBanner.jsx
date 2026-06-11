function ChatBudgetBanner({ used, limit }) {
  if (used == null || limit == null) return null;
  const pct = limit > 0 ? Math.round((used / limit) * 100) : 0;
  if (pct < 80) return null;
  return <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">Token 预算使用 {used} / {limit} ({pct}%)</div>;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatBudgetBanner = ChatBudgetBanner;
