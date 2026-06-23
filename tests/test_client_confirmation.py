"""Client-facing confirmation message tests."""
from datetime import datetime

from backend.schemas.summary import ProjectSummary


def test_client_confirmation_excludes_internal_summary_fields():
    summary = ProjectSummary(
        session_id="wa_test",
        generated_at=datetime.utcnow(),
        next_step="Call client tomorrow at 8 PM",
        project_overview="3BHK interior renovation in Bengaluru with modular kitchen.",
        scope_of_work=["Modular kitchen", "Living room false ceiling"],
        client_requirements="Minimal Japandi style with ample storage.",
        technical_specs="1200 sqft · 3BHK",
        timeline="3 months from April 2026",
        special_considerations="Vastu compliance required.",
        estimated_scope="Budget: ₹15L",
        design_direction="Japandi-inspired minimal home.",
        execution_readiness="Possession expected next month.",
        enquiry_snapshot={
            "service_category": "home_interiors",
            "property_location": "whitefield",
            "city": "bengaluru",
            "assigned_consultant": "aadhya",
        },
    )

    text = summary.client_confirmation_text()
    address_cta = summary.client_platform_address_cta_text()

    assert "TatvaOps" in text
    assert "Your enquiry has been successfully received" in text
    assert "Building Better. Together." in text
    assert "Overview" not in text
    assert "Scope" not in text
    assert "Requirements" not in text
    assert "Specs" not in text
    assert "Timeline" not in text
    assert "Budget" not in text
    assert "Japandi" not in text
    assert "Aadhya" in text
    assert "Interiors" in text
    assert "Bengaluru" in text
    assert "Whitefield" in text
    assert "Location:" in text
    assert "Property location:" in text
    assert "https://tatvaops.com/" not in text
    assert "add your address" not in text.lower()
    assert "https://withtatva.ai/my-projects" in address_cta
    assert "add your address" in address_cta.lower()


def test_client_confirmation_separate_city_and_property_location():
    """City (where client lives) and property location are distinct in confirmation."""
    summary = ProjectSummary(
        session_id="wa_test",
        generated_at=datetime.utcnow(),
        next_step="Follow up",
        project_overview="Property development enquiry.",
        scope_of_work=[],
        client_requirements="",
        technical_specs="",
        timeline="",
        special_considerations="",
        estimated_scope="",
        design_direction="",
        execution_readiness="",
        enquiry_snapshot={
            "service_category": "property_development",
            "city": "hyderabad",
            "property_location": "bengaluru, hsr layout",
            "assigned_consultant": "vikram",
        },
    )

    text = summary.client_confirmation_text()

    assert "📍 Location: Hyderabad" in text
    assert "📍 Property location: Bengaluru, Hsr Layout" in text
    assert "Bengaluru" not in text.split("Property location:")[0]
