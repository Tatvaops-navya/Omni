"""CRM admin panel API — team users, lead assignment, my leads."""
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


class AssignTatvaEmployeeRequest(BaseModel):
    employee_id: str
    employee_name: str = ""
    employee_email: str = ""
    employee_department: str = ""
    employee_role: str = ""
    staff_role: str = Field(default="presales", pattern="^(presales|rm)$")
    snapshot: dict[str, Any] = Field(default_factory=dict)


class AssignPresalesVendorRequest(BaseModel):
    vendor_id: str
    vendor_name: str = ""
    vendor_company: str = ""
    vendor_phone: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)


class CompletePresalesRequest(BaseModel):
    notes: Optional[str] = None


class LeadNotesRequest(BaseModel):
    notes: str = Field(default="", max_length=2000)


class AddProgressStageRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    insert_after: str = Field(default="assigned", min_length=1, max_length=64)


class UpsertSalesTargetRequest(BaseModel):
    staff_type: str = Field(pattern="^(sales|rm)$")
    staff_id: str = Field(min_length=1)
    period: str = Field(pattern="^(day|month|quarter|half_year|year|all)$")
    target_leads: int = Field(ge=0, le=100000)


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


@router.patch("/lead-assignments/{external_id}/assign-employee")
async def assign_tatva_employee_lead(
    external_id: str,
    body: AssignTatvaEmployeeRequest,
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    employee_id = body.employee_id.strip()
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee id required")

    try:
        row = crm_store.assign_tatva_employee_lead(
            external_id=external_id,
            employee_id=employee_id,
            employee_name=body.employee_name.strip(),
            employee_email=body.employee_email.strip(),
            employee_department=body.employee_department.strip(),
            employee_role=body.employee_role.strip(),
            staff_role=body.staff_role,
            snapshot=body.snapshot,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.patch("/lead-assignments/{external_id}/assign-presales-vendor")
async def assign_presales_vendor_lead(
    external_id: str,
    body: AssignPresalesVendorRequest,
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")

    vendor_id = body.vendor_id.strip()
    if not vendor_id:
        raise HTTPException(status_code=400, detail="Vendor id required")

    try:
        row = crm_store.assign_presales_vendor(
            external_id=external_id,
            vendor_id=vendor_id,
            vendor_name=body.vendor_name.strip(),
            vendor_company=body.vendor_company.strip(),
            vendor_phone=body.vendor_phone.strip(),
            snapshot=body.snapshot,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"vendor_assignment": row}


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
        staff_email=str(auth.get("email") or ""),
    )
    return {"success": True, "data": data, "lead_type": lead_type}


@router.get("/my-dashboard")
async def get_my_dashboard(
    period: str = Query("month"),
    auth=Depends(require_auth),
):
    role = auth.get("role")
    user_id = auth.get("user_id")
    if role not in {"presales", "rm"} or not user_id:
        raise HTTPException(status_code=403, detail="Team access required")
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    data = crm_store.my_leads_dashboard(
        staff_user_id=str(user_id),
        staff_role=str(role),
        staff_email=str(auth.get("email") or ""),
        period=period,
    )
    return {"success": True, "data": data}


@router.get("/team-performance")
async def get_team_performance(
    staff_type: str = Query(..., pattern="^(sales|rm)$"),
    staff_id: str = Query(..., min_length=1),
    period: str = Query("month"),
    staff_email: Optional[str] = Query(None),
    staff_name: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    try:
        data = crm_store.admin_staff_dashboard(
            staff_type=staff_type,
            staff_id=staff_id,
            staff_email=staff_email,
            staff_name=staff_name,
            period=period,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": data}


@router.get("/sales-targets")
async def get_sales_target(
    staff_type: str = Query(..., pattern="^(sales|rm)$"),
    staff_id: str = Query(..., min_length=1),
    period: str = Query("month"),
    auth=Depends(require_admin),
):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    row = crm_store.get_sales_target(
        staff_type=staff_type,
        staff_id=staff_id,
        period=period,
    )
    return {
        "success": True,
        "data": {
            "staff_type": staff_type,
            "staff_id": staff_id,
            "period": period,
            "target_leads": int((row or {}).get("target_leads") or 0),
            "configured": bool(row),
        },
    }


@router.put("/sales-targets")
async def upsert_sales_target(body: UpsertSalesTargetRequest, auth=Depends(require_admin)):
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    try:
        row = crm_store.upsert_sales_target(
            staff_type=body.staff_type,
            staff_id=body.staff_id,
            period=body.period,
            target_leads=body.target_leads,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "data": {
            "staff_type": body.staff_type,
            "staff_id": body.staff_id,
            "period": body.period,
            "target_leads": int(row.get("target_leads") or body.target_leads),
            "configured": True,
        },
    }


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
            staff_email=str(auth.get("email") or ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.get("/my-projects")
async def get_my_projects(
    employee_id: Optional[str] = Query(None),
    auth=Depends(require_auth),
):
    from backend.integrations.tatva_employee_projects import (
        fetch_employee_projects,
        resolve_employee_id_by_email,
    )

    role = auth.get("role")
    if role not in {"presales", "rm", "admin"}:
        raise HTTPException(status_code=403, detail="Team access required")

    emp_id = (employee_id or "").strip()
    if not emp_id:
        emp_id = await resolve_employee_id_by_email(str(auth.get("email") or "")) or ""

    if not emp_id:
        return {
            "success": False,
            "message": "No Tatva employee linked to this account",
            "data": {"items": [], "employee_id": None},
        }

    return await fetch_employee_projects(emp_id)


@router.put("/my-leads/{external_id}/notes")
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
    text = body.notes.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    try:
        row = crm_store.update_lead_notes(
            external_id=external_id,
            staff_user_id=str(user_id),
            staff_role=str(role),
            source=source,
            notes=text,
            author_id=str(user_id),
            author_name=str(auth.get("name") or ""),
            staff_email=str(auth.get("email") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.post("/my-leads/{external_id}/progress-stages")
async def add_my_lead_progress_stage(
    external_id: str,
    body: AddProgressStageRequest,
    lead_type: str = Query("user", pattern="^(user|vendor)$"),
    auth=Depends(require_auth),
):
    role = auth.get("role")
    user_id = auth.get("user_id")
    if role not in {"presales", "rm", "admin"}:
        raise HTTPException(status_code=403, detail="Team access required")
    if role != "admin" and not user_id:
        raise HTTPException(status_code=403, detail="Team access required")
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    source = (
        crm_store.SOURCE_TATVA_VENDOR
        if lead_type == "vendor"
        else crm_store.SOURCE_TATVA_PRESALES
    )
    try:
        row = crm_store.add_custom_progress_stage(
            external_id=external_id,
            source=source,
            title=body.title,
            description=body.description,
            insert_after=body.insert_after,
            author_name=str(auth.get("name") or ""),
            staff_user_id=str(user_id) if user_id else None,
            staff_role=str(role) if user_id else None,
            staff_email=str(auth.get("email") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}


@router.patch("/my-leads/{external_id}/progress-stages/{stage_id}/complete")
async def complete_my_lead_progress_stage(
    external_id: str,
    stage_id: str,
    lead_type: str = Query("user", pattern="^(user|vendor)$"),
    auth=Depends(require_auth),
):
    role = auth.get("role")
    user_id = auth.get("user_id")
    if role not in {"presales", "rm", "admin"}:
        raise HTTPException(status_code=403, detail="Team access required")
    if role != "admin" and not user_id:
        raise HTTPException(status_code=403, detail="Team access required")
    if not crm_store.crm_available():
        raise HTTPException(status_code=503, detail="CRM database not configured")
    source = (
        crm_store.SOURCE_TATVA_VENDOR
        if lead_type == "vendor"
        else crm_store.SOURCE_TATVA_PRESALES
    )
    try:
        row = crm_store.complete_custom_progress_stage(
            external_id=external_id,
            source=source,
            stage_id=stage_id,
            staff_user_id=str(user_id) if user_id else None,
            staff_role=str(role) if user_id else None,
            staff_email=str(auth.get("email") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"assignment": row}
