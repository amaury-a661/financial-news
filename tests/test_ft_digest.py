import base64

from worker.workflows.ft_digest import (
    DigestContent,
    DigestInput,
    build_email_html,
    build_email_text,
    extract_headlines,
    parse_digest_json,
)

FRONT_PAGE_HTML = """
<html><body>
<a href="/" class="logo">FT</a>
<a href="/content/abc123">Markets rally as central bank signals rate cut</a>
<a href="/content/abc123?seg=na">Markets rally as central bank signals rate cut</a>
<a href="/content/def456">Bank of Japan holds rates steady amid inflation worries</a>
<a href="/content/short">Too short</a>
<a href="/world/news">Not a content link</a>
<a href="/content/ghi789">Lifestyle: the best watches of the season</a>
</body></html>
"""


def test_extract_headlines_dedupes_and_filters():
    headlines = extract_headlines(FRONT_PAGE_HTML)
    titles = [h.title for h in headlines]
    assert titles == [
        "Markets rally as central bank signals rate cut",
        "Bank of Japan holds rates steady amid inflation worries",
        "Lifestyle: the best watches of the season",
    ]
    assert headlines[0].url == "https://www.ft.com/content/abc123"


def test_extract_headlines_respects_limit():
    assert len(extract_headlines(FRONT_PAGE_HTML, limit=2)) == 2


def test_extract_headlines_empty_page():
    assert extract_headlines("<html><body><p>Nothing here</p></body></html>") == []


def test_parse_digest_json_plain():
    raw = '{"subject": "s", "headlines": [], "podcast_script": "x"}'
    content = parse_digest_json(raw)
    assert content.subject == "s"


def test_parse_digest_json_fenced_and_wrapped():
    raw = (
        "Here is the digest:\n```json\n"
        '{"subject": "s", "headlines": [{"title": "t", "url": "u", "summary": "m"}],'
        ' "podcast_script": "x"}\n```\nDone.'
    )
    content = parse_digest_json(raw)
    assert content.headlines[0]["title"] == "t"


def test_parse_digest_json_control_chars_and_trailing_object():
    raw = (
        '{"subject": "s", "headlines": [{"title": "t", "url": "u",'
        ' "summary": "line one\nline two"}], "podcast_script": "x"}\n'
        '{"note": "model appended a second object"}'
    )
    content = parse_digest_json(raw)
    assert content.podcast_script == "x"
    assert "line one\nline two" in content.headlines[0]["summary"]


def test_digest_content_rejects_missing_fields():
    try:
        DigestContent.model_validate({"subject": "s"})
    except Exception:
        pass
    else:
        raise AssertionError("expected validation error")


def test_build_email_html_and_text():
    content = DigestContent(
        subject="FT digest",
        headlines=[
            {
                "title": "Markets rally",
                "url": "https://www.ft.com/content/abc",
                "summary": "Stocks rose.",
            }
        ],
        podcast_script="script",
    )
    html = build_email_html(content, "11 Nov 2025")
    text = build_email_text(content, "11 Nov 2025")
    assert "FT Financial Digest &mdash; 11 Nov 2025" in html
    assert 'href="https://www.ft.com/content/abc"' in html
    assert "Stocks rose." in html
    assert "ft-financial-digest.mp3" in html
    assert "* Markets rally" in text
    assert "https://www.ft.com/content/abc" in text


def test_digest_input_defaults():
    data = DigestInput(max_headlines=8)
    assert data.recipient_email == "amaury.kezachian@outlook.com"
    assert base64.b64encode(b"x").decode()


def test_digest_input_bounds():
    try:
        DigestInput(max_headlines=2)
    except Exception:
        pass
    else:
        raise AssertionError("expected validation error")
