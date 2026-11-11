"""One-shot FT financial digest workflow.

Fetches the Financial Times front page, keeps only financial-industry
headlines, emails a digest to the recipient and attaches a short
podcast-style audio rendering of the headlines.
"""

import base64
import datetime as dt
import json
import re
from typing import Any

from pydantic import BaseModel, Field

import mistralai.workflows as workflows
from mistralai.client.models import (
    ChatCompletionRequest,
    SystemMessage,
    UserMessage,
)
from mistralai.workflows import Depends
from mistralai.workflows.plugins.mistralai import (
    activities as mistralai_activities,
)
from mistralai.workflows.plugins.mistralai import get_mistral_client
from mistralai.workflows.plugins.mistralai.connectors import (
    ToolCallClient,
    connector,
    uses_connectors,
)

FT_FRONT_PAGE_URL = "https://www.ft.com/"
FT_LINK_PREFIX = "/content/"
DIGEST_MODEL = "mistral-medium-latest"
TTS_MODEL = "voxtral-mini-tts-3-0"
PODCAST_VOICE_ID = "voice_485"
DEFAULT_RECIPIENT = "amaury.kezachian@outlook.com"
AUDIO_FILENAME = "ft-financial-digest.mp3"

FETCH_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

gmail_connector = connector("gmail")


class DigestInput(BaseModel):
    recipient_email: str = DEFAULT_RECIPIENT
    max_headlines: int = Field(default=8, ge=3, le=15)


class Headline(BaseModel):
    title: str
    url: str


class DigestContent(BaseModel):
    subject: str
    headlines: list[dict[str, str]]
    podcast_script: str


def extract_headlines(html: str, limit: int = 40) -> list[Headline]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    headlines: list[Headline] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href.startswith(FT_LINK_PREFIX):
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if len(title) < 15 or title.lower() in seen:
            continue
        seen.add(title.lower())
        url = f"https://www.ft.com{href.split('?')[0]}"
        headlines.append(Headline(title=title, url=url))
        if len(headlines) >= limit:
            break
    return headlines


def parse_digest_json(raw: str) -> DigestContent:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return DigestContent.model_validate(json.loads(text))


def build_email_html(content: DigestContent, date_label: str) -> str:
    items = []
    for item in content.headlines:
        summary = item.get("summary", "")
        summary_html = f'<p style="margin:4px 0 0 0;color:#444;">{summary}</p>' if summary else ""
        items.append(
            '<li style="margin-bottom:14px;">'
            f'<a href="{item["url"]}" style="color:#0d3472;font-weight:bold;text-decoration:none;">'
            f"{item['title']}</a>{summary_html}</li>"
        )
    return (
        "<div style='font-family:Georgia,serif;max-width:640px;margin:0 auto;'>"
        f"<h2 style='color:#333;border-bottom:2px solid #0d3472;padding-bottom:8px;'>"
        f"FT Financial Digest &mdash; {date_label}</h2>"
        f"<ol style='padding-left:20px;'>{''.join(items)}</ol>"
        "<p style='color:#777;font-size:12px;margin-top:24px;'>"
        "A podcast-style audio summary of these headlines is attached "
        f"({AUDIO_FILENAME}). Links may require an FT subscription.</p>"
        "</div>"
    )


def build_email_text(content: DigestContent, date_label: str) -> str:
    lines = [f"FT Financial Digest - {date_label}", ""]
    for item in content.headlines:
        lines.append(f"* {item['title']}")
        lines.append(f"  {item['url']}")
        if item.get("summary"):
            lines.append(f"  {item['summary']}")
        lines.append("")
    lines.append(f"Podcast-style audio attached ({AUDIO_FILENAME}).")
    return "\n".join(lines)


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=120))
async def fetch_ft_front_page() -> list[Headline]:
    import httpx

    async with httpx.AsyncClient(
        headers={"User-Agent": FETCH_USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"},
        follow_redirects=True,
        timeout=60,
    ) as client:
        response = await client.get(FT_FRONT_PAGE_URL)
        response.raise_for_status()
        headlines = extract_headlines(response.text)
    if not headlines:
        raise workflows.ActivityError(
            "No headlines found on the FT front page; the page structure "
            "may have changed or the request was blocked."
        )
    return headlines


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=180))
async def summarize_headlines(
    headlines: list[Headline], max_headlines: int
) -> DigestContent:
    catalog = "\n".join(f"- {h.title} | {h.url}" for h in headlines)
    system = (
        "You are a financial news editor. You receive headlines scraped from the "
        "Financial Times front page. Keep ONLY financial-industry news: markets, "
        "banks and insurers, asset managers, central banks and monetary policy, "
        "listed companies, deals and M&A, financial regulation, and the macro "
        "economy as it affects markets. Exclude lifestyle, arts, opinion columns "
        "without concrete financial substance, sports, technology gossip, and "
        "personal blogs. Respond with JSON only, no prose, in this exact shape:\n"
        "{\n"
        '  "subject": "short email subject",\n'
        '  "headlines": [{"title": "...", "url": "...", "summary": "1-2 sentence summary"}],\n'
        '  "podcast_script": "..." \n'
        "}\n"
        f"Keep at most {max_headlines} headlines, most important first. Each summary "
        "must be factual and based only on the headline. The podcast_script must be "
        "a 200-260 word newsreader script in English: a one-sentence welcome, then "
        "one or two spoken sentences per headline in the same order, then a short "
        "sign-off. Plain spoken text only, no markup, no stage directions."
    )
    response = await mistralai_activities.mistralai_chat_complete(
        ChatCompletionRequest(
            model=DIGEST_MODEL,
            messages=[
                SystemMessage(content=system),
                UserMessage(content=catalog),
            ],
            temperature=0.2,
        )
    )
    raw = response.choices[0].message.content or ""
    content = parse_digest_json(raw)
    if not content.headlines:
        raise workflows.ActivityError(
            "The model kept no headlines as financial-industry news."
        )
    return content


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=240))
async def generate_podcast_audio(
    script: str, mistral_client: Any = Depends(get_mistral_client)
) -> str:
    response = await mistral_client.audio.speech.complete_async(
        model=TTS_MODEL,
        input=script,
        voice_id=PODCAST_VOICE_ID,
        response_format="mp3",
    )
    return response.audio_data


@workflows.activity(start_to_close_timeout=dt.timedelta(seconds=120))
async def send_digest_email(
    recipient: str,
    subject: str,
    html: str,
    text: str,
    audio_base64: str,
    gmail: ToolCallClient = Depends(gmail_connector),
) -> None:
    await gmail.call_tool(
        tool_name="send_email",
        arguments={
            "to": [recipient],
            "subject": subject,
            "body": text,
            "htmlBody": html,
            "attachments": [
                {
                    "filename": AUDIO_FILENAME,
                    "content": audio_base64,
                    "mimeType": "audio/mpeg",
                }
            ],
        },
    )


@workflows.workflow.define(
    name="ft-financial-digest",
    workflow_display_name="FT Financial Digest",
    workflow_description=(
        "One-shot: reads the FT front page, keeps financial-industry news, "
        "emails a digest with a podcast-style MP3 attached."
    ),
    on_behalf_of=True,
)
@uses_connectors(gmail_connector)
class FTDigestWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: DigestInput) -> str:
        headlines = await fetch_ft_front_page()
        content = await summarize_headlines(headlines, input.max_headlines)
        audio_base64 = await generate_podcast_audio(content.podcast_script)
        date_label = dt.date.today().strftime("%d %b %Y")
        await send_digest_email(
            recipient=input.recipient_email,
            subject=content.subject,
            html=build_email_html(content, date_label),
            text=build_email_text(content, date_label),
            audio_base64=audio_base64,
        )
        return (
            f"Digest sent to {input.recipient_email} with "
            f"{len(content.headlines)} headlines and podcast audio attached."
        )
