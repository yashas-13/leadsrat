from html.parser import HTMLParser
from pathlib import Path
import re

HTML = Path(__file__).parents[1] / 'app' / 'static' / 'index.html'

class DOM(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=set(); self.pages=set(); self.mobile_pages=set()
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if a.get('id'): self.ids.add(a['id'])
        if a.get('data-page'): self.pages.add(a['data-page'])
        if a.get('data-mobile-page'): self.mobile_pages.add(a['data-mobile-page'])

def test_admin_navigation_has_all_required_workspace_targets():
    dom=DOM(); dom.feed(HTML.read_text())
    assert {'dashboard','leads','properties','matches','team','settings'} <= dom.pages
    assert {'employee','leads','team','settings'} <= dom.mobile_pages
    assert {'page-dashboard','page-leads','page-properties','page-matches','page-team','page-settings','adminDashboardTeam','teamRows','teamMetrics'} <= dom.ids

def test_identity_update_does_not_target_nonexistent_employee_desktop_nav():
    source=HTML.read_text()
    assert "const employeeNav=document.querySelector('[data-page=\"employee\"]');if(employeeNav)employeeNav.classList.toggle" in source
    assert "document.querySelector('[data-page=\"employee\"]').classList.toggle" not in source

def test_lead_form_prevents_past_follow_up_selection():
    source=HTML.read_text()
    assert "followUpInput.min=minDate.toISOString().slice(0,16)" in source
    assert "new Date(followUpInput.value).getTime()<=Date.now())followUpInput.value=''" in source
    assert "Choose a future first follow-up time." in source
