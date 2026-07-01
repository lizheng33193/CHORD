const {
  KnowledgeBaseListPanel,
  KnowledgeDocumentPanel,
  KnowledgeVersionJobsPanel,
  KnowledgeRetrievalDebugPanel,
} = window.AppComponents;
const knowledgeAdminApi = window.AppServices.riskKnowledgeAdminApi;

function createKnowledgeDebugDraft(selectedKbId, selectedDocumentId, selectedVersionId) {
  return {
    kb_id: selectedKbId || '',
    query: '',
    document_id: selectedDocumentId || '',
    version_id: selectedVersionId || '',
    top_k: 10,
  };
}

function mergeJobsById(previousJobs, refreshedJobs) {
  const jobMap = {};
  (previousJobs || []).forEach((job) => { jobMap[job.job_id] = job; });
  (refreshedJobs || []).forEach((job) => { jobMap[job.job_id] = job; });
  return Object.values(jobMap);
}

function KnowledgeBaseConsole({ activeTab, currentUser = null }) {
  const canManageProject = !currentUser || currentUser.is_superuser || (Array.isArray(currentUser.permissions) && currentUser.permissions.includes('project:manage'));
  const [activeKnowledgeSection, setActiveKnowledgeSection] = React.useState('kbs');
  const [kbItems, setKbItems] = React.useState([]);
  const [selectedKbId, setSelectedKbId] = React.useState('');
  const [selectedKb, setSelectedKb] = React.useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = React.useState('');
  const [selectedDocument, setSelectedDocument] = React.useState(null);
  const [selectedVersionId, setSelectedVersionId] = React.useState('');
  const [versionDetail, setVersionDetail] = React.useState(null);
  const [documents, setDocuments] = React.useState([]);
  const [versions, setVersions] = React.useState([]);
  const [jobs, setJobs] = React.useState([]);
  const [trackedJobIds, setTrackedJobIds] = React.useState([]);
  const [pageVisible, setPageVisible] = React.useState(typeof document === 'undefined' ? true : document.visibilityState === 'visible');
  const [loading, setLoading] = React.useState({ kbs: false, documents: false, versions: false, jobs: false, debug: false });
  const [submitting, setSubmitting] = React.useState({ kb: false, document: false, upload: false });
  const [messages, setMessages] = React.useState({ kb: '', document: '', version: '', debug: '' });
  const [errors, setErrors] = React.useState({ kb: '', document: '', version: '', debug: '' });
  const [createKbDraft, setCreateKbDraft] = React.useState({ kb_id: '', name: '', description: '' });
  const [createDocumentDraft, setCreateDocumentDraft] = React.useState({ title: '', source_type: 'manual', source_uri: '' });
  const [uploadDraft, setUploadDraft] = React.useState({ file: null, version_label: '', auto_index: true, metadataText: '' });
  const [debugDraft, setDebugDraft] = React.useState(createKnowledgeDebugDraft('', '', ''));
  const [debugResult, setDebugResult] = React.useState(null);

  React.useEffect(() => {
    function handleVisibilityChange() {
      setPageVisible(document.visibilityState === 'visible');
    }

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  function setMessage(section, message) {
    setMessages((prev) => ({ ...prev, [section]: message || '' }));
  }

  function setError(section, message) {
    setErrors((prev) => ({ ...prev, [section]: message || '' }));
  }

  async function loadKbs(preferredKbId) {
    setLoading((prev) => ({ ...prev, kbs: true }));
    setError('kb', '');
    try {
      const payload = await knowledgeAdminApi.listKnowledgeBases();
      const items = Array.isArray(payload && payload.items) ? payload.items : [];
      setKbItems(items);
      const resolvedKbId = preferredKbId || selectedKbId || (items[0] && items[0].kb_id) || '';
      setSelectedKbId(resolvedKbId);
    } catch (error) {
      setError('kb', (error && error.message) || '获取知识库列表失败。');
    } finally {
      setLoading((prev) => ({ ...prev, kbs: false }));
    }
  }

  async function loadKbContext(kbId, preferredDocumentId) {
    if (!kbId) {
      setSelectedKb(null);
      setDocuments([]);
      return;
    }
    setLoading((prev) => ({ ...prev, documents: true }));
    setError('document', '');
    try {
      const [kbPayload, docPayload] = await Promise.all([
        knowledgeAdminApi.getKnowledgeBase(kbId),
        knowledgeAdminApi.listKnowledgeDocuments(kbId),
      ]);
      const docItems = Array.isArray(docPayload && docPayload.items) ? docPayload.items : [];
      setSelectedKb(kbPayload);
      setDocuments(docItems);
      const nextDocumentId = preferredDocumentId || selectedDocumentId || (docItems[0] && docItems[0].document_id) || '';
      setSelectedDocumentId(nextDocumentId);
      setDebugDraft((prev) => ({ ...prev, kb_id: kbPayload.kb_id }));
    } catch (error) {
      setError('document', (error && error.message) || '获取知识库上下文失败。');
    } finally {
      setLoading((prev) => ({ ...prev, documents: false }));
    }
  }

  async function loadVersionContext(versionId) {
    if (!versionId) {
      setVersionDetail(null);
      setJobs([]);
      return;
    }
    setLoading((prev) => ({ ...prev, versions: true, jobs: true }));
    setError('version', '');
    try {
      const [versionPayload, jobsPayload] = await Promise.all([
        knowledgeAdminApi.getKnowledgeVersion(versionId),
        knowledgeAdminApi.listKnowledgeJobs({ version_id: versionId }),
      ]);
      const jobItems = Array.isArray(jobsPayload && jobsPayload.items) ? jobsPayload.items : [];
      setVersionDetail(versionPayload);
      setJobs(jobItems);
      setTrackedJobIds(jobItems.map((item) => item.job_id));
      setDebugDraft((prev) => ({ ...prev, version_id: versionId }));
    } catch (error) {
      setError('version', (error && error.message) || '获取版本上下文失败。');
    } finally {
      setLoading((prev) => ({ ...prev, versions: false, jobs: false }));
    }
  }

  async function loadDocumentContext(documentId, preferredVersionId) {
    if (!documentId) {
      setSelectedDocument(null);
      setVersions([]);
      setSelectedVersionId('');
      setVersionDetail(null);
      setJobs([]);
      return;
    }
    setLoading((prev) => ({ ...prev, versions: true, jobs: true }));
    setError('version', '');
    try {
      const [documentPayload, versionsPayload] = await Promise.all([
        knowledgeAdminApi.getKnowledgeDocument(documentId),
        knowledgeAdminApi.listKnowledgeVersions(documentId),
      ]);
      const versionItems = Array.isArray(versionsPayload && versionsPayload.items) ? versionsPayload.items : [];
      const nextVersionId = preferredVersionId || selectedVersionId || (versionItems[0] && versionItems[0].version_id) || '';
      setSelectedDocument(documentPayload);
      setVersions(versionItems);
      setSelectedVersionId(nextVersionId);
      setDebugDraft((prev) => ({ ...prev, document_id: documentId }));
      if (nextVersionId) {
        await loadVersionContext(nextVersionId);
      } else {
        setVersionDetail(null);
        setJobs([]);
      }
    } catch (error) {
      setError('version', (error && error.message) || '获取文档上下文失败。');
    } finally {
      setLoading((prev) => ({ ...prev, versions: false, jobs: false }));
    }
  }

  React.useEffect(() => {
    if (activeTab === 'knowledge' && canManageProject) {
      loadKbs();
    }
  }, [activeTab, canManageProject]);

  React.useEffect(() => {
    if (!selectedKbId || activeTab !== 'knowledge') return;
    loadKbContext(selectedKbId);
  }, [selectedKbId, activeTab]);

  React.useEffect(() => {
    if (!selectedDocumentId || activeTab !== 'knowledge') return;
    loadDocumentContext(selectedDocumentId);
  }, [selectedDocumentId, activeTab]);

  React.useEffect(() => {
    if (!selectedVersionId || activeTab !== 'knowledge') return;
    loadVersionContext(selectedVersionId);
  }, [selectedVersionId, activeTab]);

  const hasRunningOrPendingJobs = trackedJobIds.some((jobId) => {
    const job = (jobs || []).find((item) => item.job_id === jobId);
    return job && (job.status === 'pending' || job.status === 'running');
  });

  React.useEffect(() => {
    if (!(activeTab === 'knowledge')) return undefined;
    if (!(document.visibilityState === 'visible')) return undefined;
    if (!pageVisible) return undefined;
    if (!hasRunningOrPendingJobs) return undefined;

    const intervalId = window.setInterval(() => {
      if (!trackedJobIds.length) return;
      Promise.all(trackedJobIds.map((jobId) => knowledgeAdminApi.getKnowledgeJob(jobId).catch(() => null))).then((results) => {
        const refreshedJobs = results.filter(Boolean);
        if (refreshedJobs.length) {
          setJobs((prev) => mergeJobsById(prev, refreshedJobs));
        }
      }).catch(() => {});
    }, 5000);

    return () => clearInterval(intervalId);
  }, [activeTab, pageVisible, hasRunningOrPendingJobs, trackedJobIds]);

  async function handleCreateKb() {
    if (!createKbDraft.kb_id.trim() || !createKbDraft.name.trim()) {
      setError('kb', '请先填写 KB ID 和名称。');
      return;
    }
    setSubmitting((prev) => ({ ...prev, kb: true }));
    setError('kb', '');
    try {
      const created = await knowledgeAdminApi.createKnowledgeBase({
        kb_id: createKbDraft.kb_id.trim(),
        name: createKbDraft.name.trim(),
        description: createKbDraft.description.trim() || null,
        domain: 'risk',
      });
      setCreateKbDraft({ kb_id: '', name: '', description: '' });
      setMessage('kb', `已创建知识库：${created.kb_id}`);
      await loadKbs(created.kb_id);
      setActiveKnowledgeSection('documents');
    } catch (error) {
      setError('kb', (error && error.message) || '创建知识库失败。');
    } finally {
      setSubmitting((prev) => ({ ...prev, kb: false }));
    }
  }

  async function handleCreateDocument() {
    if (!selectedKbId) {
      setError('document', '请先选择一个知识库。');
      return;
    }
    if (!createDocumentDraft.title.trim()) {
      setError('document', '请先填写文档标题。');
      return;
    }
    setSubmitting((prev) => ({ ...prev, document: true }));
    setError('document', '');
    try {
      const created = await knowledgeAdminApi.createKnowledgeDocument(selectedKbId, {
        title: createDocumentDraft.title.trim(),
        source_type: createDocumentDraft.source_type.trim() || 'manual',
        source_uri: createDocumentDraft.source_uri.trim() || null,
      });
      setCreateDocumentDraft({ title: '', source_type: 'manual', source_uri: '' });
      setMessage('document', `已创建文档：${created.document_id}`);
      await loadKbContext(selectedKbId, created.document_id);
      setActiveKnowledgeSection('versions');
    } catch (error) {
      setError('document', (error && error.message) || '创建文档失败。');
    } finally {
      setSubmitting((prev) => ({ ...prev, document: false }));
    }
  }

  async function handleUploadVersion() {
    if (!selectedDocumentId) {
      setError('version', '请先选择一个文档。');
      return;
    }
    if (!uploadDraft.file) {
      setError('version', '请先选择上传文件。');
      return;
    }
    let metadataPayload = '';
    const metadataText = String(uploadDraft.metadataText || '').trim();
    if (metadataText) {
      try {
        JSON.parse(metadataText);
        metadataPayload = metadataText;
      } catch (_error) {
        setError('version', 'metadata JSON 格式不正确。');
        return;
      }
    }
    setSubmitting((prev) => ({ ...prev, upload: true }));
    setError('version', '');
    try {
      const uploaded = await knowledgeAdminApi.uploadKnowledgeVersion(selectedDocumentId, {
        file: uploadDraft.file,
        version_label: uploadDraft.version_label.trim() || '',
        auto_index: Boolean(uploadDraft.auto_index),
        metadata: metadataPayload,
      });
      setUploadDraft({ file: null, version_label: '', auto_index: true, metadataText: '' });
      setMessage('version', `已上传版本：${uploaded.version_id}`);
      await loadDocumentContext(selectedDocumentId, uploaded.version_id);
      if (uploaded.indexing_job_id) {
        setTrackedJobIds((prev) => Array.from(new Set(prev.concat([uploaded.indexing_job_id]))));
      }
    } catch (error) {
      setError('version', (error && error.message) || '上传版本失败。');
    } finally {
      setSubmitting((prev) => ({ ...prev, upload: false }));
    }
  }

  function registerJobResponse(response, successLabel) {
    if (response && response.job_id) {
      setTrackedJobIds((prev) => Array.from(new Set(prev.concat([response.job_id]))));
    }
    setMessage('version', successLabel || '操作已接受。');
    if (selectedVersionId) loadVersionContext(selectedVersionId);
  }

  async function handleIndex() {
    if (!selectedVersionId) {
      setError('version', '请先选择一个版本。');
      return;
    }
    setError('version', '');
    try {
      const response = await knowledgeAdminApi.indexKnowledgeVersion(selectedVersionId);
      registerJobResponse(response, `Index result: ${response.result}`);
    } catch (error) {
      setError('version', (error && error.message) || '触发索引失败。');
    }
  }

  async function handleRebuild() {
    if (!selectedVersionId) {
      setError('version', '请先选择一个版本。');
      return;
    }
    if (!window.confirm('确认 rebuild 当前版本吗？这会重新触发解析与索引流程。')) return;
    setError('version', '');
    try {
      const response = await knowledgeAdminApi.rebuildKnowledgeVersion(selectedVersionId);
      registerJobResponse(response, `Rebuild result: ${response.result}`);
    } catch (error) {
      setError('version', (error && error.message) || '触发重建失败。');
    }
  }

  async function handleActivate() {
    if (!selectedVersionId || !versionDetail) {
      setError('version', '请先选择一个版本。');
      return;
    }
    if (!window.confirm('确认激活当前版本的 latest manifest 吗？')) return;
    const manifestIndexId = versionDetail.latest_manifest_index_id || versionDetail.active_manifest_index_id || null;
    if (!manifestIndexId) {
      setError('version', '当前版本没有可激活的 manifest。');
      return;
    }
    setError('version', '');
    try {
      const response = await knowledgeAdminApi.activateKnowledgeVersion(selectedVersionId, { manifest_index_id: manifestIndexId });
      setMessage('version', `Activate result: ${response.result}`);
      await loadVersionContext(selectedVersionId);
    } catch (error) {
      setError('version', (error && error.message) || '激活版本失败。');
    }
  }

  async function handleRetryJob(jobId) {
    if (!jobId) return;
    if (!window.confirm('确认 retry 这个 failed job 吗？')) return;
    setError('version', '');
    try {
      const response = await knowledgeAdminApi.retryKnowledgeJob(jobId);
      registerJobResponse(response, `Retry result: ${response.result}`);
    } catch (error) {
      setError('version', (error && error.message) || '重试任务失败。');
    }
  }

  async function handleRefreshVersionJobs() {
    setMessage('version', '');
    if (selectedVersionId) return await loadVersionContext(selectedVersionId);
    if (selectedDocumentId) return await loadDocumentContext(selectedDocumentId);
    if (selectedKbId) return await loadKbContext(selectedKbId);
    return await loadKbs();
  }

  async function handleDebugRetrieve() {
    const resolvedKbId = String(debugDraft.kb_id || selectedKbId || '').trim();
    const resolvedQuery = String(debugDraft.query || '').trim();
    if (!resolvedKbId) {
      setError('debug', '请先提供 kb_id。');
      return;
    }
    if (!resolvedQuery) {
      setError('debug', '请先输入检索 query。');
      return;
    }
    setLoading((prev) => ({ ...prev, debug: true }));
    setError('debug', '');
    try {
      const result = await knowledgeAdminApi.debugKnowledgeRetrieve({
        kb_id: resolvedKbId,
        query: resolvedQuery,
        document_id: String(debugDraft.document_id || '').trim() || undefined,
        version_id: String(debugDraft.version_id || '').trim() || undefined,
        top_k: Math.min(50, Math.max(1, Number(debugDraft.top_k) || 10)),
      });
      setDebugResult(result);
      setMessage('debug', 'retrieval-only debug 已更新。');
    } catch (error) {
      setError('debug', (error && error.message) || '检索调试失败。');
    } finally {
      setLoading((prev) => ({ ...prev, debug: false }));
    }
  }

  if (!canManageProject) {
    return (
      <div className="rounded-3xl border border-amber-200 bg-amber-50 px-6 py-8 text-sm text-amber-800">
        当前账号没有 project:manage 权限，Knowledge Base Console 不可用。
      </div>
    );
  }

  const sectionButtonClass = (sectionId) => (
    activeKnowledgeSection === sectionId
      ? 'border-blue-600 bg-blue-600 text-white'
      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
  );

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-slate-200 bg-gradient-to-r from-sky-50 to-cyan-50 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-600">M2D-14B</div>
            <h3 className="mt-1 text-xl font-semibold text-slate-900">Knowledge Base UI Console</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              基于 M2D-14A Admin API 的最小前端控制台，支持 KB 管理、版本上传、index / rebuild / retry / activate 和 retrieval-only debug。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => setActiveKnowledgeSection('kbs')} className={`rounded-2xl border px-4 py-2 text-sm font-semibold transition ${sectionButtonClass('kbs')}`}>Knowledge Bases</button>
            <button type="button" onClick={() => setActiveKnowledgeSection('documents')} className={`rounded-2xl border px-4 py-2 text-sm font-semibold transition ${sectionButtonClass('documents')}`}>Documents</button>
            <button type="button" onClick={() => setActiveKnowledgeSection('versions')} className={`rounded-2xl border px-4 py-2 text-sm font-semibold transition ${sectionButtonClass('versions')}`}>Versions & Jobs</button>
            <button type="button" onClick={() => setActiveKnowledgeSection('debug')} className={`rounded-2xl border px-4 py-2 text-sm font-semibold transition ${sectionButtonClass('debug')}`}>Retrieval Debug</button>
          </div>
        </div>
      </div>

      {(messages.kb || messages.document || messages.version || messages.debug) ? (
        <div className="rounded-3xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-800">
          {messages.kb || messages.document || messages.version || messages.debug}
        </div>
      ) : null}

      <KnowledgeBaseListPanel
        items={kbItems}
        selectedKbId={selectedKbId}
        createDraft={createKbDraft}
        onDraftChange={setCreateKbDraft}
        onCreate={handleCreateKb}
        onSelect={(kbId) => {
          setSelectedKbId(kbId);
          setSelectedDocumentId('');
          setSelectedVersionId('');
          setActiveKnowledgeSection('documents');
        }}
        loading={loading.kbs}
        creating={submitting.kb}
        errorMessage={errors.kb}
      />

      {(activeKnowledgeSection === 'documents' || activeKnowledgeSection === 'versions' || activeKnowledgeSection === 'debug') ? (
        <KnowledgeDocumentPanel
          selectedKb={selectedKb}
          documents={documents}
          selectedDocumentId={selectedDocumentId}
          draft={createDocumentDraft}
          onDraftChange={setCreateDocumentDraft}
          onCreate={handleCreateDocument}
          onSelectDocument={(documentId) => {
            setSelectedDocumentId(documentId);
            setSelectedVersionId('');
            setActiveKnowledgeSection('versions');
          }}
          loading={loading.documents}
          creating={submitting.document}
          errorMessage={errors.document}
        />
      ) : null}

      {(activeKnowledgeSection === 'versions' || activeKnowledgeSection === 'debug') ? (
        <KnowledgeVersionJobsPanel
          selectedDocument={selectedDocument}
          versions={versions}
          selectedVersionId={selectedVersionId}
          versionDetail={versionDetail}
          jobs={jobs}
          uploadDraft={uploadDraft}
          onUploadDraftChange={setUploadDraft}
          onUpload={handleUploadVersion}
          onSelectVersion={(versionId) => {
            setSelectedVersionId(versionId);
            setActiveKnowledgeSection('versions');
          }}
          onIndex={handleIndex}
          onRebuild={handleRebuild}
          onActivate={handleActivate}
          onRetryJob={handleRetryJob}
          onRefresh={handleRefreshVersionJobs}
          loading={loading.versions || loading.jobs}
          submitting={submitting.upload}
          actionMessage={messages.version}
          errorMessage={errors.version}
        />
      ) : null}

      {activeKnowledgeSection === 'debug' ? (
        <KnowledgeRetrievalDebugPanel
          kbId={selectedKbId}
          documentId={selectedDocumentId}
          versionId={selectedVersionId}
          draft={debugDraft}
          onDraftChange={setDebugDraft}
          onSubmit={handleDebugRetrieve}
          result={debugResult}
          loading={loading.debug}
          errorMessage={errors.debug}
        />
      ) : null}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.KnowledgeBaseConsole = KnowledgeBaseConsole;
