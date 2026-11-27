"""Collect history, corroboration, and publicly reported vendor risk."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode, urlsplit

from bs4 import BeautifulSoup

from evidence import Collection, Evidence
from vendor_site import clean, domain


TOPICS = {
    "incidents": "data breach security incident compromised disclosure status page",
    "enforcement": "regulator fine enforcement FTC GDPR court lawsuit consumer protection",
    "ownership": "acquired acquisition owner private equity CEO rebrand renamed formerly",
    "lifecycle": "discontinued product end of life sunset support documentation recent release",
    "market": "customer case study partner marketplace reviews Reddit LinkedIn employee count GitHub",
    "jurisdiction": "company legal entity headquarters incorporation Russia ownership",
}
ARCHIVE = "https://web.archive.org"
REGISTRY_PREFIX = {
    "de": "https://www.denic.de/en/service/whois-service/",
    "uk": "https://www.nominet.uk/lookup/",
}


def json_body(response, default):
    if not response or response.status != 200:
        return default
    try:
        return response.json()
    except ValueError:
        return default


def registrable(url):
    host = domain(url)
    labels = host.split(".")
    suffixes = {"co.uk", "org.uk", "com.au", "co.nz", "co.jp", "com.br"}
    return ".".join(labels[-(3 if ".".join(labels[-2:]) in suffixes else 2):])


def registration(http, url):
    name = registrable(url)
    source = f"https://rdap.org/domain/{quote(name, safe='.')}"
    record = json_body(http.get(source), {})
    for event in record.get("events", []) if isinstance(record, dict) else []:
        if event.get("eventAction") == "registration" and event.get("eventDate"):
            date = event["eventDate"]
            return Collection([Evidence("domain registration", f"The registry records {name} registered on {date}; this dates the domain, not the company.", source)])
    registry = REGISTRY_PREFIX.get(name.rsplit(".", 1)[-1])
    hint = f" Manual registry lookup: {registry}" if registry else ""
    return Collection(notes=[f"RDAP did not supply a registration date for {name}." + hint])


def archive(http, url):
    name = registrable(url)
    source = ARCHIVE + "/cdx/search/cdx?" + urlencode({
        "url": name + "/", "matchType": "domain", "output": "json",
        "filter": "statuscode:200", "fl": "timestamp,original", "limit": 5,
    })
    rows = json_body(http.get(source), [])
    if not (isinstance(rows, list) and len(rows) >= 2):
        return Collection(notes=[f"No accessible Wayback index results for {name}; archive coverage is inconclusive."])
    out = Collection()
    for row in rows[1:]:
        if not isinstance(row, list) or len(row) != 2:
            continue
        stamp, original = row
        if not isinstance(stamp, str) or not re.fullmatch(r"\d{14}", stamp) or not isinstance(original, str) or not original.startswith(("http://", "https://")):
            continue
        link = f"{ARCHIVE}/web/{stamp}/{original}"
        date = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
        out.evidence.append(Evidence("archived page", f"Wayback indexes an HTTP 200 capture of {original} on {date}; earliest usable result in the sampled index, not an incorporation date.", link))
        snapshot = http.get(link)
        if snapshot and snapshot.status == 200 and "html" in snapshot.content_type:
            soup = BeautifulSoup(snapshot.body, "html.parser")
            for tag in soup.select("script, style, #wm-ipp, #wm-ipp-base"):
                tag.decompose()
            text = clean(soup.get_text(" ", strip=True), 30_000)
            match = re.search(r"\b\d[\d,.]*\+?\s+(?:(?:million|billion)\s+)?(?:users|clients|customers|downloads)\b", text, re.I)
            if match:
                excerpt = clean(text[max(0, match.start()-45):match.end()+65])
                out.evidence.append(Evidence("archived traction claim", f'Archived page text from {date}: “{excerpt}”', link))
        break
    if not out.evidence:
        out.notes.append(f"No usable archived page link for {name}.")
    return out


def search(topic, terms, identity, http, key):
    query = f"{identity} {terms}"
    response = http.request(
        "https://api.tavily.com/search",
        payload={"query": query[:395], "search_depth": "basic", "max_results": 4},
        headers={"Authorization": f"Bearer {key}"},
    )
    data = json_body(response, None)
    if not isinstance(data, dict):
        return [], f"Search unavailable for {topic} ({response.status if response else 'request failure'})."
    results = []
    for row in data.get("results", []):
        source = row.get("url", "")
        try:
            parts = urlsplit(source)
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
                continue
        except ValueError:
            continue
        title, excerpt = clean(row.get("title"), 140), clean(row.get("content"), 850)
        if title or excerpt:
            results.append(Evidence(f"search excerpt: {topic}", f"{title} — {excerpt}", source))
    return results, ""


def github(http, evidence):
    for item in evidence:
        if domain(item.source_url) != "github.com":
            continue
        path = urlsplit(item.source_url).path.strip("/").split("/")
        if len(path) < 2 or not all(re.fullmatch(r"[a-zA-Z0-9_.-]+", slug) for slug in path[:2]):
            continue
        repo = "/".join(path[:2])
        api = "https://api.github.com/repos/" + repo
        row = json_body(http.get(api), {})
        if not isinstance(row, dict) or not row.get("full_name"):
            continue
        source = row.get("html_url", f"https://github.com/{repo}")
        claim = f"Repository {repo} has {row.get('stargazers_count', 'unknown')} stars; archived: {bool(row.get('archived'))}."
        out = [Evidence("repository metadata (verify vendor relationship)", claim, source)]
        commits = json_body(http.get(api + "/commits?per_page=1"), [])
        if isinstance(commits, list) and commits:
            commit = commits[0]
            date = commit.get("commit", {}).get("committer", {}).get("date")
            if date and commit.get("html_url"):
                out.append(Evidence("repository commit (verify vendor relationship)", f"Latest default-branch commit returned for {repo}: {date}.", commit["html_url"]))
        return out
    return []


def collect_search(http, url, identity):
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return Collection(notes=["Independent web search skipped: TAVILY_API_KEY not set."])
    name = registrable(url)
    out = Collection()
    topics = list(TOPICS.items())
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(search, topic, terms, f"{name} {identity}".strip(), http, key)
            for topic, terms in topics
        ]
        seen = set()
        for future in futures:
            results, note = future.result()
            if note:
                out.notes.append(note)
            for item in results:
                if item.source_url not in seen:
                    seen.add(item.source_url)
                    out.evidence.append(item)
    out.evidence.extend(github(http, out.evidence))
    return out
