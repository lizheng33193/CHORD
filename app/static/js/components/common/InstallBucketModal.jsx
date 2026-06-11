// Extracted from app/ui/live_frontend.py during UI separation Step-1.

const { stringValue, arrayValue, numberValue } = window.AppUtils.normalize;

function InstallBucketModal({ bucket, groups, onClose }) {
  if (!bucket) return null;
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center px-4" onClick={onClose}>
      <div className="w-full max-w-3xl max-h-[80vh] overflow-hidden rounded-3xl bg-white shadow-2xl border border-slate-200" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100"><div><div className="text-xs uppercase tracking-[0.2em] text-slate-400">Install Window</div><h3 className="text-xl font-bold text-slate-800 mt-1">{bucket} 安装明细</h3></div><button type="button" className="rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 px-3 py-2 text-sm" onClick={onClose}>关闭</button></div>
        <div className="px-6 py-5 overflow-y-auto max-h-[calc(80vh-88px)] space-y-4">{groups.length ? groups.map((group, index) => (<div key={`${group.localized_category}-${index}`} className="rounded-2xl border border-slate-200 overflow-hidden"><div className="px-4 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between"><span className="font-semibold text-slate-800">{stringValue(group.localized_category, '其他-待归类')}</span><span className="text-sm text-slate-500">{numberValue(group.count, arrayValue(group.apps).length)} 个 App</span></div><div className="divide-y divide-slate-100">{arrayValue(group.apps).map((app, appIndex) => (<div key={`${app.app_name || 'app'}-${appIndex}`} className="px-4 py-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm"><div className="font-medium text-slate-800">{stringValue(app.app_name, 'Unknown App')}</div><div className="text-slate-600"><span className="block text-xs text-slate-400">安装时间</span>{stringValue(app.first_install_time, 'Unknown')}</div><div className="text-slate-600"><span className="block text-xs text-slate-400">最后更新时间</span>{stringValue(app.last_update_time, 'Unknown')}</div></div>))}</div></div>)) : <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">当前时间段暂无安装明细。</div>}</div>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.InstallBucketModal = InstallBucketModal;
