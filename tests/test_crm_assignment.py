from backend.crm.store import (
    STATUS_UNASSIGNED,
    enrich_presales_items,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_enrich_presales_items_without_supabase(monkeypatch):
    monkeypatch.setattr("backend.crm.store.crm_available", lambda: False)
    items = [{"_id": "abc", "name": "Navya"}]
    out = enrich_presales_items(items)
    assert out[0]["_id"] == "abc"
    assert out[0]["assignment"]["status"] == STATUS_UNASSIGNED
