import os
import re
import json
import time
import html
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import (
    urljoin,
    urlparse,
    parse_qs,
    unquote,
)

import requests
import feedparser
from bs4 import BeautifulSoup

from rift_valley_video_generator import generate_video


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE
# ============================================================

APP_NAME = "Rift Valley Watch"

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

OUTPUT_DIR = "data"
STORY_FILE = os.path.join(OUTPUT_DIR, "story.json")
SCRIPT_FILE = os.path.join(OUTPUT_DIR, "script.json")

MAX_AGE_HOURS = 72

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36"
)

TIMEOUT = 20

session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# ============================================================
# SOURCE CONFIGURATION
# ============================================================

COUNTY_FEEDS = {
    "Bomet": [
        "https://news.google.com/rss/search?q=Bomet+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "Kericho": [
        "https://news.google.com/rss/search?q=Kericho+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "Nakuru": [
        "https://news.google.com/rss/search?q=Nakuru+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "Nandi": [
        "https://news.google.com/rss/search?q=Nandi+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "Uasin Gishu": [
        "https://news.google.com/rss/search?q=Uasin+Gishu+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "Elgeyo-Marakwet": [
        "https://news.google.com/rss/search?q=Elgeyo-Marakwet+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "West Pokot": [
        "https://news.google.com/rss/search?q=West+Pokot+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
    "Narok": [
        "https://news.google.com/rss/search?q=Narok+Kenya+when%3A3d&hl=en-KE&gl=KE&ceid=KE%3Aen",
    ],
}


# ============================================================
# PUBLISHER DOMAINS
# ============================================================

KNOWN_PUBLISHERS = {
    "citizen.digital",
    "nation.africa",
    "standardmedia.co.ke",
    "the-star.co.ke",
    "capitalfm.co.ke",
    "kenyans.co.ke",
    "tuko.co.ke",
    "ntvkenya.co.ke",
    "kbc.co.ke",
    "capitalfm.co.ke",
    "businessdailyafrica.com",
    "theeastafrican.co.ke",
    "kenyanwallstreet.com",
    "peopledaily.digital",
    "pulselive.co.ke",
    "mpasho.co.ke",
    "bomet.go.ke",
    "kericho.go.ke",
    "nakuru.go.ke",
    "nandi.go.ke",
    "uasingishu.go.ke",
    "elgeyomarakwet.go.ke",
    "westpokot.go.ke",
    "narok.go.ke",
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))

    soup = BeautifulSoup(value, "html.parser")

    text = soup.get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(value):
    value = clean_text(value).lower()

    value = re.sub(
        r"\b(live|update|breaking|latest|just in)\b",
        " ",
        value,
    )

    value = re.sub(r"[^a-z0-9\s]", " ", value)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def title_tokens(value):
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "after",
        "as",
        "is",
        "at",
        "by",
        "from",
        "into",
        "over",
        "new",
    }

    return {
        token
        for token in normalize_title(value).split()
        if len(token) > 2 and token not in stopwords
    }


def title_similarity(a, b):
    a_tokens = title_tokens(a)
    b_tokens = title_tokens(b)

    if not a_tokens or not b_tokens:
        return 0.0

    intersection = len(a_tokens & b_tokens)

    denominator = max(
        len(a_tokens),
        len(b_tokens),
    )

    return intersection / denominator


def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        return parsed.scheme in {
            "http",
            "https",
        } and bool(parsed.netloc)

    except Exception:
        return False


def canonical_url(url):
    if not valid_http_url(url):
        return ""

    parsed = urlparse(url)

    return (
        f"{parsed.scheme}://{parsed.netloc}"
        f"{parsed.path}"
    )


def domain_of(url):
    if not valid_http_url(url):
        return ""

    try:
        domain = urlparse(url).netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def is_google_news_url(url):
    return "news.google.com" in domain_of(url)


def is_image_url(url):
    if not valid_http_url(url):
        return False

    lower = url.lower()

    image_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".avif",
    )

    if any(ext in lower for ext in image_extensions):
        return True

    image_words = (
        "image",
        "images",
        "photo",
        "photos",
        "media",
        "picture",
        "upload",
        "wp-content",
    )

    return any(word in lower for word in image_words)


def make_story_id(title, url):
    raw = f"{title}|{url}"

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# DATE HELPERS
# ============================================================

def parse_entry_date(entry):
    for field in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):
        parsed = entry.get(field)

        if parsed:
            try:
                return datetime(
                    parsed.tm_year,
                    parsed.tm_mon,
                    parsed.tm_mday,
                    parsed.tm_hour,
                    parsed.tm_min,
                    parsed.tm_sec,
                    tzinfo=timezone.utc,
                )
            except Exception:
                pass

    for field in (
        "published",
        "updated",
        "created",
    ):
        value = entry.get(field)

        if value:
            try:
                parsed = feedparser._parse_date(value)

                if parsed:
                    return datetime(
                        parsed.tm_year,
                        parsed.tm_mon,
                        parsed.tm_mday,
                        parsed.tm_hour,
                        parsed.tm_min,
                        parsed.tm_sec,
                        tzinfo=timezone.utc,
                    )
            except Exception:
                pass

    return None


def is_recent(dt):
    if not dt:
        return False

    now = datetime.now(timezone.utc)

    age = now - dt

    return age <= timedelta(
        hours=MAX_AGE_HOURS
    )


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_urls_from_html(raw_html):
    if not raw_html:
        return []

    urls = []

    soup = BeautifulSoup(
        raw_html,
        "html.parser",
    )

    for tag in soup.find_all(
        [
            "img",
            "source",
            "meta",
        ]
    ):

        candidates = []

        for attr in (
            "src",
            "srcset",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
            "content",
        ):
            value = tag.get(attr)

            if value:
                candidates.append(value)

        for value in candidates:

            if "," in value and " " in value:
                parts = value.split(",")

                for part in parts:
                    part = part.strip()

                    if " " in part:
                        part = part.split(" ")[0]

                    if valid_http_url(part):
                        urls.append(part)
            else:
                if valid_http_url(value):
                    urls.append(value)

    return urls


def get_rss_media_images(entry):
    urls = []

    media_content = entry.get("media_content")

    if media_content:
        for item in media_content:
            if isinstance(item, dict):

                for key in (
                    "url",
                    "href",
                ):
                    value = item.get(key)

                    if valid_http_url(value):
                        urls.append(value)

    media_thumbnail = entry.get(
        "media_thumbnail"
    )

    if media_thumbnail:
        for item in media_thumbnail:
            if isinstance(item, dict):

                value = item.get("url")

                if valid_http_url(value):
                    urls.append(value)

    raw_description = entry.get(
        "raw_description",
        "",
    )

    urls.extend(
        extract_urls_from_html(
            raw_description
        )
    )

    links = entry.get("links", [])

    for link in links:
        if isinstance(link, dict):

            href = link.get("href", "")

            link_type = (
                link.get("type", "")
                or ""
            ).lower()

            if (
                valid_http_url(href)
                and (
                    "image" in link_type
                    or is_image_url(href)
                )
            ):
                urls.append(href)

    unique = []

    seen = set()

    for url in urls:
        if not valid_http_url(url):
            continue

        clean = url.strip()

        if clean not in seen:
            seen.add(clean)
            unique.append(clean)

    return unique


# ============================================================
# IMAGE VERIFICATION
# ============================================================

def verify_image(url):
    if not valid_http_url(url):
        return False

    try:
        response = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        data = b""

        for chunk in response.iter_content(
            chunk_size=8192
        ):
            data += chunk

            if len(data) >= 65536:
                break

        if (
            "image/" in content_type
            and len(data) > 1000
        ):
            return True

        signatures = [
            b"\xff\xd8\xff",
            b"\x89PNG",
            b"GIF87a",
            b"GIF89a",
            b"RIFF",
        ]

        for signature in signatures:
            if data.startswith(signature):
                return True

        return False

    except Exception as exc:
        logging.debug(
            "Image verification failed: %s",
            exc,
        )

        return False


# ============================================================
# ARTICLE HTML EXTRACTION
# ============================================================

def get_meta_content(
    soup,
    attr,
    value,
):
    tag = soup.find(
        "meta",
        attrs={
            attr: value
        },
    )

    if tag:
        return tag.get(
            "content",
            "",
        )

    return ""


def extract_jsonld_images(soup):
    images = []

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        objects = []

        if isinstance(data, list):
            objects.extend(data)

        elif isinstance(data, dict):

            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):
                objects.extend(graph)

        for obj in objects:

            if not isinstance(obj, dict):
                continue

            image = obj.get("image")

            if isinstance(image, str):
                images.append(image)

            elif isinstance(image, dict):

                value = image.get("url")

                if value:
                    images.append(value)

            elif isinstance(image, list):

                for item in image:

                    if isinstance(item, str):
                        images.append(item)

                    elif isinstance(item, dict):
                        value = item.get(
                            "url"
                        )

                        if value:
                            images.append(value)

    return images


def extract_article_image(
    soup,
    base_url,
):
    candidates = []

    # Open Graph
    for attr, value in (
        (
            "property",
            "og:image",
        ),
        (
            "property",
            "og:image:url",
        ),
        (
            "property",
            "og:image:secure_url",
        ),
        (
            "name",
            "twitter:image",
        ),
        (
            "name",
            "twitter:image:src",
        ),
    ):
        image = get_meta_content(
            soup,
            attr,
            value,
        )

        if image:
            candidates.append(image)

    # JSON-LD
    candidates.extend(
        extract_jsonld_images(soup)
    )

    # Image tags
    candidates.extend(
        extract_urls_from_html(
            str(soup)
        )
    )

    for image in candidates:

        if not image:
            continue

        image = image.strip()

        if image.startswith("//"):
            image = "https:" + image

        elif not image.startswith(
            (
                "http://",
                "https://",
            )
        ):
            image = urljoin(
                base_url,
                image,
            )

        if not valid_http_url(image):
            continue

        if verify_image(image):
            return image

    return ""


def extract_article_text(soup):
    selectors = [
        "article",
        "[itemprop='articleBody']",
        ".article-body",
        ".article-content",
        ".story-body",
        ".entry-content",
        ".post-content",
        "main",
    ]

    best = ""

    for selector in selectors:

        nodes = soup.select(selector)

        for node in nodes:

            text = clean_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) > len(best):
                best = text

    if len(best) < 250:

        paragraphs = []

        for p in soup.find_all("p"):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) >= 40:
                paragraphs.append(text)

        best = " ".join(paragraphs)

    return best[:10000]


def extract_article_summary(
    soup,
    fallback="",
):
    description = ""

    for attr, value in (
        (
            "name",
            "description",
        ),
        (
            "property",
            "og:description",
        ),
        (
            "name",
            "twitter:description",
        ),
    ):
        description = get_meta_content(
            soup,
            attr,
            value,
        )

        if description:
            break

    if len(description) >= 80:
        return clean_text(description)

    article_text = extract_article_text(
        soup
    )

    if len(article_text) >= 80:
        return article_text[:1200]

    return clean_text(fallback)


# ============================================================
# FETCH ARTICLE
# ============================================================

def fetch_html(url):
    try:
        response = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None, ""

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if (
            "html" not in content_type
            and len(response.text) < 500
        ):
            return None, ""

        return response, response.url

    except Exception as exc:
        logging.debug(
            "Fetch failed %s: %s",
            url,
            exc,
        )

        return None, ""


# ============================================================
# GOOGLE NEWS URL RESOLUTION
# ============================================================

def extract_google_redirect(url):
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        params = parse_qs(
            parsed.query
        )

        for key in (
            "url",
            "u",
            "target",
            "dest",
            "destination",
        ):
            values = params.get(key)

            if values:
                candidate = unquote(
                    values[0]
                )

                if (
                    valid_http_url(candidate)
                    and not is_google_news_url(
                        candidate
                    )
                ):
                    return candidate

    except Exception:
        pass

    return ""


def resolve_google_direct(url):
    if not valid_http_url(url):
        return ""

    redirect = extract_google_redirect(
        url
    )

    if redirect:
        return redirect

    try:
        response = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        final_url = response.url

        if (
            valid_http_url(final_url)
            and not is_google_news_url(
                final_url
            )
        ):
            return final_url

    except Exception:
        pass

    return ""


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(query, limit=8):
    try:
        url = (
            "https://www.bing.com/search"
        )

        response = session.get(
            url,
            params={
                "q": query,
                "count": limit,
                "setlang": "en",
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        results = []

        for item in soup.select(
            "li.b_algo"
        ):

            anchor = item.select_one(
                "h2 a"
            )

            if not anchor:
                continue

            title = clean_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )

            href = anchor.get(
                "href",
                "",
            )

            snippet_node = item.select_one(
                ".b_caption p"
            )

            snippet = ""

            if snippet_node:
                snippet = clean_text(
                    snippet_node.get_text(
                        " ",
                        strip=True,
                    )
                )

            if (
                title
                and valid_http_url(href)
            ):
                results.append(
                    {
                        "title": title,
                        "url": href,
                        "snippet": snippet,
                    }
                )

        return results

    except Exception as exc:
        logging.debug(
            "Bing search failed: %s",
            exc,
        )

        return []


# ============================================================
# VERIFY ARTICLE CANDIDATE
# ============================================================

def verify_article_candidate(
    candidate_url,
    expected_title,
):
    if not valid_http_url(
        candidate_url
    ):
        return None

    if is_google_news_url(
        candidate_url
    ):
        return None

    try:
        response, final_url = fetch_html(
            candidate_url
        )

        if response is None:
            return None

        if is_google_news_url(
            final_url
        ):
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        title = ""

        if soup.title:
            title = clean_text(
                soup.title.get_text()
            )

        og_title = get_meta_content(
            soup,
            "property",
            "og:title",
        )

        if og_title:
            title = og_title

        similarity = title_similarity(
            expected_title,
            title,
        )

        if similarity < 0.20:
            return None

        image = extract_article_image(
            soup,
            final_url,
        )

        summary = extract_article_summary(
            soup
        )

        if not image:
            return None

        if len(summary) < 60:
            return None

        return {
            "url": final_url,
            "title": title
            or expected_title,
            "summary": summary,
            "image": image,
            "domain": domain_of(
                final_url
            ),
            "title_similarity": similarity,
        }

    except Exception as exc:
        logging.debug(
            "Candidate verification failed: %s",
            exc,
        )

        return None


# ============================================================
# GOOGLE NEWS ARTICLE RESOLVER
# ============================================================

def resolve_google_news_article(
    item,
):
    title = item.get(
        "title",
        "",
    )

    google_url = item.get(
        "url",
        "",
    )

    source_name = item.get(
        "source_name",
        "",
    )

    source_url = item.get(
        "source_url",
        "",
    )

    print("")
    print(
        "---------------- GOOGLE NEWS RESOLUTION ----------------"
    )

    print(
        "Story:",
        title,
    )

    print(
        "Google URL:",
        google_url,
    )

    # --------------------------------------------------------
    # METHOD 1: DIRECT REDIRECT
    # --------------------------------------------------------

    direct = resolve_google_direct(
        google_url
    )

    if direct:

        print(
            "Direct publisher URL:",
            direct,
        )

        verified = (
            verify_article_candidate(
                direct,
                title,
            )
        )

        if verified:
            print(
                "SUCCESS: direct publisher article verified."
            )

            return verified

    # --------------------------------------------------------
    # METHOD 2: SOURCE DOMAIN SEARCH
    # --------------------------------------------------------

    source_domain = domain_of(
        source_url
    )

    if source_domain:

        print(
            "Publisher domain:",
            source_domain,
        )

        query = (
            f'"{title}" '
            f'site:{source_domain}'
        )

        results = bing_search(
            query,
            limit=10,
        )

        for result in results:

            verified = (
                verify_article_candidate(
                    result["url"],
                    title,
                )
            )

            if verified:
                print(
                    "SUCCESS: publisher-domain search verified."
                )

                return verified

    # --------------------------------------------------------
    # METHOD 3: SOURCE NAME SEARCH
    # --------------------------------------------------------

    if source_name:

        query = (
            f'"{title}" '
            f'"{source_name}" Kenya'
        )

        results = bing_search(
            query,
            limit=10,
        )

        for result in results:

            verified = (
                verify_article_candidate(
                    result["url"],
                    title,
                )
            )

            if verified:
                print(
                    "SUCCESS: publisher-name search verified."
                )

                return verified

    # --------------------------------------------------------
    # METHOD 4: BROAD EXACT-TITLE SEARCH
    # --------------------------------------------------------

    query = (
        f'"{title}" Kenya'
    )

    results = bing_search(
        query,
        limit=12,
    )

    for result in results:

        verified = (
            verify_article_candidate(
                result["url"],
                title,
            )
        )

        if verified:
            print(
                "SUCCESS: broad title search verified."
            )

            return verified

    print(
        "Google News article could not be verified."
    )

    return None


# ============================================================
# BING IMAGE SEARCH
# ============================================================

def extract_bing_image_urls(
    html_text,
):
    if not html_text:
        return []

    urls = []

    # Common Bing image JSON patterns
    patterns = [
        r'"murl":"(https?://[^"]+)"',
        r'"turl":"(https?://[^"]+)"',
        r'\\"murl\\":\\"(https?://[^"]+)\\"',
        r'\\"turl\\":\\"(https?://[^"]+)\\"',
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
                .replace('\\"', '"')
            )

            if valid_http_url(value):
                urls.append(value)

    # HTML img fallback
    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    for img in soup.find_all("img"):

        for attr in (
            "src",
            "data-src",
            "data-murl",
            "data-sourceurl",
        ):

            value = img.get(attr)

            if valid_http_url(value):
                urls.append(value)

    unique = []

    seen = set()

    for url in urls:

        url = html.unescape(
            url
        )

        if url not in seen:

            seen.add(url)
            unique.append(url)

    return unique


def bing_image_search(
    query,
    limit=20,
):
    try:

        response = session.get(
            "https://www.bing.com/images/search",
            params={
                "q": query,
                "form": "HDRSC2",
                "first": 1,
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        urls = extract_bing_image_urls(
            response.text
        )

        valid = []

        for url in urls:

            if len(valid) >= limit:
                break

            if verify_image(url):
                valid.append(url)

        return valid

    except Exception as exc:

        logging.debug(
            "Bing image search failed: %s",
            exc,
        )

        return []


# ============================================================
# IMAGE SEARCH FALLBACK
# ============================================================

def image_search_fallback(
    story,
):
    title = story.get(
        "title",
        "",
    )

    county = story.get(
        "county",
        "",
    )

    source_name = story.get(
        "source_name",
        "",
    )

    queries = [
        f'"{title}"',
        f'"{title}" {county}',
        f'"{title}" Kenya',
    ]

    if source_name:
        queries.append(
            f'"{title}" "{source_name}"'
        )

    print("")
    print(
        "---------------- IMAGE FALLBACK ----------------"
    )

    for query in queries:

        print(
            "Image search:",
            query,
        )

        images = bing_image_search(
            query,
            limit=10,
        )

        for image in images:

            if verify_image(image):

                print(
                    "REAL IMAGE FOUND:",
                    image,
                )

                return image

    print(
        "No verified fallback image found."
    )

    return ""


# ============================================================
# RSS FALLBACK
# ============================================================

def build_rss_verified_story(
    item,
):
    title = item.get(
        "title",
        "",
    )

    images = get_rss_media_images(
        item
    )

    for image in images:

        if verify_image(image):

            summary = clean_text(
                item.get(
                    "raw_description",
                    "",
                )
            )

            if len(summary) < 60:
                summary = title

            return {
                "title": title,
                "summary": summary,
                "image": image,
                "url": item.get(
                    "url",
                    "",
                ),
                "source_name": item.get(
                    "source_name",
                    "",
                ),
                "source_url": item.get(
                    "source_url",
                    "",
                ),
                "county": item.get(
                    "county",
                    "",
                ),
                "published": item.get(
                    "published",
                    "",
                ),
                "published_dt": item.get(
                    "published_dt",
                ),
                "verification": "rss_image",
            }

    print(
        "RSS fallback rejected: no valid RSS/article image found."
    )

    return None


# ============================================================
# RSS PARSING
# ============================================================

def parse_feed(
    feed_url,
    county,
):
    try:

        response = session.get(
            feed_url,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            logging.warning(
                "RSS HTTP %s: %s",
                response.status_code,
                feed_url,
            )

            return []

        feed = feedparser.parse(
            response.content
        )

        stories = []

        for entry in feed.entries:

            title = clean_text(
                entry.get(
                    "title",
                    "",
                )
            )

            if not title:
                continue

            link = entry.get(
                "link",
                "",
            )

            source = entry.get(
                "source",
                {},
            )

            source_name = ""

            source_url = ""

            if isinstance(
                source,
                dict,
            ):
                source_name = clean_text(
                    source.get(
                        "title",
                        "",
                    )
                )

                source_url = source.get(
                    "href",
                    "",
                )

            elif source:
                source_name = clean_text(
                    str(source)
                )

            raw_description = (
                entry.get(
                    "description",
                    "",
                )
                or ""
            )

            description = clean_text(
                raw_description
            )

            published_dt = (
                parse_entry_date(entry)
            )

            if (
                published_dt
                and not is_recent(
                    published_dt
                )
            ):
                continue

            stories.append(
                {
                    "title": title,
                    "url": link,
                    "source_name": source_name,
                    "source_url": source_url,
                    "description": description,
                    "raw_description": raw_description,
                    "county": county,
                    "published": (
                        published_dt.isoformat()
                        if published_dt
                        else ""
                    ),
                    "published_dt": published_dt,
                    "rss_images": get_rss_media_images(
                        entry
                    ),
                }
            )

        return stories

    except Exception as exc:

        logging.exception(
            "RSS parsing failed: %s",
            exc,
        )

        return []


# ============================================================
# COLLECT ALL STORIES
# ============================================================

def collect_candidates():
    candidates = []

    print("")
    print(
        "============================================================"
    )
    print(
        "RIFT VALLEY WATCH — COLLECTING CURRENT STORIES"
    )
    print(
        "============================================================"
    )

    for county in COUNTIES:

        feeds = COUNTY_FEEDS.get(
            county,
            [],
        )

        for feed_url in feeds:

            print(
                f"Fetching {county}: {feed_url}"
            )

            stories = parse_feed(
                feed_url,
                county,
            )

            candidates.extend(
                stories
            )

    # Remove duplicate titles
    unique = []

    seen = set()

    for candidate in candidates:

        key = normalize_title(
            candidate["title"]
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(candidate)

    print("")
    print(
        f"Collected {len(unique)} unique recent candidates."
    )

    return unique


# ============================================================
# RELEVANCE
# ============================================================

def story_relevance(
    story,
):
    title = normalize_title(
        story.get(
            "title",
            "",
        )
    )

    summary = normalize_title(
        story.get(
            "description",
            "",
        )
    )

    text = f"{title} {summary}"

    county = story.get(
        "county",
        "",
    )

    score = 0

    if county.lower() in text:
        score += 30

    important_terms = [
        "government",
        "county",
        "road",
        "roads",
        "project",
        "hospital",
        "school",
        "university",
        "business",
        "investment",
        "economy",
        "market",
        "police",
        "court",
        "governor",
        "senator",
        "mp",
        "president",
        "minister",
        "cabinet",
        "development",
        "construction",
        "funding",
        "budget",
        "jobs",
        "health",
        "education",
        "security",
        "agriculture",
        "farmers",
        "drought",
        "flood",
        "accident",
    ]

    for term in important_terms:

        if term in text:
            score += 3

    return score


# ============================================================
# STORY ENRICHMENT
# ============================================================

def enrich_story(
    candidate,
):
    title = candidate.get(
        "title",
        "",
    )

    print("")
    print(
        "============================================================"
    )

    print(
        "ENRICHING STORY"
    )

    print(
        "Title:",
        title,
    )

    print(
        "County:",
        candidate.get(
            "county",
            "",
        ),
    )

    print(
        "Source:",
        candidate.get(
            "source_name",
            "",
        ),
    )

    # --------------------------------------------------------
    # GOOGLE NEWS
    # --------------------------------------------------------

    if is_google_news_url(
        candidate.get(
            "url",
            "",
        )
    ):

        article = (
            resolve_google_news_article(
                candidate
            )
        )

        if article:

            candidate.update(
                {
                    "url": article["url"],
                    "title": article["title"]
                    or title,
                    "summary": article[
                        "summary"
                    ],
                    "image": article[
                        "image"
                    ],
                    "resolved_domain": article[
                        "domain"
                    ],
                    "verification": (
                        "publisher_article"
                    ),
                }
            )

            return candidate

        # RSS image fallback
        rss_story = (
            build_rss_verified_story(
                candidate
            )
        )

        if rss_story:

            candidate.update(
                rss_story
            )

            return candidate

        # Search exact story image
        fallback_image = (
            image_search_fallback(
                candidate
            )
        )

        if fallback_image:

            summary = (
                candidate.get(
                    "description",
                    "",
                )
            )

            if len(summary) < 60:
                summary = title

            candidate.update(
                {
                    "summary": summary,
                    "image": fallback_image,
                    "verification": (
                        "verified_image_search"
                    ),
                }
            )

            return candidate

        return None

    # --------------------------------------------------------
    # NON-GOOGLE DIRECT ARTICLE
    # --------------------------------------------------------

    url = candidate.get(
        "url",
        "",
    )

    if valid_http_url(url):

        article = (
            verify_article_candidate(
                url,
                title,
            )
        )

        if article:

            candidate.update(
                {
                    "url": article["url"],
                    "title": article["title"]
                    or title,
                    "summary": article[
                        "summary"
                    ],
                    "image": article[
                        "image"
                    ],
                    "resolved_domain": article[
                        "domain"
                    ],
                    "verification": (
                        "publisher_article"
                    ),
                }
            )

            return candidate

    # RSS image
    rss_story = (
        build_rss_verified_story(
            candidate
        )
    )

    if rss_story:

        candidate.update(
            rss_story
        )

        return candidate

    # Image search
    fallback_image = (
        image_search_fallback(
            candidate
        )
    )

    if fallback_image:

        summary = candidate.get(
            "description",
            "",
        )

        if len(summary) < 60:
            summary = title

        candidate.update(
            {
                "summary": summary,
                "image": fallback_image,
                "verification": (
                    "verified_image_search"
                ),
            }
        )

        return candidate

    return None


# ============================================================
# QUALITY SCORE
# ============================================================

def score_story(
    story,
):
    score = 0

    title = story.get(
        "title",
        "",
    )

    summary = story.get(
        "summary",
        "",
    )

    image = story.get(
        "image",
        "",
    )

    verification = story.get(
        "verification",
        "",
    )

    # County relevance
    score += story_relevance(
        story
    )

    # Strong title
    if len(title) >= 40:
        score += 10

    if len(title) >= 70:
        score += 5

    # Good summary
    if len(summary) >= 100:
        score += 10

    if len(summary) >= 300:
        score += 5

    # Real image
    if image:
        score += 20

    # Strong verification
    if (
        verification
        == "publisher_article"
    ):
        score += 30

    elif (
        verification
        == "rss_image"
    ):
        score += 20

    elif (
        verification
        == "verified_image_search"
    ):
        score += 15

    # Publisher quality
    domain = story.get(
        "resolved_domain",
        "",
    )

    if domain in KNOWN_PUBLISHERS:
        score += 15

    return score


# ============================================================
# HEADLINE
# ============================================================

def create_headline(
    story,
):
    title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    if not title:
        return "Rift Valley Watch"

    title = re.sub(
        r"\s+[-|]\s+[^-|]+$",
        "",
        title,
    )

    return title.strip()


# ============================================================
# NARRATION
# ============================================================

def create_narration(
    story,
):
    county = story.get(
        "county",
        "",
    )

    headline = create_headline(
        story
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    if not summary:
        summary = (
            "This is the latest development "
            f"from {county}."
        )

    summary = summary[:1000]

    narration = (
        f"Rift Valley Watch. "
        f"{headline}. "
        f"{summary}"
    )

    return narration


# ============================================================
# STORY VALIDATION
# ============================================================

def final_story_validation(
    story,
):
    if not story:
        return False

    title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    image = story.get(
        "image",
        "",
    )

    url = story.get(
        "url",
        "",
    )

    if len(title) < 15:
        print(
            "Rejected: title too short."
        )
        return False

    if len(summary) < 60:
        print(
            "Rejected: summary too short."
        )
        return False

    if not valid_http_url(image):
        print(
            "Rejected: no valid image URL."
        )
        return False

    if not verify_image(image):
        print(
            "Rejected: image failed final verification."
        )
        return False

    if not valid_http_url(url):
        print(
            "Rejected: no valid article URL."
        )
        return False

    if is_google_news_url(url):
        print(
            "Rejected: final URL is still Google News."
        )
        return False

    return True


# ============================================================
# SELECT STORY
# ============================================================

def select_story():
    candidates = collect_candidates()

    if not candidates:
        raise RuntimeError(
            "No recent RSS candidates found."
        )

    verified = []

    print("")
    print(
        "============================================================"
    )
    print(
        "RIFT VALLEY WATCH — VERIFYING CANDIDATES"
    )
    print(
        "============================================================"
    )

    # Prefer stronger relevance first,
    # but keep multiple counties represented.
    candidates.sort(
        key=lambda item: (
            story_relevance(item),
            item.get(
                "published_dt"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            ),
        ),
        reverse=True,
    )

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
            candidate.get(
                "title",
                "",
            ),
        )

        print(
            "County:",
            candidate.get(
                "county",
                "",
            ),
        )

        print(
            "Source:",
            candidate.get(
                "source_name",
                "",
            ),
        )

        try:
            story = enrich_story(
                candidate
            )

        except Exception as exc:

            print(
                "Candidate enrichment failed:",
                exc,
            )

            continue

        if not story:
            print(
                "Rejected: article did not pass verification."
            )

            continue

        if not final_story_validation(
            story
        ):
            print(
                "Rejected: final validation failed."
            )

            continue

        story["headline"] = (
            create_headline(story)
        )

        story["narration"] = (
            create_narration(story)
        )

        story["score"] = score_story(
            story
        )

        story["story_id"] = make_story_id(
            story.get(
                "title",
                "",
            ),
            story.get(
                "url",
                "",
            ),
        )

        story["verified"] = True

        verified.append(
            story
        )

        print(
            "ACCEPTED."
        )

        print(
            "Score:",
            story["score"],
        )

        print(
            "Image:",
            story["image"],
        )

        # We have a verified story.
        # Continue checking a few more so
        # the highest-quality candidate wins.
        if len(verified) >= 5:
            break

    if not verified:

        raise RuntimeError(
            "No recent story passed verification "
            "after checking all available candidates."
        )

    verified.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    selected = verified[0]

    print("")
    print(
        "============================================================"
    )

    print(
        "SELECTED STORY"
    )

    print(
        "============================================================"
    )

    print(
        "Headline:",
        selected.get(
            "headline",
            "",
        ),
    )

    print(
        "County:",
        selected.get(
            "county",
            "",
        ),
    )

    print(
        "Source:",
        selected.get(
            "source_name",
            "",
        ),
    )

    print(
        "Article:",
        selected.get(
            "url",
            "",
        ),
    )

    print(
        "Image:",
        selected.get(
            "image",
            "",
        ),
    )

    print(
        "Verification:",
        selected.get(
            "verification",
            "",
        ),
    )

    print(
        "Score:",
        selected.get(
            "score",
            0,
        ),
    )

    return selected


# ============================================================
# SAVE STORY
# ============================================================

def save_story(
    story,
):
    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    published = story.get(
        "published",
        "",
    )

    if not published:
        published = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

    output_story = {
        "story_id": story.get(
            "story_id",
            "",
        ),
        "title": story.get(
            "title",
            "",
        ),
        "headline": story.get(
            "headline",
            "",
        ),
        "county": story.get(
            "county",
            "",
        ),
        "category": "RIFT VALLEY",
        "summary": story.get(
            "summary",
            "",
        ),
        "narration": story.get(
            "narration",
            "",
        ),
        "image": story.get(
            "image",
            "",
        ),
        "source": {
            "name": story.get(
                "source_name",
                "",
            ),
            "url": story.get(
                "url",
                "",
            ),
        },
        "published": published,
        "verification": story.get(
            "verification",
            "",
        ),
        "score": story.get(
            "score",
            0,
        ),
        "verified": True,
    }

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output_story,
            file,
            indent=2,
            ensure_ascii=False,
        )

    script = {
        "title": output_story[
            "headline"
        ],
        "county": output_story[
            "county"
        ],
        "narration": output_story[
            "narration"
        ],
        "source": output_story[
            "source"
        ],
        "image": output_story[
            "image"
        ],
    }

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            script,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("")
    print(
        "============================================================"
    )

    print(
        "STORY SAVED"
    )

    print(
        "============================================================"
    )

    print(
        STORY_FILE
    )

    print(
        SCRIPT_FILE
    )

    return output_story


# ============================================================
# VIDEO
# ============================================================

def create_video(
    story,
):
    print("")
    print(
        "============================================================"
    )

    print(
        "GENERATING RIFT VALLEY WATCH VIDEO"
    )

    print(
        "============================================================"
    )

    try:

        result = generate_video(
            story
        )

        return result

    except TypeError:

        # Compatibility with generators
        # that read story.json themselves.
        result = generate_video()

        return result


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    print("")
    print(
        "============================================================"
    )
    print(
        "RIFT VALLEY WATCH"
    )
    print(
        "REAL-TIME NEWS ENGINE"
    )
    print(
        "============================================================"
    )

    print(
        "Counties:",
        ", ".join(COUNTIES),
    )

    print(
        "Maximum story age:",
        MAX_AGE_HOURS,
        "hours",
    )

    try:

        story = select_story()

        saved_story = save_story(
            story
        )

        create_video(
            saved_story
        )

        elapsed = (
            time.time()
            - start_time
        )

        print("")
        print(
            "============================================================"
        )

        print(
            "RIFT VALLEY WATCH SUCCESSFUL"
        )

        print(
            "============================================================"
        )

        print(
            f"Completed in {elapsed:.1f} seconds."
        )

        print(
            "Created:",
            STORY_FILE,
        )

        print(
            "Created:",
            SCRIPT_FILE,
        )

        print(
            "Video generation completed."
        )

    except Exception as exc:

        print("")
        print(
            "============================================================"
        )

        print(
            "RIFT VALLEY WATCH FAILED"
        )

        print(
            "============================================================"
        )

        print(
            str(exc)
        )

        raise


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
