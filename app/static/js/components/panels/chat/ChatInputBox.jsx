const { SendHorizontal, Square } = window.LucideReact || {};

function ChatInputBox({ value, onChange, onSend, onStop, disabled, running, stopping }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !disabled && !running) {
      e.preventDefault();
      onSend();
    }
  };
  const buttonDisabled = running ? !!stopping : (disabled || !value.trim());
  return (
    <div className="relative flex items-end rounded-xl border border-slate-200 bg-slate-50 shadow-sm transition-all focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-50">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        className="w-full min-h-[44px] max-h-32 resize-none bg-transparent py-3 pl-4 pr-12 text-sm outline-none disabled:cursor-not-allowed disabled:bg-slate-100/50"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行..."
      />
      <button
        onClick={running ? onStop : onSend}
        disabled={buttonDisabled}
        title={stopping ? '停止中...' : running ? '停止当前执行' : '发送'}
        className="absolute bottom-1.5 right-2 inline-flex rounded-lg p-2 transition-colors disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 enabled:bg-blue-600 enabled:text-white enabled:shadow-md enabled:hover:bg-blue-700"
      >
        {running
          ? (Square ? <Square className="h-4 w-4" /> : '停')
          : (SendHorizontal ? <SendHorizontal className="h-4 w-4" /> : '发')}
      </button>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatInputBox = ChatInputBox;
