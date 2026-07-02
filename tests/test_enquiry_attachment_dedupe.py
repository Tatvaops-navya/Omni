"""Attachment dedupe for admin enquiry display."""
from __future__ import annotations

from types import SimpleNamespace

from backend.storage import supabase_store as store


def _session(**kwargs):
    return SimpleNamespace(
        session_id="sess-1",
        attachments=kwargs.get("attachments", []),
        **{k: v for k, v in kwargs.items() if k != "attachments"},
    )


def test_all_enquiry_attachment_records_prefers_tatva_only():
    session = _session(
        flow_state={
            "tatva_enquiry_attachments": [
                {"key": "enquiries/e1/a.jpg", "url": "https://d123.cloudfront.net/enquiries/e1/a.jpg"},
                {"key": "enquiries/e1/b.jpg", "url": "https://d123.cloudfront.net/enquiries/e1/b.jpg"},
            ],
        },
        attachments=[
            SimpleNamespace(
                file_name="74167088f62f.jpg",
                file_url="https://xxx.supabase.co/storage/v1/object/public/enquiry-files/sess-1/a.jpg",
                mime_type="image/jpeg",
                uploaded_at=None,
            ),
        ],
    )
    rows = store._all_enquiry_attachment_records(session)
    assert len(rows) == 2
    assert all("cloudfront.net" in r["file_url"] for r in rows)


def test_attachments_for_admin_display_dedupes_supabase_when_tatva_present():
    attachments = [
        {"file_name": "74167088f62f.jpg", "file_url": "https://xxx.supabase.co/storage/v1/object/public/enquiry-files/sess-1/a.jpg"},
        {"file_name": "dae03b8d6fa5.jpg", "file_url": "https://xxx.supabase.co/storage/v1/object/public/enquiry-files/sess-1/b.jpg"},
        {"file_name": "7333726776215e59_1782995616351.jpg", "file_url": "https://d123.cloudfront.net/enquiries/e1/a.jpg"},
        {"file_name": "f6b26531d56632d3_1782995616414.jpg", "file_url": "https://d123.cloudfront.net/enquiries/e1/b.jpg"},
    ]
    shown = store._attachments_for_admin_display("sess-1", attachments)
    assert len(shown) == 2
    assert all(store._is_tatva_cdn_url(a["file_url"]) for a in shown)


def test_dedupe_attachments_by_filename_strips_timestamp_suffix():
    items = [
        {"file_name": "photo_1782995616351.jpg", "file_url": "https://example.com/a.jpg"},
        {"file_name": "photo.jpg", "file_url": "https://d123.cloudfront.net/enquiries/e1/photo.jpg"},
    ]
    deduped = store._dedupe_attachments_by_filename(items)
    assert len(deduped) == 1
    assert "cloudfront.net" in deduped[0]["file_url"]
