from html.parser import HTMLParser
from pathlib import Path

HTML = Path(__file__).parents[1] / "app" / "static" / "index.html"


class NavigationTargets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.desktop = set()
        self.mobile = set()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("data-page"):
            self.desktop.add(attrs["data-page"])
        if attrs.get("data-mobile-page"):
            self.mobile.add(attrs["data-mobile-page"])
        if attrs.get("id"):
            self.ids.add(attrs["id"])


def test_reports_and_assignment_workflows_have_accessible_navigation_targets():
    dom = NavigationTargets()
    dom.feed(HTML.read_text())
    assert {"reports"} <= dom.desktop
    assert {"reports"} <= dom.mobile
    assert {
        "page-reports", "reportStartDate", "reportEndDate", "applyReportRange",
        "exportReportCsv", "reportConversionFunnel", "reportPipelineTable",
        "reportTeamTable", "leadAssignmentTools", "unassignedOnly", "bulkAssignee",
        "bulkAssignSelected", "balanceSelected", "clearLeadSelection",
    } <= dom.ids


def test_reports_navigation_is_hidden_for_roles_without_team_permissions():
    source = HTML.read_text()
    assert "reportsNav.classList.toggle('hidden',!canManageTeam)" in source
    assert "reportsButton.classList.toggle('hidden',!canManageTeam)" in source
    assert "['admin','manager'].includes(currentUser.role)" in source
    assert "page==='reports'&&(!currentUser||!['admin','manager'].includes(currentUser.role))" in source
