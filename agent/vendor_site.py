"""Collect vendor-published evidence without treating marketing as fact."""

import os
import re
import threading
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

from evidence import Collection, Evidence, USER_AGENT, public_url


PAGE_TYPES = {
    "about": r"about|company|über uns|unternehmen",
    "imprint": r"imprint|impressum|legal notice",
    "pricing": r"pricing|plans|preise",
    "customers": r"customers|case stud(?:y|ies)|success stor|referenz|kunden",
    "privacy": r"privacy|datenschutz",
    "security": r"security|trust cent(?:er|re)|compliance|sicherheit",
    "docs": r"documentation|\bdocs\b|help cent(?:er|re)|knowledge base|support|handbuch",
    "releases": r"changelog|release notes|releases|what.s new|versionshistorie",
    "careers": r"careers|jobs|karriere",
}
SIGNALS = {
    "release": r"release notes|latest release|latest version|version \d+\.\d+|changelog|updated on|last updated|zuletzt aktualisiert",
    "traction claim": r"(?:\d[\d,.]*\+?\s+(?:k |m |million |billion )?(?:customers|users|clients|companies|downloads|kunden|nutzer)|trusted by)",
    "certification claim": r"ISO[ /-]*(?:IEC[ /-]*)?27001|SOC[ -]*2|BSI C5",
    "ownership claim": r"a [^.!?]{2,45} company\b|formerly|previously known as|acquired by|part of the .{2,40} group|ehemals|übernommen",
    "lifecycle notice": r"discontinued|end.of.life|end of support|no longer maintained|sunset|maintenance mode|eingestellt|nicht mehr weiterentwickelt",
    "legal entity": r"(?:[\w&.-]+\s+){1,4}(?:GmbH|UG|Ltd\.?|Inc\.?|LLC|GmbH & Co\. KG|SAS|AG)\b|Handelsregister|HRB \d+",
}
RELEASE_DATE = re.compile(r"\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}\.\d{1,2}\.20\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? 20\d{2})\b", re.I)
BROWSER_SLOTS = threading.BoundedSemaphore(2)


def domain(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def clean(text, length=200):
    return " ".join((text or "").split())[:length]


def meta(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def links(soup, base):
    for tag in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base, tag["href"]))[0]
        if urlsplit(href).scheme in {"https", "http"} and href != base:
            alt = [img.get("alt", "") for img in tag.find_all("img")]
            yield href, clean(tag.get_text(" ", strip=True) or " ".join(alt) or tag.get("aria-label"))


def emit(out, kind, claim, url):
    evidence = Evidence(kind, claim, url)
    if evidence not in out.evidence:
        out.evidence.append(evidence)


def extract(out, soup, url, purpose):
    footer = soup.find("footer")
    footer_text = footer.get_text(" ", strip=True) if footer else ""
    for tag in soup.select("script, style, template, noscript, svg"):
        tag.decompose()
    title = meta(soup, "og:title") or clean(soup.title.get_text() if soup.title else "")
    heading = clean(soup.h1.get_text(" ", strip=True) if soup.h1 else "")
    description = meta(soup, "description", "og:description")
    if purpose in {"product", "home"}:
        site_name = meta(soup, "og:site_name", "application-name")
        if purpose == "product" or not out.product:
            out.product = title or heading
        if site_name or not out.vendor:
            out.vendor = site_name or domain(url)
        if title or heading or description:
            emit(out, "vendor overview", f"{purpose}: {title} | {heading} | {description}", url)
    elif title or heading:
        emit(out, "vendor page", f"{purpose}: {title or heading}", url)

    body = clean(soup.get_text(" ", strip=True), 65_000)
    for kind, pattern in SIGNALS.items():
        for match in list(re.finditer(pattern, body, re.I))[:2]:
            snippet = clean(body[max(0, match.start() - 45): match.end() + 110])
            emit(out, kind, f'Page text: “{snippet}”', url)
    for match in re.finditer(r"(?:©|copyright|\(c\))\s*.{0,28}?\b(?:19|20)\d{2}(?:\s*[-–]\s*(?:19|20)\d{2})?", footer_text or body, re.I):
        if purpose in {"product", "home"}:
            emit(out, "copyright", f'Copyright text: “{match.group()}” (not a maintenance date)', url)
        break
    modified = meta(soup, "article:modified_time", "dateModified", "last-modified")
    if modified:
        emit(out, "page date", f"Page metadata reports modification: {modified}", url)
    if purpose in {"docs", "releases"}:
        dates = list(dict.fromkeys(RELEASE_DATE.findall(body)))[:8]
        if dates:
            emit(out, "page date", f"Dates printed on the {purpose} page: {', '.join(dates)}", url)
    logo_names = []
    for img in soup.find_all("img", alt=True):
        alt = clean(img["alt"], 90)
        label = " ".join([alt, str(img.get("src", "")), str(img.get("class", ""))])
        if alt and (purpose == "customers" or re.search(r"customer|client|partner|logo", label, re.I)):
            if alt not in logo_names:
                logo_names.append(alt)
    if logo_names:
        emit(out, "logo text", "Possible customer, partner or site logos (unverified alt text): " + ", ".join(logo_names[:12]), url)
    image_links = [a for a in soup.select("nav a, header a") if a.find("img") and not a.get_text(strip=True)]
    if image_links:
        emit(out, "image navigation", f"{len(image_links)} sampled header/navigation links contain images without visible link text.", url)
    return body


def render(http, url):
    screenshot = http.path("homepage", url, ".png")
    rendered = http.path("render", url)
    cached = http.read(rendered)
    if isinstance(cached, dict) and http.fresh(screenshot) and http.allowed(cached["url"]):
        return cached["html"], cached["url"], screenshot, ""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        return "", url, None, "Playwright not installed; skipped screenshot and browser fallback."
    if not http.allowed(url):
        return "", url, None, "Robots policy prevented browser access."
    with BROWSER_SLOTS, sync_playwright() as pw:
        context = None
        try:
            cdp = os.getenv("CHROME_CDP_URL")
            browser = (pw.chromium.connect_over_cdp(cdp, timeout=4000) if cdp
                       else pw.chromium.launch(timeout=6000))
            context = browser.new_context(
                user_agent=USER_AGENT, viewport={"width": 1440, "height": 900},
                service_workers="block", accept_downloads=False,
            )
            context.route_web_socket("**/*", lambda ws: ws.close())

            def route_request(route):
                request = route.request
                if request.resource_type in {"media", "websocket", "eventsource"} or not public_url(request.url):
                    route.abort()
                elif request.resource_type in {"document", "xhr", "fetch"} and not http.allowed(request.url):
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", route_request)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=10_000)
            page.wait_for_timeout(800)
            html = page.content()[:1_500_000]
            if not public_url(page.url) or not http.allowed(page.url):
                return "", url, None, "Browser navigation did not end on an allowed public page."
            http.write(rendered, {"url": page.url, "html": html})
            page.screenshot(path=str(screenshot), timeout=5000, animations="disabled")
            return html, page.url, screenshot, ""
        except Error as error:
            return "", url, None, f"Browser rendering unavailable: {str(error).splitlines()[0]}"
        finally:
            if context:
                context.close()


def collect_site(http, url, screenshot=True):
    out = Collection()
    pages = {}
    requested = http.get(url, crawl=True)
    resolved = requested.url if requested else url
    root = urljoin(resolved, "/")
    if requested and requested.status == 200 and "html" in requested.content_type:
        pages["product"] = (resolved, requested.body)
    else:
        status = f"HTTP {requested.status}" if requested else "robots restriction or request failure"
        out.notes.append(f"Product fetch unavailable ({status}); not evidence of discontinuation.")
    home = requested if resolved == root else http.get(root, crawl=True)
    if home and home.status == 200 and "html" in home.content_type:
        pages["home"] = (home.url, home.body)
    raw = BeautifulSoup(requested.body, "html.parser") if requested and requested.body else None
    needs_render = not raw or not raw.body or len(raw.body.get_text(" ", strip=True)) < 220
    if screenshot or needs_render:
        html, rendered_url, image, note = render(http, root if screenshot else resolved)
        out.screenshot = image if screenshot else None
        if html and (root == resolved or not screenshot):
            target = BeautifulSoup(html, "html.parser")
            if target.body and (needs_render or "product" not in pages):
                pages["product"] = (rendered_url, html)
        if html and screenshot:
            pages["home"] = (rendered_url, html)
        if note:
            out.notes.append(note)
    if needs_render and screenshot and resolved != root:
        html, rendered_url, _, note = render(http, resolved)
        if html:
            pages["product"] = (rendered_url, html)
        if note:
            out.notes.append(note)

    candidates = {}
    seen = set()
    for purpose, (final_url, html) in pages.items():
        if final_url in seen:
            continue
        seen.add(final_url)
        soup = BeautifulSoup(html, "html.parser")
        for target, label in links(soup, final_url):
            if target in seen or domain(target) != domain(final_url):
                continue
            for kind, pattern in PAGE_TYPES.items():
                if re.search(pattern, f"{label} {urlsplit(target).path}", re.I):
                    candidates.setdefault(kind, (target, final_url, label))
        extract(out, soup, final_url, purpose)
    visited = {}
    broken = 0
    for purpose, (target, parent, label) in candidates.items():
        if target not in visited:
            visited[target] = http.get(target, crawl=True)
        response = visited[target]
        if not response:
            continue
        if response.status == 200 and "html" in response.content_type and response.url not in seen:
            seen.add(response.url)
            extract(out, BeautifulSoup(response.body, "html.parser"), response.url, purpose)
        elif response.status in {404, 410} and broken < 3:
            emit(out, "dead link", f"Linked {purpose} page ({label or target}) returned HTTP {response.status}: {target}", parent)
            broken += 1
    return out
