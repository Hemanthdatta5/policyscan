"""Clean policy HTML (or pasted text) and split it into paragraphs."""

import re

import trafilatura
from bs4 import BeautifulSoup

MIN_CHARS = 40
MAX_CHARS = 1200
MAX_PARAGRAPHS = 400


def html_to_text(html: str) -> str:
    text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_recall=True)
    if text and len(text) > 200:
        return text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    return "\n\n".join(p.get_text(" ", strip=True) for p in soup.find_all(["p", "li"]))


def _split_long(par: str) -> list[str]:
    if len(par) <= MAX_CHARS:
        return [par]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", par):
        if cur and len(cur) + len(sent) > MAX_CHARS:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def segment(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    raw = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", text)]
    pars: list[str] = []
    buf = ""
    for p in raw:
        if not p:
            continue
        if len(p) < MIN_CHARS:  # headings / list stubs: glue onto the next paragraph
            buf = f"{buf} {p}".strip()
            continue
        pars.extend(_split_long(f"{buf} {p}".strip()))
        buf = ""
    if buf and len(buf) >= MIN_CHARS:
        pars.append(buf)
    return pars[:MAX_PARAGRAPHS]
