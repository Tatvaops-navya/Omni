"""
Aadhya – Project Summary Schema
"""
from __future__ import annotations
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from backend.intelligence.display_labels import display_label
from backend.integrations.tatva_enquiry_submit import format_tatva_enquiry_summary_whatsapp

TATVAOPS_PLATFORM_URL = "https://withtatva.ai/my-projects"

CLIENT_PLATFORM_ADDRESS_CTA = (
    "📍 *Next step for you*\n\n"
    "Please add your address on the TatvaOps platform:\n"
    f"{TATVAOPS_PLATFORM_URL}\n\n"
    "Open the link above to visit TatvaOps and complete your profile."
)


class ProjectSummary(BaseModel):
    """Project Summary – Ready to Initiate"""
    session_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Action
    next_step: str                           # "Call client tomorrow at 8 PM"

    # Overview
    project_overview: str                    # 1-2 sentence summary

    # Scope
    scope_of_work: List[str]                 # list of areas/services

    # Client needs
    client_requirements: str                 # style, must-haves, avoid items

    # Specs
    technical_specs: str                     # "Apartment · 1200 sqft · 3BHK · Japandi"

    # Time
    timeline: str                            # "3 months from April 2026"

    # Notes
    special_considerations: str             # kids/pets/vastu/storage combined

    # Files
    attachments_summary: str = "No attachments uploaded."

    # Budget + area
    estimated_scope: str                     # "Budget: ₹15L | Area: 1200 sqft"

    # NEW — AI vision statement
    design_direction: str                    # Japandi-inspired minimal home...

    # NEW — AI readiness assessment
    execution_readiness: str                 # Possession expected next month...

    # Raw enquiry snapshot
    enquiry_snapshot: dict = Field(default_factory=dict)

    def formatted_text(self) -> str:
        """Returns the summary as a formatted consultant document."""
        lines = [
            "═══════════════════════════════════════════════",
            "  PROJECT SUMMARY — READY TO INITIATE",
            "  Aadhya AI • TatvaOps Interior Consulting",
            "═══════════════════════════════════════════════",
            "",
            f"📌 NEXT STEP",
            f"   {self.next_step}",
            "",
            f"📋 PROJECT OVERVIEW",
            f"   {self.project_overview}",
            "",
            f"🏗️  SCOPE OF WORK",
        ]
        for item in self.scope_of_work:
            lines.append(f"   • {item}")
        lines += [
            "",
            f"🎯 CLIENT REQUIREMENTS",
            f"   {self.client_requirements}",
            "",
            f"⚙️  TECHNICAL SPECS",
            f"   {self.technical_specs}",
            "",
            f"📅 TIMELINE",
            f"   {self.timeline}",
            "",
            f"⭐ SPECIAL CONSIDERATIONS",
            f"   {self.special_considerations}",
            "",
            f"📎 ATTACHMENTS",
            f"   {self.attachments_summary}",
            "",
            f"💰 ESTIMATED SCOPE",
            f"   {self.estimated_scope}",
            "",
            f"🎨 DESIGN DIRECTION",
            f"   {self.design_direction}",
            "",
            f"✅ EXECUTION READINESS",
            f"   {self.execution_readiness}",
            "",
            "═══════════════════════════════════════════════",
        ]
        return "\n".join(lines)

    def whatsapp_text(self, max_chars: int = 1400) -> str:
        """CRM-friendly WhatsApp summary (under Twilio limits)."""
        scope_items = self.scope_of_work[:4]
        scope = ", ".join(scope_items)
        if len(self.scope_of_work) > 4:
            scope += f" (+{len(self.scope_of_work) - 4} more)"

        def _clip(s: str, n: int) -> str:
            s = (s or "").strip()
            return s if len(s) <= n else s[: n - 1] + "…"

        lines = [
            "*TatvaOps Project Summary*",
            "",
            f"*Next step*\n{_clip(self.next_step, 180)}",
            "",
            f"*Overview*\n{_clip(self.project_overview, 220)}",
            f"*Scope* { _clip(scope, 170) }",
            f"*Requirements* {_clip(self.client_requirements, 170)}",
            f"*Specs* {_clip(self.technical_specs, 110)}",
            f"*Timeline* {_clip(self.timeline, 100)}",
            f"*Budget/Scale* {_clip(self.estimated_scope, 70)}",
            "",
            "Our team will connect at your preferred time.",
        ]
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[: max_chars - 40] + "\n\n_(Full brief saved for our team.)_"
        return text

    def client_confirmation_text(
        self,
        *,
        tatva_enquiry_summary: dict | None = None,
        tatva_enquiry_attachments: list | None = None,
    ) -> str:
        """Branded client-facing confirmation — Tatva API summary when available."""
        header = (
            "🏡 TatvaOps\n\n"
            "Your enquiry has been successfully received.\n\n"
        )

        if tatva_enquiry_summary:
            try:
                from backend.integrations.tatva_enquiry_submit import format_tatva_enquiry_summary_whatsapp
                body = format_tatva_enquiry_summary_whatsapp(
                    tatva_enquiry_summary,
                    attachments=tatva_enquiry_attachments,
                )
            except ImportError:
                body = self._client_confirmation_snapshot_body()
        else:
            body = self._client_confirmation_snapshot_body()

        return (
            f"{header}{body}\n\n"
            "Our team is reviewing your requirements and will contact you "
            "during your preferred time.\n\n"
            "Thank you for choosing TatvaOps.\n\n"
            "Building Better. Together."
        )

    def client_platform_address_cta_text(self) -> str:
        """Separate follow-up message prompting the client to add their address."""
        return CLIENT_PLATFORM_ADDRESS_CTA

    def _client_confirmation_snapshot_body(self) -> str:
        snap = self.enquiry_snapshot or {}
        service_key = str(snap.get("service_category") or "").strip()

        service = display_label("service_category", service_key or "your selected service")
        consultant = display_label(
            "assigned_consultant",
            snap.get("assigned_consultant") or "our specialist",
        )
        city = display_label(
            "city",
            snap.get("city") or "—",
            service_category=service_key,
        )
        property_location = display_label(
            "property_location",
            snap.get("property_location") or "—",
            service_category=service_key,
        )

        return (
            f"📍 Location: {city}\n"
            f"📍 Property location: {property_location}\n"
            f"🏠 Service: {service}\n"
            f"👨‍💼 Assigned Specialist: {consultant}"
        )
