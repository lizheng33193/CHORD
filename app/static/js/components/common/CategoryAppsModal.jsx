// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { stringValue, arrayValue, numberValue, objectValue } = window.AppUtils.normalize;

function CategoryAppsModal({ category, detail, onClose, open }) {
  if (!open) return null;
  const safeDetail = objectValue(detail);
  const apps = arrayValue(safeDetail.apps);
  const localizedCategory = stringValue(category, stringValue(safeDetail.localized_category, '其他-待归类'));
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center px-4" onClick={onClose}>
      <div className="w-full max-w-4xl max-h-[82vh] overflow-hidden rounded-3xl bg-white shadow-2xl border border-slate-200" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-white"><div><div className="text-xs uppercase tracking-[0.2em] text-slate-400">Category Apps</div><h3 className="text-xl font-bold text-slate-800 mt-1">{localizedCategory} · {numberValue(safeDetail.count, apps.length)} 个 App</h3></div><button type="button" className="rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-2 text-sm" onClick={onClose}>关闭</button></div>
        <div className="px-6 py-5 overflow-y-auto max-h-[calc(82vh-88px)] space-y-4">{apps.length ? apps.map((app, index) => (<div key={`${app.app_name || 'app'}-${index}`} className="rounded-2xl border border-slate-200 p-4 bg-slate-50/60"><div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3"><div><div className="text-base font-semibold text-slate-800">{stringValue(app.app_name, 'Unknown App')}</div><div className="text-xs text-slate-400 mt-1">{stringValue(app.package_name, 'Unknown package')}</div></div><span className="inline-flex items-center rounded-full bg-blue-50 text-blue-700 border border-blue-100 px-3 py-1 text-xs font-medium">{stringValue(app.localized_category, localizedCategory)}</span></div><div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4 text-sm"><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">安装时间</div><div className="text-slate-700 font-medium">{stringValue(app.first_install_time, 'Unknown')}</div></div><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">最后更新时间</div><div className="text-slate-700 font-medium">{stringValue(app.last_update_time, 'Unknown')}</div></div><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">GP Category</div><div className="text-slate-700 font-medium">{stringValue(app.gp_category, 'Unknown')}</div></div><div className="rounded-2xl bg-white border border-slate-200 px-4 py-3"><div className="text-xs text-slate-400 mb-1">AI Category Level 2</div><div className="text-slate-700 font-medium">{stringValue(app.ai_category_level_2_CN, 'Unknown')}</div></div></div></div>)) : <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">当前类别暂无 App 明细。</div>}</div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.CategoryAppsModal = CategoryAppsModal;
