import io

import httpx
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from openai import APIStatusError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from qdrant_client import QdrantClient

from app.chunking import DocumentChunk
from app.config import PROJECT_ROOT, Settings
from app.qdrant_store import QdrantStore
from app.uploads import extract_document


class MemoryS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": StreamingBody(io.BytesIO(self.objects[Key]), len(self.objects[Key]))}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = Body
        return {}

    def list_objects_v2(self, Bucket, Prefix, **kwargs):
        return {"Contents": [{"Key": key} for key in self.objects if key.startswith(Prefix)]}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)
        return {}


@pytest.fixture
def upload_app(monkeypatch):
    import app.main as main
    import app.uploads as uploads
    import app.workspaces as workspaces

    settings = Settings(
        _env_file=None,
        openai_api_key=None,
        auto_ingest_on_startup=False,
        r2_endpoint="https://example.r2.cloudflarestorage.com",
        r2_bucket="test",
        r2_access_key_id="test",
        r2_secret_access_key="test",
        max_upload_bytes=2048,
    )
    storage = MemoryS3()
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(workspaces, "get_settings", lambda: settings)
    monkeypatch.setattr(uploads.boto3, "client", lambda *args, **kwargs: storage)
    return main.app, settings, storage


def test_upload_saves_original_when_indexing_is_unavailable_and_isolates_browsers(
    upload_app, authenticated_client
):
    app, _, storage = upload_app
    content = b"# Staff drill\n\nThe emergency drill starts at 9 AM every Thursday."
    with authenticated_client(app) as owner, authenticated_client(app) as stranger:
        library = owner.get("/api/documents")
        assert "sentral_workspace" not in library.headers.get("set-cookie", "")
        assert library.json()["documents"] == []
        result = owner.post(
            "/api/documents", files={"file": ("drill.md", content, "text/markdown")}
        )
        assert result.status_code == 201
        document = result.json()
        assert document["status"] == "saved"
        assert document["indexing_error"]
        assert len(storage.objects) == 3
        assert content in storage.objects.values()
        assert owner.get("/api/documents").json()["documents"][0]["id"] == document["id"]
        response = owner.get(f"/api/documents/{document['id']}/download")
        assert response.content == content
        assert response.headers["cache-control"] == "private, no-store"
        assert stranger.get("/api/documents").json()["documents"] == []
        for method, suffix in [("get", "download"), ("post", "index")]:
            assert (
                getattr(stranger, method)(f"/api/documents/{document['id']}/{suffix}").status_code
                == 404
            )
        assert stranger.delete(f"/api/documents/{document['id']}").status_code == 404
        assert (
            owner.post(
                "/api/documents",
                headers={"Origin": "https://another-site.example"},
                files={"file": ("drill.md", content)},
            ).status_code
            == 403
        )


def test_retry_indexes_saved_file_without_duplicate_vectors(
    upload_app, monkeypatch, authenticated_client
):
    import app.uploads as uploads

    app, settings, storage = upload_app
    vectors = QdrantStore.__new__(QdrantStore)
    vectors.settings = settings
    vectors.client = QdrantClient(":memory:")
    monkeypatch.setattr(uploads, "QdrantStore", lambda settings: vectors)
    with authenticated_client(app) as browser:
        doc = browser.post(
            "/api/documents",
            files={"file": ("policy.md", b"# Policy\n\nRefunds require a receipt.")},
        ).json()
        assert doc["status"] == "saved"

        class AvailableEmbeddings:
            def __init__(self, settings):
                pass

            def embed_texts(self, texts):
                return [[1.0] + [0.0] * 1535 for _ in texts]

        monkeypatch.setattr(uploads, "OpenAIClient", AvailableEmbeddings)
        indexed = browser.post(f"/api/documents/{doc['id']}/index").json()
        assert indexed["status"] == "indexed"
        assert indexed["chunks"] == 1
        assert indexed["indexing_error"] is None
        again = browser.post(
            "/api/documents",
            files={"file": ("policy.md", b"# Policy\n\nRefunds require a receipt.")},
        ).json()
        assert again["id"] == doc["id"]
        assert vectors.client.count(settings.qdrant_collection).count == 1
        assert browser.delete(f"/api/documents/{doc['id']}").status_code == 204
        assert vectors.client.count(settings.qdrant_collection).count == 0
        assert not storage.objects


@pytest.mark.parametrize(
    "status,code,expected_action",
    [
        (401, "invalid_api_key", "API key was rejected"),
        (429, "insufficient_quota", "credits and limits"),
        (402, 402, "credits and limits"),
    ],
)
def test_provider_error_keeps_upload_safe_and_retry_recovers(
    upload_app, monkeypatch, caplog, status, code, expected_action, authenticated_client
):
    import app.main as main
    import app.uploads as uploads

    app, settings, _ = upload_app
    vectors = QdrantStore.__new__(QdrantStore)
    vectors.settings = settings
    vectors.client = QdrantClient(":memory:")
    monkeypatch.setattr(uploads, "QdrantStore", lambda settings: vectors)
    secret = "sk-private-value-must-never-appear"
    error = APIStatusError(
        "Rejected credential " + secret,
        response=httpx.Response(
            status, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        ),
        body={"code": code, "message": "Rejected credential " + secret},
    )

    class Embeddings:
        failing = True

        def __init__(self, settings):
            pass

        def embed_texts(self, texts):
            if self.failing:
                raise error
            return [[1.0] + [0.0] * 1535 for _ in texts]

    class AnswerAssistant:
        def __init__(self, *args, **kwargs):
            pass

        def ask(self, *args):
            raise error

    monkeypatch.setattr(uploads, "OpenAIClient", Embeddings)
    monkeypatch.setattr(main, "RagAssistant", AnswerAssistant)
    content = b"# Visitor policy\n\nVisitors must sign in at reception."
    with authenticated_client(app) as browser:
        response = browser.post("/api/documents", files={"file": ("visitors.md", content)})
        assert response.status_code == 201
        doc = response.json()
        assert doc["status"] == "saved"
        assert expected_action in doc["indexing_error"]
        assert secret not in response.text
        assert secret not in caplog.text
        assert browser.get(f"/api/documents/{doc['id']}/download").content == content
        failed_answer = browser.post("/api/ask", json={"question": "How do visitors sign in?"})
        assert failed_answer.status_code == 503
        assert expected_action in failed_answer.json()["detail"]
        assert secret not in failed_answer.text
        assert secret not in caplog.text
        Embeddings.failing = False
        recovered = browser.post(f"/api/documents/{doc['id']}/index").json()
        assert recovered["status"] == "indexed"
        assert recovered["indexing_error"] is None
        assert recovered["chunks"] == 1
        assert vectors.client.count(settings.qdrant_collection).count == 1


@pytest.mark.parametrize(
    "filename,content",
    [
        ("bad.txt", b"text"),
        ("fake.pdf", b"not a PDF"),
        ("binary.md", b"\0data"),
        ("empty.md", b"  "),
        ("encoding.md", b"\xff\xfe"),
    ],
)
def test_invalid_files_are_rejected_before_storage(
    upload_app, filename, content, authenticated_client
):
    app, _, storage = upload_app
    with authenticated_client(app) as browser:
        response = browser.post("/api/documents", files={"file": (filename, content)})
        assert response.status_code == 422
        assert not storage.objects


def test_upload_size_limit_is_enforced_before_storage(upload_app, authenticated_client):
    app, _, storage = upload_app
    with authenticated_client(app) as browser:
        response = browser.post("/api/documents", files={"file": ("large.md", b"x" * 2049)})
        assert response.status_code == 413
        assert not storage.objects


def test_pdf_text_extraction_and_password_protection():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 30 150 Td (The emergency drill starts at 9 AM.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    text, pages = extract_document("drill.PDF", output.getvalue())
    assert "starts at 9 AM" in text
    assert pages == 1
    writer.encrypt("secret")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    with pytest.raises(ValueError, match="password protected"):
        extract_document("locked.pdf", encrypted.getvalue())


@pytest.mark.parametrize(
    "filename",
    [
        "01-visitor-registration.pdf",
        "02-it-equipment-loans.pdf",
        "03-warehouse-cycle-counts.pdf",
        "04-meeting-room-bookings.pdf",
    ],
)
def test_sample_pdf_extracts_outside_backend_directory(filename, tmp_path, monkeypatch):
    content = (PROJECT_ROOT / "sample-uploads" / filename).read_bytes()
    monkeypatch.chdir(tmp_path)

    text, pages = extract_document(filename, content)

    assert pages == 1
    assert len(text) > 100
    assert "Sentral Ops" in text


def test_vector_search_never_returns_another_workspaces_uploads():
    settings = Settings(_env_file=None, openai_embedding_dimensions=3)
    store = QdrantStore.__new__(QdrantStore)
    store.settings = settings
    store.client = QdrantClient(":memory:")
    store.ensure_collection()
    public = DocumentChunk("demo-1", "demo", "Demo", "Shared SOP")
    private = DocumentChunk("upload-shared-1", "upload-shared", "Private", "Private SOP")
    store.upsert_chunks([public], [[1.0, 0.0, 0.0]])
    store.upsert_chunks([private], [[1.0, 0.0, 0.0]], workspace_id="a" * 64)
    store.upsert_chunks([private], [[0.0, 1.0, 0.0]], workspace_id="b" * 64)
    assert store.client.count(settings.qdrant_collection).count == 3
    assert store.count() == 1
    assert [source.document_id for source in store.search([1.0, 0.0, 0.0], 8)] == ["demo"]
    assert len(store.search([1.0, 0.0, 0.0], 8, "a" * 64)) == 2
    store.delete_document("upload-shared", "a" * 64)
    assert len(store.search([1.0, 0.0, 0.0], 8, "a" * 64)) == 1
    assert len(store.search([0.0, 1.0, 0.0], 8, "b" * 64)) == 2
