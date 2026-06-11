const { Bot, UserRound } = window.LucideReact || {};

function ChatMessageList({ messages }) {
  if (!messages || messages.length === 0) {
    return <div className="text-sm italic text-slate-400">开始你的第一条消息...</div>;
  }
  return (
    <div className="space-y-6">
      {messages.map((m, index) => {
        const isUser = m.role === 'user';
        return (
          <div key={index} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div className="flex max-w-[85%] items-end gap-2">
              {isUser ? null : (
                <div className="mb-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white shadow-sm">
                  {Bot ? <Bot className="h-3.5 w-3.5" /> : null}
                </div>
              )}
              <div
                className={`p-3.5 text-[14px] leading-7 shadow-sm whitespace-pre-wrap ${
                  isUser
                    ? 'rounded-2xl rounded-br-sm bg-blue-600 text-white'
                    : 'rounded-2xl rounded-bl-sm border border-slate-100 bg-white text-slate-700'
                }`}
              >
                {m.content}
              </div>
              {isUser ? (
                <div className="mb-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-500">
                  {UserRound ? <UserRound className="h-3.5 w-3.5" /> : null}
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatMessageList = ChatMessageList;
