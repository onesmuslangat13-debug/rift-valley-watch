import json
import re
import html
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin, quote_plus
import requests
import xml.etree.ElementTree as ET

from rift_valley_video_generator import generate_video


# ============================================================
# RIFT VALLEY WATCH — NEWS ENGINE V9
# ============================================================
# Purpose:
#   1. Find recent Rift Valley stories
#   2. Resolve Google News stories to real publisher articles
#   3. Verify the article
#   4. Extract a REAL article image
#   5. If article image is unavailable, search for a real image
#      associated with the exact story/publisher
#   6. Build story.json
#   7. Generate the MP4 through rift_valley_video_generator.py
#
# Counties:
#   Bomet, Kericho, Nakuru, Nandi, Uasin Gishu,
#   Elgeyo-Marakwet, West Pokot, Narok
#
# No YouTube upload.
# ============================================================


# ============================================================
# CONFIGURATION
# ============================================================

COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Narok",
]

KEYWORDS = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Eldoret",
    "Elgeyo-Marakwet",
    "Iten",
    "West Pokot",
    "Kapenguria",
    "Narok",
    "Kilgoris",
    "road",
    "roads",
    "hospital",
    "school",
    "university",
    "market",
    "dam",
    "water",
    "project",
    "development",
    "county government",
    "governor",
    "MP",
    "senator",
    "president",
    "deputy president",
    "Kenya",
]

RSS_URLS = [
    "https://news.google.com/rss/search?q=Rift+Valley+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=Bomet+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=Kericho+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=Nakuru+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=Nandi+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=Uasin+Gishu+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=Elgeyo-Marakwet+Kenya&hl=en-KE&gl=KE&ceid=KE:en",
    "https://news.google.com/rss/search?q=West+Pokot+Kenya&hl=en-KE&gl=KE:en",
    "https://news.google.com/rss/search?q=Narok+Kenya&hl=en-KE&gl=KE:en",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 20

OUTPUT_DIR = Path("output")
DATA_DIR = Path("data")
SOURCE_DIR = Path("assets/source")

STORY_FILE = DATA_DIR / "story.json"

BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "twitter.com",
    "x.com",
    "www.x.com",
    "youtube.com",
    "www.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "linkedin.com",
    "www.linkedin.com",
    "pinterest.com",
    "www.pinterest.com",
}

SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "www.google.com",
    "google.co.ke",
    "www.google.co.ke",
    "bing.com",
    "www.bing.com",
    "news.google.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
    "yahoo.com",
    "www.yahoo.com",
}

BLOCKED_IMAGE_TERMS = [
    "logo",
    "icon",
    "avatar",
    "favicon",
    "sprite",
    "placeholder",
    "default",
    "blank",
    "loading",
    "advert",
    "ads",
    "banner-ad",
    "pixel",
    "tracking",
    "emoji",
    "profile",
]


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_text(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def domain_of(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def root_domain(url):
    domain = domain_of(url)

    if domain.startswith("www."):
        domain = domain[4:]

    parts = domain.split(".")

    if len(parts) >= 2:
        return ".".join(parts[-2:])

    return domain


def is_blocked_domain(url):
    domain = domain_of(url)

    if domain in BLOCKED_DOMAINS:
        return True

    if domain in SEARCH_ENGINE_DOMAINS:
        return True

    return False


def same_domain(url1, url2):
    return root_domain(url1) == root_domain(url2)


def valid_http_url(url):
    return bool(url and url.startswith(("http://", "https://")))


def make_absolute(base_url, value):
    if not value:
        return ""

    value = html.unescape(value).strip()

    if value.startswith("//"):
        return "https:" + value

    return urljoin(base_url, value)


# ============================================================
# RSS
# ============================================================

def fetch_rss(url):
    try:
        response = SESSION.get(url, timeout=TIMEOUT)

        if response.status_code != 200:
            print(
                f"RSS failed: HTTP {response.status_code} "
                f"{url}"
            )
            return ""

        return response.text

    except Exception as exc:
        print(f"RSS exception: {exc}")
        return ""


def get_rss_media_image(item, raw_description=""):
    candidates = []

    # --------------------------------------------------------
    # media/content/thumbnail elements
    # --------------------------------------------------------

    for element in item.iter():

        tag = element.tag

        if not isinstance(tag, str):
            continue

        tag_lower = tag.lower()

        if (
            tag_lower.endswith("content")
            or tag_lower.endswith("thumbnail")
            or tag_lower.endswith("enclosure")
        ):
            for attr_name in [
                "url",
                "href",
                "src",
                "media:url",
            ]:
                value = element.attrib.get(attr_name)

                if value:
                    candidates.append(value)

    # --------------------------------------------------------
    # raw RSS HTML
    # --------------------------------------------------------

    if raw_description:

        patterns = [
            r'<img[^>]+src=["\']([^"\']+)["\']',
            r'<img[^>]+data-src=["\']([^"\']+)["\']',
            r'<img[^>]+data-original=["\']([^"\']+)["\']',
            r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
        ]

        for pattern in patterns:

            for match in re.findall(
                pattern,
                raw_description,
                flags=re.I,
            ):
                candidates.append(match)

    # --------------------------------------------------------
    # clean
    # --------------------------------------------------------

    result = []

    for candidate in candidates:

        candidate = html.unescape(candidate).strip()

        if candidate and candidate not in result:
            result.append(candidate)

    return result


def parse_feed(xml_text):
    stories = []

    if not xml_text:
        return stories

    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        print(f"RSS XML parse failed: {exc}")
        return stories

    for item in root.findall(".//item"):

        title = clean_text(
            item.findtext("title", "")
        )

        link = clean_text(
            item.findtext("link", "")
        )

        pub_date = clean_text(
            item.findtext("pubDate", "")
        )

        source_el = item.find("source")

        source_name = ""

        source_url = ""

        if source_el is not None:

            source_name = clean_text(
                source_el.text or ""
            )

            source_url = (
                source_el.attrib.get("url", "")
                or ""
            )

        raw_description = (
            item.findtext("description", "")
            or ""
        )

        description = clean_text(
            raw_description
        )

        image_candidates = get_rss_media_image(
            item,
            raw_description,
        )

        stories.append(
            {
                "title": title,
                "link": link,
                "published": pub_date,
                "publisher": source_name,
                "source_url": source_url,
                "description": description,
                "raw_description": raw_description,
                "rss_image_candidates": image_candidates,
            }
        )

    return stories


# ============================================================
# IMAGE VERIFICATION
# ============================================================

def image_looks_bad(url):
    lowered = url.lower()

    for term in BLOCKED_IMAGE_TERMS:

        if term in lowered:
            return True

    return False


def verify_image(url):
    """
    Verify that URL points to an actual image.

    We intentionally do NOT require Content-Length because
    many legitimate image/CDN servers omit it.

    We accept:
      - image/* Content-Type
      - JPEG magic bytes
      - PNG magic bytes
      - GIF magic bytes
      - WEBP magic bytes
    """

    if not valid_http_url(url):
        return False

    if image_looks_bad(url):
        return False

    try:

        response = SESSION.get(
            url,
            timeout=TIMEOUT,
            stream=True,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            ).lower()
        )

        if content_type.startswith("image/"):
            return True

        chunk = next(
            response.iter_content(
                chunk_size=8192
            ),
            b"",
        )

        if not chunk:
            return False

        signatures = [
            b"\xff\xd8\xff",       # JPEG
            b"\x89PNG\r\n\x1a\n", # PNG
            b"GIF87a",             # GIF
            b"GIF89a",             # GIF
            b"RIFF",               # WEBP container
        ]

        for signature in signatures:

            if chunk.startswith(signature):
                return True

        return False

    except Exception:
        return False


def download_image(url, output_path):
    """
    Download a verified image for the video generator.
    """

    if not verify_image(url):
        return False

    try:

        response = SESSION.get(
            url,
            timeout=TIMEOUT,
            stream=True,
        )

        if response.status_code != 200:
            return False

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(output_path, "wb") as file:

            total = 0

            for chunk in response.iter_content(
                chunk_size=8192
            ):

                if not chunk:
                    continue

                file.write(chunk)

                total += len(chunk)

                if total > 15 * 1024 * 1024:
                    break

        return output_path.exists() and output_path.stat().st_size > 3000

    except Exception as exc:

        print(
            f"Image download failed: {exc}"
        )

        return False


# ============================================================
# HTML META / JSON-LD
# ============================================================

def get_meta_content(soup_html, property_name):
    pattern = re.compile(
        rf'<meta[^>]+(?:property|name)=["\']'
        rf'{re.escape(property_name)}'
        rf'["\'][^>]+content=["\']([^"\']+)["\']',
        flags=re.I,
    )

    match = pattern.search(soup_html)

    if match:
        return html.unescape(
            match.group(1)
        ).strip()

    reverse_pattern = re.compile(
        rf'<meta[^>]+content=["\']([^"\']+)["\']'
        rf'[^>]+(?:property|name)=["\']'
        rf'{re.escape(property_name)}'
        rf'["\']',
        flags=re.I,
    )

    match = reverse_pattern.search(
        soup_html
    )

    if match:
        return html.unescape(
            match.group(1)
        ).strip()

    return ""


def extract_json_ld_images(html_text):
    images = []

    pattern = re.compile(
        r'"(?:image|thumbnailUrl)"\s*:\s*'
        r'(?:"([^"]+)"|\[([^\]]+)\])',
        flags=re.I,
    )

    for match in pattern.finditer(html_text):

        single = match.group(1)

        if single:
            images.append(
                html.unescape(single)
            )

        array_value = match.group(2)

        if array_value:

            for value in re.findall(
                r'"([^"]+)"',
                array_value,
            ):
                images.append(
                    html.unescape(value)
                )

    return images


def extract_image_from_html(
    page_url,
    html_text,
):
    candidates = []

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    for property_name in [
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
    ]:

        value = get_meta_content(
            html_text,
            property_name,
        )

        if value:
            candidates.append(
                make_absolute(
                    page_url,
                    value,
                )
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for value in extract_json_ld_images(
        html_text
    ):

        candidates.append(
            make_absolute(
                page_url,
                value,
            )
        )

    # --------------------------------------------------------
    # IMG tags
    # --------------------------------------------------------

    for match in re.finditer(
        r"<img\b[^>]*>",
        html_text,
        flags=re.I,
    ):

        tag = match.group(0)

        attributes = [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
        ]

        for attr in attributes:

            attr_match = re.search(
                rf'{attr}\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )

            if attr_match:

                value = attr_match.group(1)

                candidates.append(
                    make_absolute(
                        page_url,
                        value,
                    )
                )

    cleaned = []

    for candidate in candidates:

        if not valid_http_url(candidate):
            continue

        if candidate not in cleaned:
            cleaned.append(candidate)

    return cleaned


# ============================================================
# ARTICLE FETCH
# ============================================================

def fetch_page(url):
    try:

        response = SESSION.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None, ""

        return response.url, response.text

    except Exception as exc:

        print(
            f"Article fetch failed: {exc}"
        )

        return None, ""


def extract_article_data(
    article_url,
    html_text,
):
    if not html_text:
        return None

    title = ""

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    title = get_meta_content(
        html_text,
        "og:title",
    )

    if not title:

        match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html_text,
            flags=re.I | re.S,
        )

        if match:
            title = clean_text(
                match.group(1)
            )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    summary = ""

    for name in [
        "description",
        "og:description",
        "twitter:description",
    ]:

        summary = get_meta_content(
            html_text,
            name,
        )

        if summary:
            break

    # --------------------------------------------------------
    # Article paragraphs
    # --------------------------------------------------------

    if len(summary) < 80:

        paragraphs = re.findall(
            r"<p\b[^>]*>(.*?)</p>",
            html_text,
            flags=re.I | re.S,
        )

        cleaned_paragraphs = []

        for paragraph in paragraphs:

            text = clean_text(
                paragraph
            )

            if len(text) >= 40:
                cleaned_paragraphs.append(
                    text
                )

        if cleaned_paragraphs:

            summary = " ".join(
                cleaned_paragraphs[:4]
            )

    summary = clean_text(
        summary
    )

    # --------------------------------------------------------
    # Images
    # --------------------------------------------------------

    image_candidates = extract_image_from_html(
        article_url,
        html_text,
    )

    verified_image = ""

    for image_url in image_candidates:

        print(
            "Checking article image:",
            image_url[:180],
        )

        if verify_image(image_url):

            verified_image = image_url

            print(
                "VALID ARTICLE IMAGE:",
                image_url,
            )

            break

    if not title:
        return None

    if len(summary) < 40:
        return None

    return {
        "title": clean_text(title),
        "summary": summary,
        "image": verified_image,
        "url": article_url,
    }


# ============================================================
# TITLE MATCHING
# ============================================================

def title_similarity(
    rss_title,
    article_title,
):
    a = set(
        normalize_text(
            rss_title
        ).split()
    )

    b = set(
        normalize_text(
            article_title
        ).split()
    )

    if not a or not b:
        return 0.0

    common = a.intersection(b)

    return len(common) / max(
        len(a),
        len(b),
    )


def title_match(
    rss_title,
    article_title,
):
    score = title_similarity(
        rss_title,
        article_title,
    )

    if score >= 0.35:
        return True

    a = normalize_text(
        rss_title
    )

    b = normalize_text(
        article_title
    )

    if a in b or b in a:
        return True

    # Compare important words
    important = [
        word
        for word in a.split()
        if len(word) >= 5
    ]

    if not important:
        return False

    matches = sum(
        1
        for word in important
        if word in b
    )

    return matches >= max(
        2,
        len(important) // 3,
    )


# ============================================================
# GOOGLE NEWS RESOLUTION
# ============================================================

def resolve_google_redirect(
    google_url,
):
    """
    Attempt to resolve a Google News URL directly.
    """

    try:

        response = SESSION.get(
            google_url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        final_url = response.url

        if (
            valid_http_url(final_url)
            and not final_url.startswith(
                "https://news.google.com"
            )
        ):

            return final_url

    except Exception:
        pass

    return ""


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(query):
    url = (
        "https://www.bing.com/search?q="
        + quote_plus(query)
    )

    try:

        response = SESSION.get(
            url,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        results = []

        for match in re.finditer(
            r'<li class="b_algo".*?</li>',
            response.text,
            flags=re.I | re.S,
        ):

            block = match.group(0)

            link_match = re.search(
                r'<a[^>]+href="([^"]+)"',
                block,
                flags=re.I,
            )

            if not link_match:
                continue

            result_url = html.unescape(
                link_match.group(1)
            )

            title_match = re.search(
                r"<h2[^>]*>(.*?)</h2>",
                block,
                flags=re.I | re.S,
            )

            result_title = (
                clean_text(
                    title_match.group(1)
                )
                if title_match
                else ""
            )

            snippet_match = re.search(
                r'<p[^>]*>(.*?)</p>',
                block,
                flags=re.I | re.S,
            )

            snippet = (
                clean_text(
                    snippet_match.group(1)
                )
                if snippet_match
                else ""
            )

            if (
                valid_http_url(result_url)
                and not is_blocked_domain(
                    result_url
                )
            ):

                results.append(
                    {
                        "url": result_url,
                        "title": result_title,
                        "snippet": snippet,
                    }
                )

        return results

    except Exception as exc:

        print(
            f"Bing search failed: {exc}"
        )

        return []


# ============================================================
# VERIFY ARTICLE CANDIDATE
# ============================================================

def verify_article_candidate(
    candidate_url,
    rss_title,
    publisher_domain="",
):
    if not valid_http_url(
        candidate_url
    ):
        return None

    if is_blocked_domain(
        candidate_url
    ):
        return None

    candidate_domain = root_domain(
        candidate_url
    )

    if (
        publisher_domain
        and candidate_domain != publisher_domain
    ):
        return None

    final_url, page_html = fetch_page(
        candidate_url
    )

    if not final_url or not page_html:
        return None

    final_domain = root_domain(
        final_url
    )

    if (
        publisher_domain
        and final_domain != publisher_domain
    ):
        return None

    article_data = extract_article_data(
        final_url,
        page_html,
    )

    if not article_data:
        return None

    if not title_match(
        rss_title,
        article_data["title"],
    ):
        return None

    if not article_data.get("image"):
        return None

    return article_data


# ============================================================
# GOOGLE NEWS ARTICLE RESOLVER
# ============================================================

def resolve_google_news_article(
    story,
):
    rss_title = story.get(
        "title",
        "",
    )

    google_url = story.get(
        "link",
        "",
    )

    source_url = story.get(
        "source_url",
        "",
    )

    publisher_domain = root_domain(
        source_url
    )

    print("")
    print(
        "============================================================"
    )
    print(
        "GOOGLE NEWS RESOLUTION"
    )
    print(
        "============================================================"
    )

    print(
        "Title:",
        rss_title,
    )

    print(
        "Publisher:",
        story.get(
            "publisher",
            "",
        ),
    )

    print(
        "Publisher domain:",
        publisher_domain,
    )

    print(
        "Google URL:",
        google_url,
    )

    # --------------------------------------------------------
    # Method 1: direct redirect
    # --------------------------------------------------------

    print("")
    print(
        "Method 1: direct Google News redirect"
    )

    direct_url = resolve_google_redirect(
        google_url
    )

    if direct_url:

        print(
            "Resolved URL:",
            direct_url,
        )

        article = verify_article_candidate(
            direct_url,
            rss_title,
            publisher_domain,
        )

        if article:

            print(
                "SUCCESS: direct publisher article"
            )

            return article

        print(
            "Direct URL failed article verification."
        )

    # --------------------------------------------------------
    # Method 2: publisher-restricted Bing
    # --------------------------------------------------------

    if publisher_domain:

        print("")
        print(
            "Method 2: publisher-restricted Bing search"
        )

        query = (
            f'"{rss_title}" '
            f"site:{publisher_domain}"
        )

        results = bing_search(
            query
        )

        for result in results:

            print(
                "Candidate:",
                result["url"],
            )

            article = verify_article_candidate(
                result["url"],
                rss_title,
                publisher_domain,
            )

            if article:

                print(
                    "SUCCESS: publisher search"
                )

                return article

    # --------------------------------------------------------
    # Method 3: broad Bing search
    # --------------------------------------------------------

    print("")
    print(
        "Method 3: broad Bing search"
    )

    results = bing_search(
        f'"{rss_title}" Kenya'
    )

    for result in results:

        print(
            "Candidate:",
            result["url"],
        )

        candidate_domain = root_domain(
            result["url"]
        )

        if (
            publisher_domain
            and candidate_domain
            != publisher_domain
        ):
            continue

        article = verify_article_candidate(
            result["url"],
            rss_title,
            publisher_domain,
        )

        if article:

            print(
                "SUCCESS: broad search"
            )

            return article

    print("")
    print(
        "Google News story failed all article "
        "resolution methods."
    )

    return None


# ============================================================
# IMAGE SEARCH FALLBACK
# ============================================================

def extract_bing_image_urls(
    html_text,
):
    """
    Extract likely image URLs from Bing image-search
    result HTML.

    Bing stores image metadata in several forms.
    """

    candidates = []

    # Direct URLs
    patterns = [
        r'"murl":"(https?://[^"]+)"',
        r'"mediaurl":"(https?://[^"]+)"',
        r'"turl":"(https?://[^"]+)"',
    ]

    for pattern in patterns:

        for match in re.findall(
            pattern,
            html_text,
            flags=re.I,
        ):

            value = (
                match
                .replace("\\/", "/")
                .replace("\\u002f", "/")
            )

            candidates.append(
                html.unescape(value)
            )

    # Generic image URLs
    for match in re.findall(
        r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?',
        html_text,
        flags=re.I,
    ):

        candidates.append(
            html.unescape(match)
        )

    cleaned = []

    for candidate in candidates:

        if not valid_http_url(
            candidate
        ):
            continue

        if candidate not in cleaned:
            cleaned.append(
                candidate
            )

    return cleaned


def bing_image_search(
    query,
):
    """
    Search Bing Images for the exact story.
    """

    url = (
        "https://www.bing.com/images/search?q="
        + quote_plus(query)
    )

    print("")
    print(
        "IMAGE SEARCH:"
    )

    print(
        query
    )

    try:

        response = SESSION.get(
            url,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            print(
                "Image search HTTP:",
                response.status_code,
            )
            return []

        return extract_bing_image_urls(
            response.text
        )

    except Exception as exc:

        print(
            "Image search failed:",
            exc,
        )

        return []


def image_search_fallback(
    story,
    article_url="",
):
    """
    Find a REAL photo when the article itself doesn't
    expose a usable image.

    Priority:
      1. exact title + publisher
      2. exact title + Kenya
      3. title + key county
      4. title + publisher domain
    """

    title = story.get(
        "title",
        "",
    )

    publisher = story.get(
        "publisher",
        "",
    )

    publisher_domain = root_domain(
        article_url
        or story.get(
            "source_url",
            "",
        )
    )

    county = ""

    title_lower = title.lower()

    for candidate_county in COUNTIES:

        if candidate_county.lower() in title_lower:

            county = candidate_county
            break

    queries = []

    if publisher:
        queries.append(
            f'"{title}" "{publisher}"'
        )

    if publisher_domain:
        queries.append(
            f'"{title}" {publisher_domain}'
        )

    queries.append(
        f'"{title}" Kenya news'
    )

    if county:
        queries.append(
            f'"{title}" {county} Kenya'
        )

    seen = set()

    for query in queries:

        if query in seen:
            continue

        seen.add(query)

        image_urls = bing_image_search(
            query
        )

        print(
            "Image candidates:",
            len(image_urls),
        )

        for image_url in image_urls:

            if image_looks_bad(
                image_url
            ):
                continue

            print(
                "Checking fallback image:",
                image_url[:180],
            )

            if verify_image(
                image_url
            ):

                print(
                    "VALID FALLBACK IMAGE:"
                )

                print(
                    image_url
                )

                return image_url

        time.sleep(0.5)

    return ""


# ============================================================
# RSS IMAGE FALLBACK
# ============================================================

def build_rss_verified_story(
    story,
):
    title = story.get(
        "title",
        "",
    )

    publisher = story.get(
        "publisher",
        "",
    )

    description = story.get(
        "description",
        "",
    )

    candidates = list(
        story.get(
            "rss_image_candidates",
            [],
        )
    )

    print("")
    print(
        "RSS IMAGE CHECK"
    )

    print(
        "Title:",
        title,
    )

    print(
        "Publisher:",
        publisher,
    )

    print(
        "RSS image candidates:",
        len(candidates),
    )

    verified_image = ""

    for image_url in candidates:

        print(
            "Checking RSS image:",
            image_url[:180],
        )

        if verify_image(
            image_url
        ):

            verified_image = image_url

            print(
                "VALID RSS IMAGE:",
                image_url,
            )

            break

    if not verified_image:

        print(
            "RSS did not contain a valid image."
        )

        return None

    if len(description) < 40:

        description = (
            f"{title}. "
            f"Latest developments reported by "
            f"{publisher}."
        )

    return {
        "title": title,
        "summary": description,
        "image": verified_image,
        "url": story.get(
            "link",
            "",
        ),
    }


# ============================================================
# STORY ENRICHMENT
# ============================================================

def enrich_story(
    story,
):
    publisher = story.get(
        "publisher",
        "",
    )

    link = story.get(
        "link",
        "",
    )

    # --------------------------------------------------------
    # Google News
    # --------------------------------------------------------

    if (
        "news.google.com"
        in domain_of(link)
    ):

        article = resolve_google_news_article(
            story
        )

        if article:

            story["resolved_url"] = article[
                "url"
            ]

            story["article_title"] = article[
                "title"
            ]

            story["summary"] = article[
                "summary"
            ]

            story["image"] = article[
                "image"
            ]

            print("")
            print(
                "ARTICLE VERIFIED"
            )

            print(
                "URL:",
                article["url"],
            )

            print(
                "IMAGE:",
                article["image"],
            )

            return story

        # ----------------------------------------------------
        # RSS image fallback
        # ----------------------------------------------------

        rss_story = build_rss_verified_story(
            story
        )

        if rss_story:

            story["resolved_url"] = (
                story.get(
                    "link",
                    "",
                )
            )

            story["article_title"] = (
                rss_story["title"]
            )

            story["summary"] = (
                rss_story["summary"]
            )

            story["image"] = (
                rss_story["image"]
            )

            print(
                "Using verified RSS story."
            )

            return story

        # ----------------------------------------------------
        # NEW: IMAGE SEARCH FALLBACK
        # ----------------------------------------------------

        print("")
        print(
            "No valid article/RSS image."
        )

        print(
            "Trying real-image search fallback..."
        )

        image_url = image_search_fallback(
            story
        )

        if image_url:

            summary = story.get(
                "description",
                "",
            )

            if len(summary) < 40:

                summary = (
                    f"{story['title']}. "
                    f"Latest developments reported by "
                    f"{publisher}."
                )

            story["resolved_url"] = (
                story.get(
                    "link",
                    "",
                )
            )

            story["article_title"] = (
                story["title"]
            )

            story["summary"] = summary

            story["image"] = image_url

            story["image_source"] = (
                "verified_image_search"
            )

            print("")
            print(
                "IMAGE FALLBACK SUCCESS"
            )

            print(
                image_url
            )

            return story

        print("")
        print(
            "RSS fallback rejected: "
            "no valid RSS/article image found."
        )

        return None

    # --------------------------------------------------------
    # Direct publisher article
    # --------------------------------------------------------

    final_url, page_html = fetch_page(
        link
    )

    if final_url and page_html:

        article = extract_article_data(
            final_url,
            page_html,
        )

        if article:

            story["resolved_url"] = (
                final_url
            )

            story["article_title"] = (
                article["title"]
            )

            story["summary"] = (
                article["summary"]
            )

            story["image"] = (
                article["image"]
            )

            return story

    # --------------------------------------------------------
    # Direct page failed image extraction
    # --------------------------------------------------------

    print(
        "Direct article failed."
    )

    image_url = image_search_fallback(
        story,
        link,
    )

    if image_url:

        story["resolved_url"] = (
            link
        )

        story["article_title"] = (
            story["title"]
        )

        story["summary"] = (
            story.get(
                "description",
                "",
            )
            or story["title"]
        )

        story["image"] = image_url

        story["image_source"] = (
            "verified_image_search"
        )

        return story

    return None


# ============================================================
# STORY RELEVANCE
# ============================================================

def is_rift_valley_story(
    story,
):
    text = " ".join(
        [
            story.get(
                "title",
                "",
            ),
            story.get(
                "description",
                "",
            ),
            story.get(
                "publisher",
                "",
            ),
        ]
    ).lower()

    for county in COUNTIES:

        if county.lower() in text:
            return True

    return False


# ============================================================
# STORY SCORING
# ============================================================

def score_story(
    story,
):
    title = story.get(
        "title",
        "",
    )

    summary = story.get(
        "summary",
        "",
    )

    publisher = story.get(
        "publisher",
        "",
    )

    score = 0

    text = (
        title
        + " "
        + summary
    ).lower()

    # County relevance
    for county in COUNTIES:

        if county.lower() in text:
            score += 20

    # Strong news terms
    strong_terms = [
        "project",
        "road",
        "hospital",
        "school",
        "water",
        "dam",
        "market",
        "development",
        "governor",
        "president",
        "deputy president",
        "senator",
        "mp",
        "government",
        "funding",
        "construction",
        "launch",
        "opened",
        "approved",
        "announced",
    ]

    for term in strong_terms:

        if term in text:
            score += 5

    # Publisher bonus
    publisher_lower = publisher.lower()

    trusted_publishers = [
        "citizen",
        "nation",
        "standard",
        "star",
        "capital",
        "ntv",
        "kbc",
        "county government",
        "government",
    ]

    for publisher_name in trusted_publishers:

        if publisher_name in publisher_lower:
            score += 10
            break

    # Image bonus
    if story.get("image"):
        score += 25

    # Article verification bonus
    if story.get("resolved_url"):
        score += 20

    return score


# ============================================================
# HEADLINE
# ============================================================

def build_headline(
    story,
):
    title = clean_text(
        story.get(
            "article_title",
            "",
        )
        or story.get(
            "title",
            "",
        )
    )

    title = re.sub(
        r"\s+[-|]\s+[^-|]+$",
        "",
        title,
    )

    return title.strip()


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story,
):
    headline = build_headline(
        story
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    publisher = clean_text(
        story.get(
            "publisher",
            "",
        )
    )

    if not summary:
        summary = headline

    if len(summary) > 700:
        summary = summary[:700]

    narration = (
        f"Rift Valley Watch. "
        f"{headline}. "
        f"{summary}. "
        f"According to {publisher}, "
        f"these are the latest developments."
    )

    return narration


# ============================================================
# COLLECT STORIES
# ============================================================

def collect_stories():
    all_stories = []

    seen_titles = set()

    print("")
    print(
        "============================================================"
    )
    print(
        "RIFT VALLEY WATCH NEWS ENGINE V9"
    )
    print(
        "============================================================"
    )

    for rss_url in RSS_URLS:

        print("")
        print(
            "Fetching:",
            rss_url,
        )

        xml_text = fetch_rss(
            rss_url
        )

        if not xml_text:
            continue

        feed_stories = parse_feed(
            xml_text
        )

        print(
            "Stories found:",
            len(feed_stories),
        )

        for story in feed_stories:

            title = story.get(
                "title",
                "",
            )

            if not title:
                continue

            normalized = normalize_text(
                title
            )

            if normalized in seen_titles:
                continue

            seen_titles.add(
                normalized
            )

            if not is_rift_valley_story(
                story
            ):
                continue

            all_stories.append(
                story
            )

    print("")
    print(
        "Total relevant candidates:",
        len(all_stories),
    )

    return all_stories


# ============================================================
# SELECT STORY
# ============================================================

def select_story():
    candidates = collect_stories()

    if not candidates:
        raise RuntimeError(
            "No Rift Valley news candidates found."
        )

    # Most recent-looking RSS order first.
    candidates = candidates[:80]

    verified = []

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        print("")
        print(
            "============================================================"
        )

        print(
            f"CHECKING CANDIDATE {index}/{len(candidates)}"
        )

        print(
            "Title:",
           
