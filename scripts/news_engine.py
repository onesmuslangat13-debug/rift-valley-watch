from pathlib import Path
import json
import html
import hashlib
import re
import sys
import time
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE V13
#
# FIXES:
# - Does not require county detection
# - Follows redirects
# - Extracts Google News redirect destinations
# - Uses RSS descriptions when publisher pages fail
# - Extracts image URLs from RSS and article pages
# - Provides rejection diagnostics
# - Downloads only real photographic images
# - No BS4
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_JSON = DATA_DIR / "story.json"
SCRIPT_JSON = DATA_DIR / "script.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/153.0 Safari/537.36"
)

MAX_STORIES = 12
MAX_IMAGES = 5

MIN_IMAGE_BYTES = 6000
MIN_WIDTH = 400
MIN_HEIGHT = 250


COUNTY_ALIASES = {
    "Bomet": ["bomet", "sotik", "konoin", "chepalungu", "longisa"],
    "Kericho": ["kericho", "ainamoi", "belgut", "bureti", "litein"],
    "Nakuru": ["nakuru", "naivasha", "gilgil", "molo", "bahati", "njoro"],
    "Nandi": ["nandi", "kapsabet", "aldai", "emgwen", "mosop"],
    "Uasin Gishu": ["uasin gishu", "eldoret", "kesses", "kapseret", "soy"],
    "Elgeyo-Marakwet": [
        "elgeyo",
        "marakwet",
        "iten",
        "keiyo",
        "kapsowar",
    ],
    "West Pokot": [
        "west pokot",
        "pokot",
        "kapenguria",
        "kacheliba",
        "sigor",
    ],
    "Narok": ["narok", "kilgoris", "suswa", "transmara"],
    "Trans Nzoia": [
        "trans nzoia",
        "kitale",
        "endebess",
        "saboti",
        "cherangany",
    ],
    "Samburu": ["samburu", "maralal", "baragoi", "wamba"],
    "Turkana": ["turkana", "lodwar", "kakuma", "lokichar"],
    "Laikipia": ["laikipia", "nanyuki", "nyahururu", "rumuruti"],
    "Kajiado": [
        "kajiado",
        "kitengela",
        "ngong",
        "loitokitok",
        "namanga",
    ],
}


SEARCH_QUERIES = [
    "Rift Valley Kenya latest news",
    "Bomet latest news Kenya",
    "Kericho latest news Kenya",
    "Nakuru latest news Kenya",
    "Nandi latest news Kenya",
    "Eldoret Uasin Gishu latest news",
    "Elgeyo Marakwet latest news",
    "West Pokot latest news",
    "Narok latest news Kenya",
    "Trans Nzoia Kitale latest news",
    "Samburu latest news Kenya",
    "Turkana latest news Kenya",
    "Laikipia latest news Kenya",
    "Kajiado latest news Kenya",
]


FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "rigathi",
    "gachagua",
]


FORBIDDEN_IMAGE_TERMS = [
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "news.google.com",
    "bing.com",
    "bingusercontent.com",
    "search-result",
    "search_result",
    "screenshot",
    "screen-shot",
    "citizen",
    "citizen-digital",
    "citizentv",
    "ctv",
    "worldcup",
    "world-cup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
    "missing-image",
    "missing_image",
    "generic",
    "dummy",
    "logo",
    "favicon",
    "icon",
    "sprite",
    "advert",
    "advertisement",
    "social",
    "share",
]


def log(message=""):
    print(message, flush=True)


def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]*>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(value, base_url=""):
    if not value:
        return ""

    value = html.unescape(str(value)).strip()
    value = value.replace("\\/", "/")

    if value.startswith("//"):
        value = "https:" + value

    if base_url:
        value = urljoin(base_url, value)

    return value


def is_http_url(value):
    try:
        return urlparse(value).scheme in ("http", "https")
    except Exception:
        return False


def hostname(value):
    try:
        return urlparse(value).netloc.lower()
    except Exception:
        return ""


def forbidden_story(text):
    lower = clean_text(text).lower()

    return any(
        term in lower
        for term in FORBIDDEN_STORY_TERMS
    )


def forbidden_image(value):
    lower = str(value).lower()

    return any(
        term in lower
        for term in FORBIDDEN_IMAGE_TERMS
    )


def fetch_response(url, timeout=30, limit=12_000_000):
    if not is_http_url(url):
        return b"", ""

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml,image/avif,image/webp,"
                    "image/apng,image/svg+xml,image/*,*/*;q=0.8"
                ),
                "Accept-Language": "en-KE,en;q=0.9",
                "Cache-Control": "no-cache",
            },
        )

        with urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            data = response.read(limit + 1)

        if len(data) > limit:
            return b"", final_url

        return data, final_url

    except Exception:
        return b"", ""


def fetch_bytes(url, timeout=30, limit=12_000_000):
    data, _ = fetch_response(
        url,
        timeout=timeout,
        limit=limit,
    )

    return data


def fetch_text(url):
    data, final_url = fetch_response(url)

    if not data:
        return ""

    try:
        return data.decode(
            "utf-8",
            errors="ignore",
        )
    except Exception:
        return ""


def resolve_google_news_url(url):
    url = normalize_url(url)

    if not url:
        return ""

    parsed = urlparse(url)

    if "news.google.com" not in parsed.netloc.lower():
        return url

    query = parse_qs(parsed.query)

    for key in ["url", "u", "link"]:
        values = query.get(key)

        if values:
            candidate = normalize_url(values[0])

            if is_http_url(candidate):
                return candidate

    data, final_url = fetch_response(url)

    if final_url and "news.google.com" not in hostname(final_url):
        return final_url

    page = data.decode(
        "utf-8",
        errors="ignore",
    ) if data else ""

    candidates = []

    candidates.extend(
        re.findall(
            r'https?://[^"\'<> ]+',
            page,
            flags=re.IGNORECASE,
        )
    )

    for candidate in candidates:
        candidate = html.unescape(candidate)
        candidate = candidate.replace("\\u003d", "=")
        candidate = candidate.replace("\\u0026", "&")
        candidate = candidate.replace("\\/", "/")

        if not is_http_url(candidate):
            continue

        if "news.google.com" in hostname(candidate):
            continue

        if "google.com" in hostname(candidate):
            continue

        return candidate

    return url


def google_rss_url(query):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        "&hl=en-KE&gl=KE&ceid=KE:en"
    )


def parse_rss(xml_text):
    results = []

    if not xml_text:
        return results

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return results

    for item in root.findall(".//item"):
        title_node = item.find("title")
        link_node = item.find("link")
        description_node = item.find("description")
        date_node = item.find("pubDate")
        source_node = item.find("source")

        title = clean_text(
            title_node.text
            if title_node is not None
            else ""
        )

        link = clean_text(
            link_node.text
            if link_node is not None
            else ""
        )

        description = clean_text(
            description_node.text
            if description_node is not None
            else ""
        )

        published = clean_text(
            date_node.text
            if date_node is not None
            else ""
        )

        source = clean_text(
            source_node.text
            if source_node is not None
            else ""
        )

        if title and link:
            results.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published": published,
                    "source": source,
                }
            )

    return results


def meta_value(page, key):
    if not page:
        return ""

    pattern_one = (
        r'<meta[^>]+'
        r'(?:property|name|itemprop)\s*=\s*["\']'
        + re.escape(key)
        + r'["\'][^>]+content\s*=\s*["\']'
        r'([^"\']+)'
    )

    match = re.search(
        pattern_one,
        page,
        flags=re.IGNORECASE,
    )

    if match:
        return html.unescape(match.group(1))

    pattern_two = (
        r'<meta[^>]+content\s*=\s*["\']'
        r'([^"\']+)["\'][^>]+'
        r'(?:property|name|itemprop)\s*=\s*["\']'
        + re.escape(key)
        + r'["\']'
    )

    match = re.search(
        pattern_two,
        page,
        flags=re.IGNORECASE,
    )

    if match:
        return html.unescape(match.group(1))

    return ""


def page_title(page):
    value = meta_value(page, "og:title")

    if value:
        return clean_text(value)

    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        return clean_text(match.group(1))

    return ""


def page_description(page):
    for key in [
        "og:description",
        "twitter:description",
        "description",
    ]:
        value = meta_value(page, key)

        if value:
            return clean_text(value)

    return ""


def extract_article_text(page):
    if not page:
        return ""

    blocks = re.findall(
        r"<p[^>]*>(.*?)</p>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    output = []

    for block in blocks:
        text = clean_text(block)

        if len(text) < 45:
            continue

        lower = text.lower()

        if "subscribe" in lower:
            continue

        if "advertisement" in lower:
            continue

        if "cookie" in lower:
            continue

        if "sign up" in lower:
            continue

        output.append(text)

        if len(output) >= 12:
            break

    return " ".join(output)[:4500]


def add_image_url(results, value, base_url=""):
    value = normalize_url(value, base_url)

    if not value:
        return

    if not is_http_url(value):
        return

    if forbidden_image(value):
        return

    if value not in results:
        results.append(value)


def extract_srcset(value, results, base_url=""):
    if not value:
        return

    for item in value.split(","):
        parts = item.strip().split()

        if not parts:
            continue

        add_image_url(
            results,
            parts[0],
            base_url,
        )


def extract_image_urls(page, base_url=""):
    results = []

    if not page:
        return results

    for key in [
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
    ]:
        add_image_url(
            results,
            meta_value(page, key),
            base_url,
        )

    tags = re.findall(
        r"<img[^>]*>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    for tag in tags:
        attributes = dict(
            re.findall(
                r'([:\w-]+)\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.IGNORECASE,
            )
        )

        for key in [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-url",
            "data-fsrc",
            "data-lazy",
        ]:
            add_image_url(
                results,
                attributes.get(key, ""),
                base_url,
            )

        for key in [
            "srcset",
            "data-srcset",
        ]:
            extract_srcset(
                attributes.get(key, ""),
                results,
                base_url,
            )

    raw_urls = re.findall(
        r'https?://[^"\'<> ]+?\.(?:jpg|jpeg|png|webp)'
        r'(?:\?[^"\'<> ]*)?',
        page,
        flags=re.IGNORECASE,
    )

    for value in raw_urls:
        add_image_url(
            results,
            value,
            base_url,
        )

    return results


def extract_rss_image_urls(item):
    results = []

    for key in [
        "description",
        "title",
        "link",
    ]:
        value = item.get(key, "")

        if not value:
            continue

        raw_urls = re.findall(
            r'https?://[^"\'<> ]+?\.(?:jpg|jpeg|png|webp)'
            r'(?:\?[^"\'<> ]*)?',
            str(value),
            flags=re.IGNORECASE,
        )

        for image_url in raw_urls:
            add_image_url(
                results,
                image_url,
                "",
            )

    return results


def detect_county(title, description, article_text):
    text = (
        title
        + " "
        + description
        + " "
        + article_text
    ).lower()

    best_county = ""
    best_score = 0

    for county, aliases in COUNTY_ALIASES.items():
        score = 0

        for alias in aliases:
            if alias in text:
                score += 1

        if score > best_score:
            best_score = score
            best_county = county

    return best_county or "Rift Valley"


def detect_category(title, description, article_text):
    text = (
        title
        + " "
        + description
        + " "
        + article_text
    ).lower()

    if any(
        word in text
        for word in [
            "governor",
            " mp ",
            "mp ",
            "senator",
            "president",
            "politics",
            "political",
            "election",
            "parliament",
            "deputy president",
            "cabinet secretary",
        ]
    ):
        return "Politics"

    if any(
        word in text
        for word in [
            "farmer",
            "agriculture",
            "tea",
            "maize",
            "livestock",
            "coffee",
            "harvest",
        ]
    ):
        return "Agriculture"

    if any(
        word in text
        for word in [
            "police",
            "arrest",
            "crime",
            "murder",
            "accident",
            "security",
            "investigation",
        ]
    ):
        return "Security"

    if any(
        word in text
        for word in [
            "hospital",
            "health",
            "doctor",
            "patients",
            "disease",
            "medical",
        ]
    ):
        return "Health"

    if any(
        word in text
        for word in [
            "road",
            "project",
            "development",
            "water",
            "school",
            "electricity",
            "bridge",
        ]
    ):
        return "Development"

    if any(
        word in text
        for word in [
            "business",
            "economy",
            "company",
            "market",
            "trade",
            "finance",
            "investment",
        ]
    ):
        return "Business"

    return "Regional News"


def image_score(url):
    lower = url.lower()
    score = 0

    for word in [
        "article",
        "news",
        "upload",
        "uploads",
        "media",
        "image",
        "images",
        "photo",
        "photos",
        "content",
        "featured",
        "story",
        "wp-content",
        "2026",
        "2025",
    ]:
        if word in lower:
            score += 2

    for word in [
        "logo",
        "icon",
        "favicon",
        "avatar",
        "profile",
        "placeholder",
        "default",
        "banner",
        "advert",
        "social",
        "share",
        "thumbnail",
    ]:
        if word in lower:
            score -= 8

    return score


def valid_image(path):
    try:
        if not path.exists():
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        with Image.open(path) as image:
            width, height = image.size

            if width < MIN_WIDTH:
                return False

            if height < MIN_HEIGHT:
                return False

            image.verify()

        return True

    except Exception:
        return False


def image_signature(path):
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((80, 80))

            return hashlib.sha256(
                image.tobytes()
            ).hexdigest()

    except Exception:
        return ""


def download_image(url, story_id, number):
    if forbidden_image(url):
        return ""

    digest = hashlib.sha256(
        f"{story_id}-{number}-{url}".encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:24]

    temporary = SOURCE_DIR / f"{digest}.tmp"
    final = SOURCE_DIR / f"{digest}.jpg"

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "image/avif,image/webp,image/apng,"
                    "image/svg+xml,image/*,*/*;q=0.8"
                ),
                "Accept-Language": "en-KE,en;q=0.9",
                "Referer": (
                    f"https://{hostname(url)}/"
                    if hostname(url)
                    else ""
                ),
            },
        )

        with urlopen(
            request,
            timeout=35,
        ) as response:
            data = response.read(15_000_000)

        if len(data) < MIN_IMAGE_BYTES:
            return ""

        temporary.write_bytes(data)

        with Image.open(temporary) as image:
            image = image.convert("RGB")

            image.thumbnail(
                (2400, 2400),
                Image.Resampling.LANCZOS,
            )

            image.save(
                final,
                "JPEG",
                quality=92,
                optimize=True,
            )

        temporary.unlink(missing_ok=True)

        if not valid_image(final):
            final.unlink(missing_ok=True)
            return ""

        return str(
            final.relative_to(BASE_DIR)
        ).replace("\\", "/")

    except Exception:
        temporary.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        return ""


def clean_old_images():
    extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".bmp",
        ".tif",
        ".tiff",
        ".tmp",
    }

    removed = 0

    for path in SOURCE_DIR.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() in extensions:
            try:
                path.unlink()
                removed += 1
            except Exception:
                pass

    log(f"Old source images removed: {removed}")


def enrich_item(item):
    original_title = clean_text(
        item.get("title", "")
    )

    original_link = normalize_url(
        item.get("link", "")
    )

    description = clean_text(
        item.get("description", "")
    )

    source = clean_text(
        item.get("source", "")
    )

    published = clean_text(
        item.get("published", "")
    )

    if not original_title or not original_link:
        return None

    if forbidden_story(original_title):
        log("    rejected: forbidden story title")
        return None

    link = resolve_google_news_url(
        original_link
    )

    if not link:
        link = original_link

    page = fetch_text(link)

    title = original_title
    article_text = ""
    page_description_text = ""

    if page:
        real_title = page_title(page)

        if real_title:
            title = real_title

        page_description_text = page_description(page)

        if page_description_text:
            description = page_description_text

        article_text = extract_article_text(page)

    combined_text = (
        title
        + " "
        + description
        + " "
        + article_text
    )

    if forbidden_story(combined_text):
        log("    rejected: forbidden story text")
        return None

    county = detect_county(
        title,
        description,
        article_text,
    )

    category = detect_category(
        title,
        description,
        article_text,
    )

    candidates = []

    if page:
        candidates.extend(
            extract_image_urls(
                page,
                link,
            )
        )

    candidates.extend(
        extract_rss_image_urls(item)
    )

    unique_candidates = []

    for candidate in candidates:
        candidate = normalize_url(
            candidate,
            link,
        )

        if not candidate:
            continue

        if forbidden_image(candidate):
            continue

        if candidate not in unique_candidates:
            unique_candidates.append(candidate)

    unique_candidates.sort(
        key=image_score,
        reverse=True,
    )

    log(
        f"    image candidates: "
        f"{len(unique_candidates)}"
    )

    if not unique_candidates:
        log("    rejected: no image candidates")
        return None

    story_id = hashlib.sha256(
        link.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:18]

    images = []
    signatures = set()

    for number, image_url in enumerate(
        unique_candidates
    ):
        if len(images) >= MAX_IMAGES:
            break

        local_path = download_image(
            image_url,
            story_id,
            number,
        )

        if not local_path:
            continue

        absolute_path = BASE_DIR / local_path

        signature = image_signature(
            absolute_path
        )

        if not signature:
            continue

        if signature in signatures:
            continue

        signatures.add(signature)
        images.append(local_path)

    if not images:
        log("    rejected: image downloads failed")
        return None

    if not description:
        description = article_text[:600]

    if not description:
        description = title

    if not article_text:
        article_text = description

    source_name = source or hostname(link)

    return {
        "id": story_id,
        "title": title,
        "url": link,
        "source": source_name,
        "source_name": source_name,
        "published": published,
        "description": description,
        "summary": description,
        "article_text": article_text,
        "county": county,
        "category": category,
        "images": images,
        "image": images[0],
        "image_path": images[0],
        "image_paths": images,
        "article_images": images,
        "photo_count": len(images),
    }


def collect_items():
    items = []

    for query in SEARCH_QUERIES:
        log(f"Searching: {query}")

        rss_url = google_rss_url(query)
        xml = fetch_text(rss_url)

        if not xml:
            log("    RSS unavailable")
            continue

        parsed = parse_rss(xml)

        log(
            f"    RSS items: {len(parsed)}"
        )

        items.extend(parsed)

        time.sleep(0.3)

    return items


def deduplicate(stories):
    output = []
    seen_titles = set()
    seen_urls = set()

    for story in stories:
        title = clean_text(
            story.get("title", "")
        ).lower()

        url = clean_text(
            story.get("url", "")
        ).lower()

        title_key = re.sub(
            r"[^a-z0-9]+",
            " ",
            title,
        ).strip()

        if title_key and title_key in seen_titles:
            continue

        if url and url in seen_urls:
            continue

        if title_key:
            seen_titles.add(title_key)

        if url:
            seen_urls.add(url)

        output.append(story)

    return output


def build_script(story):
    title = clean_text(
        story.get("title", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    category = clean_text(
        story.get("category", "")
    )

    source = clean_text(
        story.get("source_name", "")
    )

    article_text = clean_text(
        story.get("article_text", "")
    )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        article_text,
    )

    sentences = [
        sentence.strip()
        for sentence in sentences
        if len(sentence.strip()) >= 35
    ][:4]

    parts = [
        title +
