// Loading view with cycling text animation.
// Props: loadingTexts (array of strings), durationMs (total display time), text (legacy single string fallback).

const { BrainCircuit } = window.LucideReact || {};
const { useState: useLoadingState, useEffect: useLoadingEffect } = React;

function LoadingView({ text, loadingTexts, durationMs }) {
  const texts = Array.isArray(loadingTexts) && loadingTexts.length ? loadingTexts : [text || '正在分析中...'];
  const [index, setIndex] = useLoadingState(0);

  useLoadingEffect(() => {
    if (texts.length <= 1) return;
    const intervalMs = Math.max(500, Math.round((Number(durationMs) || 4000) / texts.length));
    const id = window.setInterval(() => {
      setIndex((prev) => (prev + 1) % texts.length);
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [texts.length, durationMs]);

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white">
      <div className="relative w-32 h-32 mb-8 flex items-center justify-center">
        <div className="absolute inset-0 border-4 border-blue-500/30 rounded-full" />
        <div className="absolute inset-0 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <BrainCircuit className="w-12 h-12 text-blue-400 animate-pulse" />
      </div>
      <h2 className="text-2xl font-semibold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
        AI 智能体矩阵运算中
      </h2>
      <p className="text-slate-400 text-lg transition-all duration-300">{texts[index]}</p>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.LoadingView = LoadingView;
