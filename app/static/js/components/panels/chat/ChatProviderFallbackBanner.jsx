function ChatProviderFallbackBanner({ from, to, reason }) {
  if (!from || !to) return null;
  return <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">模型已从 {from} 切换到 {to}{reason ? `：${reason}` : ''}</div>;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatProviderFallbackBanner = ChatProviderFallbackBanner;
