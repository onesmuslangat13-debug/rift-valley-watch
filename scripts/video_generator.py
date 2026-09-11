import json
import re
import html
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE + REAL PHOTO COLLECTION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

SOURCE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SETTINGS
# ============================================================

MAX_STORIES = 10
MIN_STORIES = 5

TODAY_HOURS = 24
RECENT_HOURS = 48

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "Chrome/153.0 Safari/537.36"
)


# ============================================================
# RIFT VALLEY COUNTIES
# ============================================================

COUNTIES = {
    "Bomet": [
        "Bomet",
        "Chepalungu",
        "Sotik",
        "Konoin",
        "Kipkelion",
        "Longisa",
    ],
    "Kericho": [
        "Kericho",
        "Ainamoi",
        "Belgut",
        "Bureti",
        "Kipkelion",
        "Litein",
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
        "Transmara",
        "Suswa",
        "Maasai Mara",
    ],
    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Aldai",
        "Chesumei",
        "Mosop",
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
        "Keiyo",
        "Marakwet",
        "Kabarnet",
        "Kapsowar",
    ],
    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Pokot",
        "Sigor",
    ],
    "Trans Nzoia": [
        "Trans Nzoia",
        "Kitale",
        "Endebess",
        "Kwanza",
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
    ],
    "Laikipia": [
        "Laikipia",
        "Nanyuki",
        "Nyahururu",
        "Rumuruti",
    ],
    "Kajiado": [
        "Kajiado",
        "Magadi",
        "Loitokitok",
        "Kitengela",
        "Ngong",
        "Isinya",
    ],
}


# ============================================================
# EXCLUSIONS
# ============================================================

EXCLUDED_TERMS = [
    "rigathi gachagua",
    "rigathi",
    "gachagua",
]


# ============================================================
# TOPICS
# ============================================================

TOPICS = {
    "POLITICS": [
        "politics",
        "political",
        "president",
        "william ruto",
        "ruto",
        "governor",
        "governors",
        "senator",
        "senators",
        "mp ",
        "member of parliament",
        "uda",
        "party",
        "election",
        "2027",
        "campaign",
        "rally",
        "coalition",
        "alliance",
        "politician",
        "politicians",
        "parliament",
        "assembly",
        "cabinet",
        "deputy president",
    ],
    "DEVELOPMENT": [
        "development",
        "project",
        "construction",
        "government",
        "launch",
        "launched",
        "commissioned",
        "funding",
        "investment",
        "hospital",
        "school",
        "water",
        "electricity",
    ],
    "BUSINESS": [
        "business",
        "economy",
        "economic",
        "investment",
        "investor",
        "company",
        "industry",
        "factory",
        "trade",
        "market",
        "jobs",
        "employment",
        "enterprise",
    ],
    "AGRICULTURE": [
        "agriculture",
        "farmer",
        "farmers",
        "tea",
        "coffee",
        "dairy",
        "livestock",
        "maize",
        "fertilizer",
        "crops",
        "farming",
        "milk",
    ],
    "INFRASTRUCTURE": [
        "road",
        "roads",
        "highway",
        "bridge",
        "railway",
        "airport",
        "transport",
        "infrastructure",
        "drainage",
    ],
    "HEALTH": [
        "health",
        "hospital",
        "doctor",
        "doctors",
        "nurse",
        "nurses",
        "clinic",
        "medical",
        "disease",
        "patients",
        "healthcare",
    ],
    "EDUCATION": [
        "education",
        "school",
        "schools",
        "university",
        "students",
        "teachers",
        "teacher",
        "college",
        "exam",
    ],
    "SECURITY": [
        "security",
        "police",
        "crime",
        "arrest",
        "arrests",
        "robbery",
        "accident",
        "fire",
        "missing",
        "killed",
        "death",
        "attack",
        "flood",
        "disaster",
    ],
    "COMMUNITY": [
        "community",
        "residents",
        "residents say",
        "locals",
        "county",
        "public",
        "citizens",
    ],
}


# ============================================================
# SEARCH QUERIES
# ============================================================

GENERAL_QUERIES = [
    "Rift Valley Kenya today",
    "Rift Valley Kenya latest news",
    "Rift Valley politics Kenya today",
    "Rift Valley development Kenya today",
    "Rift Valley government Kenya today",
    "Rift Valley business Kenya today",
    "Rift Valley agriculture Kenya today",
    "Rift Valley roads Kenya today",
    "Rift Valley health Kenya today",
    "Rift Valley security Kenya today",
    "William Ruto Rift Valley today",
    "Ruto South Rift today",
    "Kericho politics today",
    "Bomet politics today",
    "Nakuru politics today",
    "Narok politics today",
    "Nandi politics today",
    "Uasin Gishu politics today",
    "Trans Nzoia politics today",
]


# ============================================================
# HTTP
# ============================================================

def request_bytes(url, timeout=15):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:

        return response.read()


def request_text(url, timeout=15):
    data = request_bytes(
        url,
        timeout,
    )

    return data.decode(
        "utf-8",
        errors="ignore",
    )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
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


def normalize(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_text(value).lower(),
    ).strip()


def contains_excluded(text):
    value = normalize(text)

    for term in EXCLUDED_TERMS:
        if normalize(term) in value:
            return True

    return False


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    value = normalize(text)

    # Specific counties first.
    for county, places in COUNTIES.items():

        if normalize(county) in value:
            return county

        for place in places:
            if normalize(place) in value:
                return county

    return ""


# ============================================================
# TOPIC DETECTION
# ============================================================

def detect_topic(text):
    value = normalize(text)

    scores = {}

    for topic, keywords in TOPICS.items():

        score = 0

        for keyword in keywords:

            key = normalize(keyword)

            if key and key in value:
                score += 1

        scores[topic] = score

    best = max(
        scores,
        key=scores.get,
    )

    if scores[best] == 0:
        return "REGIONAL"

    return best


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(value):
    if not value:
        return None

    value = value.strip()

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in formats:

        try:

            result = datetime.strptime(
                value,
                fmt,
            )

            if result.tzinfo is None:
                result = result.replace(
                    tzinfo=timezone.utc
                )

            return result.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_url(query):
    encoded = urllib.parse.quote(
        query
    )

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}&"
        "hl=en-KE&"
        "gl=KE&"
        "ceid=KE:en"
    )


def parse_google_news(xml_text):
    stories = []

    try:
        root = ET.fromstring(
            xml_text
        )
    except Exception as exc:
        print(
            "RSS parse error:",
            exc,
        )
        return stories

    channel = root.find("channel")

    if channel is None:
        return stories

    for item in channel.findall("item"):

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

        published_raw = clean_text(
            item.findtext(
                "pubDate",
                "",
            )
        )

        published = parse_date(
            published_raw
        )

        source_node = item.find(
            "{http://search.yahoo.com/mrss/}source"
        )

        source = ""

        if source_node is not None:
            source = clean_text(
                source_node.text
            )

        if not source:
            source = "News source"

        if not title or not link:
            continue

        stories.append(
            {
                "title": title,
                "url": link,
                "description": description,
                "source": source,
                "published": published,
            }
        )

    return stories


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_url(article_url):
    try:

        request = urllib.request.Request(
            article_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:

            content_type = response.headers.get(
                "Content-Type",
                "",
            )

            if "text/html" not in content_type:
                return ""

            page = response.read(
                800000
            ).decode(
                "utf-8",
                errors="ignore",
            )

    except Exception as exc:

        print(
            "Image page fetch failed:",
            exc,
        )

        return ""

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page,
            flags=re.I,
        )

        if match:

            image_url = html.unescape(
                match.group(1)
            ).strip()

            if image_url:

                return urllib.parse.urljoin(
                    article_url,
                    image_url,
                )

    # --------------------------------------------------------
    # JSON-LD image
    # --------------------------------------------------------

    jsonld_patterns = [
        r'"image"\s*:\s*"([^"]+)"',
        r'"thumbnailUrl"\s*:\s*"([^"]+)"',
    ]

    for pattern in jsonld_patterns:

        match = re.search(
            pattern,
            page,
            flags=re.I,
        )

        if match:

            image_url = html.unescape(
                match.group(1)
            ).strip()

            if image_url.startswith(
                "http"
            ):

                return image_url

    return ""


# ============================================================
# DOWNLOAD PHOTO
# ============================================================

def download_image(image_url, story_id):
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
            timeout=20,
        ) as response:

            data = response.read(
                5000000
            )

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

        if len(data) < 5000:
            return ""

        extension = ".jpg"

        if "png" in content_type:
            extension = ".png"

        elif "webp" in content_type:
            extension = ".webp"

        filename = (
            "story_"
            + story_id
            + extension
        )

        output = (
            SOURCE_DIR
            / filename
        )

        with open(
            output,
            "wb",
        ) as f:

            f.write(data)

        print(
            "PHOTO SAVED:",
            output,
            f"({len(data) / 1024:.1f} KB)",
        )

        return str(
            output.relative_to(ROOT)
        ).replace(
            "\\",
            "/",
        )

    except Exception as exc:

        print(
            "Photo download failed:",
            exc,
        )

        return ""


# ============================================================
# SOURCE PHOTO
# ============================================================

def get_story_photo(story):
    url = story.get(
        "url",
        "",
    )

    if not url:
        return ""

    image_url = extract_image_url(
        url
    )

    if not image_url:
        print(
            "No article photo found:"
        )
        print(
            story.get(
                "title",
                "",
            )
        )

        return ""

    story_id = hashlib.sha1(
        (
            story.get(
                "title",
                "",
            )
            + url
        ).encode(
            "utf-8"
        )
    ).hexdigest()[:12]

    return download_image(
        image_url,
        story_id,
    )


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story, now):
    title = story.get(
        "title",
        "",
    )

    description = story.get(
        "description",
        "",
    )

    source = story.get(
        "source",
        "",
    )

    combined = (
        title
        + " "
        + description
    )

    county = detect_county(
        combined
    )

    topic = detect_topic(
        combined
    )

    published = story.get(
        "published"
    )

    score = 0

    # --------------------------------------------------------
    # County relevance
    # --------------------------------------------------------

    if county:
        score += 35

    # --------------------------------------------------------
    # Freshness
    # --------------------------------------------------------

    if published:

        age = (
            now - published
        ).total_seconds() / 3600

        if age <= 3:
            score += 60

        elif age <= 6:
            score += 50

        elif age <= 12:
            score += 40

        elif age <= 24:
            score += 30

        elif age <= 48:
            score += 15

        else:
            score -= 30

    # --------------------------------------------------------
    # Topic
    # --------------------------------------------------------

    topic_weights = {
        "POLITICS": 35,
        "DEVELOPMENT": 28,
        "BUSINESS": 24,
        "INFRASTRUCTURE": 24,
        "AGRICULTURE": 20,
        "HEALTH": 18,
        "SECURITY": 18,
        "EDUCATION": 17,
        "COMMUNITY": 12,
        "REGIONAL": 5,
    }

    score += topic_weights.get(
        topic,
        5,
    )

    # --------------------------------------------------------
    # Political priority
    # --------------------------------------------------------

    normalized = normalize(
        combined
    )

    political_terms = [
        "william ruto",
        "president ruto",
        "ruto",
        "governor",
        "senator",
        "member of parliament",
        "uda",
        "2027",
        "election",
        "party",
        "rally",
    ]

    political_hits = 0

    for term in political_terms:

        if normalize(term) in normalized:
            political_hits += 1

    score += min(
        political_hits * 8,
        32,
    )

    # --------------------------------------------------------
    # Official / major media sources
    # --------------------------------------------------------

    source_lower = normalize(
        source
    )

    trusted_sources = [
        "nation",
        "standard",
        "star",
        "citizen",
        "kbc",
        "capital fm",
        "people daily",
        "ntv",
        "business daily",
        "the east african",
        "reuters",
        "associated press",
    ]

    for trusted in trusted_sources:

        if normalize(trusted) in source_lower:
            score += 12
            break

    # --------------------------------------------------------
    # Photo availability
    # --------------------------------------------------------

    if story.get(
        "image_path"
    ):
        score += 15

    return score


# ============================================================
# DEDUPLICATION
# ============================================================

def story_key(story):
    title = normalize(
        story.get(
            "title",
            "",
        )
    )

    title = re.sub(
        r"\b(today|latest|update)\b",
        "",
        title,
    )

    return title[:180]


def deduplicate(stories):
    result = []
    seen = set()

    for story in stories:

        key = story_key(
            story
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(story)

    return result


# ============================================================
# BUILD SEARCH LIST
# ============================================================

def build_queries():
    queries = list(
        GENERAL_QUERIES
    )

    for county in COUNTIES:

        queries.extend(
            [
                f"{county} Kenya today",
                f"{county} politics today",
                f"{county} development today",
                f"{county} business today",
                f"{county} government today",
            ]
        )

    return queries


# ============================================================
# COLLECT STORIES
# ============================================================

def collect_news():
    print("")
    print("=" * 60)
    print("RIFT VALLEY WATCH")
    print("REAL-TIME NEWS COLLECTION")
    print("=" * 60)

    now = datetime.now(
        timezone.utc
    )

    all_stories = []

    queries = build_queries()

    print(
        "Search queries:",
        len(queries),
    )

    for number, query in enumerate(
        queries,
        1,
    ):

        print("")
        print(
            f"[{number}/{len(queries)}]",
            query,
        )

        try:

            feed_url = google_news_url(
                query
            )

            xml = request_text(
                feed_url,
                timeout=15,
            )

            results = parse_google_news(
                xml
            )

            print(
                "Results:",
                len(results),
            )

            for story in results:

                combined = (
                    story.get(
                        "title",
                        "",
                    )
                    + " "
                    + story.get(
                        "description",
                        "",
                    )
                )

                # Hard exclusion
                if contains_excluded(
                    combined
                ):
                    continue

                county = detect_county(
                    combined
                )

                # We only want Rift Valley relevance.
                if not county:
                    continue

                published = story.get(
                    "published"
                )

                # Reject stories older than 48 hours.
                if published:

                    age = (
                        now - published
                    ).total_seconds() / 3600

                    if age > RECENT_HOURS:
                        continue

                story["county"] = county

                story["category"] = detect_topic(
                    combined
                )

                all_stories.append(
                    story
                )

        except Exception as exc:

            print(
                "Search failed:",
                exc,
            )

    return all_stories


# ============================================================
# PREPARE STORIES
# ============================================================

def prepare_stories(stories):
    now = datetime.now(
        timezone.utc
    )

    stories = deduplicate(
        stories
    )

    print("")
    print(
        "Unique stories:",
        len(stories),
    )

    for story in stories:

        story["score"] = score_story(
            story,
            now,
        )

    stories.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # County diversity
    # --------------------------------------------------------

    selected = []
    used_counties = set()

    # First pass: one story per county.
    for story in stories:

        county = story.get(
            "county",
            "",
        )

        if county in used_counties:
            continue

        selected.append(
            story
        )

        used_counties.add(
            county
        )

        if len(selected) >= MAX_STORIES:
            break

    # Second pass: fill remaining slots.
    if len(selected) < MAX_STORIES:

        selected_keys = {
            story_key(story)
            for story in selected
        }

        for story in stories:

            if story_key(
                story
            ) in selected_keys:
                continue

            selected.append(
                story
            )

            if len(selected) >= MAX_STORIES:
                break

    return selected


# ============================================================
# DOWNLOAD PHOTOS
# ============================================================

def attach_photos(stories):
    print("")
    print("=" * 60)
    print("COLLECTING REAL ARTICLE PHOTOS")
    print("=" * 60)

    successful = 0

    for number, story in enumerate(
        stories,
        1,
    ):

        print("")
        print(
            f"[PHOTO {number}/{len(stories)}]"
        )

        print(
            story.get(
                "title",
                "",
            )
        )

        image_path = get_story_photo(
            story
        )

        story["image_path"] = (
            image_path
        )

        if image_path:
            successful += 1

    print("")
    print(
        "Photos collected:",
        successful,
        "/",
        len(stories),
    )

    return stories


# ============================================================
# NARRATION
# ============================================================

def make_narration(story):
    county = clean_text(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    category = clean_text(
        story.get(
            "category",
            "NEWS",
        )
    )

    title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    description = clean_text(
        story.get(
            "description",
            "",
        )
    )

    if description:
        description = description[:350]

    text = (
        f"{county}. "
        f"{category}. "
        f"{title}."
    )

    if description:
        text += (
            " "
            + description
            + "."
        )

    return text


# ============================================================
# DATE DISPLAY
# ============================================================

def kenya_date():
    now = datetime.now(
        timezone.utc
    )

    kenya = now + timedelta(
        hours=3
    )

    return kenya.strftime(
        "%A, %d %B %Y"
    )


def iso_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# SAVE STORY.JSON
# ============================================================

def save_story_json(stories):
    output_stories = []

    for story in stories:

        published = story.get(
            "published"
        )

        published_text = ""

        if published:
            published_text = published.isoformat()

        output_stories.append(
            {
                "title": clean_text(
                    story.get(
                        "title",
                        "",
                    )
                ),
                "county": clean_text(
                    story.get(
                        "county",
                        "",
                    )
                ),
                "category": clean_text(
                    story.get(
                        "category",
                        "NEWS",
                    )
                ),
                "description": clean_text(
                    story.get(
                        "description",
                        "",
                    )
                ),
                "source": clean_text(
                    story.get(
                        "source",
                        "",
                    )
                ),
                "url": clean_text(
                    story.get(
                        "url",
                        "",
                    )
                ),
                "published": published_text,
                "score": story.get(
                    "score",
                    0,
                ),
                "image_path": story.get(
                    "image_path",
                    "",
                ),
                "narration": make_narration(
                    story
                ),
            }
        )

    output = {
        "project": "Rift Valley Watch",
        "date": kenya_date(),
        "generated_at": iso_now(),
        "stories": output_stories,
        "story_count": len(
            output_stories
        ),
    }

    # Keep compatibility with older generator.
    if output_stories:

        first = output_stories[0]

        output["title"] = first[
            "title"
        ]

        output["county"] = first[
            "county"
        ]

        output["category"] = first[
            "category"
        ]

        output["source"] = first[
            "source"
        ]

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return output


# ============================================================
# SAVE SCRIPT.JSON
# ============================================================

def save_script_json(stories):
    script_stories = []

    for story in stories:

        script_stories.append(
            {
                "county": story.get(
                    "county",
                    "",
                ),
                "category": story.get(
                    "category",
                    "NEWS",
                ),
                "headline": story.get(
                    "title",
                    "",
                ),
                "narration": make_narration(
                    story
                ),
                "source": story.get(
                    "source",
                    "",
                ),
                "source_url": story.get(
                    "url",
                    "",
                ),
                "image_path": story.get(
                    "image_path",
                    "",
                ),
                "published": (
                    story.get(
                        "published"
                    ).isoformat()
                    if story.get(
                        "published"
                    )
                    else ""
                ),
            }
        )

    output = {
        "project": "Rift Valley Watch",
        "date": kenya_date(),
        "generated_at": iso_now(),
        "stories": script_stories,
    }

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# FALLBACK
# ============================================================

def fallback():
    print("")
    print(
        "WARNING: No fresh qualifying "
        "Rift Valley stories found."
    )

    output = {
        "project": "Rift Valley Watch",
        "date": kenya_date(),
        "generated_at": iso_now(),
        "story_count": 0,
        "stories": [],
        "title": "Rift Valley Watch",
        "county": "Rift Valley",
        "category": "NEWS",
        "source": "Live news feeds",
    }

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
        )

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "project": "Rift Valley Watch",
                "date": kenya_date(),
                "stories": [],
            },
            f,
            indent=2,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("RIFT VALLEY WATCH NEWS ENGINE")
    print("LIVE NEWS + REAL PHOTOS")
    print("=" * 70)

    print(
        "Bulletin date:",
        kenya_date(),
    )

    print(
        "Generated:",
        iso_now(),
    )

    print(
        "Excluded:",
        ", ".join(
            EXCLUDED_TERMS
        ),
    )

    raw = collect_news()

    print("")
    print(
        "Raw qualifying stories:",
        len(raw),
    )

    selected = prepare_stories(
        raw
    )

    print("")
    print(
        "Selected stories:",
        len(selected),
    )

    if not selected:
        fallback()
        return

    # --------------------------------------------------------
    # Photos
    # --------------------------------------------------------

    selected = attach_photos(
        selected
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_story_json(
        selected
    )

    save_script_json(
        selected
    )

    print("")
    print("=" * 70)
    print("FINAL BULLETIN")
    print("=" * 70)

    for number, story in enumerate(
        selected,
        1,
    ):

        published = story.get(
            "published"
        )

        if published:
            published_text = (
                published.isoformat()
            )
        else:
            published_text = "unknown"

        print("")
        print(
            f"{number}. "
            f"{story.get('county', '')} | "
            f"{story.get('category', '')}"
        )

        print(
            story.get(
                "title",
                "",
            )
        )

        print(
            "Source:",
            story.get(
                "source",
                "",
            )
        )

        print(
            "Published:",
            published_text,
        )

        print(
            "Score:",
            story.get(
                "score",
                0,
            )
        )

        print(
            "Photo:",
            story.get(
                "image_path",
                "NONE",
            )
        )

    print("")
    print("=" * 70)
    print("NEWS ENGINE SUCCESSFUL")
    print("=" * 70)

    print(
        "Created:",
        STORY_FILE,
    )

    print(
        "Created:",
        SCRIPT_FILE,
    )

    print(
        "Photo directory:",
        SOURCE_DIR,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print("")
        print("=" * 70)
        print("NEWS ENGINE FAILED")
        print("=" * 70)

        print(
            "ERROR:",
            str(exc),
        )

        raise
