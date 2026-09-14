from pathlib import Path
import json
import html
import hashlib
import re
import sys
import time
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE V12
# NO BS4
# NO COMPLEX MULTILINE REGEX
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
    "Elgeyo-Marakwet": ["elgeyo", "marakwet", "iten", "keiyo", "kapsowar"],
    "West Pokot": ["west pokot", "pokot", "kapenguria", "kacheliba", "sigor"],
    "Narok": ["narok", "kilgoris", "suswa", "transmara"],
    "Trans Nzoia": ["trans nzoia", "kitale", "endebess", "saboti", "cherangany"],
    "Samburu": ["samburu", "maralal", "baragoi", "wamba"],
    "Turkana": ["turkana", "lodwar", "kakuma", "lokichar"],
    "Laikipia": ["laikipia", "nanyuki", "nyahururu", "rumuruti"],
    "Kajiado": ["kajiado", "kitengela", "ngong", "loitokitok", "namanga"],
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


def log(message):
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

    for term in FORBIDDEN_STORY_TERMS:
        if term in lower:
            return True

    return False


def forbidden_image(value):
    lower = str(value).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lower:
            return True

    return False


def fetch_bytes(url, timeout=25, limit=8_000_000):
    if not is_http_url(url):
        return b""

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            },
        )

        with urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)

        if len(data) > limit:
            return b""

        return data

    except Exception:
        return b""


def fetch_text(url):
    data = fetch_bytes(url)

    if not data:
        return ""

    return data.decode(
        "utf-8",
        errors="ignore",
    )


def google_rss_url(query):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-KE&gl=KE&ceid=KE:en"
    )


def parse_rss(xml_text):
    results = []

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

        title = ""
        link = ""
        description = ""
        published = ""
        source = ""

        if title_node is not None:
            title = clean_text(title_node.text)

        if link_node is not None:
            link = clean_text(link_node.text)

        if description_node is not None:
            description = clean_text(
                description_node.text
            )

        if date_node is not None:
            published = clean_text(date_node.text)

        if source_node is not None:
            source = clean_text(source_node.text)

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
    pattern_one = (
        r'<meta[^>]+(?:property|name|itemprop)\s*=\s*["\']'
        + re.escape(key)
        + r'["\'][^>]+content\s*=\s*["\']([^"\']+)'
    )

    match = re.search(
        pattern_one,
        page,
        flags=re.IGNORECASE,
    )

    if match:
        return html.unescape(match.group(1))

    pattern_two = (
        r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\']'
        r'[^>]+(?:property|name|itemprop)\s*=\s*["\']'
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
    blocks = re.findall(
        r"<p[^>]*>(.*?)</p>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    output = []

    for block in blocks:
        text = clean_text(block)

        if len(text) >= 45:
            lower = text.lower()

            if "subscribe" in lower:
                continue

            if "advertisement" in lower:
                continue

            if "cookie" in lower:
                continue

            output.append(text)

        if len(output) >= 12:
            break

    return " ".join(output)[:4500]


def add_image_url(results, value, base_url):
    value = normalize_url(value, base_url)

    if not value:
        return

    if not is_http_url(value):
        return

    if forbidden_image(value):
        return

    if value not in results:
        results.append(value)


def extract_srcset(value, results, base_url):
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


def extract_image_urls(page, base_url):
    results = []

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
        r'https?://[^"\'>\s]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\'>\s]*)?',
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

    return best_county


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
            "mp ",
            "senator",
            "president",
            "politics",
            "election",
            "political",
            "parliament",
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
    ).hexdigest()[:20]

    temporary = SOURCE_DIR / f"{digest}.tmp"
    final = SOURCE_DIR / f"{digest}.jpg"

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/*,*/*;q=0.8",
                "Referer": f"https://{hostname(url)}/",
            },
        )

        with urlopen(
            request,
            timeout=30,
        ) as response:
            data = response.read(12_000_000)

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
                quality=91,
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
    title = clean_text(item.get("title", ""))
    link = normalize_url(item.get("link", ""))
    description = clean_text(
        item.get("description", "")
    )
    source = clean_text(
        item.get("source", "")
    )
    published = clean_text(
        item.get("published", "")
    )

    if not title or not link:
        return None

    if forbidden_story(title):
        return None

    page = fetch_text(link)

    if not page:
        return None

    real_title = page_title(page)

    if real_title:
        title = real_title

    real_description = page_description(page)

    if real_description:
        description = real_description

    article_text = extract_article_text(page)

    county = detect_county(
        title,
        description,
        article_text,
    )

    if not county:
        return None

    if forbidden_story(
        title + " " + article_text
    ):
        return None

    category = detect_category(
        title,
        description,
        article_text,
    )

    candidates = extract_image_urls(
        page,
        link,
    )

    candidates.sort(
        key=image_score,
        reverse=True,
    )

    story_id = hashlib.sha256(
        link.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:18]

    images = []
    signatures = set()

    for number, image_url in enumerate(
        candidates
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

        signature = image_signature(
            BASE_DIR / local_path
        )

        if not signature:
            continue

        if signature in signatures:
            continue

        signatures.add(signature)
        images.append(local_path)

    if not images:
        return None

    return {
        "title": title,
        "url": link,
        "source": source or hostname(link),
        "source_name": source or hostname(link),
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

        xml = fetch_text(
            google_rss_url(query)
        )

        if not xml:
            continue

        items.extend(
            parse_rss(xml)
        )

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

        url = story.get(
            "url",
            "",
        ).lower()

        title_key = re.sub(
            r"[^a-z0-9]+",
            " ",
            title,
        ).strip()

        if title_key in seen_titles:
            continue

        if url in seen_urls:
            continue

        seen_titles.add(title_key)
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

    parts = [title + "."]

    parts.extend(sentences)

    if county:
        parts.append(
            f"The development is being reported in {county} County."
        )

    if category:
        parts.append(
            f"This is part of the latest {category.lower()} news from the Rift Valley region."
        )

    if source:
        parts.append(
            f"Reporting from {source}."
        )

    narration = clean_text(
        " ".join(parts)
    )

    if len(narration) < 180:
        narration += (
            " Rift Valley Watch is following the development "
            "and will provide further verified updates "
            "as more information becomes available."
        )

    return {
        "title": title,
        "county": county,
        "category": category,
        "source": source,
        "narration": narration,
        "script": narration,
        "text": narration,
        "images": story.get(
            "images",
            [],
        ),
        "story_url": story.get(
            "url",
            "",
        ),
    }


def write_outputs(stories):
    story_payload = {
        "version": "RVW_NEWS_ENGINE_V12",
        "generated_at": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "count": len(stories),
        "stories": stories,
    }

    script_payload = {
        "version": "RVW_NEWS_ENGINE_V12",
        "generated_at": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "count": len(stories),
        "scripts": [
            build_script(story)
            for story in stories
        ],
    }

    STORY_JSON.write_text(
        json.dumps(
            story_payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    SCRIPT_JSON.write_text(
        json.dumps(
            script_payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main():
    log("=" * 68)
    log("RIFT VALLEY WATCH NEWS ENGINE V12")
    log("=" * 68)

    clean_old_images()

    items = collect_items()

    log(f"RSS items collected: {len(items)}")

    stories = []

    for index, item in enumerate(items, start=1):
        log(
            f"[{index}] {item.get('title', '')[:100]}"
        )

        story = enrich_item(item)

        if not story:
            log("    skipped")
            continue

        log(
            f"    County: {story['county']}"
        )

        log(
            f"    Real photos: {len(story['images'])}"
        )

        stories.append(story)

        if len(stories) >= MAX_STORIES:
            break

    stories = deduplicate(stories)

    if not stories:
        raise RuntimeError(
            "No valid stories with real article photographs were found."
        )

    write_outputs(stories)

    log("=" * 68)
    log(f"Valid stories: {len(stories)}")
    log(
        "REAL STORY IMAGES FOUND: "
        + str(
            sum(
                len(
                    story.get(
                        "images",
                        [],
                    )
                )
                for story in stories
            )
        )
    )
    log(f"Created: {STORY_JSON}")
    log(f"Created: {SCRIPT_JSON}")
    log("NEWS ENGINE EXIT: SUCCESS")
    log("=" * 68)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log("")
        log("FULL NEWS ENGINE OUTPUT:")
        log(str(exc))
        import traceback
        traceback.print_exc()
        sys.exit(1)
