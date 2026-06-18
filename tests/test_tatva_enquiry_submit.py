"""Tests for Tatva service-questionnaire submission."""
import json

import pytest

from backend.integrations.tatva_enquiry_submit import (
    build_questionnaire_form_fields,
    build_questionnaire_summary,
    extract_tatva_attachment_urls,
    format_attachments_section_whatsapp,
    format_tatva_enquiry_summary_whatsapp,
    list_tatva_attachment_links,
    submit_service_questionnaire,
)
from backend.integrations.tatva_service_questions import (
    build_steps_from_api_questions,
    sync_questionnaire_state,
)
from backend.schemas.service import ServiceCategory
from backend.schemas.session import Session, ConversationStage, AttachmentMeta
from backend.intelligence import stage_engine as se
from backend.intelligence.conversation_controller import ConversationController
from tests.test_tatva_service_questions import RESIDENTIAL_API_QUESTIONS


def _session_with_residential_answers() -> Session:
    session = Session(
        session_id="submit-test",
        phone_number="whatsapp:+919876543210",
        channel="whatsapp",
        conversation_stage=ConversationStage.CONFIRMATION,
    )
    se.start_client_stage(session)
    for field, value in (
        ("client_name", "Test User"),
        ("city", "Bengaluru"),
        ("property_location", "HSR Layout"),
        ("preferred_contact_time", "afternoon"),
        ("willing_to_create_project", "yes"),
    ):
        se.mark_field_validated(session, field, value)

    se.on_service_selected(session, ServiceCategory.RESIDENTIAL_CONSTRUCTION)
    steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
    sync_questionnaire_state(session, steps, source="tatva_api")
    session.flow_state["tatva_service_id"] = "6926b7865c6d9f597ae41693"
    session.extracted_fields["tatva_service_name"] = "Residential Construction"
    session.extracted_fields["tatva_user_id"] = "698045af7d79fe3c880dab0f"

    se.mark_field_validated(session, "order_1", "new home build")
    se.mark_field_validated(session, "order_2", "under ₹25 lakhs")
    se.mark_field_validated(session, "order_4", "scd")
    se.mark_field_validated(session, "file_order_5", "1 file(s) uploaded")
    session.attachments.append(
        AttachmentMeta(
            file_name="Screenshot 2026-04-13 at 10.38.22 PM.png",
            file_url="https://example.com/file.png",
            mime_type="image/png",
        )
    )
    return session


def test_format_tatva_enquiry_summary_whatsapp():
    summary = {
        "projectOverview": "The client submitted a Residential Construction enquiry",
        "scopeOfWork": "Scope for Residential Construction is based on the client's written requirements",
        "clientRequirements": "sdffdsds",
        "technicalSpecs": "Project type = New Home Build = Drawings or permits = Yes, fully approved",
        "timeline": "12 months",
        "specialConsiderations": "No special considerations noted",
        "estimatedScope": "Budget = ₹25 Lakhs",
    }
    attachments = [
        {
            "key": "enquiries/user/service/file.png",
            "url": "https://d187u6mpwmtl08.cloudfront.net/enquiries/file.png",
        },
        {
            "key": "enquiries/user/service/plan.pdf",
            "url": "https://d187u6mpwmtl08.cloudfront.net/enquiries/plan.pdf",
        },
    ]
    text = format_tatva_enquiry_summary_whatsapp(summary, attachments=attachments)
    assert "*Project Overview*" in text
    assert "Residential Construction enquiry" in text
    assert "*Client Requirements*" in text
    assert "sdffdsds" in text
    assert "*Estimated Scope*" in text
    assert "₹25 Lakhs" in text
    assert "*Attachments*" in text
    assert "↗ View image\nhttps://d187u6mpwmtl08.cloudfront.net/enquiries/file.png" in text
    assert "↗ View PDF\nhttps://d187u6mpwmtl08.cloudfront.net/enquiries/plan.pdf" in text
    assert text.index("*Estimated Scope*") < text.index("*Attachments*")
    assert text.index("↗ View image") < text.index("↗ View PDF")

    text_without_files = format_tatva_enquiry_summary_whatsapp(summary)
    assert "*Attachments*" not in text_without_files


def test_list_tatva_attachment_links_preserves_urls_for_delivery():
    attachments = [
        {"key": "a.jpg", "url": "https://example.com/a.jpg"},
        {"key": "c.pdf", "url": "https://example.com/c.pdf"},
    ]
    links = list_tatva_attachment_links(attachments)
    assert links == [
        {"label": "↗ View image", "url": "https://example.com/a.jpg", "kind": "image"},
        {"label": "↗ View PDF", "url": "https://example.com/c.pdf", "kind": "pdf"},
    ]
    assert extract_tatva_attachment_urls(attachments) == [
        "https://example.com/a.jpg",
        "https://example.com/c.pdf",
    ]


def test_format_attachments_section_whatsapp_labels_and_urls():
    attachments = [
        {"key": "a.jpg", "url": "https://example.com/a.jpg"},
        {"key": "b.mp4", "url": "https://example.com/b.mp4"},
        {"key": "c.pdf", "url": "https://example.com/c.pdf"},
        {"key": "d.bin", "url": "https://example.com/d.bin"},
    ]
    section = format_attachments_section_whatsapp(attachments)
    assert section.startswith("*Attachments*")
    assert "↗ View image\nhttps://example.com/a.jpg" in section
    assert "↗ View video\nhttps://example.com/b.mp4" in section
    assert "↗ View PDF\nhttps://example.com/c.pdf" in section
    assert "↗ View file\nhttps://example.com/d.bin" in section
    assert section.index("a.jpg") < section.index("b.mp4") < section.index("c.pdf")
    assert extract_tatva_attachment_urls(attachments) == [
        "https://example.com/a.jpg",
        "https://example.com/b.mp4",
        "https://example.com/c.pdf",
        "https://example.com/d.bin",
    ]


def test_client_confirmation_uses_tatva_api_summary():
    from datetime import datetime
    from backend.schemas.summary import ProjectSummary

    tatva_summary = {
        "projectOverview": "The client submitted a Residential Construction enquiry",
        "clientRequirements": "sdffdsds",
        "timeline": "12 months",
        "estimatedScope": "Budget = ₹25 Lakhs",
    }
    summary = ProjectSummary(
        session_id="wa_test",
        generated_at=datetime.utcnow(),
        next_step="Call client",
        project_overview="internal",
        scope_of_work=[],
        client_requirements="internal",
        technical_specs="",
        timeline="internal",
        special_considerations="",
        estimated_scope="",
        design_direction="",
        execution_readiness="",
        enquiry_snapshot={"city": "hsr", "service_category": "residential_construction"},
    )
    attachments = [
        {
            "key": "enquiries/user/service/file.png",
            "url": "https://d187u6mpwmtl08.cloudfront.net/enquiries/file.png",
        }
    ]
    text = summary.client_confirmation_text(
        tatva_enquiry_summary=tatva_summary,
        tatva_enquiry_attachments=attachments,
    )
    assert "Your enquiry has been successfully received" in text
    assert "*Project Overview*" in text
    assert "sdffdsds" in text
    assert "*Attachments*" in text
    assert "↗ View image\nhttps://d187u6mpwmtl08.cloudfront.net/enquiries/file.png" in text
    assert "Location:" not in text
    assert "Assigned Specialist:" not in text


    session = _session_with_residential_answers()
    steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
    summary = build_questionnaire_summary(session, steps)

    assert len(summary) == 3
    assert summary[0]["id"] == "project-details"
    assert summary[0]["items"][0]["value"] == "New Home Build"
    assert summary[1]["id"] == "description"
    assert summary[1]["items"][0]["value"] == "scd"
    assert summary[2]["id"] == "files"
    assert "Screenshot" in summary[2]["items"][0]["value"]


def test_build_questionnaire_form_fields_use_question_prompts():
    session = _session_with_residential_answers()
    steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
    fields = build_questionnaire_form_fields(session, steps)

    assert fields["What type of residential construction project are you planning?"] == "New Home Build"
    assert fields["Describe your project."] == "scd"
    assert "Upload supporting documents." not in fields


@pytest.mark.asyncio
async def test_submit_service_questionnaire_posts_multipart(monkeypatch):
    session = _session_with_residential_answers()
    steps = build_steps_from_api_questions(RESIDENTIAL_API_QUESTIONS)
    captured: dict = {}

    async def fake_download(meta):
        return b"png-bytes", meta.file_name, meta.mime_type

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "Enquiry created",
                "data": {
                    "enquiry": {
                        "_id": "6a2fcf4acb6f548d14911a49",
                        "summary": {
                            "projectOverview": "The client submitted a Residential Construction enquiry",
                            "clientRequirements": "scd",
                            "timeline": "12 months",
                        },
                        "attachments": [
                            {
                                "key": "enquiries/user/service/file.png",
                                "url": "https://d187u6mpwmtl08.cloudfront.net/enquiries/file.png",
                            }
                        ],
                    }
                },
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data=None, files=None):
            captured["url"] = url
            captured["data"] = data
            captured["files"] = files
            return FakeResponse()

    monkeypatch.setattr(
        "backend.integrations.tatva_enquiry_submit._download_attachment",
        fake_download,
    )
    monkeypatch.setattr(
        "backend.integrations.tatva_enquiry_submit.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )

    result = await submit_service_questionnaire(session)
    assert result is not None
    assert result["projectOverview"].startswith("The client submitted")
    assert session.flow_state.get("tatva_enquiry_submitted") is True
    assert session.flow_state.get("tatva_enquiry_summary")["clientRequirements"] == "scd"
    assert session.flow_state.get("tatva_enquiry_attachments")[0]["url"].endswith("file.png")
    assert captured["url"].endswith("/users/api/enquiries/service-questionnaire")
    assert captured["data"]["userId"] == "698045af7d79fe3c880dab0f"
    assert captured["data"]["serviceId"] == "6926b7865c6d9f597ae41693"
    assert captured["data"]["serviceName"] == "Residential Construction"
    summary = json.loads(captured["data"]["summary"])
    assert summary[0]["title"] == "PROJECT DETAILS"
    assert captured["files"] is not None
    assert len(captured["files"]) == 1


@pytest.mark.asyncio
async def test_confirm_submit_triggers_tatva_enquiry(monkeypatch):
    called = {"count": 0}

    async def fake_submit(session):
        called["count"] += 1
        session.flow_state["tatva_enquiry_submitted"] = True
        session.flow_state["tatva_enquiry_summary"] = {
            "projectOverview": "The client submitted a Residential Construction enquiry",
            "clientRequirements": "sdffdsds",
        }
        return session.flow_state["tatva_enquiry_summary"]

    async def fake_summary(self, session):
        from backend.schemas.summary import ProjectSummary
        from datetime import datetime

        return ProjectSummary(
            session_id=session.session_id,
            generated_at=datetime.utcnow(),
            next_step="Call client",
            project_overview="Test overview",
            scope_of_work=["Scope"],
            client_requirements="Req",
            technical_specs="Specs",
            timeline="Soon",
            special_considerations="None",
            estimated_scope="Budget",
            design_direction="Modern",
            execution_readiness="Ready",
            enquiry_snapshot=session.extracted_fields,
        )

    monkeypatch.setattr(
        "backend.intelligence.conversation_controller.submit_service_questionnaire",
        fake_submit,
    )
    monkeypatch.setattr(
        "backend.summarizer.summary_generator.SummaryGenerator.generate",
        fake_summary,
    )

    session = _session_with_residential_answers()
    se.enter_final_review(session)
    session.flow_state["final_review_shown"] = True

    controller = ConversationController()
    resp = await controller.process_message(
        session,
        "confirm_submit",
        channel="whatsapp",
        list_id="confirm_submit",
    )
    assert called["count"] == 1
    assert resp.summary_generated is True
    assert "*Project Overview*" in resp.text
    assert "sdffdsds" in resp.text
    assert resp.follow_up_text is not None
    assert "add your address" in resp.follow_up_text.lower()
