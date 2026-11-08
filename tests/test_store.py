# -*- coding: utf-8 -*-
import html
import json
import unittest
import tempfile
from unittest.mock import patch

import video_studio_store
from video_studio_store import _parse_gumroad_public_html, load_products_catalog


class TestGumroadCatalogParser(unittest.TestCase):
    def test_embedded_data_page_json_matches_reference_strategy(self):
        payload = {
            "props": {
                "products": [
                    {
                        "name": "Smart File Hub",
                        "url": "https://hmzbytes.gumroad.com/l/smart-file-hub",
                        "description": "Organize files <b>quickly</b>.",
                        "price_cents": 1200,
                    },
                    {
                        "title": "PDF Toolkit Pro",
                        "long_url": "/l/pdf-toolkit-pro?layout=profile",
                        "description": "PDF tools for Windows",
                        "formatted_price": "$14",
                    },
                    # Duplicate product should not produce a second card.
                    {
                        "name": "Smart File Hub Duplicate",
                        "permalink_url": "https://hmzbytes.gumroad.com/l/smart-file-hub",
                    },
                ]
            }
        }
        html_doc = f'<div data-page="{html.escape(json.dumps(payload), quote=True)}"></div>'

        products = _parse_gumroad_public_html(html_doc, "https://hmzbytes.gumroad.com/")

        self.assertEqual([p["id"] for p in products], ["smart-file-hub", "pdf-toolkit-pro"])
        self.assertEqual(products[0]["name_en"], "Smart File Hub")
        self.assertEqual(products[0]["desc_en"], "Organize files quickly.")
        self.assertEqual(products[0]["price"], "$12")
        self.assertEqual(products[1]["price"], "$14")
        self.assertTrue(all(p["url"].startswith("https://") for p in products))

    def test_nested_and_relative_product_links(self):
        html_doc = '''
        <main>
          <a class="product-card" data-name="Video Studio Pro" href="/l/video-studio-pro?utm_source=profile">
            <div><h2>Video Studio Pro</h2><span>Professional editor</span></div>
          </a>
          <a href="https://hmzbytes.gumroad.com/l/omnicalc-studio" class="card">
            <img alt="OmniCalc Studio" src="cover.png"><span>Explore product</span>
          </a>
          <a href="/about">About HMZ</a>
          <a href="mailto:support@example.com">Support</a>
        </main>
        '''

        products = _parse_gumroad_public_html(html_doc, "https://hmzbytes.gumroad.com/")

        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["name_en"], "Video Studio Pro")
        self.assertEqual(products[0]["url"], "https://hmzbytes.gumroad.com/l/video-studio-pro")
        self.assertEqual(products[1]["name_en"], "OmniCalc Studio")
        self.assertEqual(products[1]["id"], "omnicalc-studio")

    def test_current_gumroad_data_and_prices_script_blocks(self):
        catalogue = {
            "products_total": 1,
            "products": [{
                "permalink": "video-studio-pro",
                "name": "HMZ Video Studio Pro",
                "description": "Local desktop video editor",
            }],
            "posts": [],
        }
        prices = {
            "video-studio-pro": {"price": "$19", "currency": "USD"}
        }
        html_doc = (
            '<script id="gumroad-data">' + json.dumps(catalogue) + '</script>'
            '<script id="gumroad-prices">' + json.dumps(prices) + '</script>'
        )

        products = _parse_gumroad_public_html(html_doc, "https://hmzbytes.gumroad.com/")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name_en"], "HMZ Video Studio Pro")
        self.assertEqual(products[0]["url"], "https://hmzbytes.gumroad.com/l/video-studio-pro")
        self.assertEqual(products[0]["price"], "$19")

    def test_json_ld_is_a_second_embedded_data_source(self):
        payload = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "HMZ Utility",
            "url": "https://hmzbytes.gumroad.com/l/hmz-utility",
            "description": "Useful desktop tool",
            "offers": {"price": "8.00", "priceCurrency": "USD"},
        }
        html_doc = '<script type="application/ld+json">' + json.dumps(payload) + '</script>'

        products = _parse_gumroad_public_html(html_doc, "https://hmzbytes.gumroad.com/")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name_en"], "HMZ Utility")
        self.assertIn("hmz-utility", products[0]["url"])

    def test_empty_or_unrelated_markup_returns_no_products(self):
        self.assertEqual(_parse_gumroad_public_html(""), [])
        self.assertEqual(_parse_gumroad_public_html('<a href="/about">About</a>'), [])

    def test_external_or_insecure_product_links_are_ignored(self):
        html_doc = """
        <a href="https://attacker.example/l/not-hmz">Unexpected external</a>
        <a href="http://hmzbytes.gumroad.com/l/insecure">Insecure link</a>
        """
        self.assertEqual(_parse_gumroad_public_html(html_doc, "https://hmzbytes.gumroad.com/"), [])

    def test_slug_fallback_for_cta_only_anchor(self):
        products = _parse_gumroad_public_html(
            '<a href="/l/smart-file-hub">Buy now</a>',
            "https://hmzbytes.gumroad.com/",
        )
        self.assertEqual(products[0]["name_en"], "smart file hub")

    def test_configured_gumroad_url_is_fetched_as_html_not_json(self):
        payload = {
            "props": {"products": [{
                "name": "Video Studio Pro",
                "url": "/l/video-studio-pro",
                "description": "A desktop video editor",
            }]}
        }
        html_doc = f'<div data-page="{html.escape(json.dumps(payload), quote=True)}"></div>'

        class FakeResponse:
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit=-1):
                return html_doc.encode("utf-8")

            def geturl(self):
                return "https://hmzbytes.gumroad.com/"

        with tempfile.TemporaryDirectory() as cache_dir:
            with patch.object(video_studio_store.urllib.request, "urlopen", return_value=FakeResponse()) as opener:
                products, is_live = load_products_catalog(
                    products_url="https://hmzbytes.gumroad.com/",
                    gumroad_url="https://hmzbytes.gumroad.com/",
                    force_refresh=True,
                    custom_cache_dir=cache_dir,
                )

        self.assertTrue(is_live)
        self.assertEqual(products[0]["name_en"], "Video Studio Pro")
        self.assertEqual(opener.call_count, 1)
        self.assertIn("text/html", opener.call_args.args[0].headers.get("Accept", ""))


if __name__ == "__main__":
    unittest.main()
