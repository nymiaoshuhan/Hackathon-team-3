#!/usr/bin/env python3
"""Research vendor URLs and emit buyer verdicts."""

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv

from evidence import Collection, Http
from judge import LABELS, judge
from research import archive, collect_search, registration
from vendor_site import collect_site, domain


COLUMNS = ("url", "product", "vendor", "overall", "confidence", "green_flags",
           "yellow_flags", "red_flags", "reasoning")


def normalize(url):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {"https", "http"} or not parts.hostname or "." not in parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.port not in {None, 80, 443} or any(ch.isspace() for ch in url)):
            raise ValueError()
    except ValueError:
        raise ValueError(f"Expected a public HTTP(S) vendor URL: {url!r}") from None
    return url


def identity_hint(url):
    path = unquote(urlsplit(url).path)
    bits = [
        re.sub(r"[-_]+", " ", bit)
        for bit in path.split("/") if len(bit) > 3 and bit.lower() not in {
            "overview", "index", "products", "product", "solutions", "software", "for-individuals"
        }
    ]
    return " ".join(bits[-2:])[:110]


def run_vendor(raw_url, http, *, screenshot=True, excluded_row=None, audit=False):
    url = normalize(raw_url)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {
            "site": pool.submit(collect_site, http, url, screenshot),
            "RDAP": pool.submit(registration, http, url),
            "Wayback": pool.submit(archive, http, url),
            "web search": pool.submit(collect_search, http, url, identity_hint(url)),
        }
        bundle = Collection()
        for name, future in jobs.items():
            try:
                output = future.result()
            except (ValueError, RuntimeError, OSError) as error:
                bundle.notes.append(f"{name} collector unavailable ({type(error).__name__}).")
                continue
            bundle.evidence.extend(output.evidence)
            bundle.notes.extend(output.notes)
            bundle.screenshot = output.screenshot or bundle.screenshot
            bundle.product = output.product or bundle.product
            bundle.vendor = output.vendor or bundle.vendor
    bundle.product = bundle.product or identity_hint(url) or domain(url)
    bundle.vendor = bundle.vendor or domain(url)
    result, mode, note = judge(url, bundle, excluded_row)
    if note:
        bundle.notes.append(note)
    result = {"url": url, **result, "judge_mode": mode, "coverage_notes": bundle.notes}
    for color in LABELS:
        result[f"{color.lower()}_flags"] = [
            {"claim": r["claim"], "source_url": r["source_url"]} for r in result["reasons"]
            if r["severity"] == color
        ]
    if bundle.screenshot:
        result["homepage_screenshot"] = str(bundle.screenshot)
    if audit:
        result["evidence"] = [asdict(item) for item in bundle.evidence]
    return result


def csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_results(path, rows):
    path = Path(path)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    if path.suffix.lower() != ".csv":
        raise ValueError("Output filename must end in .csv or .json.")
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            record = {name: row[name] for name in COLUMNS}
            for name in ("green_flags", "yellow_flags", "red_flags"):
                record[name] = "\n".join(f"{flag['claim']} — {flag['source_url']}" for flag in row[name])
            writer.writerow({name: csv_cell(value) for name, value in record.items()})


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def common_args(parser):
    parser.add_argument("--workers", type=positive_int, default=4, help="concurrent vendors (default 4)")
    parser.add_argument("--cache-dir", default="cache")
    parser.add_argument("--no-screenshot", action="store_true", help="skip routine screenshots, retaining JS fallback")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?")
    parser.add_argument("--input", type=Path, help="text file with one vendor URL per line")
    parser.add_argument("--out", type=Path, help=".json or .csv output path (default: stdout JSON)")
    parser.add_argument("--evidence", action="store_true", help="include all collected evidence in JSON")
    common_args(parser)
    args = parser.parse_args()
    if bool(args.url) == bool(args.input):
        parser.error("provide a URL or --input")
    if args.out and args.out.suffix.lower() not in {".csv", ".json"}:
        parser.error("--out must end in .csv or .json")
    try:
        urls = ([args.url] if args.url else [
            line.strip() for line in args.input.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ])
        urls = list(dict.fromkeys(map(normalize, urls)))
        if not urls:
            parser.error("--input contains no vendor URLs")
        http = Http(args.cache_dir)
        with ThreadPoolExecutor(max_workers=min(12, args.workers)) as pool:
            results = list(pool.map(
                lambda url: run_vendor(url, http, screenshot=not args.no_screenshot, audit=args.evidence), urls
            ))
        if args.out:
            write_results(args.out, results)
            print(f"Wrote {len(results)} verdict(s) to {args.out}", file=sys.stderr)
        else:
            print(json.dumps(results[0] if args.url else results, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
