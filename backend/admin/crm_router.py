"""Krsna CRM API — team users, lead assignment, my leads."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.admin.auth import require_admin, require_auth
from backend.crm import store as crm_store

router = APIRouter(prefix="/admin", tags=["crm"])


class CrmLoginRequest(BaseModel):
    email: str
    password: str


class CreateCrmUserRequest(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=6)
    role: str = Field(pattern="^(presales|rm|admin)$")


class AssignPresalesRequest(BaseModel):
    presales_user_id: str
    snapshot: dict[str, Any] = Field(default_factory=dict)


class AssignStaffLeadRequest(BaseModel):
    staff_user_id: str
    snapshot: dict[str, Any] = Field(default_factory=dict)


class CompletePresalesRequest(BaseModel):
    notes: Optional[str] = None


class LeadNotesRequest(BaseModel):
    notes: str = Field(default="", max_length=2000)


@router.post("/crm-login")
async def crm_login(body: CrmLoginRequest):
    from backend.admin.auth import generate_session_token

    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    user = crm_store.get_crm_user_by_email(body.email)
    if not user or not user.get("active"):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not crm_store.verify_password(body.password, str(user.get("password_hash") or "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_session_token(
        role=str(user.get("role") or "presales"),
        user_id=str(user.get("id")),
        name=str(user.get("name") or ""),
        email=str(user.get("email") or ""),
    )
    return {
        "token": token,
        "expires_in_hours": 8,
        "user": {
            "id": user.get("id"),
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role"),
        },
    }


@router.get("/me")
async def get_me(auth=Depends(require_auth)):
    return {
        "role": auth.get("role"),
        "user_id": auth.get("user_id"),
        "name": auth.get("name"),
        "email": auth.get("email"),
    }


@router.get("/crm-users")
async def list_team_users(
    role: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        return {"users": [], "configured": False}
    users = crm_store.list_crm_users(role=role)
    return {"users": users, "configured": True}


@router.post("/crm-users")
async def create_team_user(body: CreateCrmUserRequest, auth=Depends(require_admin)):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    try:
        user = crm_store.create_crm_user(
            name=body.name,
            email=body.email,
            password=body.password,
            role=body.role,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "user": {
            "id": user.get("id"),
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role"),
        }
    }


@router.patch("/lead-assignments/{external_id}/assign-presales")
async def assign_presales_lead(
    external_id: str,
    body: AssignPresalesRequest,
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    team = crm_store.list_crm_users(role="presales")
    if not any(str(u.get("id")) == body.presales_user_id for u in team):
        raise HTTPException(status_code=400, detail="Invalid presales user")

    try:
        row = crm_store.assign_presales_lead(
            external_id=external_id,
            presales_user_id=body.presales_user_id,
            snapshot=body.snapshot,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.patch("/lead-assignments/{external_id}/assign-user")
async def assign_user_lead(
    external_id: str,
    body: AssignStaffLeadRequest,
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    staff = crm_store.get_crm_user_by_id(body.staff_user_id)
    if not staff or not staff.get("active"):
        raise HTTPException(status_code=400, detail="Invalid team member")
    role = str(staff.get("role") or "")
    if role not in {"presales", "rm"}:
        raise HTTPException(status_code=400, detail="Assign to presales or RM only")

    try:
        row = crm_store.assign_staff_lead(
            external_id=external_id,
            staff_user_id=body.staff_user_id,
            staff_role=role,
            snapshot=body.snapshot,
            source=crm_store.SOURCE_TATVA_PRESALES,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.patch("/lead-assignments/{external_id}/assign-vendor")
async def assign_vendor_lead(
    external_id: str,
    body: AssignStaffLeadRequest,
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    staff = crm_store.get_crm_user_by_id(body.staff_user_id)
    if not staff or not staff.get("active"):
        raise HTTPException(status_code=400, detail="Invalid team member")
    role = str(staff.get("role") or "")
    if role not in {"presales", "rm"}:
        raise HTTPException(status_code=400, detail="Assign to presales or RM only")

    try:
        row = crm_store.assign_staff_lead(
            external_id=external_id,
            staff_user_id=body.staff_user_id,
            staff_role=role,
            snapshot=body.snapshot,
            source=crm_store.SOURCE_TATVA_VENDOR,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.get("/my-leads")
async def get_my_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    lead_type: str = Query("user", pattern="^(user|vendor)$"),
    auth=Depends(require_auth),
):
    role = auth.get("role")
    user_id = auth.get("user_id")
    if role not in {"presales", "rm"} or not user_id:
        raise HTTPException(status_code=403, detail="Team access required")

    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    source = (
        crm_store.SOURCE_TATVA_VENDOR
        if lead_type == "vendor"
        else crm_store.SOURCE_TATVA_PRESALES
    )
    data = crm_store.list_my_leads(
        staff_user_id=str(user_id),
        staff_role=str(role),
        source=source,
        page=page,
        limit=limit,
        status=status,
    )
    return {"success": True, "data": data, "lead_type": lead_type}


@router.patch("/my-leads/{external_id}/complete")
async def complete_my_lead(
    external_id: str,
    body: CompletePresalesRequest,
    lead_type: str = Query("user", pattern="^(user|vendor)$"),
    auth=Depends(require_auth),
):
    role = auth.get("role")
    user_id = auth.get("user_id")
    if role not in {"presales", "rm"} or not user_id:
        raise HTTPException(status_code=403, detail="Team access required")
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    source = (
        crm_store.SOURCE_TATVA_VENDOR
        if lead_type == "vendor"
        else crm_store.SOURCE_TATVA_PRESALES
    )
    try:
        row = crm_store.mark_lead_completed(
            external_id=external_id,
            staff_user_id=str(user_id),
            staff_role=str(role),
            source=source,
            notes=body.notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.patch("/my-leads/{external_id}/notes")
async def update_my_lead_notes(
    external_id: str,
    body: LeadNotesRequest,
    lead_type: str = Query("user", pattern="^(user|vendor)$"),
    auth=Depends(require_auth),
):
    role = auth.get("role")
    user_id = auth.get("user_id")
    if role not in {"presales", "rm"} or not user_id:
        raise HTTPException(status_code=403, detail="Team access required")
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    source = (
        crm_store.SOURCE_TATVA_VENDOR
        if lead_type == "vendor"
        else crm_store.SOURCE_TATVA_PRESALES
    )
    try:
        row = crm_store.update_lead_notes(
            external_id=external_id,
            staff_user_id=str(user_id),
            staff_role=str(role),
            source=source,
            notes=body.notes.strip(),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}
