# -*- coding: utf-8 -*-
"""HMZ Video Studio Pro — remote catalog and Gumroad storefront parsing.

The GitHub JSON catalog remains the preferred source.  Gumroad is used as a
fallback, because creator profile pages can be custom HTML and their markup is
not stable enough for a single regular expression.
"""

import html as html_lib
import json
import os
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

DEFAULT_PRODUCTS_JSON_URL = "https://raw.githubusercontent.com/hmz-bytes/hmz-products-catalog/refs/heads/main/products.json"
DEFAULT_GUMROAD_PROFILE_URL = "https://hmzbytes.gumroad.com/"
CACHE_TTL_SECONDS = 3600
MAX_CATALOG_BYTES = 5 * 1024 * 1024
MAX_EMBEDDED_JSON_NODES = 100_000

FALLBACK_PRODUCTS: List[Dict[str, str]] = [
    {
        "id": "smart-file-hub",
        "name_ar": "Smart File Hub — مركز إدارة وتنظيم الملفات الذكي",
        "name_en": "Smart File Hub — Intelligent File Organizer & Batch Processor",
        "desc_ar": "تنظيم وفرز وإعادة تسمية وفحص آلاف الملفات والمجلدات تلقائياً.",
        "desc_en": "Organize, deduplicate, batch-rename, and inspect thousands of files effortlessly.",
        "price": "$12 / 350 EGP",
        "url": "https://hmzbytes.gumroad.com/l/smart-file-hub",
    },
    {
        "id": "pdf-toolkit-pro",
        "name_ar": "PDF Toolkit Pro — استوديو أدوات الـ PDF المتكامل",
        "name_en": "PDF Toolkit Pro — Complete Offline PDF Suite",
        "desc_ar": "دمج، تقسيم، ضغط، تشفير، واستخراج النصوص والصور من ملفات PDF محلياً.",
        "desc_en": "Merge, split, compress, watermark, encrypt, and extract PDF content offline.",
        "price": "$14 / 400 EGP",
        "url": "https://hmzbytes.gumroad.com/l/pdf-toolkit-pro",
    },
    {
        "id": "omnicalc-studio",
        "name_ar": "OmniCalc Studio — الحاسبة الهندسية والمالية الشاملة",
        "name_en": "OmniCalc Studio — Engineering, Financial & Unit Suite",
        "desc_ar": "حاسبات مالية وهندسية وإحصائية وتحويل وحدات مع تقارير قابلة للتصدير.",
        "desc_en": "Comprehensive financial, scientific, and engineering calculators with exportable reports.",
        "price": "$10 / 300 EGP",
        "url": "https://hmzbytes.gumroad.com/l/omnicalc-studio",
    },
]


def _get_cache_path(custom_dir: Optional[Path] = None) -> Path:
    if custom_dir is not None:
        base = Path(custom_dir)
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home() / ".config")
        base = Path(appdata) / "HMZVideoStudioPro"
    base.mkdir(parents=True, exist_ok=True)
    return base / "products_cache.json"


def _clean_text(value: Any, limit: int = 240) -> str:
    """Convert HTML-ish/untrusted display text to a compact, plain string."""
    if value is None:
        return ""
    text = html_lib.unescape(str(value))
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = " ".join(text.split())
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    return text[:limit]


def _canonical_product_url(base: str, raw_url: Any) -> str:
    """Resolve a Gumroad product URL and reject non-product/non-web links."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        return ""
    raw_url = html_lib.unescape(raw_url.strip())
    if raw_url.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    full = urljoin(base, raw_url)
    try:
        parts = urlsplit(full)
    except ValueError:
        return ""
    if parts.scheme.lower() != "https" or not parts.netloc:
        return ""
    try:
        base_host = (urlsplit(base).hostname or "").lower()
        host = (parts.hostname or "").lower()
    except ValueError:
        return ""
    if not (host == base_host or host == "gumroad.com" or host.endswith(".gumroad.com")):
        return ""
    path = re.sub(r"/+$", "", parts.path or "")
    # Gumroad product pages have /l/<permalink>; allow any host so custom
    # domains continue to work, but do not turn arbitrary links into cards.
    if not re.search(r"(?:^|/)l/[A-Za-z0-9_-]+(?:/|$)", path):
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _product_price(record: Dict[str, Any]) -> str:
    for key in ("formatted_price", "price_formatted", "display_price", "formattedPrice"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_text(value, 40)
    cents = record.get("price_cents", record.get("priceCents"))
    if isinstance(cents, (int, float)) and not isinstance(cents, bool):
        currency = str(record.get("currency") or record.get("currency_code") or record.get("currencyCode") or "USD").upper()
        symbol = {"USD": "$", "EUR": "€", "GBP": "£", "EGP": "EGP "}.get(currency, currency + " " if currency else "")
        return "Free" if cents == 0 else f"{symbol}{cents / 100:,.2f}".replace(".00", "")
    # Some custom page data uses a string-valued `price` already formatted for
    # display.  Numeric `price` is deliberately ignored because Gumroad's
    # public payloads have used cents in more than one field historically.
    price = record.get("price")
    if isinstance(price, str) and re.search(r"(?:\$|€|£|\bfree\b|\bUSD\b|\bEGP\b)", price, re.I):
        return _clean_text(price, 40)
    offers = record.get("offers")
    if isinstance(offers, dict):
        offer_price = offers.get("price")
        currency = str(offers.get("priceCurrency") or "").upper()
        if isinstance(offer_price, (int, float)) and not isinstance(offer_price, bool):
            symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " " if currency else "")
            return f"{symbol}{offer_price:,.2f}".replace(".00", "")
        if isinstance(offer_price, str) and offer_price.strip():
            symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "")
            return _clean_text((symbol + offer_price) if symbol else offer_price, 40)
    return ""


def _record_to_product(record: Dict[str, Any], base: str) -> Optional[Dict[str, str]]:
    raw_url = (record.get("url") or record.get("long_url") or record.get("permalink_url")
               or record.get("product_url") or record.get("productUrl"))
    if not raw_url:
        # Gumroad's current gumroad-data block may expose only the product
        # permalink, not a full URL.  Reconstruct the public product route.
        permalink = (record.get("permalink") or record.get("custom_permalink")
                     or record.get("short_permalink") or record.get("shortPermalink"))
        if isinstance(permalink, str) and permalink.strip():
            permalink = permalink.strip().strip("/")
            raw_url = permalink if re.search(r"(?:^|/)l/", permalink) else f"/l/{permalink.rsplit('/', 1)[-1]}"
    url = _canonical_product_url(base, raw_url)
    if not url:
        return None
    name = record.get("name") or record.get("title") or record.get("product_name") or record.get("display_name")
    if not isinstance(name, str) or not _clean_text(name, 100):
        return None
    name = _clean_text(name, 90)
    desc = _clean_text(record.get("description") or record.get("short_description") or record.get("summary") or "", 220)
    slug = urlsplit(url).path.rsplit("/", 1)[-1]
    return {
        "id": str(record.get("id") or slug),
        "name_ar": name,
        "name_en": name,
        "desc_ar": desc or "تطبيق سطح مكتب احترافي من سلسلة HMZ-Bytes",
        "desc_en": desc or "Professional desktop application by HMZ-Bytes",
        "price": _product_price(record),
        "url": url,
    }


class _GumroadHTMLParser(HTMLParser):
    """Tolerant HTML collector for embedded page JSON and nested product links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_payloads: List[str] = []
        self.json_scripts: List[str] = []
        self.price_scripts: List[str] = []
        self.links: List[Dict[str, str]] = []
        self._anchors: List[Dict[str, Any]] = []
        self._script_parts: Optional[List[str]] = None
        self._script_is_json = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr = {str(k).lower(): (v or "") for k, v in attrs}
        page_data = attr.get("data-page")
        if page_data:
            self.page_payloads.append(page_data)

        # Some generated Gumroad pages and custom themes expose product metadata
        # in data-* attributes rather than in the old data-page blob.
        for name_key in ("data-product", "data-product-json", "data-page-props"):
            payload = attr.get(name_key)
            if payload:
                self.page_payloads.append(payload)

        if tag.lower() == "script":
            script_type = attr.get("type", "").lower()
            script_id = attr.get("id", "").lower()
            self._script_is_json = (
                "json" in script_type
                or script_id in ("__next_data__", "__nuxt_data__", "gumroad-data", "gumroad-prices")
            )
            self._script_id = script_id
            self._script_parts = [] if self._script_is_json else None

        if tag.lower() == "a":
            self._anchors.append({
                "href": attr.get("href", ""),
                "title": attr.get("title", ""),
                "aria_label": attr.get("aria-label", ""),
                "data_name": attr.get("data-product-name", "") or attr.get("data-name", ""),
                "description": attr.get("data-description", ""),
                "parts": [],
                "alts": [],
            })
        elif tag.lower() == "img" and self._anchors:
            alt = attr.get("alt", "").strip()
            if alt:
                for anchor in self._anchors:
                    anchor["alts"].append(alt)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._anchors:
            anchor = self._anchors.pop()
            text = _clean_text(" ".join(anchor["parts"]), 500)
            alt = _clean_text(" ".join(anchor["alts"]), 120)
            self.links.append({
                "href": anchor["href"],
                "title": anchor["title"],
                "aria_label": anchor["aria_label"],
                "data_name": anchor["data_name"],
                "description": anchor["description"],
                "text": text,
                "alt": alt,
            })
        elif tag.lower() == "script" and self._script_parts is not None:
            payload = "".join(self._script_parts).strip()
            if payload:
                if getattr(self, "_script_id", "") == "gumroad-prices":
                    self.price_scripts.append(payload)
                else:
                    self.json_scripts.append(payload)
            self._script_parts = None
            self._script_is_json = False
            self._script_id = ""

    def handle_data(self, data: str) -> None:
        if self._script_parts is not None:
            self._script_parts.append(data)
        for anchor in self._anchors:
            anchor["parts"].append(data)

    def handle_entityref(self, name: str) -> None:  # pragma: no cover - handled by convert_charrefs
        self.handle_data(html_lib.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:  # pragma: no cover - handled by convert_charrefs
        self.handle_data(html_lib.unescape(f"&#{name};"))


def _walk_embedded_products(value: Any, base: str, out: List[Dict[str, str]], seen: set[str], budget: List[int]) -> None:
    """Recursively inspect Gumroad's embedded JSON without assuming a fixed schema."""
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if isinstance(value, dict):
        product = _record_to_product(value, base)
        if product:
            url = product["url"]
            if url not in seen:
                seen.add(url)
                out.append(product)
        for child in value.values():
            _walk_embedded_products(child, base, out, seen, budget)
    elif isinstance(value, list):
        for child in value:
            _walk_embedded_products(child, base, out, seen, budget)


def _walk_gumroad_price_map(value: Any, prices: Dict[str, str], budget: List[int]) -> None:
    """Read price records keyed by product permalink from Gumroad's gumroad-prices JSON."""
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if isinstance(value, dict):
        permalink = (value.get("permalink") or value.get("custom_permalink")
                     or value.get("short_permalink") or value.get("shortPermalink"))
        display_price = _product_price(value)
        if isinstance(permalink, str) and display_price:
            prices[permalink.strip("/").rsplit("/", 1)[-1]] = display_price
        for key, child in value.items():
            if isinstance(key, str) and isinstance(child, dict):
                child_price = _product_price(child)
                if child_price:
                    prices[key.strip("/").rsplit("/", 1)[-1]] = child_price
            elif isinstance(key, str) and isinstance(child, str) and re.search(r"(?:\$|€|£|\bfree\b|\bUSD\b|\bEGP\b)", child, re.I):
                prices[key.strip("/").rsplit("/", 1)[-1]] = _clean_text(child, 40)
            _walk_gumroad_price_map(child, prices, budget)
    elif isinstance(value, list):
        for child in value:
            _walk_gumroad_price_map(child, prices, budget)


def _parse_gumroad_public_html(html_text: str, base_url: str = DEFAULT_GUMROAD_PROFILE_URL) -> List[Dict[str, str]]:
    """Extract products from a public Gumroad profile.

    Strategy matches the working OmniCalc reference: embedded page data first,
    then public ``/l/<permalink>`` anchors.  Unlike the original regex-only
    scraper, this parser supports HTML entities, relative links, nested markup,
    JSON-LD, and attribute ordering without relying on one exact card template.
    """
    if not isinstance(html_text, str) or not html_text.strip():
        return []

    parser = _GumroadHTMLParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        # HTMLParser is intentionally tolerant, but malformed markup should not
        # prevent falling back to whatever it managed to collect.
        pass

    products: List[Dict[str, str]] = []
    seen: set[str] = set()
    budget = [MAX_EMBEDDED_JSON_NODES]

    for payload in parser.page_payloads + parser.json_scripts:
        candidates = [payload, html_lib.unescape(payload)]
        for candidate in candidates:
            try:
                decoded = json.loads(candidate)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            _walk_embedded_products(decoded, base_url, products, seen, budget)
            break
        if budget[0] <= 0:
            break

    # Gumroad's current custom-profile format separates display prices into
    # `gumroad-prices`; join them to products by their public permalink.
    price_map: Dict[str, str] = {}
    for payload in parser.price_scripts:
        try:
            price_data = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        _walk_gumroad_price_map(price_data, price_map, budget)
    for product in products:
        if not product.get("price"):
            slug = urlsplit(product["url"]).path.rsplit("/", 1)[-1]
            product["price"] = price_map.get(slug, "")

    # As in OmniCalc, use the visible product links when the embedded JSON is
    # absent or does not contain product entries.
    if not products:
        ignored_cta = {"buy", "buy now", "get it", "learn more", "view product", "view details", "explore product", "shop now", "purchase", "open", "download"}
        for anchor in parser.links:
            url = _canonical_product_url(base_url, anchor.get("href"))
            if not url or url in seen:
                continue
            name = (anchor.get("data_name") or anchor.get("aria_label") or anchor.get("title")
                    or anchor.get("text") or anchor.get("alt") or "")
            name = _clean_text(name, 90)
            if not name or name.casefold() in ignored_cta:
                name = _clean_text(anchor.get("alt") or urlsplit(url).path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " "), 90)
            if not name:
                continue
            desc = _clean_text(anchor.get("description", ""), 220)
            seen.add(url)
            slug = urlsplit(url).path.rsplit("/", 1)[-1]
            products.append({
                "id": slug,
                "name_ar": name,
                "name_en": name,
                "desc_ar": desc or "تطبيق سطح مكتب احترافي من سلسلة HMZ-Bytes",
                "desc_en": desc or "Professional desktop application by HMZ-Bytes",
                "price": "",
                "url": url,
            })

    return products


def _read_response_text(response: Any, limit: int = MAX_CATALOG_BYTES) -> Tuple[str, str]:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Remote catalog is larger than the allowed size")
    headers = getattr(response, "headers", None)
    content_type = headers.get("Content-Type", "") if headers is not None else ""
    charset = "utf-8"
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset() or charset
    return raw.decode(charset, errors="replace"), content_type


def load_cached_products_catalog(custom_cache_dir: Optional[Path] = None) -> Tuple[List[Dict[str, str]], bool]:
    """Return the last known catalog without performing network I/O."""
    try:
        cache_file = _get_cache_path(custom_cache_dir)
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        items = cached.get("products", [])
        if isinstance(items, list) and items:
            return items, False
    except Exception:
        pass
    return list(FALLBACK_PRODUCTS), False


def _write_cache(cache_file: Path, products: List[Dict[str, str]]) -> None:
    """Write the cache atomically so an interrupted write cannot corrupt it."""
    payload = {"timestamp": time.time(), "products": products}
    temp_file = cache_file.with_suffix(cache_file.suffix + ".tmp")
    try:
        temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_file, cache_file)
    finally:
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass


def load_products_catalog(
    products_url: str = DEFAULT_PRODUCTS_JSON_URL,
    gumroad_url: str = DEFAULT_GUMROAD_PROFILE_URL,
    force_refresh: bool = False,
    custom_cache_dir: Optional[Path] = None,
    timeout: float = 4.0,
) -> Tuple[List[Dict[str, str]], bool]:
    """Load catalog data, preferring the signed-off static JSON feed.

    Returns ``(products, is_live)``.  A valid fresh cache is returned without a
    network request; stale cache is retained as the final offline fallback.
    """
    cache_file = _get_cache_path(custom_cache_dir)

    if not force_refresh and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            ts = float(cached.get("timestamp", 0))
            items = cached.get("products", [])
            if (time.time() - ts) < CACHE_TTL_SECONDS and isinstance(items, list) and items:
                return items, False
        except Exception:
            pass

    common_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 HMZVideoStudioPro/1.1",
        "Accept": "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.7",
    }

    def fetch_gumroad(profile_url: str) -> List[Dict[str, str]]:
        req = urllib.request.Request(profile_url, headers=common_headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html_text, _content_type = _read_response_text(response)
            final_url = getattr(response, "geturl", lambda: profile_url)() or profile_url
        return _parse_gumroad_public_html(html_text, final_url)

    # When the user points the product URL directly at Gumroad, treat it as a
    # storefront rather than first trying to decode its HTML as JSON. Keep the
    # static JSON feed as the default/primary source for the normal setup.
    configured_is_gumroad = False
    if products_url:
        try:
            configured_parts = urlsplit(products_url)
            host = (configured_parts.hostname or "").lower()
            configured_is_gumroad = (
                (host == "gumroad.com" or host.endswith(".gumroad.com"))
                and not re.search(r"(?:^|/)l/", configured_parts.path or "")
            )
        except ValueError:
            configured_is_gumroad = False

    if configured_is_gumroad:
        try:
            parsed = fetch_gumroad(products_url)
            if parsed:
                _write_cache(cache_file, parsed)
                return parsed, True
        except Exception:
            pass

    # Preferred catalog: small static JSON hosted separately from the app.
    if products_url and not configured_is_gumroad:
        try:
            req = urllib.request.Request(products_url, headers={**common_headers, "Accept": "application/json,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data_text, _content_type = _read_response_text(resp)
            data = json.loads(data_text)
            products = data.get("products", data.get("items", data)) if isinstance(data, dict) else data
            if isinstance(products, list) and products:
                _write_cache(cache_file, products)
                return products, True
        except Exception:
            pass

    # Gumroad storefront fallback: embedded data-page JSON, then visible /l/ links.
    if gumroad_url and (not configured_is_gumroad or gumroad_url.rstrip("/") != products_url.rstrip("/")):
        try:
            parsed = fetch_gumroad(gumroad_url)
            if parsed:
                _write_cache(cache_file, parsed)
                return parsed, True
        except Exception:
            pass

    # 3) Stale cache remains more useful than an empty store when offline.
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            items = cached.get("products", [])
            if isinstance(items, list) and items:
                return items, False
        except Exception:
            pass

    return FALLBACK_PRODUCTS, False

