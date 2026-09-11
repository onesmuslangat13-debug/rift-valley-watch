# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE V5
#
# PURPOSE:
# - Fetch fresh Rift Valley news at runtime
# - Prioritize TODAY'S events
# - Cover the entire Rift Valley
# - Prioritize politics + major regional developments
# - Exclude Rigathi Gachagua
# - Download real article photographs
# - Create data/story.json
# - Create data/script.json
# - Preserve compatibility with video_generator.py
# ============================================================

import json
import hashlib
import html
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone, timedelta


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"


# ============================================================
# SETTINGS
# ============================================================

MAX_STORIES = 4

TODAY_PRIORITY_HOURS = 24
RECENT_PRIORITY_HOURS = 48

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 "
    "(X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


# ============================================================
# RIFT VALLEY COVERAGE
# ============================================================

COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Narok",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Trans Nzoia",
    "Samburu",
    "Turkana",
    "Laikipia",
    "Kajiado",
]


COUNTY_ALIASES = {
    "Bomet": [
        "Bomet",
        "Sotik",
        "Longisa",
        "Chebunyo",
        "Konoin",
        "Chepalungu",
        "Kipkelion",
    ],

    "Kericho": [
        "Kericho",
        "Litein",
        "Londiani",
        "Ainamoi",
        "Bureti",
        "Belgut",
    ],

    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Njoro",
        "Bahati",
        "Subukia",
        "Rongai",
    ],

    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Mai Mahiu",
        "Mara",
        "Transmara",
    ],

    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Nandi Hills",
        "Mosop",
        "Aldai",
        "Emgwen",
    ],

    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Turbo",
        "Kesses",
        "Soy",
        "Moiben",
    ],

    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Iten",
        "Kapsowar",
        "Keiyo",
        "Marakwet",
        "Kabarnet",
    ],

    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Sigor",
        "Pokot",
    ],

    "Trans Nzoia": [
        "Trans Nzoia",
        "Kitale",
        "Endebess",
        "Kiminini",
        "Cherangany",
        "Saboti",
    ],

    "Samburu": [
        "Samburu",
        "Maralal",
        "Baragoi",
        "Wamba",
    ],

    "Turkana": [
        "Turkana",
        "Lodwar",
        "Kakuma",
        "Lokichar",
        "Kalokol",
    ],

    "Laikipia": [
        "Laikipia",
        "Nanyuki",
        "Rumuruti",
        "Nyahururu",
        "Ndaragwa",
    ],

    "Kajiado": [
        "Kajiado",
        "Kitengela",
        "Ngong",
        "Loitokitok",
        "Namanga",
        "Isinya",
        "Magadi",
    ],
}


# ============================================================
# TOPIC SEARCHES
# ============================================================

SEARCH_QUERIES = [

    # Regional political coverage
    '"Rift Valley" Kenya politics',
    '"Rift Valley" Kenya government',
    '"Rift Valley" Kenya Ruto',
    '"Rift Valley" Kenya UDA',
    '"Rift Valley" Kenya 2027 politics',

    # Development
    '"Rift Valley" Kenya development',
    '"Rift Valley" Kenya roads',
    '"Rift Valley" Kenya infrastructure',
    '"Rift Valley" Kenya projects',

    # Economy
    '"Rift Valley" Kenya business',
    '"Rift Valley" Kenya economy',
    '"Rift Valley" Kenya investment',
    '"Rift Valley" Kenya agriculture',

    # Major events
    '"Rift Valley" Kenya security',
    '"Rift Valley" Kenya health',
    '"Rift Valley" Kenya education',

    # County searches
    '"Bomet" Kenya news',
    '"Kericho" Kenya news',
    '"Nakuru" Kenya news',
    '"Narok" Kenya news',
    '"Nandi" Kenya news',
    '"Uasin Gishu" Kenya news',
    '"Elgeyo-Marakwet" Kenya news',
    '"West Pokot" Kenya news',
    '"Trans Nzoia" Kenya news',
    '"Samburu" Kenya news',
    '"Turkana" Kenya news',
    '"Laikipia" Kenya news',
    '"Kajiado" Kenya news',

    # Major political actors
    '"William Ruto" "Rift Valley"',
    '"President Ruto" "Rift Valley"',
    '"UDA" "Rift Valley"',
    '"Rift Valley" governor Kenya',
    '"Rift Valley" MP Kenya',
    '"Rift Valley" senator Kenya',
]


# ============================================================
# HARD EXCLUSIONS
# ============================================================

FORBIDDEN_NAMES = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# TRUSTED SOURCES
# ============================================================

TRUSTED_SOURCES = {
    "citizen digital": 24,
    "nation": 22,
    "the standard": 22,
    "standard media": 22,
    "kbc": 22,
    "capital fm": 20,
    "the star": 20,
    "ntv kenya": 20,
    "kenya news agency": 24,
    "business daily": 20,
    "business daily africa": 20,
    "tuko": 15,
    "the east african": 18,
    "people daily": 16,
    "county government": 18,
    "government of kenya": 18,
}


# ============================================================
# CATEGORY KEYWORDS
# ============================================================

CATEGORY_KEYWORDS = {

    "POLITICS": [
        "president",
        "ruto",
        "uda",
        "politics",
        "political",
        "governor",
        "senator",
        "mp ",
        "member of parliament",
        "election",
        "2027",
        "party",
        "campaign",
        "rally",
        "coalition",
        "government",
        "deputy president",
        "cabinet",
    ],

    "DEVELOPMENT": [
        "development",
        "project",
        "launched",
        "construction",
        "funding",
        "government project",
        "county project",
        "development plan",
    ],

    "INFRASTRUCTURE": [
        "road",
        "roads",
        "highway",
        "bridge",
        "railway",
        "airport",
        "water",
        "sewer",
        "infrastructure",
        "construction",
        "dam",
    ],

    "BUSINESS & ECONOMY": [
        "business",
        "economy",
        "investment",
        "investor",
        "market",
        "trade",
        "company",
        "jobs",
        "employment",
        "industry",
        "finance",
        "revenue",
    ],

    "AGRICULTURE": [
        "agriculture",
        "farmer",
        "farmers",
        "tea",
        "coffee",
        "maize",
        "livestock",
        "dairy",
        "crop",
        "harvest",
        "fertilizer",
        "farming",
    ],

    "HEALTH": [
        "health",
        "hospital",
        "hospitality",
        "doctor",
        "patients",
        "disease",
        "clinic",
        "medical",
        "healthcare",
    ],

    "EDUCATION": [
        "education",
        "school",
        "schools",
        "university",
        "students",
        "teachers",
        "college",
        "education ministry",
    ],

    "SECURITY": [
        "police",
        "security",
        "crime",
        "arrest",
        "attack",
        "fire",
        "accident",
        "missing",
        "terror",
        "bandit",
        "investigation",
        "death",
    ],
}


# ============================================================
# HTTP
# ============================================================

def http_get(url, timeout=REQUEST_TIMEOUT):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            return response.read()

    except Exception:

        return b""


# ============================================================
# CLEANING
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = html.unescape(str(value))

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def clean_title(value):

    value = clean_text(value)

    value = re.sub(
        r"\s*-\s*(Citizen Digital|Nation|KBC|The Star|The Standard).*$",
        "",
        value,
        flags=re.IGNORECASE
    )

    return value.strip(" -")


# ============================================================
# RSS DATE
# ============================================================

def parse_date(value):

    if not value:
        return None

    value = value.strip()

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M GMT",
        "%a, %d %b %Y %H:%M:%S %Z",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def fetch_google_news(query):

    encoded = urllib.parse.quote_plus(
        query
    )

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )

    raw = http_get(url)

    if not raw:
        return []

    try:

        root = ET.fromstring(
            raw
        )

    except Exception:

        return []

    results = []

    for item in root.findall(
        ".//item"
    ):

        title = clean_title(
            item.findtext("title", "")
        )

        link = clean_text(
            item.findtext("link", "")
        )

        description = clean_text(
            item.findtext("description", "")
        )

        pub_date = clean_text(
            item.findtext("pubDate", "")
        )

        source_element = item.find(
            "source"
        )

        source = ""

        if source_element is not None:
            source = clean_text(
                source_element.text
            )

        if not title or not link:
            continue

        results.append({

            "title": title,

            "url": link,

            "description": description,

            "published": pub_date,

            "source": source,

            "query": query,

        })

    return results


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_meta_image(page):

    if not page:
        return ""

    text = page.decode(
        "utf-8",
        errors="ignore"
    )

    patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+name=["\']twitter:image:src["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image:src["\']',

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:

            image_url = html.unescape(
                match.group(1)
            ).strip()

            if image_url.startswith("//"):
                image_url = "https:" + image_url

            if image_url.startswith("/"):
                parsed = urllib.parse.urlparse(
                    "https://" + urllib.parse.urlparse("").netloc
                )

            if image_url.startswith("http"):
                return image_url

    return ""


# ============================================================
# BETTER URL RESOLUTION
# ============================================================

def absolute_url(
    base_url,
    image_url
):

    if not image_url:
        return ""

    image_url = html.unescape(
        image_url.strip()
    )

    if image_url.startswith("//"):
        return "https:" + image_url

    if image_url.startswith("http://"):
        return image_url

    if image_url.startswith("https://"):
        return image_url

    return urllib.parse.urljoin(
        base_url,
        image_url
    )


# ============================================================
# ARTICLE IMAGE
# ============================================================

def find_article_image(url):

    page = http_get(
        url,
        timeout=REQUEST_TIMEOUT
    )

    if not page:
        return ""

    image_url = extract_meta_image(
        page
    )

    return absolute_url(
        url,
        image_url
    )


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    image_url,
    story_id
):

    if not image_url:
        return ""

    try:

        request = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            content = response.read()

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

        if len(content) < 10000:
            return ""

        extension = ".jpg"

        if "webp" in content_type:
            extension = ".webp"

        elif "png" in content_type:
            extension = ".png"

        elif "jpeg" in content_type:
            extension = ".jpg"

        elif "avif" in content_type:
            extension = ".avif"

        filename = (
            f"story_{story_id}{extension}"
        )

        output = SOURCE_DIR / filename

        with open(
            output,
            "wb"
        ) as f:

            f.write(content)

        return (
            "assets/source/"
            + filename
        )

    except Exception:

        return ""


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    matches = []

    for county, aliases in COUNTY_ALIASES.items():

        for alias in aliases:

            if alias.lower() in text:

                matches.append(
                    county
                )

                break

    if not matches:
        return ""

    # Prefer exact county-name matches.
    for county in matches:

        if county.lower() in text:
            return county

    return matches[0]


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():

        score = 0

        for keyword in keywords:

            if keyword.lower() in text:
                score += 1

        scores[category] = score

    best = max(
        scores,
        key=scores.get
    )

    if scores[best] == 0:
        return "REGIONAL NEWS"

    return best


# ============================================================
# EXCLUSION
# ============================================================

def is_forbidden(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    for name in FORBIDDEN_NAMES:

        if name in text:
            return True

    return False


# ============================================================
# TRUSTED SOURCE SCORE
# ============================================================

def source_score(source):

    source_lower = clean_text(
        source
    ).lower()

    score = 0

    for name, points in TRUSTED_SOURCES.items():

        if name in source_lower:
            score = max(
                score,
                points
            )

    return score


# ============================================================
# POLITICAL PRIORITY
# ============================================================

def political_score(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    score = 0

    priority_terms = {

        "william ruto": 35,

        "president ruto": 35,

        "ruto": 25,

        "uda": 20,

        "governor": 18,

        "senator": 18,

        "mp ": 15,

        "member of parliament": 15,

        "2027": 25,

        "election": 20,

        "politics": 15,

        "political": 15,

        "party": 12,

        "government": 10,

        "cabinet": 15,

    }

    for term, points in priority_terms.items():

        if term in text:
            score += points

    return min(
        score,
        60
    )


# ============================================================
# FRESHNESS
# ============================================================

def freshness_score(
    published
):

    dt = parse_date(
        published
    )

    if dt is None:
        return 0

    now = datetime.now(
        timezone.utc
    )

    age = (
        now - dt
    ).total_seconds() / 3600

    if age < 0:
        age = 0

    if age <= 6:
        return 80

    if age <= 12:
        return 70

    if age <= 24:
        return 60

    if age <= 36:
        return 35

    if age <= 48:
        return 15

    return 0


# ============================================================
# CURRENTNESS CLASSIFICATION
# ============================================================

def freshness_label(
    published
):

    dt = parse_date(
        published
    )

    if dt is None:
        return "UNKNOWN"

    now = datetime.now(
        timezone.utc
    )

    age = (
        now - dt
    ).total_seconds() / 3600

    if age <= 24:
        return "TODAY"

    if age <= 48:
        return "RECENT"

    return "OLD"


# ============================================================
# RELEVANCE
# ============================================================

def relevance_score(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    score = 0

    for county in COUNTIES:

        if county.lower() in text:
            score += 12

    regional_terms = [
        "rift valley",
        "eldoret",
        "nakuru",
        "narok",
        "kericho",
        "bomet",
        "nandi",
        "turkana",
        "pokot",
        "samburu",
        "laikipia",
        "kajiado",
        "trans nzoia",
        "marakwet",
    ]

    for term in regional_terms:

        if term in text:
            score += 5

    return min(
        score,
        50
    )


# ============================================================
# STORY ID
# ============================================================

def story_id(
    title,
    url
):

    raw = (
        title
        + "|"
        + url
    ).encode(
        "utf-8"
    )

    return hashlib.sha1(
        raw
    ).hexdigest()[:12]


# ============================================================
# NORMALIZE STORY
# ============================================================

def normalize_story(
    item
):

    title = clean_title(
        item.get("title")
    )

    description = clean_text(
        item.get("description")
    )

    source = clean_text(
        item.get("source")
    )

    url = clean_text(
        item.get("url")
    )

    published = clean_text(
        item.get("published")
    )

    county = detect_county(
        title,
        description
    )

    category = detect_category(
        title,
        description
    )

    currentness = freshness_label(
        published
    )

    freshness = freshness_score(
        published
    )

    relevance = relevance_score(
        title,
        description
    )

    politics = political_score(
        title,
        description
    )

    source_points = source_score(
        source
    )

    score = (
        freshness
        + relevance
        + politics
        + source_points
    )

    return {

        "title": title,

        "county": county
        if county
        else "Rift Valley",

        "category": category,

        "description": description,

        "source": source,

        "url": url,

        "published": published,

        "currentness": currentness,

        "freshness_score": freshness,

        "relevance_score": relevance,

        "political_score": politics,

        "source_score": source_points,

        "score": score,

        "image_url": "",

        "image_path": "",

    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate(
    stories
):

    seen_urls = set()
    seen_titles = set()

    result = []

    for story in stories:

        url = story["url"].lower()

        title = re.sub(
            r"[^a-z0-9]+",
            " ",
            story["title"].lower()
        ).strip()

        if url in seen_urls:
            continue

        if title in seen_titles:
            continue

        seen_urls.add(
            url
        )

        seen_titles.add(
            title
        )

        result.append(
            story
        )

    return result


# ============================================================
# COUNTY DIVERSITY
# ============================================================

def select_diverse_stories(
    stories
):

    if not stories:
        return []

    today = [
        s for s in stories
        if s["currentness"] == "TODAY"
    ]

    recent = [
        s for s in stories
        if s["currentness"] == "RECENT"
    ]

    # TODAY always comes first.
    pool = today + recent

    selected = []

    counties_used = set()

    # Pass 1:
    # one strong story per county.
    for story in pool:

        county = story["county"]

        if county in counties_used:
            continue

        selected.append(
            story
        )

        counties_used.add(
            county
        )

        if len(selected) >= MAX_STORIES:
            return selected

    # Pass 2:
    # fill remaining slots.
    for story in pool:

        if story in selected:
            continue

        selected.append(
            story
        )

        if len(selected) >= MAX_STORIES:
            break

    return selected


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story
):

    title = clean_text(
        story["title"]
    )

    county = clean_text(
        story["county"]
    )

    category = clean_text(
        story["category"]
    )

    description = clean_text(
        story["description"]
    )

    source = clean_text(
        story["source"]
    )

    parts = []

    parts.append(
        f"{county}. {title}."
    )

    if description:

        parts.append(
            description
        )

    if category:

        parts.append(
            f"This is a {category.lower()} story."
        )

    if source:

        parts.append(
            f"The report was published by {source}."
        )

    return " ".join(
        parts
    )


# ============================================================
# STORY JSON
# ============================================================

def write_story_json(
    stories
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    payload = {

        "version":
            "RIFT VALLEY WATCH REAL-TIME NEWS V5",

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "coverage":
            COUNTIES,

        "stories":
            stories,

    }

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# SCRIPT JSON
# ============================================================

def write_script_json(
    stories
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    script_stories = []

    for index, story in enumerate(
        stories,
        start=1
    ):

        narration = build_narration(
            story
        )

        script_stories.append({

            "sequence":
                index,

            "title":
                story["title"],

            "county":
                story["county"],

            "category":
                story["category"],

            "date":
                story["published"],

            "source": {

                "name":
                    story["source"],

                "type":
                    "NEWS",

                "url":
                    story["url"],

            },

            "image_path":
                story.get(
                    "image_path",
                    ""
                ),

            "image_url":
                story.get(
                    "image_url",
                    ""
                ),

            "full_script":
                narration,

            "narration":
                narration,

            "currentness":
                story["currentness"],

        })

    payload = {

        "version":
            "RIFT VALLEY WATCH REAL-TIME NEWS V5",

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "story_count":
            len(script_stories),

        "stories":
            script_stories,

    }

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# CLEAN OLD PHOTOS
# ============================================================

def clean_old_photos():

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    for file in SOURCE_DIR.iterdir():

        if not file.is_file():
            continue

        if file.name.startswith(
            "story_"
        ):

            try:
                file.unlink()
            except Exception:
                pass


# ============================================================
# MAIN NEWS COLLECTION
# ============================================================

def collect_news():

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH — REAL-TIME NEWS ENGINE V5")
    print("=" * 70)
    print()

    now = datetime.now(
        timezone.utc
    )

    print(
        "Runtime UTC:",
        now.isoformat()
    )

    print(
        "Runtime EAT:",
        (
            now + timedelta(hours=3)
        ).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    print()
    print(
        "TODAY-FIRST MODE: ENABLED"
    )

    print(
        "Coverage:",
        len(COUNTIES),
        "Rift Valley counties"
    )

    print(
        "Maximum stories:",
        MAX_STORIES
    )

    print()

    all_items = []

    for number, query in enumerate(
        SEARCH_QUERIES,
        start=1
    ):

        print(
            f"[{number:02d}/{len(SEARCH_QUERIES)}] "
            f"Searching: {query}"
        )

        results = fetch_google_news(
            query
        )

        print(
            f"       Found: {len(results)}"
        )

        all_items.extend(
            results
        )

        # Avoid hammering RSS.
        time.sleep(
            0.15
        )

    print()
    print(
        "Raw articles collected:",
        len(all_items)
    )

    normalized = []

    for item in all_items:

        title = clean_title(
            item.get("title")
        )

        description = clean_text(
            item.get("description")
        )

        if not title:
            continue

        if is_forbidden(
            title,
            description
        ):

            print(
                "EXCLUDED:",
                title
            )

            continue

        story = normalize_story(
            item
        )

        # A Rift Valley story must contain
        # a detectable regional connection.
        if (
            story["county"] == "Rift Valley"
            and story["relevance_score"] < 5
        ):
            continue

        # Reject articles older than 48 hours.
        if story["currentness"] == "OLD":
            continue

        normalized.append(
            story
        )

    normalized = deduplicate(
        normalized
    )

    normalized.sort(
        key=lambda x: (
            1
            if x["currentness"] == "TODAY"
            else 0,
            x["score"]
        ),
        reverse=True
    )

    print()
    print(
        "Current/recent unique stories:",
        len(normalized)
    )

    today_count = sum(
        1
        for s in normalized
        if s["currentness"] == "TODAY"
    )

    recent_count = sum(
        1
        for s in normalized
        if s["currentness"] == "RECENT"
    )

    print(
        "TODAY stories:",
        today_count
    )

    print(
        "RECENT stories:",
        recent_count
    )

    # ========================================================
    # TODAY-FIRST SELECTION
    # ========================================================

    selected = select_diverse_stories(
        normalized
    )

    # If we have enough stories from today,
    # do not allow RECENT stories to displace them.
    today_selected = [
        s for s in selected
        if s["currentness"] == "TODAY"
    ]

    if len(today_selected) >= MAX_STORIES:

        selected = today_selected[
            :MAX_STORIES
        ]

    print()
    print("=" * 70)
    print("SELECTED BULLETIN")
    print("=" * 70)

    if not selected:

        raise RuntimeError(
            "NO CURRENT RIFT VALLEY STORIES FOUND."
        )

    for index, story in enumerate(
        selected,
        start=1
    ):

        print()
        print(
            f"STORY {index}"
        )

        print(
            "County:",
            story["county"]
        )

        print(
            "Category:",
            story["category"]
        )

        print(
            "Freshness:",
            story["currentness"]
        )

        print(
            "Published:",
            story["published"]
        )

        print(
            "Source:",
            story["source"]
        )

        print(
            "Score:",
            story["score"]
        )

        print(
            "Headline:",
            story["title"]
        )


    # ========================================================
    # REAL PHOTO DOWNLOAD
    # ========================================================

    print()
    print("=" * 70)
    print("DOWNLOADING REAL SOURCE PHOTOS")
    print("=" * 70)

    clean_old_photos()

    photo_count = 0

    for index, story in enumerate(
        selected,
        start=1
    ):

        print()
        print(
            f"[PHOTO {index}/{len(selected)}]"
        )

        print(
            story["title"]
        )

        image_url = find_article_image(
            story["url"]
        )

        if image_url:

            print(
                "Image found:"
            )

            print(
                image_url
            )

            story["image_url"] = (
                image_url
            )

            sid = story_id(
                story["title"],
                story["url"]
            )

            image_path = download_image(
                image_url,
                sid
            )

            if image_path:

                story["image_path"] = (
                    image_path
                )

                photo_count += 1

                print(
                    "Photo downloaded:",
                    image_path
                )

            else:

                print(
                    "Photo download failed."
                )

        else:

            print(
                "No article image found."
            )


    # ========================================================
    # NARRATION
    # ========================================================

    for story in selected:

        story["narration"] = (
            build_narration(
                story
            )
        )


    # ========================================================
    # SAVE
    # ========================================================

    write_story_json(
        selected
    )

    write_script_json(
        selected
    )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print("=" * 70)
    print("NEWS ENGINE SUCCESSFUL")
    print("=" * 70)

    print()

    print(
        "Created:",
        STORY_FILE
    )

    print(
        "Created:",
        SCRIPT_FILE
    )

    print(
        "Photo directory:",
        SOURCE_DIR
    )

    print(
        "Stories selected:",
        len(selected)
    )

    print(
        "TODAY stories selected:",
        sum(
            1
            for s in selected
            if s["currentness"] == "TODAY"
        )
    )

    print(
        "Real photos downloaded:",
        photo_count
    )

    print()

    print("=" * 70)
    print("FINAL NEWS CHECK")
    print("=" * 70)

    for index, story in enumerate(
        selected,
        start=1
    ):

        print()

        print(
            f"{index}. {story['county']} | "
            f"{story['category']} | "
            f"{story['currentness']}"
        )

        print(
            story["title"]
        )

        print(
            "Source:",
            story["source"]
        )

        print(
            "Published:",
            story["published"]
        )

        print(
            "Photo:",
            "YES"
            if story.get("image_path")
            else "NO"
        )

    print()
    print(
        "RIFT VALLEY WATCH NEWS ENGINE COMPLETE."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    collect_news()
