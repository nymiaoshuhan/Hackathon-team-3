import base64
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from agent import COLUMNS, identity_hint, normalize, run_vendor, write_results
from batch import bounded_vendor
from customers import inspect_customer
from evidence import Collection, Evidence, Http, Response, public_url
from judge import documented_blocker, judge, model_request, pending_only, provider_for, purchase_caution, validate, verify_claims, vote_verdict
from research import corroborate_records
from vendor_site import collect_site, inspect_privacy_document


class FixtureHttp:
    def __init__(self, responses):
        self.responses = responses
        self.visited = []

    def get(self, url, *, crawl=False, binary=False):
        self.visited.append((url, crawl))
        return self.responses.get(url)


class AgentTests(unittest.TestCase):
    def test_privacy_document_gap_reaches_regulated_product_verdict(self):
        url = "https://example.org/privacy.docx"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("word/document.xml", '<doc xmlns:w="urn:word"><w:t>Account FAQ</w:t>'
                            '<w:t>' + "A password reset is available by email. " * 35 + '</w:t></doc>')
        http = FixtureHttp({url: Response(url, 200, "application/zip", base64.b64encode(stream.getvalue()).decode())})
        collection = Collection()
        inspect_privacy_document(http, collection, url)
        self.assertEqual(collection.evidence[0].kind, "inspected privacy artifact gap")
        self.assertEqual(documented_blocker("https://example.org", collection), ([], ""))
        collection.evidence.append(Evidence("vendor overview", "A tool for financial institutions.", "https://example.org"))
        reasons, _ = documented_blocker("https://example.org", collection)
        self.assertEqual((reasons[0]["severity"], reasons[0]["source_url"]), ("Red", url))

    def test_pending_litigation_is_not_a_final_action(self):
        source = "https://example.org/complaint"
        verdict = {"reasons": [{"severity": "Red", "source_url": source, "claim": "Lawsuit filed"}]}
        self.assertTrue(pending_only(verdict, [Evidence("search excerpt: enforcement", "Agency alleges violations", source)]))
        self.assertFalse(pending_only(verdict, [Evidence("search excerpt: enforcement", "Agency complaint resolved by final order", source)]))
        evidence = [
            Evidence("search excerpt: enforcement", "Agency alleges violations", source),
            Evidence("search excerpt: enforcement", "FTC order requires Example to pay.", "https://www.ftc.gov/news"),
            Evidence("search excerpt: enforcement", "Example agreed to pay $7 to settle the complaint.", "https://legal.example/updates"),
        ]
        self.assertFalse(pending_only(verdict, evidence, "https://example.org"))
        self.assertTrue(pending_only(verdict, evidence, "https://unrelated.org"))

    def test_timed_out_worker_returns_yellow_without_evidence(self):
        url = "https://example.org/"
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "slow_worker.py"
            script.write_text("import time\ntime.sleep(10)\n")
            result, stats = bounded_vendor(script, url, 0.1, directory, False, False)
        self.assertEqual((result["url"], result["overall"], result["reasons"]), (url, "Yellow", []))
        self.assertIn("Insufficient evidence", result["reasoning"])
        self.assertLess(result["elapsed_seconds"], 3)
        self.assertEqual(stats, {})

    def test_product_identity_stays_separate_from_root(self):
        root = "https://example.org/"
        url = root + "products/widget"
        docs = root + "docs"
        target = root + "pricing"
        http = FixtureHttp({
            url: Response(url, 200, "text/html", (
                '<title>Widget Pro</title><meta property="og:site_name" content="Acme">'
                '<body><a href="/docs">Docs</a><a href="/pricing">Pricing</a>'
                + " Product marketing describes what the widget actually does." * 7 + "</body>"
            )),
            root: Response(root, 200, "text/html", "<title>Acme home</title><footer>Copyright 2003</footer>"),
            docs: Response(docs, 200, "text/html", "<h1>Release notes</h1>Version 4.1, 2026-01-01"),
            target: Response(target, 404, "text/html", ""),
        })
        result = collect_site(http, url, screenshot=False)
        self.assertEqual((result.product, result.vendor), ("Widget Pro", "Acme"))
        self.assertTrue(any(r.kind == "release" and r.source_url == docs for r in result.evidence))
        self.assertTrue(any(r.kind == "dead link" and r.source_url == url for r in result.evidence))
        self.assertTrue(all(crawl for _, crawl in http.visited))

    def test_model_grounding_drops_unknown_link_and_out_of_range_id(self):
        url = "https://example.org/releases"
        evidence = [Evidence("release", "Version 4.1 released.", url)]
        packet = {"overall": "Green", "confidence": 0.77, "reasons": [
            {"severity": "Green", "claim": "Published version 4.1.", "evidence_id": 1},
            {"severity": "Red", "claim": "Invented.", "evidence_id": 2},
            {"severity": "Red", "claim": "Invented.", "evidence_id": 1, "source_url": "https://example.net/"},
        ]}
        self.assertEqual(validate(packet, evidence, Collection())["reasons"], [
            {"severity": "Green", "claim": "Published version 4.1.", "source_url": url},
        ])
        packet["overall"] = "Red"
        with self.assertRaises(ValueError):
            validate(packet, evidence, Collection())

    @patch.dict("os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    @patch("judge.model_request")
    def test_held_out_row_does_not_appear_as_example(self, request):
        verdict = {"overall": "Green", "reasons": [
            {"severity": "Green", "claim": "Published release", "evidence_id": 1},
        ]}
        request.side_effect = lambda *args, **kwargs: (
            {"checks": [{"id": 1, "status": "yes", "quote": "Version 4.1"}]}
            if "system" in kwargs else verdict
        )
        source = "https://example.org/release"
        result, mode, _ = judge(source, Collection([Evidence("release", "Version 4.1", source)]), "15")
        payload = json.loads(request.call_args_list[0].args[1])
        self.assertEqual(mode, "llm")
        self.assertEqual(len(payload["examples"]), 5)
        self.assertNotIn("old-looking open-source", json.dumps(payload["examples"]))
        self.assertEqual(result["reasons"][0]["source_url"], source)

    @patch("judge.model_request")
    def test_majority_vote_selects_a_valid_representative(self, request):
        source = "https://example.org/release"
        evidence = [Evidence("release", "Version 4.1", source)]
        colors = ["Yellow", "Green", "Green"]
        request.side_effect = lambda *args, sample, **kwargs: {
            "overall": colors[sample],
            "reasons": [{"severity": colors[sample], "claim": "Published release", "evidence_id": 1}],
        }
        result = vote_verdict("test-key", "payload", None, None, evidence, Collection(evidence))
        self.assertEqual(result["overall"], "Green")
        self.assertEqual(result["judge_votes"], colors)
        colors[2] = "Red"
        result = vote_verdict("test-key", "payload", None, None, evidence, Collection(evidence))
        self.assertEqual(result["overall"], "Yellow")

    @patch("judge.model_request")
    def test_claim_check_drops_unsupported_and_softens_partial_claims(self, request):
        source = "https://example.org/release"
        request.return_value = {"checks": [
            {"id": 1, "status": "no"},
            {"id": 2, "status": "partial", "quote": "Version 4.1", "source_date": "2025-02-01"},
            {"id": 3, "status": "yes", "quote": "not in source"},
        ]}
        verdict = {"overall": "Red", "confidence": 0.92, "reasons": [
            {"severity": "Red", "claim": "Ends support today.", "source_url": source},
            {"severity": "Green", "claim": "Version 4.1 guarantees support.", "source_url": source},
            {"severity": "Red", "claim": "Vendor closed.", "source_url": source},
        ]}
        evidence = [Evidence("release", "Version 4.1. Published 2025-02-01.", source)]
        result = verify_claims(verdict, evidence, "test-key", None)
        self.assertEqual(result["overall"], "Yellow")
        self.assertEqual([row["status"] for row in result["claim_verification"]], ["no", "partial", "unverified"])
        self.assertEqual(result["reasons"][0]["claim"], "Source reports: “Version 4.1”")
        self.assertEqual(result["reasons"][0]["source_date"], "2025-02-01")

    @patch.dict("os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    @patch("judge.model_request")
    def test_sourced_purchase_caution_does_not_override_green(self, request):
        url = "https://example.org/"
        evidence = [
            Evidence("release", "Version 4.1", url),
            Evidence("ownership claim", "Product formerly known as Old Tool.", url),
        ]
        request.side_effect = lambda *args, **kwargs: ({
            "checks": [
                {"id": 1, "status": "yes", "quote": "formerly known as Old Tool"},
                {"id": 2, "status": "yes", "quote": "Version 4.1"},
            ],
        } if "system" in kwargs else {
            "overall": "Green",
            "reasons": [{"severity": "Green", "claim": "Version 4.1", "evidence_id": 1}],
        })
        result, _, _ = judge(url, Collection(evidence))
        self.assertEqual(result["overall"], "Green")
        self.assertEqual([reason["severity"] for reason in result["reasons"]], ["Yellow", "Green"])

    @patch.dict("os.environ", {}, clear=True)
    def test_keyless_batch_contract(self):
        url = "https://example.org/"
        source = Evidence("copyright", "Copyright 2003 (not a maintenance date)", url)
        empty = Collection()
        with tempfile.TemporaryDirectory() as directory:
            with patch("agent.collect_site", return_value=Collection([source])), \
                 patch("agent.archive", return_value=empty), patch("agent.registration", return_value=empty), \
                 patch("agent.collect_search", return_value=empty):
                row = run_vendor(url, Http(Path(directory) / "cache"), audit=True)
            self.assertEqual((row["overall"], row["judge_mode"]), ("Yellow", "rules"))
            self.assertEqual(row["red_flags"], [])
            self.assertEqual(row["evidence"][0]["source_url"], url)
            path = Path(directory) / "verdicts.csv"
            write_results(path, [row])
            with path.open() as file:
                reader = csv.DictReader(file)
                self.assertEqual(tuple(reader.fieldnames), COLUMNS)
                self.assertEqual(next(reader)["url"], url)

    @patch.dict("os.environ", {}, clear=True)
    def test_provider_inference(self):
        self.assertEqual(provider_for("sk-ant-test"), "anthropic")
        self.assertEqual(provider_for("sk-proj-test"), "openai")
        self.assertEqual(provider_for("opaque"), "nebius")

    @patch.dict("os.environ", {}, clear=True)
    @patch("judge.requests.post")
    def test_model_cache_does_not_bill_same_evidence_twice(self, post):
        reply = Mock()
        reply.json.return_value = {
            "choices": [{"message": {"content": '{"overall":"Yellow"}'}}],
            "usage": {"prompt_tokens": 70, "completion_tokens": 10},
        }
        post.return_value = reply
        with tempfile.TemporaryDirectory() as directory:
            http = Http(directory)
            for _ in range(2):
                self.assertEqual(model_request("opaque", "review vendor", None, http), {"overall": "Yellow"})
            self.assertEqual(post.call_count, 1)
            self.assertEqual(http.usage_summary()["llm_cache_hits"], 1)
            self.assertEqual(http.usage_summary()["llm_input_tokens"], 70)

    def test_cached_search_costs_no_new_credit(self):
        url = "https://api.tavily.com/search"
        payload = {"query": "vendor", "search_depth": "basic"}
        with tempfile.TemporaryDirectory() as directory:
            http = Http(directory)
            key = json.dumps([url, payload, False], sort_keys=True)
            http.write(http.path("http", key), {
                "url": url, "status": 200, "content_type": "application/json", "body": '{"results":[]}',
            })
            with patch.object(http, "session") as session:
                self.assertEqual(http.request(url, payload=payload, tavily=True).json(), {"results": []})
                session.assert_not_called()
            self.assertEqual(http.usage_summary()["tavily_estimated_credits"], 0)
            self.assertEqual(http.usage_summary()["tavily_cache_hits"], 1)

    def test_public_record_verifier_requires_subject_in_source(self):
        url = "https://www.ftc.gov/action"
        http = FixtureHttp({
            url: Response(url, 200, "text/html", "<main><p>Acme Ltd. agreed to pay an FTC settlement.</p>"
                          "<p>Another Company separately reached a settlement.</p></main>"),
        })
        search = [Evidence("search excerpt: enforcement", "Agency announces a settlement", url)]
        records = corroborate_records(http, "acme.example", search)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_url, url)
        self.assertIn("Acme Ltd.", records[0].claim)
        self.assertNotIn("Another Company", records[0].claim)
        self.assertEqual(corroborate_records(http, "unrelated.example", search), [])

    def test_purchase_caution_requires_matching_product_and_vendor_source(self):
        url = "https://example.org/products/old-widget/overview"
        migration = "We recommend customers migrate from Old Widget to our new offering."
        evidence = Evidence("purchase transition", migration, "https://docs.example.org/upgrade")
        unrelated = Evidence("purchase transition", migration, "https://unrelated.org/upgrade")
        self.assertEqual(purchase_caution(url, Collection([unrelated])), ([], ""))
        self.assertEqual(purchase_caution(url.replace("old-widget", "new-widget"), Collection([evidence])), ([], ""))
        flags, _ = purchase_caution(url, Collection([evidence]))
        self.assertEqual(flags[0]["source_url"], evidence.source_url)

    def test_customer_confirmation_requires_own_site_and_an_operating_statement(self):
        url = "https://customer-inc.org/news"
        vendor = "https://product-vendor.net/"
        responses = {
            url: Response(url, 200, "text/html",
                          '<meta property="og:site_name" content="Customer Inc"><article>'
                          '<p>We deployed Product Vendor for our payroll workflow.</p></article>'),
            vendor: Response(vendor, 200, "text/html", "<p>Customer Inc deployed Product Vendor.</p>"),
        }
        http = FixtureHttp(responses)
        self.assertIsNone(inspect_customer(http, vendor, vendor, ["Customer Inc"]))
        self.assertIsNone(inspect_customer(http, url, vendor, ["Wrong company"]))
        verified = inspect_customer(http, url, vendor, ["Customer Inc"])
        self.assertEqual((verified.kind, verified.source_url), ("customer confirms use", url))
        responses[url] = Response(url, 200, "text/html",
                                  '<meta property="og:site_name" content="Customer Inc">'
                                  '<p>Product Vendor participates in our partner program.</p>')
        self.assertEqual(inspect_customer(http, url, vendor, ["Customer Inc"]).kind, "partner role evidence")

    def test_regional_risk_blocker_requires_privileged_access_and_direct_record(self):
        home = "https://example.org/"
        source = "https://example.edu/companies"
        record = Evidence("direct third-party source",
                          "Example Co. continues to provide services in Russia; not publicly disclosed.", source)
        vpn = Evidence("vendor overview", "Access private networks via privileged access.", home)
        docs = Evidence("vendor overview", "Text document editor.", home)
        self.assertEqual(documented_blocker(home, Collection([docs, record])), ([], ""))
        reasons, _ = documented_blocker(home, Collection([vpn, record]))
        self.assertEqual(reasons[0]["source_url"], source)
        self.assertEqual(reasons[0]["severity"], "Red")
        unrelated = Evidence("search excerpt: jurisdiction", "Examples of privileged access", "https://unrelated.org")
        self.assertEqual(documented_blocker(home, Collection([unrelated, record])), ([], ""))

    def test_normalize_and_require_public_http(self):
        self.assertEqual(normalize("example.org/x#y"), "https://example.org/x#y")
        self.assertEqual(identity_hint("https://example.org/products/widget-pro/overview"), "widget pro")
        with self.assertRaises(ValueError):
            normalize("file:///etc/passwd")
        self.assertFalse(public_url("http://127.0.0.1/"))


if __name__ == "__main__":
    unittest.main()
