from __future__ import annotations

from agents.tools.html_clean import extract_main_text, post_clean_text
from agents.tools.parse_tables import extract_tables_markdown, html_table_to_markdown
from bs4 import BeautifulSoup


def test_post_clean_text_strips_cookie_banner() -> None:
    raw = "Product pricing starts at $29.\nWe use cookies to improve your experience.\n"
    cleaned = post_clean_text(raw)
    assert "cookies" not in cleaned.lower()
    assert "$29" in cleaned


def test_extract_main_text_removes_script_noise() -> None:
    html = """
    <html><head><script>var x=1;</script></head><body>
    <nav>Home Login</nav>
    <main><h1>Pricing</h1><p>Pro plan costs $99 per month for teams.</p></main>
    <footer>All rights reserved</footer>
    </body></html>
    """
    text = extract_main_text(html)
    assert "Pricing" in text
    assert "var x=1" not in text


def test_html_table_to_markdown_preserves_columns() -> None:
    soup = BeautifulSoup(
        "<table><tr><th>Plan</th><th>Price</th></tr>"
        "<tr><td>Pro</td><td>$99</td></tr></table>",
        "lxml",
    )
    table = soup.find("table")
    assert table is not None
    markdown = html_table_to_markdown(table)
    assert "| Plan | Price |" in markdown
    assert "| Pro | $99 |" in markdown


def test_extract_tables_markdown_multiple_tables() -> None:
    html = """
    <table><tr><th>A</th></tr><tr><td>1</td></tr></table>
    <table><tr><th>B</th></tr><tr><td>2</td></tr></table>
    """
    markdown = extract_tables_markdown(html)
    assert "### Table 1" in markdown
    assert "### Table 2" in markdown
