import json
import re
import html
from pathlib import Path
from urllib.parse import urlparse, urljoin, quote_plus

import requests
import xml.etree.ElementTree as ET

from rift_valley_video_generator import generate_video


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STORY_FILE = DATA_DIR / "story.json"


# ============================================================
# RIFT VALLEY COUNTIES
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


# ============================================================
# STORY KEYWORDS
# ============================================================

KEYWORDS = [
    "project",
    "road",
    "hospital",
    "school",
    "water",
    "jobs",
    "investment",
    "funding",
    "billion",
    "million",
    "county",
    "government",
    "governor",
    "president",
    "minister",
    "development",
    "agriculture",
    "tourism",
    "education",
    "health",
    "infrastructure",
    "trade",
    "manufacturing",
    "farmers",
    "construction",
    "economy",
    "business",
]


# ============================================================
# HTTP HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36 "
        "RiftValleyWatch/7.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "en-KE,en;q=0.9",
}


# ============================================================
# BLOCKED DOMAINS
# ============================================================

BLOCKED_FINAL_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "x.com",
    "twitter.com",
}


GOOGLE_NEWS_DOMAINS = {
    "news.google.com",
}


SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "bing.com",
    "yahoo.com",
    "search.yahoo.com",
    "duckduckgo.com",
}


# ============================================================
# BLOCKED IMAGE TERMS
# ============================================================

BLOCKED_IMAGE_TERMS = [
    "logo",
    "favicon",
    "icon",
    "placeholder",
    "default-image",
    "default_image",
    "avatar",
    "profile",
    "sprite",
    "loading",
    "blank",
    "transparent",
]


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(
        str(value)
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# DOMAIN HELPERS
# ============================================================

def get_domain(url):

    try:

        parsed = urlparse(
            url
        )

        return (
            parsed.netloc
            .lower()
            .split(":")[0]
            .replace("www.", "")
        )

    except Exception:

        return ""


def is_social_domain(url):

    domain = get_domain(
        url
    )

    if not domain:
        return False

    return any(
        domain == blocked
        or domain.endswith(
            "." + blocked
        )
        for blocked in BLOCKED_FINAL_DOMAINS
    )


def is_google_news_url(url):

    domain = get_domain(
        url
    )

    if not domain:
        return False

    return (
        domain == "news.google.com"
        or domain.endswith(
            ".news.google.com"
        )
    )


def is_search_engine_url(url):

    domain = get_domain(
        url
    )

    if not domain:
        return False

    return (
        domain in SEARCH_ENGINE_DOMAINS
        or domain.endswith(
            ".google.com"
        )
        or domain.endswith(
            ".bing.com"
        )
        or domain.endswith(
            ".yahoo.com"
        )
    )


# ============================================================
# RSS FETCH
# ============================================================

def fetch_rss(query):

    url = (
        "https://news.google.com/rss/search"
    )

    params = {
        "q": query,
        "hl": "en-KE",
        "gl": "KE",
        "ceid": "KE:en",
    }

    try:

        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        return ET.fromstring(
            response.content
        )

    except Exception as exc:

        print(
            f"RSS ERROR for [{query}]: {exc}"
        )

        return None


# ============================================================
# RSS IMAGE
# ============================================================

def get_rss_media_image(item):

    image_url = ""

    for child in item.iter():

        tag = str(
            child.tag
        ).lower()

        if tag.endswith(
            "content"
        ):

            url = child.attrib.get(
                "url",
                "",
            )

            if url:

                image_url = url

                break

    if not image_url:

        for child in item.iter():

            tag = str(
                child.tag
            ).lower()

            if tag.endswith(
                "thumbnail"
            ):

                url = child.attrib.get(
                    "url",
                    "",
                )

                if url:

                    image_url = url

                    break

    return image_url.strip()


# ============================================================
# RSS PARSER
# ============================================================

def parse_feed(root):

    stories = []

    if root is None:
        return stories

    channel = root.find(
        "channel"
    )

    if channel is None:
        return stories

    for item in channel.findall(
        "item"
    ):

        title = clean_text(
            item.findtext(
                "title",
                "",
            )
        )

        link = clean_text(
            item.findtext(
                "link",
                "",
            )
        )

        description = clean_text(
            item.findtext(
                "description",
                "",
            )
        )

        pub_date = clean_text(
            item.findtext(
                "pubDate",
                "",
            )
        )

        source_element = item.find(
            "source"
        )

        source = ""
        source_url = ""

        if source_element is not None:

            source = clean_text(
                source_element.text or ""
            )

            source_url = clean_text(
                source_element.attrib.get(
                    "url",
                    "",
                )
            )

        rss_image = get_rss_media_image(
            item
        )

        if not title or not link:
            continue

        stories.append(
            {
                "title": title,
                "url": link,
                "summary": description,
                "raw_description": description,
                "published": pub_date,
                "source": source,
                "source_url": source_url,
                "rss_image": rss_image,
            }
        )

    return stories


# ============================================================
# IMAGE VALIDATION
# ============================================================

def is_bad_image_url(url):

    if not url:
        return True

    lower = url.lower()

    for term in BLOCKED_IMAGE_TERMS:

        if term in lower:
            return True

    return False


def verify_image(image_url):

    if not image_url:
        return False

    if is_bad_image_url(
        image_url
    ):
        return False

    try:

        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=20,
            stream=True,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if not content_type.startswith(
            "image/"
        ):
            return False

        content_length = (
            response.headers.get(
                "Content-Length"
            )
        )

        if content_length:

            try:

                if int(
                    content_length
                ) < 5000:

                    return False

            except Exception:
                pass

        return True

    except Exception:

        return False


# ============================================================
# META EXTRACTION
# ============================================================

def extract_meta(
    page,
    property_name=None,
    name=None,
):

    pattern = r"<meta\b[^>]*>"

    for match in re.finditer(
        pattern,
        page,
        flags=re.I,
    ):

        tag = match.group(
            0
        )

        if property_name:

            property_match = re.search(
                r'property\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )

            if (
                property_match
                and property_match.group(
                    1
                ).lower()
                == property_name.lower()
            ):

                content_match = re.search(
                    r'content\s*=\s*["\'](.*?)["\']',
                    tag,
                    flags=re.I | re.S,
                )

                if content_match:

                    return clean_text(
                        content_match.group(
                            1
                        )
                    )

        if name:

            name_match = re.search(
                r'name\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )

            if (
                name_match
                and name_match.group(
                    1
                ).lower()
                == name.lower()
            ):

                content_match = re.search(
                    r'content\s*=\s*["\'](.*?)["\']',
                    tag,
                    flags=re.I | re.S,
                )

                if content_match:

                    return clean_text(
                        content_match.group(
                            1
                        )
                    )

    return ""


# ============================================================
# JSON-LD DESCRIPTION
# ============================================================

def extract_jsonld_objects(page):

    objects = []

    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
        r'(.*?)'
        r'</script>',
        page,
        flags=re.I | re.S,
    )

    for script in scripts:

        try:

            data = json.loads(
                html.unescape(
                    script
                )
            )

        except Exception:

            continue

        if isinstance(
            data,
            list
        ):

            objects.extend(
                data
            )

        elif isinstance(
            data,
            dict
        ):

            graph = data.get(
                "@graph"
            )

            if isinstance(
                graph,
                list
            ):

                objects.extend(
                    graph
                )

            objects.append(
                data
            )

    return objects


def extract_jsonld_description(page):

    objects = extract_jsonld_objects(
        page
    )

    for obj in objects:

        if not isinstance(
            obj,
            dict
        ):
            continue

        description = clean_text(
            obj.get(
                "description",
                "",
            )
        )

        if description:

            return description

    return ""


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_from_html(
    page,
    base_url,
):

    candidates = []

    # --------------------------------------------------------
    # OPEN GRAPH
    # --------------------------------------------------------

    for property_name in [
        "og:image",
        "og:image:url",
        "og:image:secure_url",
    ]:

        value = extract_meta(
            page,
            property_name=property_name,
        )

        if value:

            candidates.append(
                value
            )

    # --------------------------------------------------------
    # TWITTER
    # --------------------------------------------------------

    for name in [
        "twitter:image",
        "twitter:image:src",
    ]:

        value = extract_meta(
            page,
            name=name,
        )

        if value:

            candidates.append(
                value
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    objects = extract_jsonld_objects(
        page
    )

    for obj in objects:

        if not isinstance(
            obj,
            dict
        ):
            continue

        image = obj.get(
            "image"
        )

        if isinstance(
            image,
            str
        ):

            candidates.append(
                image
            )

        elif isinstance(
            image,
            dict
        ):

            value = (
                image.get(
                    "url"
                )
                or image.get(
                    "contentUrl"
                )
            )

            if value:

                candidates.append(
                    value
                )

        elif isinstance(
            image,
            list
        ):

            for item in image:

                if isinstance(
                    item,
                    str
                ):

                    candidates.append(
                        item
                    )

                elif isinstance(
                    item,
                    dict
                ):

                    value = (
                        item.get(
                            "url"
                        )
                        or item.get(
                            "contentUrl"
                        )
                    )

                    if value:

                        candidates.append(
                            value
                        )

    # --------------------------------------------------------
    # IMAGE TAGS
    # --------------------------------------------------------

    img_tags = re.findall(
        r"<img\b[^>]*>",
        page,
        flags=re.I,
    )

    for tag in img_tags:

        for attribute in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
            "data-url",
        ]:

            match = re.search(
                rf'{attribute}\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )

            if match:

                candidates.append(
                    match.group(
                        1
                    )
                )

    final_candidates = []

    for candidate in candidates:

        candidate = html.unescape(
            candidate.strip()
        )

        if not candidate:
            continue

        candidate = urljoin(
            base_url,
            candidate,
        )

        if (
            candidate
            not in final_candidates
        ):

            final_candidates.append(
                candidate
            )

    return final_candidates


# ============================================================
# TITLE NORMALIZATION
# ============================================================

def normalize_title(title):

    title = clean_text(
        title
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    words = title.split()

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
        "as",
        "at",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "this",
        "that",
        "kenya",
        "kenyan",
    }

    return [
        word
        for word in words
        if word not in stopwords
    ]


def title_similarity(
    title_a,
    title_b,
):

    words_a = set(
        normalize_title(
            title_a
        )
    )

    words_b = set(
        normalize_title(
            title_b
        )
    )

    if not words_a or not words_b:

        return 0.0

    overlap = (
        words_a
        .intersection(
            words_b
        )
    )

    return (
        len(overlap)
        / max(
            len(words_a),
            len(words_b),
        )
    )


def title_has_reasonable_match(
    original_title,
    candidate_title,
):

    original_words = normalize_title(
        original_title
    )

    candidate_words = set(
        normalize_title(
            candidate_title
        )
    )

    if not original_words:

        return False

    overlap = len(
        set(
            original_words
        ).intersection(
            candidate_words
        )
    )

    similarity = title_similarity(
        original_title,
        candidate_title,
    )

    # Much more tolerant than the previous version.
    minimum_overlap = 2

    if len(
        original_words
    ) <= 5:

        minimum_overlap = 1

    return (
        overlap >= minimum_overlap
        and similarity >= 0.12
    )


# ============================================================
# PUBLISHER DOMAIN
# ============================================================

def normalize_publisher_domain(
    source_url="",
    source_name="",
):

    domain = get_domain(
        source_url
    )

    if domain:

        if not is_search_engine_url(
            "https://" + domain
        ):

            return domain

    return ""


def publisher_domains_match(
    candidate_domain,
    publisher_domain,
):

    if not candidate_domain:

        return False

    if not publisher_domain:

        return True

    return (
        candidate_domain
        == publisher_domain
        or candidate_domain.endswith(
            "." + publisher_domain
        )
        or publisher_domain.endswith(
            "." + candidate_domain
        )
    )


# ============================================================
# DIRECT GOOGLE RESOLUTION
# ============================================================

def try_direct_google_resolution(
    google_url,
):

    try:

        response = requests.get(
            google_url,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        final_url = response.url

        if (
            final_url
            and not is_google_news_url(
                final_url
            )
            and not is_social_domain(
                final_url
            )
            and not is_search_engine_url(
                final_url
            )
        ):

            return final_url

    except Exception as exc:

        print(
            f"Google direct resolution failed: {exc}"
        )

    return None


# ============================================================
# BING ARTICLE SEARCH
# ============================================================

def search_bing_for_article(
    title,
    publisher_domain="",
):

    query = clean_text(
        title
    )

    if publisher_domain:

        query += (
            f" site:{publisher_domain}"
        )

    search_url = (
        "https://www.bing.com/search?q="
        + quote_plus(
            query
        )
    )

    try:

        response = requests.get(
            search_url,
            headers=HEADERS,
            timeout=25,
        )

        response.raise_for_status()

        page = response.text

    except Exception as exc:

        print(
            f"Bing search failed: {exc}"
        )

        return []

    candidates = []

    # --------------------------------------------------------
    # BING RESULT BLOCKS
    # --------------------------------------------------------

    result_blocks = re.findall(
        r'<li[^>]+class=["\'][^"\']*b_algo[^"\']*["\'][^>]*>'
        r'(.*?)'
        r'</li>',
        page,
        flags=re.I | re.S,
    )

    for block in result_blocks:

        links = re.findall(
            r'<a[^>]+href=["\']([^"\']+)["\']',
            block,
            flags=re.I,
        )

        for link in links:

            link = html.unescape(
                link.strip()
            )

            if not link.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                continue

            if (
                is_google_news_url(
                    link
                )
                or is_social_domain(
                    link
                )
                or is_search_engine_url(
                    link
                )
            ):
                continue

            if link not in candidates:

                candidates.append(
                    link
                )

    # --------------------------------------------------------
    # GENERAL FALLBACK
    # --------------------------------------------------------

    if not candidates:

        links = re.findall(
            r'href=["\'](https?://[^"\']+)["\']',
            page,
            flags=re.I,
        )

        for link in links:

            link = html.unescape(
                link.strip()
            )

            if (
                is_google_news_url(
                    link
                )
                or is_social_domain(
                    link
                )
                or is_search_engine_url(
                    link
                )
            ):
                continue

            if link not in candidates:

                candidates.append(
                    link
                )

    return candidates[:30]


# ============================================================
# VERIFY PUBLISHER ARTICLE
# ============================================================

def verify_article_candidate(
    candidate_url,
    original_title,
    publisher_domain="",
):

    if not candidate_url:

        return None

    if (
        is_social_domain(
            candidate_url
        )
        or is_google_news_url(
            candidate_url
        )
        or is_search_engine_url(
            candidate_url
        )
    ):

        return None

    candidate_domain = get_domain(
        candidate_url
    )

    # Do not reject before trying the page
    # if publisher domain is unknown.
    if (
        publisher_domain
        and candidate_domain
        and not publisher_domains_match(
            candidate_domain,
            publisher_domain,
        )
    ):

        return None

    try:

        response = requests.get(
            candidate_url,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"Candidate fetch failed: {exc}"
        )

        return None

    resolved_url = response.url

    if not resolved_url:

        return None

    if (
        is_google_news_url(
            resolved_url
        )
        or is_social_domain(
            resolved_url
        )
        or is_search_engine_url(
            resolved_url
        )
    ):

        return None

    resolved_domain = get_domain(
        resolved_url
    )

    if (
        publisher_domain
        and resolved_domain
        and not publisher_domains_match(
            resolved_domain,
            publisher_domain,
        )
    ):

        return None

    page = response.text

    if not page:

        return None

    candidate_title = (
        extract_meta(
            page,
            property_name="og:title",
        )
        or extract_meta(
            page,
            name="twitter:title",
        )
    )

    if not candidate_title:

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            page,
            flags=re.I | re.S,
        )

        if title_match:

            candidate_title = clean_text(
                title_match.group(
                    1
                )
            )

    candidate_title = clean_text(
        candidate_title
    )

    if not candidate_title:

        return None

    if (
        not title_has_reasonable_match(
            original_title,
            candidate_title,
        )
    ):

        print(
            "Candidate rejected: title mismatch."
        )

        return None

    print(
        f"ARTICLE MATCH: {candidate_title}"
    )

    print(
        f"ARTICLE URL: {resolved_url}"
    )

    return {
        "url": resolved_url,
        "page": page,
        "title": candidate_title,
    }


# ============================================================
# GOOGLE NEWS ARTICLE RESOLUTION
# ============================================================

def resolve_google_news_article(
    story,
):

    google_url = story.get(
        "url",
        "",
    )

    original_title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source",
            "",
        )
    )

    source_url = clean_text(
        story.get(
            "source_url",
            "",
        )
    )

    print()
    print(
        "=" * 70
    )
    print(
        "GOOGLE NEWS RESOLUTION"
    )
    print(
        "=" * 70
    )

    print(
        f"Original title : {original_title}"
    )

    print(
        f"Publisher      : {source}"
    )

    print(
        f"Publisher URL  : {source_url}"
    )

    # --------------------------------------------------------
    # METHOD 1
    # --------------------------------------------------------

    direct_url = (
        try_direct_google_resolution(
            google_url
        )
    )

    if direct_url:

        print(
            "DIRECT GOOGLE RESOLUTION: SUCCESS"
        )

        return {
            "url": direct_url,
            "method": "direct",
        }

    print(
        "Direct Google resolution did not reach publisher."
    )

    # --------------------------------------------------------
    # METHOD 2
    # --------------------------------------------------------

    publisher_domain = (
        normalize_publisher_domain(
            source_url=source_url,
            source_name=source,
        )
    )

    if publisher_domain:

        print(
            f"Publisher domain: {publisher_domain}"
        )

    # --------------------------------------------------------
    # METHOD 3 — BING WITH PUBLISHER
    # --------------------------------------------------------

    candidates = search_bing_for_article(
        original_title,
        publisher_domain,
    )

    print(
        f"Bing publisher search returned "
        f"{len(candidates)} candidates."
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        print(
            f"Trying publisher candidate "
            f"{index}: {candidate}"
        )

        verified = (
            verify_article_candidate(
                candidate_url=candidate,
                original_title=original_title,
                publisher_domain=publisher_domain,
            )
        )

        if verified:

            return {
                "url": verified["url"],
                "page": verified["page"],
                "title": verified["title"],
                "method": "bing_publisher",
            }

    # --------------------------------------------------------
    # METHOD 4 — BROAD BING
    # --------------------------------------------------------

    print(
        "Trying broad Bing article search..."
    )

    candidates = search_bing_for_article(
        original_title,
        "",
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        print(
            f"Trying broad candidate "
            f"{index}: {candidate}"
        )

        verified = (
            verify_article_candidate(
                candidate_url=candidate,
                original_title=original_title,
                publisher_domain="",
            )
        )

        if verified:

            return {
                "url": verified["url"],
                "page": verified["page"],
                "title": verified["title"],
                "method": "bing_broad",
            }

    print(
        "Publisher article could not be resolved."
    )

    return None


# ============================================================
# GOOGLE GENERIC TEXT
# ============================================================

def is_google_generic_text(text):

    text = clean_text(
        text
    ).lower()

    if not text:

        return True

    generic_phrases = [
        "google news",
        "news.google.com",
        "google account",
        "search results",
        "before continuing",
        "privacy",
        "terms of service",
    ]

    matches = sum(
        phrase in text
        for phrase in generic_phrases
    )

    return matches >= 2


# ============================================================
# SUMMARY VALIDATION
# ============================================================

def usable_summary(text):

    text = clean_text(
        text
    )

    if not text:

        return False

    if is_google_generic_text(
        text
    ):

        return False

    return len(text) >= 60


# ============================================================
# EXTRACT ARTICLE DATA
# ============================================================

def extract_article_data(
    page,
    resolved_url,
    story,
):

    if not page:

        return None

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = (
        extract_meta(
            page,
            property_name="og:title",
        )
        or extract_meta(
            page,
            name="twitter:title",
        )
    )

    if not title:

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            page,
            flags=re.I | re.S,
        )

        if title_match:

            title = clean_text(
                title_match.group(
                    1
                )
            )

    title = clean_text(
        title
    )

    if not title:

        title = clean_text(
            story.get(
                "title",
                "",
            )
        )

    if not title:

        return None

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source = (
        extract_meta(
            page,
            property_name="og:site_name",
        )
        or story.get(
            "source",
            "",
        )
        or get_domain(
            resolved_url
        )
    )

    source = clean_text(
        source
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary_candidates = [

        extract_meta(
            page,
            property_name="og:description",
        ),

        extract_meta(
            page,
            name="description",
        ),

        extract_meta(
            page,
            name="twitter:description",
        ),

        extract_jsonld_description(
            page
        ),

        story.get(
            "summary",
            "",
        ),

        story.get(
            "raw_description",
            "",
        ),
    ]

    summary = ""

    for candidate in summary_candidates:

        candidate = clean_text(
            candidate
        )

        if usable_summary(
            candidate
        ):

            summary = candidate

            break

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_candidates = (
        extract_image_from_html(
            page,
            resolved_url,
        )
    )

    rss_image = clean_text(
        story.get(
            "rss_image",
            "",
        )
    )

    if rss_image:

        image_candidates.append(
            rss_image
        )

    image_url = ""

    checked = set()

    for candidate in image_candidates:

        candidate = clean_text(
            candidate
        )

        if not candidate:

            continue

        candidate = urljoin(
            resolved_url,
            candidate,
        )

        if candidate in checked:

            continue

        checked.add(
            candidate
        )

        if is_bad_image_url(
            candidate
        ):

            continue

        print(
            f"Checking image: {candidate}"
        )

        if verify_image(
            candidate
        ):

            image_url = candidate

            print(
                f"VALID ARTICLE IMAGE: {candidate}"
            )

            break

    if not summary:

        return None

    if not image_url:

        return None

    return {
        "title": title,
        "summary": summary,
        "source": source,
        "url": resolved_url,
        "resolved_url": resolved_url,
        "image_url": image_url,
    }


# ============================================================
# RSS FALLBACK
# ============================================================

def build_rss_verified_story(
    story
):

    print()
    print(
        "=" * 70
    )
    print(
        "RSS FALLBACK VERIFICATION"
    )
    print(
        "=" * 70
    )

    title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source",
            "",
        )
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    image_url = clean_text(
        story.get(
            "rss_image",
            "",
        )
    )

    if not title:

        print(
            "RSS fallback rejected: no title."
        )

        return None

    if not source:

        print(
            "RSS fallback rejected: no publisher."
        )

        return None

    if not usable_summary(
        summary
    ):

        print(
            "RSS fallback rejected: weak summary."
        )

        return None

    if not image_url:

        print(
            "RSS fallback rejected: no RSS image."
        )

        return None

    image_url = urljoin(
        story.get(
            "url",
            "",
        ),
        image_url,
    )

    print(
        f"Checking RSS image: {image_url}"
    )

    if not verify_image(
        image_url
    ):

        print(
            "RSS fallback rejected: RSS image failed validation."
        )

        return None

    print(
        "RSS FALLBACK PASSED"
    )

    print(
        f"Publisher: {source}"
    )

    print(
        f"Image: {image_url}"
    )

    return {
        "title": title,
        "summary": summary,
        "source": source,
        "url": story.get(
            "url",
            "",
        ),
        "resolved_url": story.get(
            "url",
            "",
        ),
        "image_url": image_url,
        "verification": "google_news_rss",
    }


# ============================================================
# ARTICLE ENRICHMENT
# ============================================================

def enrich_story(story):

    original_url = story.get(
        "url",
        "",
    )

    if not original_url:

        print(
            "Rejected: story has no URL."
        )

        return None

    if is_social_domain(
        original_url
    ):

        print(
            "Rejected: social-media URL."
        )

        return None

    # ========================================================
    # GOOGLE NEWS STORY
    # ========================================================

    if is_google_news_url(
        original_url
    ):

        resolution = (
            resolve_google_news_article(
                story
            )
        )

        # ----------------------------------------------------
        # PUBLISHER ARTICLE FOUND
        # ----------------------------------------------------

        if resolution:

            article_url = resolution.get(
                "url",
                "",
            )

            print(
                f"Resolved publisher article: {article_url}"
            )

            try:

                response = requests.get(
                    article_url,
                    headers=HEADERS,
                    timeout=30,
                    allow_redirects=True,
                )

                response.raise_for_status()

                resolved_url = response.url

                page = response.text

            except Exception as exc:

                print(
                    f"Publisher fetch failed: {exc}"
                )

                page = ""
                resolved_url = ""

            if (
                page
                and resolved_url
                and not is_google_news_url(
                    resolved_url
                )
            ):

                article = extract_article_data(
                    page,
                    resolved_url,
                    story,
                )

                if article:

                    story.update(
                        article
                    )

                    story[
                        "verification"
                    ] = resolution.get(
                        "method",
                        "publisher",
                    )

                    print()
                    print(
                        "=" * 70
                    )
                    print(
                        "ARTICLE VERIFICATION PASSED"
                    )
                    print(
                        "=" * 70
                    )

                    return story

                print(
                    "Publisher page did not provide complete article data."
                )

        # ----------------------------------------------------
        # RSS FALLBACK
        # ----------------------------------------------------

        fallback = (
            build_rss_verified_story(
                story
            )
        )

        if fallback:

            story.update(
                fallback
            )

            return story

        print(
            "Google News story failed all verification methods."
        )

        return None

    # ========================================================
    # NON-GOOGLE ARTICLE
    # ========================================================

    try:

        response = requests.get(
            original_url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"Rejected: article fetch failed: {exc}"
        )

        return None

    resolved_url = response.url

    if not resolved_url:

        return None

    if (
        is_google_news_url(
            resolved_url
        )
        or is_social_domain(
            resolved_url
        )
        or is_search_engine_url(
            resolved_url
        )
    ):

        return None

    page = response.text

    article = extract_article_data(
        page,
        resolved_url,
        story,
    )

    if not article:

        print(
            "Rejected: article data incomplete."
        )

        return None

    story.update(
        article
    )

    story[
        "verification"
    ] = "direct"

    print()
    print(
        "=" * 70
    )
    print(
        "ARTICLE VERIFICATION PASSED"
    )
    print(
        "=" * 70
    )

    return story


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story):

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

    text = (
        f"{title} {summary}"
    ).lower()

    score = 0

    # --------------------------------------------------------
    # COUNTY RELEVANCE
    # --------------------------------------------------------

    for county in COUNTIES:

        if county.lower() in text:

            score += 10

    # --------------------------------------------------------
    # KEYWORDS
    # --------------------------------------------------------

    for keyword in KEYWORDS:

        if keyword in text:

            score += 2

    # --------------------------------------------------------
    # NUMBERS
    # --------------------------------------------------------

    if re.search(
        r"\d",
        title,
    ):

        score += 5

    # --------------------------------------------------------
    # MONEY
    # --------------------------------------------------------

    if re.search(
        r"\b(?:kes|ksh|sh|million|billion)\b",
        text,
    ):

        score += 5

    # --------------------------------------------------------
    # ACTION TERMS
    # --------------------------------------------------------

    action_terms = [
        "announced",
        "approved",
        "launched",
        "opened",
        "started",
        "began",
        "signed",
        "funded",
        "awarded",
        "construction",
        "completed",
        "commissioned",
        "invest",
        "investment",
        "development",
    ]

    for term in action_terms:

        if term in text:

            score += 4

    # --------------------------------------------------------
    # PUBLIC INTEREST
    # --------------------------------------------------------

    public_interest_terms = [
        "road",
        "hospital",
        "school",
        "water",
        "jobs",
        "farmers",
        "health",
        "education",
        "housing",
        "electricity",
        "bridge",
        "market",
    ]

    for term in public_interest_terms:

        if term in text:

            score += 3

    # --------------------------------------------------------
    # STORY DEPTH
    # --------------------------------------------------------

    if len(summary) >= 150:

        score += 5

    if len(summary) >= 300:

        score += 5

    if len(summary) >= 500:

        score += 3

    # --------------------------------------------------------
    # WEAK STORIES
    # --------------------------------------------------------

    weak_terms = [
        "opinion",
        "podcast",
        "newsletter",
        "sports results",
        "horoscope",
        "celebrity",
        "gossip",
        "weekly roundup",
        "daily roundup",
    ]

    for term in weak_terms:

        if term in text:

            score -= 10

    if len(
        title.split()
    ) < 4:

        score -= 5

    if len(summary) < 60:

        score -= 10

    return score


# ============================================================
# HEADLINE
# ============================================================

def create_short_headline(
    title
):

    title = clean_text(
        title
    )

    if len(title) <= 100:

        return title

    words = title.split()

    result = []

    current_length = 0

    for word in words:

        extra = (
            len(word)
            + (
                1
                if result
                else 0
            )
        )

        if (
            current_length
            + extra
            > 100
        ):

            break

        result.append(
            word
        )

        current_length += extra

    shortened = " ".join(
        result
    )

    if not shortened:

        return title[:100]

    return shortened


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story
):

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

    county = clean_text(
        story.get(
            "county",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source",
            "",
        )
    )

    if county:

        opening = (
            f"Here is the latest development "
            f"from {county}."
        )

    else:

        opening = (
            "Here is the latest major "
            "development from the Rift Valley."
        )

    narration = (
        f"{opening} "
        f"{title}. "
        f"{summary} "
        f"This is Rift Valley Watch, "
        f"bringing you verified developments "
        f"from across the region."
    )

    if source:

        narration += (
            f" The report comes from {source}."
        )

    return " ".join(
        narration.split()
    )


# ============================================================
# COLLECT CANDIDATES
# ============================================================

def collect_candidates():

    all_candidates = []

    seen_titles = set()

    print()
    print(
        "=" * 70
    )
    print(
        "COLLECTING RIFT VALLEY NEWS"
    )
    print(
        "=" * 70
    )

    for county in COUNTIES:

        query = (
            f'"{county}" Kenya when:1d'
        )

        print()
        print(
            f"SEARCHING: {county}"
        )

        root = fetch_rss(
            query
        )

        stories = parse_feed(
            root
        )

        print(
            f"Found {len(stories)} RSS stories."
        )

        for story in stories:

            title = clean_text(
                story.get(
                    "title",
                    "",
                )
            )

            if not title:

                continue

            normalized = " ".join(
                normalize_title(
                    title
                )
            )

            if normalized in seen_titles:

                continue

            seen_titles.add(
                normalized
            )

            story[
                "county"
            ] = county

            story[
                "score"
            ] = score_story(
                story
            )

            all_candidates.append(
                story
            )

    all_candidates.sort(
        key=lambda story: story.get(
            "score",
            0,
        ),
        reverse=True,
    )

    return all_candidates


# ============================================================
# SELECT VERIFIED STORY
# ============================================================

def select_story():

    candidates = collect_candidates()

    if not candidates:

        raise RuntimeError(
            "No recent Rift Valley stories found."
        )

    print()
    print(
        f"Found {len(candidates)} candidates."
    )

    maximum_checks = min(
        len(candidates),
        80,
    )

    for index, candidate in enumerate(
        candidates[
            :maximum_checks
        ],
        start=1,
    ):

        print()
        print(
            "=" * 70
        )

        print(
            f"CHECKING STORY "
            f"{index}/{maximum_checks}"
        )

        print(
            f"County : "
            f"{candidate.get('county', '')}"
        )

        print(
            f"Title  : "
            f"{candidate.get('title', '')}"
        )

        print(
            f"Source : "
            f"{candidate.get('source', '')}"
        )

        print(
            f"Score  : "
            f"{candidate.get('score', 0)}"
        )

        print(
            "=" * 70
        )

        story = enrich_story(
            candidate
        )

        if not story:

            print(
                "Rejected: article did not pass verification."
            )

            continue

        story[
            "title"
        ] = create_short_headline(
            story[
                "title"
            ]
        )

        story[
            "narration"
        ] = build_narration(
            story
        )

        story[
            "brand"
        ] = "Rift Valley Watch"

        print()
        print(
            "=" * 70
        )

        print(
            "SELECTED STORY"
        )

        print(
            f"County       : {story.get('county', '')}"
        )

        print(
            f"Title        : {story.get('title', '')}"
        )

        print(
            f"Source       : {story.get('source', '')}"
        )

        print(
            f"Verification : {story.get('verification', '')}"
        )

        print(
            f"Image        : {story.get('image_url', '')}"
        )

        print(
            "=" * 70
        )

        return story

    raise RuntimeError(
        "No recent story passed verification after checking all available candidates."
    )


# ============================================================
# SAVE STORY
# ============================================================

def save_story(
    story
):

    STORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with STORY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            story,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        f"Story saved to: {STORY_FILE}"
    )

    return STORY_FILE


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=" * 70
    )

    print(
        "RIFT VALLEY WATCH — NEWS ENGINE V7"
    )

    print(
        "=" * 70
    )

    story = select_story()

    save_story(
        story
    )

    print()
    print(
        "=" * 70
    )

    print(
        "GENERATING VIDEO"
    )

    print(
        "=" * 70
    )

    output = generate_video(
        story
    )

    print()
    print(
        "=" * 70
    )

    print(
        "RIFT VALLEY WATCH COMPLETE"
    )

    print(
        f"VIDEO: {output}"
    )

    print(
        "=" * 70
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
