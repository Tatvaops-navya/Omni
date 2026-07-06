"""Staff assignment lookup for my-leads comment log."""
from backend.crm.store import (
    TEAM_COMMENT_LOG_KEY,
    TATVA_EMPLOYEE_PREFIX,
    _tatva_employee_email_from_assignment,
    comment_log_from_assignment,
    format_my_lead_row,
)


def test_tatva_employee_email_from_snapshot():
    email = _tatva_employee_email_from_assignment({
        "snapshot": {"tatva_employee": {"email": "Navya@Example.com"}},
    })
    assert email == "navya@example.com"


def test_comment_log_from_snapshot_still_works():
    row = {
        "snapshot": {
            TEAM_COMMENT_LOG_KEY: [
                {"text": "Follow up tomorrow", "created_at": "2026-07-04T10:00:00Z"},
            ],
        },
    }
    assert comment_log_from_assignment(row)[0]["text"] == "Follow up tomorrow"


def test_format_my_lead_row_exposes_comment_log():
    row = format_my_lead_row({
        "external_id": "lead-1",
        "snapshot": {
            TEAM_COMMENT_LOG_KEY: [{"text": "Called client", "created_at": "2026-07-03T08:00:00Z"}],
        },
    })
    assert row["comment_log"][0]["text"] == "Called client"


def test_tatva_prefix_constant():
    assert TATVA_EMPLOYEE_PREFIX == "tatva:"
