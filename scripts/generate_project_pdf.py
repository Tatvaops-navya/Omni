#!/usr/bin/env python3
"""Generate TatvaOps Omnichannel CRM project documentation PDF."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "TatvaOps_Omnichannel_CRM_Project.pdf"

TABLE_HEAD_STYLE = FontFace(emphasis="BOLD", color=(30, 41, 59), fill_color=(241, 245, 249))
TABLE_BODY_STYLE = FontFace(color=(71, 85, 105))
TABLE_LINE_HEIGHT = 6
TABLE_WIDTH = 190


class ProjectPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(99, 102, 241)
        self.cell(0, 8, "TatvaOps Omnichannel CRM", align="L")
        self.set_text_color(100, 116, 139)
        self.cell(0, 8, "Project Documentation", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}  |  TatvaOps  |  Confidential", align="C")

    def cover_page(self):
        self.add_page()
        self.ln(40)
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(30, 41, 59)
        self.multi_cell(0, 14, "TatvaOps Omnichannel\nLead Qualification & CRM System", align="C")
        self.ln(8)
        self.set_font("Helvetica", "", 14)
        self.set_text_color(99, 102, 241)
        self.cell(0, 10, "Aadhya AI Platform  |  Krsna Admin Panel", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(20)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(71, 85, 105)
        lines = [
            "AI-powered lead qualification across WhatsApp and Voice",
            "Google Gemini intelligence  |  11 service consultants",
            "Full CRM for Presales, RM, and Admin teams",
            "Integrated with Tatva Platform (withtatva.ai)",
        ]
        for line in lines:
            self.cell(0, 8, line, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, "Version 1.0  |  July 2026", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "TatvaOps Pvt. Ltd.", align="C")

    def section_title(self, title: str):
        self.ln(4)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 41, 59)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(99, 102, 241)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 80, self.get_y())
        self.ln(4)

    def sub_title(self, title: str):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(51, 65, 85)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(71, 85, 105)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(71, 85, 105)
        x = self.get_x()
        self.cell(6, 5.5, "-")
        self.multi_cell(0, 5.5, text)
        self.set_x(x)

    def render_table(self, headers: list[str], rows: list[list[str]], col_widths: list[int] | None = None):
        if not col_widths:
            w = TABLE_WIDTH / len(headers)
            col_widths = [int(w)] * len(headers)

        self.ln(2)
        self.set_font("Helvetica", "", 9)

        with super().table(
            width=TABLE_WIDTH,
            col_widths=tuple(col_widths),
            headings_style=TABLE_HEAD_STYLE,
            line_height=TABLE_LINE_HEIGHT,
            text_align=("LEFT",) * len(headers),
            first_row_as_headings=True,
        ) as table:
            header_row = table.row()
            for h in headers:
                header_row.cell(h)

            for row in rows:
                data_row = table.row()
                for cell in row:
                    data_row.cell(cell, style=TABLE_BODY_STYLE)

        self.ln(4)


def build_pdf() -> Path:
    pdf = ProjectPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.cover_page()

    # 1. Executive Summary
    pdf.add_page()
    pdf.section_title("1. Executive Summary")
    pdf.body_text(
        "The TatvaOps Omnichannel Lead Qualification & CRM System (codename: Aadhya) is an "
        "end-to-end platform that captures, qualifies, and manages homeowner leads across "
        "WhatsApp and Voice channels. AI consultants guide customers through structured "
        "questionnaires, generate project summaries, score leads, and sync data to the Tatva "
        "platform. The Krsna Admin Panel provides CRM capabilities for presales, relationship "
        "managers, and administrators."
    )
    pdf.sub_title("Key Capabilities")
    for item in [
        "Dual-channel intake: WhatsApp (Twilio) and Voice (Vapi + ElevenLabs)",
        "11 specialized AI consultants for TatvaOps home services",
        "Hybrid qualification: MCQ buttons, free-text, and file uploads",
        "Google Gemini-powered conversation, extraction, and summaries",
        "Lead scoring: Hot / Warm / Cold tiers",
        "CRM: lead assignment, progress tracking, meet scheduling, sales targets",
        "Deep integration with Tatva Platform API (withtatva.ai)",
    ]:
        pdf.bullet(item)

    # 2. System Architecture
    pdf.section_title("2. System Architecture")
    pdf.body_text("End-to-end data flow:")
    flow_steps = [
        "Customer contacts via WhatsApp or Voice",
        "EVA receptionist greets and presents service menu",
        "Customer selects one of 11 TatvaOps services",
        "Specialized AI consultant runs hybrid qualification flow",
        "ConversationController + Gemini extract structured enquiry data",
        "Lead scored, summary generated, enquiry submitted to Tatva API",
        "Data persisted in Redis (sessions) and Supabase (CRM/enquiries)",
        "Krsna CRM panel: assign, track, and close leads",
    ]
    for i, step in enumerate(flow_steps, 1):
        pdf.bullet(f"{i}. {step}")

    pdf.sub_title("Deployment Architecture")
    pdf.render_table(
        ["Component", "Technology", "URL / Host"],
        [
            ["Backend API", "FastAPI on Render", "tatvaops-omni-dev.onrender.com"],
            ["Admin UI (CRM)", "React + Vite on Vercel", "Vercel deployment /krsna"],
            ["Session Store", "Upstash Redis", "REST API, 24h TTL"],
            ["Persistent DB", "Supabase (PostgreSQL)", "Enquiries, CRM, files"],
            ["File CDN", "CloudFront", "Attachment URLs"],
            ["Tatva Platform", "withtatva.ai API", "Users, presales, vendors"],
        ],
        [45, 55, 90],
    )

    # 3. Technology Stack
    pdf.add_page()
    pdf.section_title("3. Technology Stack")

    pdf.sub_title("Backend")
    pdf.render_table(
        ["Technology", "Purpose"],
        [
            ["Python 3.11+", "Runtime"],
            ["FastAPI + Uvicorn", "REST API, webhooks, admin APIs"],
            ["Pydantic", "Configuration and data schemas"],
            ["Google Gemini 2.0 Flash", "AI conversation, extraction, summaries"],
            ["Twilio", "WhatsApp messaging and interactive templates"],
            ["Vapi + Deepgram", "Voice calls and transcription"],
            ["ElevenLabs", "Voice synthesis"],
            ["Upstash Redis", "Live session state"],
            ["Supabase", "PostgreSQL + file storage"],
            ["httpx", "External API client"],
        ],
        [70, 120],
    )

    pdf.sub_title("Frontend (Krsna Admin Panel)")
    pdf.render_table(
        ["Technology", "Purpose"],
        [
            ["React 18 + TypeScript", "Single-page application"],
            ["Vite", "Dev server and production build"],
            ["Tailwind CSS", "UI styling"],
            ["React Router", "Client-side routing"],
            ["Recharts", "Dashboard charts and analytics"],
            ["Lucide React", "Icon library"],
            ["date-fns", "Date formatting"],
        ],
        [70, 120],
    )

    # 4. Services & Consultants
    pdf.section_title("4. Services & AI Consultants")
    pdf.body_text(
        "Each TatvaOps service has a dedicated AI consultant persona with a service-specific "
        "qualification flow defined in JSON configuration files."
    )
    pdf.render_table(
        ["#", "Service", "Consultant"],
        [
            ["1", "Residential Construction", "Aravind Narayanan"],
            ["2", "Home Interiors", "Aadhya"],
            ["3", "Painting & Waterproofing", "Manjunath Gowda"],
            ["4", "Electrical Services", "Vivek Shetty"],
            ["5", "Plumbing Services", "Suresh Kumar"],
            ["6", "Solar Rooftop", "Kavya Nair"],
            ["7", "Event Management", "Meera Iyer"],
            ["8", "Property Development", "Vikram Desai"],
            ["9", "Home Automation", "Riya Mehta"],
            ["10", "Farm Infrastructure Setup", "Anil Reddy"],
            ["11", "Irrigation Automation", "Deepak Patil"],
        ],
        [12, 80, 98],
    )

    # 5. CRM Features
    pdf.add_page()
    pdf.section_title("5. CRM Features (Krsna Admin Panel)")

    pdf.sub_title("User Roles")
    pdf.render_table(
        ["Role", "Access Level"],
        [
            ["admin", "Full: dashboard, presales, users, vendor leads, vendors, system health"],
            ["presales", "Team dashboard, My Leads, My Projects"],
            ["rm (Relationship Manager)", "Team dashboard, My Leads, My Projects"],
        ],
        [50, 140],
    )

    pdf.sub_title("CRM Pages")
    pdf.render_table(
        ["Page", "Path", "Description"],
        [
            ["Login", "/krsna", "CRM team authentication (email + password)"],
            ["Dashboard", "/krsna/dashboard", "Stats, charts, lead acquisition, team performance"],
            ["Pre-sales", "/krsna/presales", "Admin view: assign leads to staff/vendors"],
            ["My Leads", "/krsna/my-leads", "Staff assigned leads, comments, meet scheduling"],
            ["My Projects", "/krsna/my-projects", "Employee projects from Tatva API"],
            ["Users", "/krsna/users", "Manage CRM team users (admin only)"],
            ["Vendor Leads", "/krsna/vendor-leads", "Vendor-sourced leads (admin only)"],
            ["Vendors", "/krsna/vendors", "Approved vendors from Tatva (admin only)"],
            ["System Health", "/krsna/system", "API health monitoring (admin only)"],
        ],
        [35, 45, 110],
    )

    pdf.sub_title("Lead Management")
    for item in [
        "Assign leads to presales staff, RM, Tatva employees, or vendors",
        "Custom progress stages and comment logs per lead",
        "Google Meet scheduling via Tatva meet-links API",
        "Sales targets per staff (day/month/quarter/year) with achievement %",
        "Lead scoring: Hot (75+), Warm (45-74), Cold (<45)",
        "UTM and lead acquisition filtering on dashboard",
    ]:
        pdf.bullet(item)

    pdf.sub_title("Lead Status Workflow")
    pdf.body_text("unassigned -> assigned -> in_progress -> presales_completed")

    # 6. External Integrations
    pdf.section_title("6. External Integrations (Tatva Platform)")
    pdf.body_text("The system integrates with the Tatva main API (api.withtatva.ai / devopsapi.withtatva.ai):")
    pdf.render_table(
        ["Integration", "Purpose"],
        [
            ["User check / register", "Phone lookup on first message; register new users"],
            ["Service questionnaire", "POST completed enquiry to Tatva"],
            ["Presales API", "Submit lead after create-project decision"],
            ["Presales / Vendor leads", "Fetch leads for CRM pages"],
            ["Employees API", "Sales team list for assignment"],
            ["Employee projects", "RM/presales My Projects view"],
            ["Meet links", "Schedule customer meetings"],
            ["User addresses", "Returning user saved locations"],
        ],
        [65, 125],
    )

    # 7. Data Storage
    pdf.add_page()
    pdf.section_title("7. Data Storage")

    pdf.render_table(
        ["Store", "Contents", "Fallback"],
        [
            ["Upstash Redis", "Live chat sessions, conversation state", "In-memory (data lost on restart)"],
            ["Supabase PostgreSQL", "enquiries, summaries, sessions_log, CRM tables", "Not available without config"],
            ["Supabase Storage", "Uploaded files (enquiry-files bucket)", "N/A"],
            ["CloudFront CDN", "Public attachment URLs", "N/A"],
        ],
        [45, 95, 50],
    )

    pdf.sub_title("Key Database Tables")
    pdf.render_table(
        ["Table", "Purpose"],
        [
            ["enquiries", "Structured enquiry field data"],
            ["project_summaries", "AI-generated project summaries"],
            ["sessions_log", "Conversation session logs"],
            ["enquiry_attachments", "File upload metadata"],
            ["crm_users", "CRM team accounts (admin/presales/rm)"],
            ["lead_assignments", "Lead ownership and status tracking"],
            ["sales_targets", "Staff performance targets"],
        ],
        [55, 135],
    )

    # 8. Project Structure
    pdf.section_title("8. Project Structure")
    structure = """omnichannel-main/
  backend/
    main.py                 FastAPI entry, mounts /krsna UI
    config.py               Environment configuration
    agents/chat/            WhatsApp (Twilio) webhook handler
    agents/voice/           Voice (Vapi) webhook handler
    intelligence/           AI orchestration, flows, scoring
    integrations/           Tatva API clients
    crm/                    CRM users and lead assignments
    admin/                  Admin and CRM API routers
    summarizer/             AI summary generation
    storage/                Redis + Supabase persistence
  admin-ui/                 React CRM dashboard (Krsna)
  scripts/                  SQL schemas, Twilio templates, utilities
  tests/                    Pytest test suite
  render.yaml               Render deployment config
  .env                      Environment variables"""
    pdf.set_font("Courier", "", 8)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 4.5, structure)
    pdf.ln(4)

    # 9. Configuration
    pdf.section_title("9. Key Environment Variables")
    pdf.render_table(
        ["Variable", "Purpose", "Required"],
        [
            ["GEMINI_API_KEY", "Google Gemini AI", "Yes"],
            ["TWILIO_*", "WhatsApp messaging and templates", "For WhatsApp"],
            ["VAPI_API_KEY", "Voice calls", "For Voice"],
            ["ELEVENLABS_*", "Voice synthesis", "For Voice"],
            ["UPSTASH_REDIS_*", "Session storage", "Recommended"],
            ["SUPABASE_URL + KEY", "Database and CRM", "Recommended"],
            ["ADMIN_PASSWORD / API_KEY", "Legacy admin auth", "Yes"],
            ["TATVA_USERS_API_BASE_URL", "Tatva platform API", "Yes"],
            ["BASE_URL", "Public URL for webhooks", "Production"],
            ["CORS_ORIGINS", "Allowed frontend origins", "Production"],
        ],
        [55, 85, 50],
    )

    # 10. Local Setup
    pdf.section_title("10. Local Development Setup")
    setup = """Prerequisites: Python 3.11+, Node.js 18+, Gemini API key

Backend:
  pip install -r requirements.txt
  cp .env.example .env   (configure API keys)
  uvicorn backend.main:app --reload --port 8000

Admin UI:
  cd admin-ui && npm install && npm run dev
  Open http://localhost:3000/krsna

API Documentation: http://localhost:8000/docs
Health Check:      http://localhost:8000/health"""
    pdf.set_font("Courier", "", 8.5)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 4.5, setup)

    # 11. Lead Scoring
    pdf.add_page()
    pdf.section_title("11. Lead Scoring Model")
    pdf.body_text("Leads are automatically scored (0-100) and tiered based on qualification completeness:")
    pdf.render_table(
        ["Factor", "Points"],
        [
            ["Field completion percentage", "Up to 50 points"],
            ["AI summary generated", "+20 points"],
            ["File attachments uploaded", "+15 points"],
            ["Budget range provided", "+10 points"],
            ["Timeline provided", "+5 points"],
            ["Urgent timeline (ASAP, this month)", "+10 points"],
        ],
        [120, 70],
    )
    pdf.sub_title("Tiers")
    pdf.render_table(
        ["Tier", "Score Range", "Meaning"],
        [
            ["Hot", "75 - 100", "High-intent, well-qualified lead"],
            ["Warm", "45 - 74", "Moderate intent, partial qualification"],
            ["Cold", "0 - 44", "Low intent or incomplete data"],
        ],
        [30, 40, 120],
    )

    # 12. API Endpoints
    pdf.section_title("12. Key API Endpoints")
    pdf.render_table(
        ["Endpoint", "Method", "Description"],
        [
            ["/webhook/whatsapp", "POST", "Twilio WhatsApp webhook"],
            ["/webhook/vapi", "POST", "Vapi voice webhook"],
            ["/admin/crm-login", "POST", "CRM team login"],
            ["/admin/dashboard", "GET", "Dashboard statistics"],
            ["/admin/presales", "GET", "Presales lead list"],
            ["/admin/lead-assignments/*", "PATCH", "Assign and update leads"],
            ["/admin/team-dashboard", "GET", "Team performance metrics"],
            ["/health", "GET", "Service health check"],
            ["/docs", "GET", "Swagger API documentation"],
        ],
        [65, 20, 105],
    )

    # Footer note
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(148, 163, 184)
    pdf.multi_cell(
        0, 5,
        "This document describes the TatvaOps Omnichannel Lead Qualification & CRM System "
        "(Aadhya / Krsna). For technical support or updates, contact the TatvaOps engineering team.",
        align="C",
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT))
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    print(f"PDF generated: {path}")
