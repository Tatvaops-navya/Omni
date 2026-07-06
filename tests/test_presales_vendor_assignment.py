"""Presales vendor assignment CRM helpers."""
from backend.crm.store import (
    SOURCE_TATVA_PRESALES_VENDOR,
    _vendor_assignment_meta,
    assign_presales_vendor,
)


def test_vendor_assignment_meta_from_snapshot():
    meta = _vendor_assignment_meta({
        "status": "assigned",
        "assigned_at": "2026-07-04T10:00:00Z",
        "snapshot": {
            "tatva_vendor": {
                "id": "v1",
                "name": "Acme Interiors",
                "company": "Acme Pvt Ltd",
            },
        },
    })
    assert meta["vendor_id"] == "v1"
    assert "Acme Interiors" in str(meta["vendor_name"])
    assert meta["status"] == "assigned"


def test_assign_presales_vendor_source_constant():
    assert SOURCE_TATVA_PRESALES_VENDOR == "tatva_presales_vendor"
