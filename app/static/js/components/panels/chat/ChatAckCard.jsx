function ChatAckCard({ pending, onApprove, onReject }) {
  if (!pending) return null;
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
      <div className="font-semibold text-amber-900">即将执行 SQL，预计 {pending.rows_estimated ?? '?'} 行</div>
      <pre className="mt-2 max-h-32 overflow-auto rounded-lg bg-white p-3 text-xs text-slate-700">{pending.sql_text || ''}</pre>
      <div className="mt-3 flex gap-2">
        <button onClick={onApprove} className="rounded-lg bg-emerald-600 px-3 py-1 text-sm font-semibold text-white">同意 Enter</button>
        <button onClick={onReject} className="rounded-lg bg-rose-600 px-3 py-1 text-sm font-semibold text-white">拒绝 Esc</button>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatAckCard = ChatAckCard;
