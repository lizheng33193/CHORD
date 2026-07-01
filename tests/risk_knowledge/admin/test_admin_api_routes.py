from __future__ import annotations


def test_kb_admin_routes_support_create_list_and_detail(admin_client) -> None:
    create = admin_client.post(
        "/api/risk-knowledge/admin/kbs",
        json={
            "kb_id": "risk_domain_knowledge",
            "name": "风控领域知识库",
            "description": "用于画像解释的风控知识资料",
            "domain": "risk",
        },
    )
    assert create.status_code == 201
    created = create.json()
    assert created["kb_id"] == "risk_domain_knowledge"
    assert created["name"] == "风控领域知识库"
    assert created["status"] == "active"
    assert created["document_count"] == 0
    assert created["active_document_count"] == 0

    listing = admin_client.get("/api/risk-knowledge/admin/kbs")
    assert listing.status_code == 200
    listed = listing.json()
    assert listed["items"] == [created]
    assert listed["total"] == 1

    detail = admin_client.get("/api/risk-knowledge/admin/kbs/risk_domain_knowledge")
    assert detail.status_code == 200
    assert detail.json() == created


def test_kb_admin_create_rejects_duplicates(admin_client) -> None:
    body = {
        "kb_id": "risk_domain_knowledge",
        "name": "风控领域知识库",
        "description": "用于画像解释的风控知识资料",
        "domain": "risk",
    }

    assert admin_client.post("/api/risk-knowledge/admin/kbs", json=body).status_code == 201

    duplicate = admin_client.post("/api/risk-knowledge/admin/kbs", json=body)
    assert duplicate.status_code == 409
    detail = duplicate.json()["detail"]
    assert detail["code"] == "KNOWLEDGE_BASE_ALREADY_EXISTS"
    assert detail["resource_id"] == "risk_domain_knowledge"


def test_document_admin_routes_support_create_list_and_upload(admin_client, tmp_path, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt")

    create_kb = admin_client.post(
        "/api/risk-knowledge/admin/kbs",
        json={
            "kb_id": "risk_domain_knowledge",
            "name": "风控领域知识库",
            "description": "用于画像解释的风控知识资料",
            "domain": "risk",
        },
    )
    assert create_kb.status_code == 201

    create_document = admin_client.post(
        "/api/risk-knowledge/admin/kbs/risk_domain_knowledge/documents",
        json={
            "title": "智能风控指南",
            "source_type": "manual",
            "source_uri": None,
            "metadata": {"language": "zh"},
        },
    )
    assert create_document.status_code == 201
    document = create_document.json()
    assert document["kb_id"] == "risk_domain_knowledge"
    assert document["title"] == "智能风控指南"
    assert document["version_count"] == 0
    assert document["active_version_id"] is None

    list_documents = admin_client.get("/api/risk-knowledge/admin/kbs/risk_domain_knowledge/documents")
    assert list_documents.status_code == 200
    assert list_documents.json()["items"] == [document]

    upload = admin_client.post(
        f"/api/risk-knowledge/admin/documents/{document['document_id']}/versions:upload",
        files={"file": ("risk-guide.txt", b"risk knowledge body", "text/plain")},
        data={"version_label": "v1", "auto_index": "false"},
    )
    assert upload.status_code == 201
    uploaded = upload.json()
    assert uploaded["document_id"] == document["document_id"]
    assert uploaded["filename"] == "risk-guide.txt"
    assert uploaded["file_size_bytes"] == len(b"risk knowledge body")
    assert uploaded["indexing_job_id"] is None


def test_document_admin_detail_and_versions_reflect_uploaded_version(admin_client, tmp_path, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt")

    admin_client.post(
        "/api/risk-knowledge/admin/kbs",
        json={
            "kb_id": "risk_domain_knowledge",
            "name": "风控领域知识库",
            "description": "用于画像解释的风控知识资料",
            "domain": "risk",
        },
    )
    document = admin_client.post(
        "/api/risk-knowledge/admin/kbs/risk_domain_knowledge/documents",
        json={
            "title": "智能风控指南",
            "source_type": "manual",
            "source_uri": None,
            "metadata": {"language": "zh"},
        },
    ).json()
    uploaded = admin_client.post(
        f"/api/risk-knowledge/admin/documents/{document['document_id']}/versions:upload",
        files={"file": ("risk-guide.txt", b"risk knowledge body", "text/plain")},
        data={"version_label": "v1", "auto_index": "false"},
    ).json()

    document_detail = admin_client.get(
        f"/api/risk-knowledge/admin/documents/{document['document_id']}"
    )
    assert document_detail.status_code == 200
    detail = document_detail.json()
    assert detail["document_id"] == document["document_id"]
    assert detail["version_count"] == 1
    assert detail["active_version_id"] is None

    versions = admin_client.get(
        f"/api/risk-knowledge/admin/documents/{document['document_id']}/versions"
    )
    assert versions.status_code == 200
    version_items = versions.json()["items"]
    assert len(version_items) == 1
    assert version_items[0]["version_id"] == uploaded["version_id"]

    version_detail = admin_client.get(
        f"/api/risk-knowledge/admin/versions/{uploaded['version_id']}"
    )
    assert version_detail.status_code == 200
    assert version_detail.json()["version_id"] == uploaded["version_id"]


def test_indexing_admin_routes_cover_job_endpoints(admin_client, tmp_path, monkeypatch, fake_redis_client) -> None:
    from app.api import risk_knowledge_admin
    from app.core.config import settings
    from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService

    monkeypatch.setattr(settings, "risk_knowledge_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "risk_knowledge_max_upload_mb", 1)
    monkeypatch.setattr(settings, "risk_knowledge_allowed_upload_extensions", "pdf,docx,md,txt")
    monkeypatch.setattr(
        risk_knowledge_admin,
        "_indexing_service",
        lambda db: IndexingAdminService(db, redis_client=fake_redis_client, job_launcher=lambda task: None),
    )

    admin_client.post(
        "/api/risk-knowledge/admin/kbs",
        json={
            "kb_id": "risk_domain_knowledge",
            "name": "风控领域知识库",
            "description": "用于画像解释的风控知识资料",
            "domain": "risk",
        },
    )
    document = admin_client.post(
        "/api/risk-knowledge/admin/kbs/risk_domain_knowledge/documents",
        json={
            "title": "智能风控指南",
            "source_type": "manual",
            "source_uri": None,
            "metadata": {},
        },
    ).json()
    uploaded = admin_client.post(
        f"/api/risk-knowledge/admin/documents/{document['document_id']}/versions:upload",
        files={"file": ("risk-guide.txt", b"risk knowledge body", "text/plain")},
        data={"version_label": "v1", "auto_index": "false"},
    ).json()

    launched = admin_client.post(
        f"/api/risk-knowledge/admin/versions/{uploaded['version_id']}:index"
    )
    assert launched.status_code == 200
    launched_body = launched.json()
    assert launched_body["result"] == "accepted"
    assert launched_body["job_id"]

    job_detail = admin_client.get(
        f"/api/risk-knowledge/admin/indexing-jobs/{launched_body['job_id']}"
    )
    assert job_detail.status_code == 200
    assert job_detail.json()["job_id"] == launched_body["job_id"]

    job_list = admin_client.get(
        f"/api/risk-knowledge/admin/indexing-jobs?version_id={uploaded['version_id']}"
    )
    assert job_list.status_code == 200
    assert job_list.json()["total"] == 1


def test_debug_retrieve_route_returns_retrieval_only_payload(admin_client, monkeypatch) -> None:
    from app.api import risk_knowledge_admin
    from app.risk_knowledge.admin.schemas import (
        DebugRetrieveCandidateResponse,
        DebugRetrieveCandidateScoresResponse,
        DebugRetrieveDiagnosticsResponse,
        DebugRetrieveResponse,
        DebugRetrieveScopeResponse,
    )

    class StubDebugService:
        def debug_retrieve(self, _request):
            return DebugRetrieveResponse(
                query="loan risk",
                kb_id="risk_domain_knowledge",
                scope=DebugRetrieveScopeResponse(
                    scope_type="kb_active_documents",
                    active_manifest_index_ids=["idx_manifest_active"],
                ),
                candidates=[
                    DebugRetrieveCandidateResponse(
                        rank=1,
                        document_id="risk_guide",
                        version_id="risk_guide_v1",
                        chunk_id="risk_guide_v1_chunk_000001",
                        manifest_index_id="idx_manifest_active",
                        section_path="贷前风控 / 多头借贷",
                        page_start=1,
                        page_end=1,
                        content_hash="sha256:chunk",
                        text_preview="preview",
                        scores=DebugRetrieveCandidateScoresResponse(
                            vector_score=0.9,
                            bm25_score=1.5,
                            rrf_score=0.03,
                        ),
                    )
                ],
                diagnostics=DebugRetrieveDiagnosticsResponse(
                    candidate_count=1,
                    fusion_method="rrf",
                    latency_ms=12,
                    vector_hit_count=1,
                    keyword_hit_count=1,
                    fused_hit_count=1,
                ),
            )

    monkeypatch.setattr(risk_knowledge_admin, "_retrieval_debug_service", lambda _db: StubDebugService())

    response = admin_client.post(
        "/api/risk-knowledge/admin/debug/retrieve",
        json={
            "kb_id": "risk_domain_knowledge",
            "query": "loan risk",
            "top_k": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scope"]["scope_type"] == "kb_active_documents"
    assert body["candidates"][0]["text_preview"] == "preview"
    assert "answer" not in body
    assert "citations" not in body


def test_indexing_admin_routes_cover_rebuild_activate_and_retry(admin_client, monkeypatch) -> None:
    from app.api import risk_knowledge_admin
    from app.risk_knowledge.admin.schemas import (
        IndexingJobLaunchResponse,
        VersionActivateResponse,
    )

    class StubIndexingService:
        def start_rebuild(self, version_id: str) -> IndexingJobLaunchResponse:
            assert version_id == "ver_1"
            return IndexingJobLaunchResponse(
                result="accepted",
                job_id="idxjob_rebuild",
                version_id=version_id,
                status="pending",
                trigger="rebuild_from_parsed",
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )

        def activate_version(self, version_id: str, *, manifest_index_id: str | None = None) -> VersionActivateResponse:
            assert version_id == "ver_1"
            assert manifest_index_id == "idx_manifest_1"
            return VersionActivateResponse(
                result="activated",
                version_id=version_id,
                document_id="doc_1",
                manifest_index_id="idx_manifest_1",
                status="active",
            )

        def retry_job(self, job_id: str) -> IndexingJobLaunchResponse:
            assert job_id == "idxjob_failed"
            return IndexingJobLaunchResponse(
                result="accepted",
                job_id="idxjob_retry",
                version_id="ver_1",
                status="pending",
                trigger="retry",
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )

    monkeypatch.setattr(risk_knowledge_admin, "_indexing_service", lambda _db: StubIndexingService())

    rebuild = admin_client.post("/api/risk-knowledge/admin/versions/ver_1:rebuild")
    assert rebuild.status_code == 200
    assert rebuild.json()["job_id"] == "idxjob_rebuild"

    activate = admin_client.post(
        "/api/risk-knowledge/admin/versions/ver_1:activate",
        json={"manifest_index_id": "idx_manifest_1"},
    )
    assert activate.status_code == 200
    assert activate.json()["result"] == "activated"

    retry = admin_client.post("/api/risk-knowledge/admin/indexing-jobs/idxjob_failed:retry")
    assert retry.status_code == 200
    assert retry.json()["job_id"] == "idxjob_retry"
