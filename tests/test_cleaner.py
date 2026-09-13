from src.cleaner import html_to_clean_markdown, build_context
from src.models import LeadEnrichmentResult, TeamMember


SAMPLE_HTML = """
<html><head><style>.x{color:red}</style><script>alert(1)</script></head>
<body>
<nav>Home About Contact</nav>
<main>
<h1>Acme Inc</h1>
<p>We build developer tools for backend teams.</p>
<p>Contact us at contact@acme.com</p>
</main>
<footer>copyright 2026</footer>
</body></html>
"""


def test_strips_script_and_style():
    cleaned = html_to_clean_markdown(SAMPLE_HTML)
    assert "alert(1)" not in cleaned
    assert "color:red" not in cleaned


def test_keeps_main_content():
    cleaned = html_to_clean_markdown(SAMPLE_HTML)
    assert "Acme Inc" in cleaned
    assert "contact@acme.com" in cleaned


def test_build_context_multiple_pages():
    ctx = build_context({"https://acme.com": SAMPLE_HTML})
    assert "Source: https://acme.com" in ctx
    assert "Acme Inc" in ctx


def test_model_confidence_score_bounds():
    result = LeadEnrichmentResult(
        domain="acme.com",
        company_overview="Test overview.",
        target_audience="Test audience",
        contact_points=[],
        key_team_members=[TeamMember(name="Jane Doe")],
        data_confidence_score=0.5,
    )
    assert 0.0 <= result.data_confidence_score <= 1.0
