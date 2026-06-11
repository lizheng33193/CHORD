"""Mock frontend template for the homepage and dashboard UI.

This module keeps the HTML template out of `app/main.py` so the FastAPI entry
point stays small and easy to read. The page intentionally uses mock data only
for now and does not call the real backend analysis endpoints yet.
"""


MOCK_FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>多 Agent 用户画像分析平台</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script type="importmap">
      {
        "imports": {
          "react": "https://esm.sh/react@18.2.0",
          "react-dom/client": "https://esm.sh/react-dom@18.2.0/client",
          "lucide-react": "https://esm.sh/lucide-react@0.292.0?deps=react@18.2.0"
        }
      }
    </script>
</head>
<body class="bg-slate-50">
    <div id="root"></div>

    <script type="text/babel" data-type="module">
        import React, { useEffect, useMemo, useState } from 'react';
        import { createRoot } from 'react-dom/client';
        import {
          Activity, AlertCircle, AlertTriangle, Award, Bot, BrainCircuit, Calendar,
          CheckCircle2, ChevronRight, CreditCard, Database, Lightbulb, MessageSquare,
          MousePointerClick, Network, PieChart, Search, ShieldCheck, ShoppingCart,
          Smartphone, Target, TrendingUp, User, UserCheck
        } from 'lucide-react';

        const MOCK_RESULTS = {
          uid: 'user_001',
          app_profile: {
            summary: '用户近 30 天 App 活跃度高，核心兴趣集中在生活消费类应用。',
            structured_result: {
              activity_level: 'high',
              evidence: {
                installed_apps: ['wechat', 'alipay', 'taobao', 'douyin'],
                top_category: 'lifestyle',
                active_days_30d: 26
              },
              metrics: {
                installed_app_count: 4,
                active_days_30d: 26
              },
              tags: ['lifestyle-focused', 'heavy-app-user', 'high-retention']
            },
            charts: [
              {
                title: 'App 活跃天数',
                series: [{ name: 'days', data: [26] }]
              }
            ],
            report_markdown: '## App Profile\\n\\n- 活跃度高\\n- 偏好生活消费类应用'
          },
          behavior_profile: {
            summary: '用户会话时长较深，近 30 天登录行为稳定。',
            structured_result: {
              engagement_level: 'deep',
              evidence: {
                avg_session_minutes: 52,
                login_days_30d: 27,
                purchase_preference: 'premium_quality'
              },
              metrics: {
                avg_session_minutes: 52,
                login_days_30d: 27
              },
              tags: ['premium-quality', 'deep-engagement', 'high-attention']
            },
            charts: [
              {
                title: '行为指标',
                series: [{ name: 'behavior', data: [52, 27] }]
              }
            ],
            report_markdown: '## Behavior Profile\\n\\n- 会话时长深\\n- 登录稳定'
          },
          credit_profile: {
            summary: '用户信用等级 A，履约稳定，整体风险低。',
            structured_result: {
              evidence: {
                credit_score_band: 'A',
                repayment_status: 'stable',
                risk_level: 'low'
              },
              metrics: {
                credit_score_band: 'A',
                repayment_status: 'stable',
                risk_level: 'low'
              },
              tags: ['risk-low', 'credit-a']
            },
            charts: [
              {
                title: '信用风险',
                series: [{ name: 'risk', data: [1] }]
              }
            ],
            report_markdown: '## Credit Profile\\n\\n- 风险低\\n- 履约稳定'
          },
          comprehensive_profile: {
            summary: '综合判断：该用户属于高活跃、稳健消费、低风险画像。',
            structured_result: {
              persona: 'lifestyle oriented premium-quality user (low risk)',
              metrics: {
                risk_level: 'low',
                chart_count: 4
              },
              tags: [
                'credit-a',
                'deep-engagement',
                'heavy-app-user',
                'high-retention',
                'lifestyle-focused',
                'premium-quality',
                'risk-low'
              ]
            },
            charts: [
              {
                title: '综合画像强度',
                series: [{ name: 'overview', data: [3, 4, 5] }]
              }
            ],
            report_markdown: '## Comprehensive Profile\\n\\n- 高活跃\\n- 稳健消费\\n- 低风险'
          }
        };

        const LOADING_TEXTS = [
          '正在唤醒多 Agent 画像系统...',
          'App 画像 Agent：正在整理安装列表与分类标签...',
          '行为画像 Agent：正在分析活跃度与会话时长...',
          '信用画像 Agent：正在解析信用等级与风险状态...',
          '综合画像 Agent：正在汇总多维结果...'
        ];

        function App() {
          const [view, setView] = useState('home');
          const [uid, setUid] = useState('user_001');
          const [activeTab, setActiveTab] = useState('comprehensive');
          const [loadingIndex, setLoadingIndex] = useState(0);

          useEffect(() => {
            if (view !== 'loading') {
              return undefined;
            }

            setLoadingIndex(0);
            const intervalId = window.setInterval(() => {
              setLoadingIndex((current) => {
                if (current >= LOADING_TEXTS.length - 1) {
                  window.clearInterval(intervalId);
                  window.setTimeout(() => setView('dashboard'), 250);
                  return current;
                }
                return current + 1;
              });
            }, 850);

            return () => window.clearInterval(intervalId);
          }, [view]);

          const selectedResult = useMemo(() => ({
            ...MOCK_RESULTS,
            uid: uid || 'user_001'
          }), [uid]);

          const handleStart = () => {
            if (!uid.trim()) {
              window.alert('请输入 UID');
              return;
            }
            setView('loading');
          };

          if (view === 'home') {
            return <HomeView uid={uid} setUid={setUid} onStart={handleStart} />;
          }

          if (view === 'loading') {
            return <LoadingView text={LOADING_TEXTS[loadingIndex]} />;
          }

          return (
            <DashboardView
              uid={uid}
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              result={selectedResult}
              onBack={() => setView('home')}
            />
          );
        }

        function HomeView({ uid, setUid, onStart }) {
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
                <div className="inline-flex items-center gap-2 rounded-full bg-white/80 backdrop-blur px-4 py-2 shadow-sm border border-slate-200 mb-6">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-sm text-slate-600">MVP Mock UI Preview</span>
                </div>
                <h1 className="text-4xl md:text-5xl font-bold text-slate-800 mb-4 tracking-wide flex items-center gap-3 text-center">
                  <BrainCircuit className="w-10 h-10 text-blue-600" />
                  多 Agent 用户画像分析平台
                </h1>
                <p className="text-slate-500 text-center max-w-2xl mb-12 text-lg leading-8">
                  先完成主页、加载态和结果页的交互预览。当前页面使用 mock 数据渲染，
                  保留旧版视觉风格与四个 tab 结构。
                </p>
                <div className="relative w-64 h-64 mb-12 flex items-center justify-center">
                  <div className="absolute inset-0 bg-blue-500 rounded-full blur-3xl opacity-20 animate-pulse" />
                  <div className="absolute inset-4 border border-blue-300 rounded-full animate-[spin_10s_linear_infinite]" />
                  <div className="absolute inset-8 border border-dashed border-indigo-400 rounded-full animate-[spin_15s_linear_infinite_reverse]" />
                  <div className="relative bg-white p-6 rounded-full shadow-2xl border border-blue-100">
                    <Bot className="w-24 h-24 text-blue-600" strokeWidth={1.5} />
                  </div>
                </div>
                <div className="w-full bg-white p-2 pl-6 rounded-full shadow-lg border border-slate-200 flex items-center gap-4 transition-all focus-within:ring-4 ring-blue-100">
                  <Search className="w-6 h-6 text-slate-400" />
                  <input
                    type="text"
                    className="flex-1 outline-none text-lg text-slate-700 placeholder-slate-400 bg-transparent"
                    placeholder="请输入用户 UID 进入多维画像分析..."
                    value={uid}
                    onChange={(event) => setUid(event.target.value)}
                    onKeyDown={(event) => event.key === 'Enter' && onStart()}
                  />
                  <button
                    onClick={onStart}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-full font-medium transition-colors flex items-center gap-2"
                  >
                    开始分析
                    <ChevronRight className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          );
        }

        function LoadingView({ text }) {
          return (
            <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white relative overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.18),_transparent_45%),radial-gradient(circle_at_bottom,_rgba(168,85,247,0.16),_transparent_35%)]" />
              <div className="relative w-32 h-32 mb-8 flex items-center justify-center">
                <div className="absolute inset-0 border-4 border-blue-500/30 rounded-full" />
                <div className="absolute inset-0 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                <BrainCircuit className="w-12 h-12 text-blue-400 animate-pulse" />
              </div>
              <h2 className="text-2xl font-semibold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
                AI 智能体矩阵运算中
              </h2>
              <p className="text-slate-400 text-lg transition-all duration-300">{text}</p>
            </div>
          );
        }

        function DashboardView({ activeTab, setActiveTab, uid, result, onBack }) {
          const tabs = [
            { id: 'comprehensive', title: '综合画像', sub: 'Comprehensive', icon: Network, bg: 'from-amber-400 to-fuchsia-600', shadow: 'shadow-fuchsia-500/30' },
            { id: 'app', title: 'App画像', sub: 'App Usage', icon: Smartphone, bg: 'from-cyan-400 to-blue-600', shadow: 'shadow-blue-500/30' },
            { id: 'behavior', title: '行为画像', sub: 'Behavioral', icon: Activity, bg: 'from-orange-400 to-red-500', shadow: 'shadow-red-500/30' },
            { id: 'credit', title: '信用画像', sub: 'Credit Report', icon: CreditCard, bg: 'from-slate-500 to-slate-700', shadow: 'shadow-slate-500/30' }
          ];

          return (
            <div className="min-h-screen bg-slate-50 flex flex-col">
              <header className="bg-white/95 backdrop-blur border-b border-slate-200 px-6 py-4 flex items-center justify-between sticky top-0 z-50">
                <div className="flex items-center gap-3">
                  <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                    <ChevronRight className="w-6 h-6 rotate-180" />
                  </button>
                  <div className="w-10 h-10 bg-blue-600 rounded-full flex items-center justify-center">
                    <Bot className="w-6 h-6 text-white" />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-slate-800">Multi-Agent Profiling System</h1>
                    <p className="text-xs text-slate-500">当前用户 UID: {uid}</p>
                  </div>
                </div>
                <div className="hidden md:flex items-center gap-4">
                  <span className="text-sm text-slate-500">
                    当前模式:
                    <span className="font-semibold text-slate-700 bg-slate-100 px-2 py-1 rounded ml-2">mock-preview</span>
                  </span>
                  <span className="text-sm text-slate-500">
                    四类画像结果:
                    <span className="text-blue-600 font-semibold ml-2">ready</span>
                  </span>
                </div>
              </header>

              <main className="flex-1 max-w-7xl w-full mx-auto p-6 flex flex-col gap-6">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                  {tabs.map((tab) => {
                    const isActive = activeTab === tab.id;
                    const Icon = tab.icon;
                    return (
                      <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`relative overflow-hidden rounded-xl p-5 text-left transition-all duration-300 transform ${isActive ? `scale-[1.02] shadow-xl ${tab.shadow} ring-2 ring-white ring-offset-2` : 'hover:scale-[1.01] shadow-md hover:shadow-lg opacity-85 hover:opacity-100'} bg-gradient-to-br ${tab.bg}`}
                      >
                        <div className="relative z-10 flex justify-between items-start">
                          <div>
                            <h3 className="text-xl font-bold text-white mb-1">{tab.title}</h3>
                            <p className="text-xs text-white/80 uppercase tracking-wider">{tab.sub}</p>
                          </div>
                          <Icon className={`w-8 h-8 text-white ${isActive ? 'animate-pulse' : 'opacity-70'}`} />
                        </div>
                        <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-white opacity-10 rounded-full blur-xl" />
                        <div className="absolute top-0 right-0 w-full h-full bg-gradient-to-t from-black/20 to-transparent pointer-events-none" />
                      </button>
                    );
                  })}
                </div>

                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 min-h-[560px]">
                  {activeTab === 'comprehensive' && <ComprehensivePanelV2 profile={result.comprehensive_profile} />}
                  {activeTab === 'app' && <AppPanel profile={result.app_profile} />}
                  {activeTab === 'behavior' && <BehaviorPanel profile={result.behavior_profile} />}
                  {activeTab === 'credit' && <CreditPanel profile={result.credit_profile} />}
                </div>
              </main>
            </div>
          );
        }

        function ComprehensivePanel({ profile }) {
          const tags = profile.structured_result.tags || [];
          return (
            <div className="animate-in fade-in duration-500">
              <div className="flex items-center gap-3 mb-8 pb-4 border-b border-slate-100">
                <Network className="w-8 h-8 text-fuchsia-600" />
                <h2 className="text-2xl font-bold text-slate-800">Skill 4: 综合画像 Agent 结论</h2>
              </div>
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
                <div className="xl:col-span-2 bg-slate-50 rounded-xl p-6 border border-slate-200 flex flex-col items-center justify-center min-h-[320px]">
                  <div className="text-center mb-6 text-slate-500">整合三维画像 → 用户标签体系</div>
                  <div className="relative w-full max-w-md h-64">
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 bg-fuchsia-100 rounded-full flex items-center justify-center border-4 border-fuchsia-500 z-10 shadow-lg">
                      <span className="font-bold text-fuchsia-700">综合判定</span>
                    </div>
                    <div className="absolute top-4 left-4 w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center border-2 border-blue-400">
                      <span className="text-xs font-semibold text-blue-700">App 偏好</span>
                    </div>
                    <div className="absolute bottom-4 left-1/4 w-20 h-20 bg-orange-50 rounded-full flex items-center justify-center border-2 border-orange-400">
                      <span className="text-xs font-semibold text-orange-700">行为活跃</span>
                    </div>
                    <div className="absolute top-12 right-8 w-20 h-20 bg-slate-100 rounded-full flex items-center justify-center border-2 border-slate-500">
                      <span className="text-xs font-semibold text-slate-700">信用状态</span>
                    </div>
                    <svg className="absolute inset-0 w-full h-full">
                      <line x1="20%" y1="20%" x2="50%" y2="50%" stroke="#cbd5e1" strokeWidth="2" strokeDasharray="4" />
                      <line x1="30%" y1="80%" x2="50%" y2="50%" stroke="#cbd5e1" strokeWidth="2" strokeDasharray="4" />
                      <line x1="80%" y1="30%" x2="50%" y2="50%" stroke="#cbd5e1" strokeWidth="2" strokeDasharray="4" />
                    </svg>
                  </div>
                </div>
                <div className="space-y-4">
                  <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-800 mb-3 flex items-center gap-2">
                      <ShieldCheck className="w-5 h-5 text-green-500" />
                      用户核心标签
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {tags.map((tag) => (
                        <span key={tag} className="bg-purple-100 text-purple-700 px-3 py-1 rounded-full text-sm font-medium">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="bg-slate-800 rounded-xl p-5 shadow-sm text-slate-300 font-mono text-xs overflow-hidden h-56 relative">
                    <div className="absolute top-0 right-0 bg-slate-700 px-2 py-1 text-slate-400 rounded-bl-lg">LLM Style Output</div>
                    <p className="mt-6 text-green-400">&gt; 综合分析完成。</p>
                    <p className="mt-2">&gt; {profile.summary}</p>
                    <p className="mt-2">&gt; Persona: {profile.structured_result.persona}</p>
                    <p className="text-white mt-4 font-bold">综合评级：低风险稳健用户</p>
                  </div>
                </div>
              </div>
            </div>
          );
        }

        function ComprehensivePanelV2({ profile }) {
          const structured = profile?.structured_result || {};
          const metrics = structured.metrics || {};
          const tags = structured.tags || [];
          const riskLevel = String(metrics.risk_level || 'low');
          const segment = String(metrics.segment || 'S2');
          const valueSignal = String(metrics.value_signal_level || 'medium');
          const confidenceLevel = String(metrics.confidence_level || 'high');
          const conflictCount = Number(metrics.conflict_count || 1);
          const conflictExplanations = metrics.conflict_explanations || ['App 侧活跃度与信用侧稳定性同时偏高，说明当前用户更像短期比价而非恶化风险。'];
          const conflictText = conflictExplanations[0] || '暂无明显的跨信号冲突说明。';
          const persona = structured.persona || 'lifestyle oriented premium-quality user (low risk)';
          const llmStatus = 'LLM 推理完成';
          const appSummary = 'App 画像显示用户偏好稳定消费与金融服务，安装结构较清晰。';
          const behaviorSummary = '行为画像显示登录与会话深度较好，具备持续互动基础。';
          const creditSummary = '信用画像显示履约稳定，整体风险偏低。';
          const marketingSuggestion = buildComprehensiveMarketingSuggestion(segment, valueSignal, true);
          const riskSuggestion = buildComprehensiveRiskSuggestion(riskLevel, conflictCount, confidenceLevel);
          return (
            <div className="animate-in fade-in duration-500">
              <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-100 flex-wrap gap-4">
                <div className="flex items-center gap-3">
                  <Network className="w-8 h-8 text-fuchsia-600" />
                  <h2 className="text-2xl font-bold text-slate-800">Skill 4: 综合画像与客群归属分析</h2>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium bg-green-50 text-green-700 border-green-200">{llmStatus}</span>
                  <span className="bg-slate-100 px-3 py-1.5 rounded-md text-xs font-medium text-slate-600 flex items-center gap-1.5"><Calendar className="w-4 h-4" /> 置信度 {toConfidenceDisplay(confidenceLevel)}</span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                <div className="bg-gradient-to-br from-fuchsia-600 to-indigo-700 rounded-2xl p-6 shadow-lg text-white relative overflow-hidden group">
                  <div className="absolute -right-6 -bottom-6 opacity-20 transform group-hover:scale-110 transition-transform duration-500"><UserCheck className="w-36 h-36" /></div>
                  <div className="relative z-10">
                    <p className="text-white/80 text-sm font-semibold mb-2 flex items-center gap-1.5"><Target className="w-4 h-4" /> 最终客群分层</p>
                    <h3 className="text-3xl font-black mb-3 tracking-wide">{toSegmentDisplay(segment)}</h3>
                    <div className="inline-block bg-white/20 px-3 py-1 rounded-full text-xs font-medium backdrop-blur-sm border border-white/20 shadow-sm">{segment} · {toSegmentFeature(segment)}</div>
                  </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex items-center justify-between relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-16 h-16 bg-green-50 rounded-bl-full z-0"></div>
                  <div className="relative z-10">
                    <p className="text-slate-500 text-sm font-bold mb-1">综合风险等级</p>
                    <h3 className="text-2xl font-bold text-green-600 mb-1">{toRiskDisplay(riskLevel)}</h3>
                    <p className="text-xs text-slate-400">{conflictCount > 0 ? `存在 ${conflictCount} 个跨信号冲突，已纳入解释。` : '当前未发现明显跨信号冲突。'}</p>
                  </div>
                  <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center text-green-500 relative z-10 shadow-sm border border-green-200/50"><ShieldCheck className="w-7 h-7" /></div>
                </div>

                <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex items-center justify-between relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-16 h-16 bg-amber-50 rounded-bl-full z-0"></div>
                  <div className="relative z-10">
                    <p className="text-slate-500 text-sm font-bold mb-1">综合价值等级</p>
                    <h3 className="text-2xl font-bold text-amber-600 mb-1">{toValueSignalDisplay(valueSignal)}</h3>
                    <p className="text-xs text-slate-400">{profile.summary}</p>
                  </div>
                  <div className="w-14 h-14 rounded-full bg-amber-100 flex items-center justify-center text-amber-500 relative z-10 shadow-sm border border-amber-200/50"><Award className="w-7 h-7" /></div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
                  <h4 className="text-sm font-bold text-slate-700 mb-5 flex items-center gap-2"><User className="w-4 h-4 text-blue-500" /> 基础归属</h4>
                  <ul className="space-y-4">
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">Persona</span><span className="font-semibold text-slate-800 text-sm text-right">{persona}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">Segment</span><span className="font-semibold text-slate-800 text-sm">{segment}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">价值层级</span><span className="font-semibold text-slate-800 text-sm">{toValueSignalDisplay(valueSignal)}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">当前状态</span><span className="text-[11px] font-bold px-2 py-0.5 rounded border bg-green-100 text-green-700 border-green-200">{llmStatus}</span></li>
                  </ul>
                </div>

                <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
                  <h4 className="text-sm font-bold text-slate-700 mb-5 flex items-center gap-2"><Activity className="w-4 h-4 text-green-500" /> 行为与偏好</h4>
                  <ul className="space-y-4">
                    <li className="flex flex-col gap-1.5"><span className="text-slate-500 text-xs">App 画像摘要</span><span className="font-medium text-slate-800 text-sm">{appSummary}</span></li>
                    <li className="flex flex-col gap-1.5"><span className="text-slate-500 text-xs">行为画像摘要</span><span className="font-medium text-slate-800 text-sm">{behaviorSummary}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">冲突数量</span><span className="font-semibold text-slate-800 text-sm">{conflictCount}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">置信度</span><span className="font-semibold text-slate-800 text-sm">{toConfidenceDisplay(confidenceLevel)}</span></li>
                  </ul>
                </div>

                <div className="bg-slate-50/70 border border-slate-200 rounded-2xl p-5 hover:bg-white transition-colors duration-300">
                  <h4 className="text-sm font-bold text-slate-700 mb-5 flex items-center gap-2"><CreditCard className="w-4 h-4 text-orange-500" /> 风险与金融</h4>
                  <ul className="space-y-3.5">
                    <li className="flex items-center justify-between"><span className="text-slate-500 text-sm">综合风险</span><span className="font-semibold text-slate-800 text-sm">{toRiskDisplay(riskLevel)}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">信用画像摘要</span><span className="font-semibold text-slate-800 text-sm text-right max-w-[58%]">{creditSummary}</span></li>
                    <li className="flex items-center justify-between"><span className="text-slate-500 text-sm">客群特征</span><span className="font-semibold text-slate-800 text-sm">{toSegmentFeature(segment)}</span></li>
                    <li className="flex items-center justify-between gap-4"><span className="text-slate-500 text-sm">核心标签</span><span className="font-semibold text-slate-800 text-sm text-right max-w-[58%]">{tags.slice(0, 2).join(' / ') || '暂无标签'}</span></li>
                  </ul>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1 bg-gradient-to-b from-amber-50 to-white border border-amber-200 rounded-2xl p-6 shadow-sm relative overflow-hidden flex flex-col">
                  <div className="absolute top-0 left-0 w-1.5 h-full bg-amber-400"></div>
                  <h4 className="text-sm font-bold text-amber-900 mb-5 flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-amber-500" /> 多智能体信号冲突校验</h4>
                  <div className="flex-1 flex flex-col justify-center space-y-4">
                    <div className="bg-white p-4 rounded-xl border border-amber-100 shadow-sm relative">
                      <div className="absolute -left-2 top-4 w-4 h-4 bg-white border border-amber-200 rotate-45 transform -translate-x-1/2"></div>
                      <p className="text-xs text-amber-700 font-bold mb-2 flex items-center gap-1.5"><AlertCircle className="w-4 h-4" /> 发现的主要冲突</p>
                      <p className="text-[13px] text-slate-700 leading-relaxed text-justify">{conflictText}</p>
                    </div>
                    <div className="flex justify-center -my-2"><ChevronRight className="w-6 h-6 text-amber-300 rotate-90" /></div>
                    <div className="bg-amber-500 text-white p-4 rounded-xl shadow-md relative overflow-hidden">
                      <div className="absolute -right-4 -bottom-4 opacity-10"><BrainCircuit className="w-24 h-24" /></div>
                      <p className="text-xs text-amber-100 font-bold mb-2 flex items-center gap-1.5 relative z-10"><CheckCircle2 className="w-4 h-4" /> 综合判定</p>
                      <p className="text-[13px] leading-relaxed relative z-10 text-justify">{profile.summary}</p>
                    </div>
                  </div>
                </div>

                <div className="lg:col-span-2 bg-slate-800 rounded-2xl p-6 shadow-md relative overflow-hidden text-slate-300 flex flex-col">
                  <div className="absolute top-0 right-0 w-64 h-64 bg-fuchsia-600/20 rounded-full blur-3xl mix-blend-screen pointer-events-none"></div>
                  <div className="absolute bottom-0 left-10 w-40 h-40 bg-blue-500/20 rounded-full blur-2xl mix-blend-screen pointer-events-none"></div>
                  <div className="flex items-center gap-2 mb-5 relative z-10"><Bot className="w-5 h-5 text-fuchsia-400" /><h4 className="text-sm font-bold text-white tracking-wide">LLM 业务研判与运营建议</h4></div>
                  <div className="bg-slate-900/60 rounded-xl p-5 mb-5 border border-slate-700/50 relative z-10 shadow-inner"><p className="text-[13px] leading-relaxed text-slate-200 text-justify">{profile.summary}</p></div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5 relative z-10 mt-auto">
                    <div className="bg-slate-800/80 border border-slate-600/50 p-4.5 rounded-xl hover:border-fuchsia-500/50 transition-colors">
                      <p className="text-[11px] font-bold text-fuchsia-400 uppercase tracking-wider mb-3 flex items-center gap-1.5"><Lightbulb className="w-3.5 h-3.5" /> 营销触达策略</p>
                      <ul className="space-y-3">
                        <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-fuchsia-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(217,70,239,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">{marketingSuggestion}</span></li>
                        <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-fuchsia-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(217,70,239,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">建议结合 {toSegmentDisplay(segment)} 的客群定位，优先展示与 {toValueSignalDisplay(valueSignal)} 匹配的权益或额度方案。</span></li>
                      </ul>
                    </div>
                    <div className="bg-slate-800/80 border border-slate-600/50 p-4.5 rounded-xl hover:border-blue-500/50 transition-colors">
                      <p className="text-[11px] font-bold text-blue-400 uppercase tracking-wider mb-3 flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> 风险控制策略</p>
                      <ul className="space-y-3">
                        <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">{riskSuggestion}</span></li>
                        <li className="flex items-start gap-2.5"><div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div><span className="text-xs text-slate-300 leading-relaxed">Mock 页面使用静态数据模拟与主项目一致的综合画像展示结构。</span></li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        }

        function AppPanel({ profile }) {
          const metrics = profile.structured_result.metrics || {};
          const evidence = profile.structured_result.evidence || {};
          const tags = profile.structured_result.tags || [];
          const [activeCategoryIndex, setActiveCategoryIndex] = useState(0);
          const [showCategoryDetail, setShowCategoryDetail] = useState(false);
          const activeDays = metrics.active_days_30d || 0;
          const installedCount = metrics.installed_app_count || 0;
          const topCategory = evidence.top_category || 'unknown';
          const activityLevel = profile.structured_result.activity_level || 'unknown';
          const summary = profile.summary || '暂无 App 画像结果';
          const categorySeries = [
            { label: '生活消费', share: 46, value: 2, color: 'bg-blue-500' },
            { label: '社交媒体', share: 24, value: 1, color: 'bg-cyan-500' },
            { label: '支付金融', share: 18, value: 1, color: 'bg-indigo-500' },
            { label: '其他-待归类', share: 12, value: 0, color: 'bg-purple-500' },
          ];
          const categoryDetails = {
            '生活消费': [
              { app_name: 'Taobao', first_install_time: '2025-02-02 09:20', last_update_time: '2025-03-03 13:10', gp_category: 'Shopping', ai_category_level_2_CN: '电商消费' },
              { app_name: 'Meituan', first_install_time: '2025-02-10 18:45', last_update_time: '2025-03-01 08:30', gp_category: 'Food & Drink', ai_category_level_2_CN: '外卖-出行' },
            ],
            '社交媒体': [
              { app_name: 'WeChat', first_install_time: '2024-12-12 11:10', last_update_time: '2025-03-05 10:00', gp_category: 'Communication', ai_category_level_2_CN: '社交媒体' },
            ],
            '支付金融': [
              { app_name: 'Alipay', first_install_time: '2025-01-05 14:00', last_update_time: '2025-03-06 09:40', gp_category: 'Finance', ai_category_level_2_CN: '银行-金融' },
            ],
          };
          const activeCategory = categorySeries[activeCategoryIndex] || categorySeries[0];
          const activeCategoryApps = categoryDetails[activeCategory.label] || [];
          const appInsights = [
            { label: '分类稳定度', value: 76, color: 'bg-blue-500', risk: '偏好清晰', riskLevel: 'low' },
            { label: '活跃覆盖度', value: Math.max(18, Math.min(88, activeDays * 3)), color: 'bg-cyan-500', risk: '近30天活跃', riskLevel: 'safe' },
            { label: '留存表现', value: 72, color: 'bg-indigo-500', risk: '长期保留较好', riskLevel: 'low' },
            { label: '数据完整度', value: tags.length ? 82 : 30, color: 'bg-purple-500', risk: tags.length ? '标签完整' : '待补数据', riskLevel: tags.length ? 'safe' : 'mid' },
          ];
          const timelineItems = [
            { time: '09:30', title: 'App Profile Started', sub: `Top Category: ${topCategory}`, icon: Smartphone, color: 'bg-blue-500' },
            { time: '09:36', title: 'Installed Apps Parsed', sub: `${installedCount} 个应用已识别`, icon: Database, color: 'bg-cyan-500' },
            { time: '09:42', title: 'Activity Pattern Updated', sub: `活跃等级: ${activityLevel}`, icon: Search, color: 'bg-green-500' },
            { time: '09:50', title: 'App Summary Generated', sub: summary, icon: MousePointerClick, color: 'bg-slate-400', isLast: true }
          ];
          const predictionCards = [
            { title: '借贷风险等级', value: '低', accentClass: 'text-amber-300', description: '代表应用：DiDi Finanzas、MexiCash', reason: '样本中借贷类应用数量少，且近期新增有限，因此风险等级偏低。' },
            { title: '金融成熟度', value: '银行化', accentClass: 'text-cyan-300', description: '代表应用：Alipay / WeChat Pay', reason: '支付与金融基础设施覆盖较好，说明用户对数字金融工具较熟悉。' },
            { title: '消费能力', value: '中等', accentClass: 'text-fuchsia-300', description: '代表类型：电商消费、外卖出行', reason: '消费类应用安装集中在日常场景，体现稳定但非高奢型消费能力。' },
          ];

          return (
            <div className="animate-in fade-in duration-500">
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100"><Smartphone className="w-8 h-8 text-blue-500" /><h2 className="text-2xl font-bold text-slate-800">Skill 1: App画像 Agent</h2></div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                <div className="col-span-1 md:col-span-8 space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-gradient-to-br from-blue-50 to-cyan-50 p-5 rounded-2xl border border-blue-100 flex items-center gap-4"><div className="w-12 h-12 bg-blue-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-blue-500/30"><Smartphone className="w-6 h-6" /></div><div><p className="text-sm text-blue-600/80 font-medium mb-0.5">安装 App 数量</p><p className="text-2xl font-bold text-slate-800">{installedCount} <span className="text-sm font-normal text-slate-500">apps</span></p></div></div>
                    <div className="bg-white p-5 rounded-2xl border border-slate-200 flex items-center gap-4 shadow-sm"><div className="w-12 h-12 bg-cyan-100 rounded-full flex items-center justify-center text-cyan-600"><Database className="w-6 h-6" /></div><div><p className="text-sm text-slate-500 font-medium mb-0.5">Top Category</p><p className="text-2xl font-bold text-slate-800">{topCategory}</p></div></div>
                    <div className="bg-white p-5 rounded-2xl border border-slate-200 flex items-center gap-4 shadow-sm"><div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center text-green-600"><TrendingUp className="w-6 h-6" /></div><div><p className="text-sm text-slate-500 font-medium mb-0.5">Activity Level</p><p className="text-2xl font-bold text-slate-800">{activityLevel}</p></div></div>
                  </div>
                  <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm"><h3 className="text-base font-bold text-slate-800 mb-6 flex items-center justify-between"><div className="flex items-center gap-2"><PieChart className="w-5 h-5 text-slate-400" />App 偏好分布与安装洞察</div><span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-1 rounded-md">应用画像模型</span></h3><div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)] gap-8 items-start"><div className="space-y-5"><div className="flex flex-col items-center"><div className="relative w-[240px] h-[240px] rounded-full flex items-center justify-center shadow-md" style={{ background: `conic-gradient(#3b82f6 0% 46%, #06b6d4 46% 70%, #6366f1 70% 88%, #8b5cf6 88% 100%)` }}><div className="absolute inset-[54px] bg-white rounded-full flex flex-col items-center justify-center shadow-inner border border-slate-100"><span className="text-3xl font-bold text-slate-800">{activeCategory.share}%</span><span className="text-xs text-slate-500 px-2 text-center">{activeCategory.label}</span></div></div></div><div className="rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-blue-50/60 px-5 py-4 shadow-sm"><div className="flex items-start justify-between gap-4"><div><div className="text-xs text-slate-500 mb-1">当前选中类别</div><div className="text-2xl font-bold text-slate-800">{activeCategory.label}</div><div className="text-sm text-slate-600 mt-2">{activeCategory.value} 个 App，占比 {activeCategory.share}%</div></div><button type="button" disabled={!activeCategoryApps.length} onClick={() => activeCategoryApps.length && setShowCategoryDetail(true)} className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium ${activeCategoryApps.length ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed'}`}>{activeCategoryApps.length ? '(查看该类App)' : '(暂无明细)'}</button></div></div><div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3 text-sm w-full">{categorySeries.map((item, index) => (<button key={item.label} type="button" className={`text-left rounded-2xl border px-4 py-3 ${activeCategoryIndex === index ? 'border-blue-300 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:bg-slate-50'}`} onClick={() => setActiveCategoryIndex(index)}><LegendDot color={item.color} label={`${item.label} (${item.share}%)`} /></button>))}</div></div><div className="space-y-5"><div className="rounded-3xl border border-slate-200 bg-slate-50/80 p-5">{appInsights.map((item) => (<div key={item.label} className="mb-5 last:mb-0"><div className="flex justify-between items-end mb-2 gap-4"><span className="text-sm font-medium text-slate-700">{item.label}</span><span className={riskBadgeClass(item.riskLevel)}>{item.risk}</span></div><div className="w-full bg-slate-100 rounded-full h-1.5 flex items-center"><div className={`${item.color} h-1.5 rounded-full`} style={{ width: `${item.value}%` }} /><span className="text-xs text-slate-400 ml-3">{item.value}</span></div></div>))}</div><div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-3 mb-4"><div><h4 className="text-base font-bold text-slate-800">用户核心标签</h4><p className="text-xs text-slate-500 mt-1">Mock 页面同步新的布局与标签呈现效果。</p></div><span className="text-xs text-slate-400">标签画像</span></div><div className="flex flex-wrap gap-3">{tags.map((tag, index) => (<span key={tag} className={`px-3.5 py-2 rounded-full text-sm font-medium border ${mockTagTone(index)}`}>{tag}</span>))}</div></div></div></div></div>
                </div>
                <div className="col-span-1 md:col-span-4 space-y-6"><div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm h-auto relative overflow-hidden"><div className="absolute top-0 right-0 w-20 h-20 bg-blue-50 rounded-bl-full z-0"></div><div className="relative z-10"><div className="flex justify-between items-center mb-6"><h3 className="text-base font-bold text-slate-800">App 画像轨迹</h3><span className="text-xs font-medium bg-slate-100 text-slate-600 px-2 py-1 rounded">Today</span></div><div className="mt-4">{timelineItems.map((item, index) => (<TimelineItem key={`${item.time}-${index}`} time={item.time} title={item.title} sub={item.sub} icon={item.icon} color={item.color} isLast={Boolean(item.isLast)} />))}</div></div></div><div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl shadow-lg relative overflow-hidden group min-h-[540px]"><div className="absolute -right-4 -top-4 w-24 h-24 bg-blue-500/20 rounded-full blur-xl group-hover:bg-blue-500/30 transition-all"></div><BrainCircuit className="absolute -bottom-2 -right-2 w-20 h-20 text-slate-700/50" /><h3 className="text-base font-bold text-white mb-5 relative z-10">Next App Predictions</h3><div className="flex items-center justify-between bg-slate-800/80 p-4 rounded-xl border border-slate-700/50 mb-4 relative z-10 backdrop-blur-sm gap-4"><div><p className="text-xs text-slate-400 mb-1">Retention Confidence</p><p className="text-3xl font-bold text-cyan-400 flex items-center gap-1">78%<TrendingUp className="w-5 h-5 text-cyan-400" /></p></div><div className="text-right"><p className="text-xs text-slate-400 mb-1">Predicted Focus</p><p className="text-lg font-bold text-white">{topCategory}</p></div></div><div className="rounded-2xl border border-slate-700/70 bg-slate-800/70 px-4 py-4 relative z-10"><p className="text-sm text-slate-100 leading-6">{summary}</p><p className="text-xs text-slate-400 mt-3">Mock 说明：这里额外补充了等级解释与代表应用说明。</p></div><div className="mt-4 space-y-3 relative z-10">{predictionCards.map((item) => (<div key={item.title} className="rounded-2xl border border-slate-700/70 bg-slate-800/70 px-4 py-3"><div className="flex items-center justify-between gap-3"><span className="text-xs uppercase tracking-[0.18em] text-slate-400">{item.title}</span><span className={`text-sm font-semibold ${item.accentClass}`}>{item.value}</span></div><div className="text-xs text-slate-200 mt-2 leading-5">{item.description}</div><div className="text-xs text-slate-300 mt-2 leading-5">{item.reason}</div></div>))}</div></div></div>
              </div>
              <MockCategoryAppsModal open={showCategoryDetail} category={activeCategory.label} apps={activeCategoryApps} onClose={() => setShowCategoryDetail(false)} />
            </div>
          );
        }

        function BehaviorPanel({ profile }) {
          const metrics = profile.structured_result.metrics || {};
          const evidence = profile.structured_result.evidence || {};
          const summary = profile.summary || '暂无行为画像结果';
          const avgSessionMinutes = metrics.avg_session_minutes || evidence.avg_session_minutes || 0;
          const loginDays30d = metrics.login_days_30d || evidence.login_days_30d || 0;
          const preference = evidence.purchase_preference || 'balanced';
          const engagementLevel = profile.structured_result.engagement_level || 'unknown';
          const ltvScore = Math.min(95, Math.max(45, loginDays30d * 3 + Math.min(avgSessionMinutes, 20)));
          const totalSpend = avgSessionMinutes > 0 ? avgSessionMinutes * 240 : 12500;
          const orderValue = avgSessionMinutes > 0 ? avgSessionMinutes * 8 + 34 : 450;
          const mainPreferenceShare = preference === 'premium_quality' ? 45 : preference === 'value_sensitive' ? 38 : 35;
          const behaviorInsights = [
            { label: '高频浏览设备评测', value: Math.min(92, loginDays30d * 3 + 12), color: 'bg-orange-500', risk: '冲动消费倾向', riskLevel: 'high' },
            { label: '比价与加入购物车', value: Math.min(88, avgSessionMinutes + 26), color: 'bg-blue-500', risk: '价格极度敏感', riskLevel: 'mid' },
            { label: '金融社区活跃度', value: Math.min(78, loginDays30d * 2 + 11), color: 'bg-green-500', risk: '多头借贷低风险', riskLevel: 'low' },
            { label: '夜间活跃频率', value: Math.min(65, Math.max(18, avgSessionMinutes / 2)), color: 'bg-purple-500', risk: '作息规律正常', riskLevel: 'safe' }
          ];
          const timelineItems = [
            { time: '10:02', title: 'App Launched', sub: `会话深度: ${engagementLevel}`, icon: Smartphone, color: 'bg-blue-500' },
            { time: '10:05', title: `Checked ${preference}`, sub: `近 30 天登录 ${loginDays30d} 天`, icon: Search, color: 'bg-green-500' },
            { time: '10:15', title: 'Behavior Snapshot Updated', sub: `平均会话 ${avgSessionMinutes} 分钟`, icon: ShoppingCart, color: 'bg-orange-500' },
            { time: '10:30', title: 'App Closed', sub: summary, icon: MousePointerClick, color: 'bg-slate-400', isLast: true }
          ];

          return (
            <div className="animate-in fade-in duration-500">
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
                <Activity className="w-8 h-8 text-orange-500" />
                <h2 className="text-2xl font-bold text-slate-800">Skill 2: 行为轨迹与价值预测 (Behavior & Value)</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                <div className="col-span-1 md:col-span-8 space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-gradient-to-br from-amber-50 to-orange-50 p-5 rounded-2xl border border-orange-100 flex items-center gap-4">
                      <div className="w-12 h-12 bg-orange-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-orange-500/30">
                        <Target className="w-6 h-6" />
                      </div>
                      <div>
                        <p className="text-sm text-orange-600/80 font-medium mb-0.5">客户价值评分 (LTV)</p>
                        <p className="text-2xl font-bold text-slate-800">{ltvScore} <span className="text-sm font-normal text-slate-500">/100</span></p>
                      </div>
                    </div>
                    <div className="bg-white p-5 rounded-2xl border border-slate-200 flex items-center gap-4 shadow-sm">
                      <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center text-blue-600">
                        <CreditCard className="w-6 h-6" />
                      </div>
                      <div>
                        <p className="text-sm text-slate-500 font-medium mb-0.5">总消费估值</p>
                        <p className="text-2xl font-bold text-slate-800">{formatCurrency(totalSpend)}</p>
                      </div>
                    </div>
                    <div className="bg-white p-5 rounded-2xl border border-slate-200 flex items-center gap-4 shadow-sm">
                      <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center text-green-600">
                        <TrendingUp className="w-6 h-6" />
                      </div>
                      <div>
                        <p className="text-sm text-slate-500 font-medium mb-0.5">客单价水平</p>
                        <p className="text-2xl font-bold text-slate-800">{formatCurrency(orderValue)}</p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                    <h3 className="text-base font-bold text-slate-800 mb-6 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <PieChart className="w-5 h-5 text-slate-400" />
                        偏好分布与行为风险洞察
                      </div>
                      <span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-1 rounded-md">综合数据模型</span>
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
                      <div className="flex flex-col items-center">
                        <div className="relative w-40 h-40 rounded-full flex items-center justify-center shadow-md mb-6" style={{ background: `conic-gradient(#f97316 0% ${mainPreferenceShare}%, #3b82f6 ${mainPreferenceShare}% ${mainPreferenceShare + 30}%, #22c55e ${mainPreferenceShare + 30}% ${mainPreferenceShare + 45}%, #8b5cf6 ${mainPreferenceShare + 45}% 100%)` }}>
                          <div className="absolute inset-0 m-5 bg-white rounded-full flex flex-col items-center justify-center shadow-inner">
                            <span className="text-2xl font-bold text-slate-800">{mainPreferenceShare}%</span>
                            <span className="text-xs text-slate-500">主偏好占比</span>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm w-full pl-2">
                          <LegendDot color="bg-orange-500" label={`${preference} (${mainPreferenceShare}%)`} />
                          <LegendDot color="bg-blue-500" label={`登录活跃 (${Math.max(10, 100 - mainPreferenceShare - 25)}%)`} />
                          <LegendDot color="bg-green-500" label={`会话深度 (${Math.max(10, Math.min(25, loginDays30d))}%)`} />
                          <LegendDot color="bg-purple-500" label={`价值信号 (${Math.max(10, Math.min(20, Math.round(avgSessionMinutes / 3 || 10)))}%)`} />
                        </div>
                      </div>

                      <div className="space-y-6 border-l border-slate-100 pl-6">
                        {behaviorInsights.map((item) => (
                          <div key={item.label}>
                            <div className="flex justify-between items-end mb-2 gap-4">
                              <span className="text-sm font-medium text-slate-700">{item.label}</span>
                              <span className={riskBadgeClass(item.riskLevel)}>{item.risk}</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-1.5 flex items-center">
                              <div className={`${item.color} h-1.5 rounded-full transition-all duration-1000`} style={{ width: `${item.value}%` }} />
                              <span className="text-xs text-slate-400 ml-3">{item.value}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="col-span-1 md:col-span-4 space-y-6">
                  <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm h-auto relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-20 h-20 bg-blue-50 rounded-bl-full z-0"></div>
                    <div className="relative z-10">
                      <div className="flex justify-between items-center mb-6">
                        <h3 className="text-base font-bold text-slate-800">实时行为轨迹</h3>
                        <span className="text-xs font-medium bg-slate-100 text-slate-600 px-2 py-1 rounded">Today</span>
                      </div>

                      <div className="mt-4">
                        {timelineItems.map((item, index) => (
                          <TimelineItem
                            key={`${item.time}-${index}`}
                            time={item.time}
                            title={item.title}
                            sub={item.sub}
                            icon={item.icon}
                            color={item.color}
                            isLast={Boolean(item.isLast)}
                          />
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl shadow-lg relative overflow-hidden group">
                    <div className="absolute -right-4 -top-4 w-24 h-24 bg-blue-500/20 rounded-full blur-xl group-hover:bg-blue-500/30 transition-all"></div>
                    <BrainCircuit className="absolute -bottom-2 -right-2 w-20 h-20 text-slate-700/50" />

                    <h3 className="text-base font-bold text-white mb-5 relative z-10">Next Behavior Predictions</h3>

                    <div className="flex items-center justify-between bg-slate-800/80 p-4 rounded-xl border border-slate-700/50 mb-3 relative z-10 backdrop-blur-sm gap-4">
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Purchase Probability</p>
                        <p className="text-3xl font-bold text-green-400 flex items-center gap-1">
                          {Math.min(95, Math.max(52, loginDays30d * 2 + Math.round(avgSessionMinutes / 2)))}%
                          <TrendingUp className="w-5 h-5 text-green-500" />
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-slate-400 mb-1">Predicted Category</p>
                        <p className="text-lg font-bold text-white">{preference}</p>
                      </div>
                    </div>
                    <p className="text-xs text-slate-500 text-right relative z-10">{summary}</p>
                  </div>
                </div>
              </div>
            </div>
          );
        }

        function CreditPanel({ profile }) {
          const metrics = profile.structured_result.metrics || {};
          const riskLevel = metrics.risk_level || '-';
          const riskPercentMap = { low: 35, medium: 62, high: 88 };
          const debtRatio = riskPercentMap[riskLevel] || 20;

          return (
            <div className="animate-in fade-in duration-500">
              <div className="flex items-center gap-3 mb-8 pb-4 border-b border-slate-100">
                <CreditCard className="w-8 h-8 text-slate-600" />
                <h2 className="text-2xl font-bold text-slate-800">Skill 3: 信用画像 Agent</h2>
              </div>
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                <div className="border border-slate-200 rounded-xl p-6">
                  <h3 className="font-bold text-slate-700 mb-4 flex items-center gap-2">
                    <PieChart className="w-5 h-5" />
                    信用风险结构
                  </h3>
                  <div className="flex items-center justify-center py-6">
                    <div className="relative w-40 h-40 rounded-full border-8 border-slate-100 flex items-center justify-center">
                      <div className="absolute inset-0 rounded-full" style={{ background: `conic-gradient(#3b82f6 0 ${debtRatio}%, #cbd5e1 ${debtRatio}% 100%)` }} />
                      <div className="absolute inset-4 rounded-full bg-white" />
                      <div className="relative text-center">
                        <span className="block text-2xl font-bold text-slate-700">{debtRatio}%</span>
                        <span className="text-xs text-slate-500">风险映射值</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-center gap-4 text-sm mt-2">
                    <span className="flex items-center gap-1"><div className="w-3 h-3 bg-blue-500 rounded-full" /> 风险强度</span>
                    <span className="flex items-center gap-1"><div className="w-3 h-3 bg-slate-300 rounded-full" /> 稳定区间</span>
                  </div>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-6">
                  <h3 className="font-bold text-slate-700 mb-4">信用历史指标</h3>
                  <div className="space-y-5">
                    <ProgressRow label="Credit Score Band" value={metrics.credit_score_band || '-'} widthClass="w-4/5" barClass="bg-blue-500" />
                    <ProgressRow label="Repayment Status" value={metrics.repayment_status || '-'} widthClass="w-full" barClass="bg-green-500" />
                    <ProgressRow label="Risk Level" value={riskLevel} widthClass={riskLevel === 'low' ? 'w-1/3' : riskLevel === 'medium' ? 'w-2/3' : 'w-full'} barClass="bg-slate-600" />
                  </div>
                </div>
              </div>
            </div>
          );
        }

        function InfoRow({ label, value, valueClass }) {
          return (
            <li className="bg-white p-3 rounded shadow-sm border border-slate-100 flex justify-between gap-3">
              <span className="text-slate-600">{label}</span>
              <span className={`font-semibold text-right ${valueClass}`}>{value}</span>
            </li>
          );
        }

        function ProgressRow({ label, value, widthClass, barClass }) {
          return (
            <div>
              <div className="flex justify-between text-sm mb-1 text-slate-600">
                <span>{label}</span>
                <span className="text-slate-800 font-bold">{value}</span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-1.5">
                <div className={`${barClass} h-1.5 rounded-full ${widthClass}`} />
              </div>
            </div>
          );
        }


        function MockCategoryAppsModal({ open, category, apps, onClose }) {
          if (!open) return null;
          return (
            <div className="fixed inset-0 z-50 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center px-4" onClick={onClose}>
              <div className="w-full max-w-4xl max-h-[82vh] overflow-hidden rounded-3xl bg-white shadow-2xl border border-slate-200" onClick={(event) => event.stopPropagation()}>
                <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-white"><div><div className="text-xs uppercase tracking-[0.2em] text-slate-400">Category Apps</div><h3 className="text-xl font-bold text-slate-800 mt-1">{category} · {apps.length} 个 App</h3></div><button type="button" className="rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-2 text-sm" onClick={onClose}>关闭</button></div>
                <div className="px-6 py-5 overflow-y-auto max-h-[calc(82vh-88px)] space-y-4">{apps.map((app, index) => (<div key={`${app.app_name}-${index}`} className="rounded-2xl border border-slate-200 p-4 bg-slate-50/60"><div className="text-base font-semibold text-slate-800">{app.app_name}</div><div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4 text-sm"><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">安装时间</div><div className="text-slate-700 font-medium">{app.first_install_time}</div></div><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">最后更新时间</div><div className="text-slate-700 font-medium">{app.last_update_time}</div></div><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">GP Category</div><div className="text-slate-700 font-medium">{app.gp_category}</div></div><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">AI Category Level 2</div><div className="text-slate-700 font-medium">{app.ai_category_level_2_CN}</div></div></div></div>))}</div>
              </div>
            </div>
          );
        }

        function mockTagTone(index) {
          const tones = ['bg-blue-50 text-blue-700 border-blue-100','bg-cyan-50 text-cyan-700 border-cyan-100','bg-violet-50 text-violet-700 border-violet-100','bg-emerald-50 text-emerald-700 border-emerald-100'];
          return tones[index % tones.length];
        }

        function LegendDot({ color, label }) {
          return (
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${color}`} />
              <span className="text-slate-600">{label}</span>
            </div>
          );
        }

        function TimelineItem({ time, title, sub, icon: Icon, color, isLast }) {
          return (
            <div className="relative pl-8 pb-8">
              {!isLast && <div className="absolute left-3.5 top-8 bottom-0 w-0.5 bg-slate-200" />}
              <div className={`absolute left-0 top-1 w-7 h-7 rounded-full flex items-center justify-center text-white shadow-md ${color} ring-4 ring-white`}>
                <Icon className="w-3.5 h-3.5" />
              </div>
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <span className="text-sm font-bold text-slate-700">{time}</span>
                  <span className="text-sm font-medium text-slate-800">{title}</span>
                </div>
                {sub && <p className="text-xs text-slate-500 bg-slate-50 p-2 rounded-md border border-slate-100 inline-block mt-1">{sub}</p>}
              </div>
            </div>
          );
        }

        function formatCurrency(value) {
          return `¥${Number(value || 0).toLocaleString('en-US')}`;
        }

        function riskBadgeClass(riskLevel) {
          const mapping = {
            high: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-red-50 text-red-600 border-red-200',
            mid: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-amber-50 text-amber-600 border-amber-200',
            low: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-blue-50 text-blue-600 border-blue-200',
            safe: 'text-[11px] font-medium px-2 py-0.5 rounded-full border bg-slate-50 text-slate-500 border-slate-200'
          };
          return mapping[riskLevel] || mapping.safe;
        }

        function toSegmentDisplay(segment) {
          const mapping = {
            S1: 'S1 高价值稳健客群',
            S2: 'S2 稳健经营客群',
            S3: 'S3 机会转化客群',
            S4: 'S4 流失预警客群',
            S5: 'S5 风险关注客群',
            S6: 'S6 待观察客群'
          };
          return mapping[String(segment || 'S6').toUpperCase()] || `${String(segment || 'S6')} 待观察客群`;
        }

        function toSegmentFeature(segment) {
          const mapping = {
            S1: '高价值 + 低风险',
            S2: '稳健经营 + 中低风险',
            S3: '活跃需求 + 待转化',
            S4: '高流失风险',
            S5: '高风险重点关注',
            S6: '信息有限待补充'
          };
          return mapping[String(segment || 'S6').toUpperCase()] || '信息有限待补充';
        }

        function toValueSignalDisplay(level) {
          const mapping = {
            high: '高价值',
            medium: '中高价值',
            low: '基础价值'
          };
          return mapping[String(level || 'low').toLowerCase()] || '待确认';
        }

        function toConfidenceDisplay(level) {
          const mapping = {
            high: '高',
            medium: '中',
            low: '低'
          };
          return mapping[String(level || 'low').toLowerCase()] || '低';
        }

        function toRiskDisplay(level) {
          const mapping = {
            low: '中低风险',
            medium: '中等风险',
            high: '高风险'
          };
          return mapping[String(level || 'low').toLowerCase()] || '待确认风险';
        }

        function buildComprehensiveMarketingSuggestion(segment, valueSignal, llmAccepted) {
          const normalizedSegment = String(segment || '').toUpperCase();
          const normalizedValue = String(valueSignal || '').toLowerCase();
          if (normalizedSegment === 'S1' || normalizedValue === 'high') {
            return '建议优先推送提额、续贷或高价值权益方案，突出稳定经营与长期合作收益。';
          }
          if (normalizedSegment === 'S5') {
            return '营销触达应更克制，避免过强刺激，优先传递透明规则与稳健服务信息。';
          }
          return llmAccepted
            ? '建议以常规权益、分层额度和场景化触达为主，逐步验证转化与留存表现。'
            : '当前结果为回退展示，建议先观察后续补充数据，再决定是否推送更强营销动作。';
        }

        function buildComprehensiveRiskSuggestion(riskLevel, conflictCount, confidenceLevel) {
          const normalizedRisk = String(riskLevel || '').toLowerCase();
          const normalizedConfidence = String(confidenceLevel || '').toLowerCase();
          if (normalizedRisk === 'high') {
            return '维持强规则校验与名单监控，必要时收紧额度或转人工复核。';
          }
          if (conflictCount > 0) {
            return '建议保留监控名单，并持续跟踪跨模块冲突信号是否扩大。';
          }
          if (normalizedConfidence === 'low') {
            return '当前置信度偏低，建议先补数或等待更多行为样本后再放大自动化决策权重。';
          }
          return '可维持当前风险策略，并按周期复评综合画像变化趋势。';
        }

        const root = createRoot(document.getElementById('root'));
        root.render(<App />);
    </script>
</body>
</html>
"""
