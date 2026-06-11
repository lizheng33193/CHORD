// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// Note: '\\n' (Python-escaped) → '\n' (single-escape) is a string un-nesting fix
// extending Plan G.3 关键改动 2 (UID_PATTERN precedent).

const { stringValue } = window.AppUtils.normalize;

function renderInlineMarkdown(text, keyPrefix) {
  const safeText = String(text || '');
  const parts = safeText.split('**');
  return parts.map((part, index) => (
    index % 2 === 1
      ? <strong key={`${keyPrefix}-${index}`} className="font-semibold text-slate-900">{part}</strong>
      : <React.Fragment key={`${keyPrefix}-${index}`}>{part}</React.Fragment>
  ));
}

function MarkdownBlock({ text }) {
  const lines = stringValue(text, '').split('\n').filter((line, index, arr) => line.trim() || (index > 0 && arr[index - 1].trim()));
  return (
    <div className="space-y-3 text-sm text-slate-700 leading-7">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (trimmed.startsWith('## ') && !trimmed.startsWith('### ')) {
          return <h3 key={index} className="text-xl font-bold text-slate-900 pt-4 pb-1 border-b border-slate-200 mb-2">{renderInlineMarkdown(trimmed.slice(3), `h2-${index}`)}</h3>;
        }
        if (trimmed.startsWith('### ')) {
          return <h4 key={index} className="text-lg font-bold text-slate-800 pt-3">{renderInlineMarkdown(trimmed.slice(4), `heading-${index}`)}</h4>;
        }
        if (trimmed.startsWith('#### ')) {
          return <h5 key={index} className="text-base font-semibold text-slate-800 pt-2">{renderInlineMarkdown(trimmed.slice(5), `subheading-${index}`)}</h5>;
        }
        if (/^[一二三四五六七八九十]+[、.]/.test(trimmed)) {
          return <h4 key={index} className="text-lg font-bold text-slate-800 pt-4 pb-1 flex items-center gap-2"><span className="w-1.5 h-6 bg-blue-500 rounded-full inline-block"></span>{renderInlineMarkdown(trimmed, `section-${index}`)}</h4>;
        }
        if (trimmed.startsWith('- ')) {
          return (
            <p key={index} className="pl-4 before:content-['•'] before:mr-2 before:text-blue-500">
              {renderInlineMarkdown(trimmed.slice(2), `bullet-${index}`)}
            </p>
          );
        }
        return <p key={index}>{renderInlineMarkdown(trimmed, `paragraph-${index}`)}</p>;
      })}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.MarkdownBlock = MarkdownBlock;
