"""Build the new ?next=1 frontend HTML by inlining all .jsx/.js sources.

Babel Standalone does not guarantee execution order across multiple
<script type="text/babel" src="..."> tags (each is fetched + compiled
asynchronously). The original live_frontend.py worked because it kept
all JSX in a single inline <script type="text/babel"> block.

This module replicates that contract: physically split the source into
many .jsx files (good for editing / diff / review), but at runtime
concatenate them in topological order and inject as one inline block.
The result is cached on first read.
"""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Topological load order — utils -> services -> common -> charts ->
# panels -> top-level views -> entry. Mirrors what app/static/index.html
# used to declare before we collapsed to a single inline block.
LOAD_ORDER = [
    "js/utils/normalize.js",
    "js/utils/chartLookup.js",
    "js/utils/displayMappers.js",
    "js/utils/advice.js",
    "js/state/authStore.js",
    "js/services/httpClient.js",
    "js/services/authApi.js",
    "js/services/api.js",
    "js/services/riskKnowledgeAdminApi.js",
    "js/components/LoginPage.jsx",
    "js/components/RegisterPage.jsx",
    "js/components/AuthGate.jsx",
    "js/components/common/InfoRow.jsx",
    "js/components/common/ProgressRow.jsx",
    "js/components/common/CreditProgressRow.jsx",
    "js/components/common/LegendDot.jsx",
    "js/components/common/MarkdownBlock.jsx",
    "js/components/common/MetricHelpTip.jsx",
    "js/components/common/InstallBucketModal.jsx",
    "js/components/common/CategoryAppsModal.jsx",
    "js/components/common/TimelineItem.jsx",
    "js/components/common/LabelsOverviewCard.jsx",
    "js/components/common/ModuleStatusPanel.jsx",
    "js/components/charts/DonutChart.jsx",
    "js/components/charts/CreditGauge.jsx",
    "js/components/charts/CreditRiskStructure.jsx",
    "js/components/panels/AppPanel.jsx",
    "js/components/panels/BehaviorPanel.jsx",
    "js/components/panels/CreditPanel.jsx",
    "js/components/panels/RichCreditPanel.jsx",
    "js/components/panels/ComprehensivePanel.jsx",
    "js/components/panels/ProductAdvicePanel.jsx",
    "js/components/panels/OpsAdvicePanel.jsx",
    "js/components/panels/trace/ChurnStoryCard.jsx",
    "js/components/panels/trace/FrictionHotspotGrid.jsx",
    "js/components/panels/trace/InterventionList.jsx",
    "js/components/panels/trace/KeyEventsTimeline.jsx",
    "js/components/panels/trace/PathGraphCard.jsx",
    "js/components/panels/trace/TimePatternCard.jsx",
    "js/components/panels/trace/TracePanel.jsx",
    "js/components/panels/knowledge/KnowledgeBaseListPanel.jsx",
    "js/components/panels/knowledge/KnowledgeDocumentPanel.jsx",
    "js/components/panels/knowledge/KnowledgeVersionJobsPanel.jsx",
    "js/components/panels/knowledge/KnowledgeRetrievalDebugPanel.jsx",
    "js/components/panels/knowledge/KnowledgeBaseConsole.jsx",
    "js/components/panels/chat/ChatMessageList.jsx",
    "js/components/panels/chat/ChatInputBox.jsx",
    "js/components/panels/chat/ChatExecutionTraceCard.jsx",
    "js/components/panels/chat/ChatToolCallStream.jsx",
    "js/components/panels/chat/ChatAckCard.jsx",
    "js/components/panels/chat/DataAgentRunForm.jsx",
    "js/components/panels/chat/SQLReviewCard.jsx",
    "js/components/panels/chat/ChatBudgetBanner.jsx",
    "js/components/panels/chat/ChatProviderFallbackBanner.jsx",
    "js/components/panels/chat/MemoryInspector.jsx",
    "js/components/panels/chat/chatReducer.js",
    "js/components/panels/chat/ChatPanel.jsx",
    "js/components/HomeView.jsx",
    "js/components/LoadingView.jsx",
    "js/components/ProgressView.jsx",
    "js/components/DashboardView.jsx",
    "js/app.jsx",
]

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>多 Agent 用户画像分析平台</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600;700&family=Source+Sans+3:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script crossorigin src="https://unpkg.com/react@18.2.0/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18.2.0/umd/react-dom.development.js"></script>
    <script>window.react = window.React;</script>
    <script src="https://unpkg.com/lucide-react@0.292.0/dist/umd/lucide-react.js"></script>
    <script src="https://unpkg.com/@babel/standalone@7/babel.min.js"></script>
    <style>
      :root {
        --maps-bg: #f4f7f9;
        --maps-text: #0f172a;
        --maps-heading: "Lexend", sans-serif;
        --maps-body: "Source Sans 3", sans-serif;
      }

      html, body, #root {
        height: 100%;
      }

      body {
        margin: 0;
        background: var(--maps-bg);
        color: var(--maps-text);
        font-family: var(--maps-body);
      }

      h1, h2, h3, h4, h5, h6 {
        font-family: var(--maps-heading);
      }

      @media (prefers-reduced-motion: reduce) {
        *,
        *::before,
        *::after {
          animation-duration: 0.01ms !important;
          animation-iteration-count: 1 !important;
          transition-duration: 0.01ms !important;
          scroll-behavior: auto !important;
        }
      }
    </style>
</head>
<body class="h-screen overflow-hidden bg-[#F4F7F9] font-sans text-slate-800">
    <div id="root" class="h-full"></div>
    <script type="text/babel" data-presets="env,react">
{bundle}
    </script>
</body>
</html>
"""


def _read_concat() -> str:
    chunks = []
    for rel in LOAD_ORDER:
        path = STATIC_DIR / rel
        body = path.read_text(encoding='utf-8')
        chunks.append(
            f"// === {rel} ===\n"
            f"(function() {{\n"
            f"{body}\n"
            f"}})();"
        )
    return "\n".join(chunks)


def build_frontend_html() -> str:
    """Build the full HTML page with all JSX/JS inlined. Called on every
    request in dev (--reload) to pick up JSX edits without server restart."""
    return _HTML_TEMPLATE.replace("{bundle}", _read_concat())


# Pre-built for production (single read at import time).
BUILT_FRONTEND_HTML = build_frontend_html()
