"""API contract tests (SPEC 1.3/1.9): all offline, OCR mocked."""

import io
import json
import zipfile

from app.core.config import settings
from app.core.rate_limit import limiter
from tests.conftest import make_pdf

API = "/api/v1"


def _process(client, sample_png, mask_type="blackbox", filename="doc.png"):
    return client.post(
        f"{API}/process",
        files={"file": (filename, sample_png, "image/png")},
        data={"mask_type": mask_type, "confidence_threshold": "0.0"},
    )


# -- health --------------------------------------------------------------------

def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["ollama"], bool) and isinstance(body["spacy"], bool)
    assert body["version"]


# -- process ---------------------------------------------------------------------

def test_process_returns_full_response(client, sample_png):
    r = _process(client, sample_png)
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"]
    assert body["pii_count"] == 2  # email + phone from fake OCR regions
    assert {d["pii_type"] for d in body["detections"]} == {"email", "phone"}
    assert body["masked_image_base64"]
    assert body["original_image_base64"]
    assert body["masked_image_base64"] != body["original_image_base64"]
    assert body["processing_time_ms"] > 0
    for det in body["detections"]:
        assert det["id"] and det["source"] == "regex"
        assert det["bounding_box"] is not None


def test_process_rejects_non_image(client):
    r = client.post(f"{API}/process",
                    files={"file": ("x.png", b"definitely not an image", "image/png")},
                    data={"mask_type": "blur"})
    assert r.status_code == 415
    assert "detail" in r.json()


def test_process_rejects_oversize(client, sample_png, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 16)
    r = _process(client, sample_png)
    assert r.status_code == 413


def test_process_generic_error_on_bad_png(client):
    # PNG magic bytes but corrupt payload -> generic 400, no internals leaked
    r = client.post(f"{API}/process",
                    files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"junk" * 10,
                                    "image/png")},
                    data={"mask_type": "blur"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Corrupt or unreadable image file"


# -- remask / download -------------------------------------------------------------

def test_remask_with_exclusions(client, sample_png):
    job = _process(client, sample_png).json()
    excluded = [d["id"] for d in job["detections"]]
    r = client.post(f"{API}/jobs/{job['job_id']}/remask",
                    json={"mask_type": "blur", "excluded_detection_ids": excluded,
                          "confidence_threshold": 0.0})
    assert r.status_code == 200
    body = r.json()
    assert body["pii_count"] == 0
    assert body["masked_image_base64"] == body["original_image_base64"]


def test_remask_partial_exclusion(client, sample_png):
    job = _process(client, sample_png).json()
    keep = job["detections"][0]["id"]
    r = client.post(f"{API}/jobs/{job['job_id']}/remask",
                    json={"mask_type": "blackbox", "excluded_detection_ids": [keep]})
    assert r.status_code == 200
    assert r.json()["pii_count"] == len(job["detections"]) - 1


def test_remask_404(client):
    r = client.post(f"{API}/jobs/doesnotexist/remask",
                    json={"mask_type": "blur"})
    assert r.status_code == 404


def test_download_masked_png(client, sample_png):
    job = _process(client, sample_png).json()
    r = client.get(f"{API}/jobs/{job['job_id']}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_download_404(client):
    assert client.get(f"{API}/jobs/nope/download").status_code == 404


# -- batch ---------------------------------------------------------------------------

def test_batch_lifecycle_and_zip(client, sample_png):
    r = client.post(
        f"{API}/batch",
        files=[("files", ("a.png", sample_png, "image/png")),
               ("files", ("b.png", sample_png, "image/png"))],
        data={"mask_type": "blackbox"},
    )
    assert r.status_code == 200
    batch = r.json()
    assert batch["status"] == "queued" and batch["total_files"] == 2

    # TestClient runs BackgroundTasks synchronously before returning, so the
    # batch is completed by now — verify the real lifecycle persisted in DB.
    s = client.get(f"{API}/batch/{batch['batch_id']}")
    assert s.status_code == 200
    status = s.json()
    assert status["status"] == "completed"
    assert status["processed"] == 2 and status["failed"] == 0
    assert len(status["items"]) == 2
    assert all(i["pii_count"] == 2 for i in status["items"])

    z = client.get(f"{API}/batch/{batch['batch_id']}/download")
    assert z.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    assert len(zf.namelist()) == 2


def test_batch_marks_bad_file_failed(client, sample_png):
    r = client.post(
        f"{API}/batch",
        files=[("files", ("ok.png", sample_png, "image/png")),
               ("files", ("bad.png", b"junk", "image/png"))],
        data={"mask_type": "blur"},
    )
    batch_id = r.json()["batch_id"]
    status = client.get(f"{API}/batch/{batch_id}").json()
    assert status["processed"] == 1 and status["failed"] == 1
    failed_item = [i for i in status["items"] if i["status"] == "failed"][0]
    assert failed_item["error"]


def test_batch_max_files_413(client, sample_png):
    files = [("files", (f"f{i}.png", sample_png, "image/png")) for i in range(21)]
    r = client.post(f"{API}/batch", files=files, data={"mask_type": "blur"})
    assert r.status_code == 413


def test_batch_unknown_404(client):
    assert client.get(f"{API}/batch/nope").status_code == 404
    assert client.get(f"{API}/batch/nope/download").status_code == 404


# -- pdf -------------------------------------------------------------------------------

def test_pdf_processing(client, tiny_pdf):
    r = client.post(f"{API}/pdf",
                    files={"file": ("doc.pdf", tiny_pdf, "application/pdf")},
                    data={"mask_type": "blackbox"})
    assert r.status_code == 200
    body = r.json()
    assert body["total_pages"] == 1 and body["processed_pages"] == 1
    assert body["job_id"]
    assert body["total_pii_found"] == 2
    assert body["processing_time_ms"] > 0  # measured, not hardcoded 0.0
    page = body["pages"][0]
    assert page["page_number"] == 1
    assert page["masked_image_base64"] != page["original_image_base64"]


def test_pdf_rejects_non_pdf(client, sample_png):
    r = client.post(f"{API}/pdf",
                    files={"file": ("doc.pdf", sample_png, "application/pdf")},
                    data={"mask_type": "blur"})
    assert r.status_code == 415


def test_pdf_page_cap_413(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_PDF_PAGES", 1)
    r = client.post(f"{API}/pdf",
                    files={"file": ("big.pdf", make_pdf(3), "application/pdf")},
                    data={"mask_type": "blur"})
    assert r.status_code == 413


def test_pdf_corrupt_generic_error(client):
    r = client.post(f"{API}/pdf",
                    files={"file": ("x.pdf", b"%PDF-corruptjunk", "application/pdf")},
                    data={"mask_type": "blur"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid or corrupt PDF file"


# -- history ------------------------------------------------------------------------------

def test_history_list_and_delete(client, sample_png):
    job = _process(client, sample_png).json()
    r = client.get(f"{API}/history")
    assert r.status_code == 200
    items = r.json()
    assert any(i["job_id"] == job["job_id"] for i in items)
    item = [i for i in items if i["job_id"] == job["job_id"]][0]
    assert item["kind"] == "image" and item["pii_count"] == 2
    assert item["created_at"]

    assert client.delete(f"{API}/history/{job['job_id']}").status_code == 200
    assert client.get(f"{API}/jobs/{job['job_id']}/download").status_code == 404
    assert client.delete(f"{API}/history/{job['job_id']}").status_code == 404


# -- security ----------------------------------------------------------------------------

def test_api_key_enforcement(client, sample_png, monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "topsecret")
    assert _process(client, sample_png).status_code == 401
    r = client.post(
        f"{API}/process",
        files={"file": ("doc.png", sample_png, "image/png")},
        data={"mask_type": "blur"},
        headers={"X-API-Key": "topsecret"},
    )
    assert r.status_code == 200
    # health stays open
    assert client.get(f"{API}/health").status_code == 200
    assert client.get(f"{API}/history").status_code == 401


def test_rate_limit_429(client):
    limiter.enabled = True
    try:
        codes = [client.post(f"{API}/jobs/x/remask", json={"mask_type": "blur"}).status_code
                 for _ in range(31)]
        assert 429 in codes
    finally:
        limiter.enabled = False
