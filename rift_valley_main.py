# ============================================================
# RIFT VALLEY WATCH
# MAIN CONTROLLER
#
# VERSION: RVW_MAIN_V7_TITLE_COMPATIBILITY
#
# PURPOSE:
# - Run news engine
# - Load the selected story
# - Normalize story fields for the video generator
# - GUARANTEE title + headline exist
# - Create selected_story.json
# - Create selected_script.json
# - Remove publisher/source attribution from narration
# - Run video generator
# - Verify final MP4
# ============================================================

from pathlib import Path
import json
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"
NEWS_ENGINE = ROOT / "scripts" / "news_engine.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception as exc:
        log(f"WARNING: Could not read {path}: {exc}")
        return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# VALUE HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    return str(value).strip()


def first_value(data, keys):
    if not isinstance(data, dict):
        return ""

    for key in keys:
        value = clean_text(data.get(key))

        if value:
            return value

    return ""


def recursive_find(data, wanted_keys):
    """
    Recursively search nested dictionaries/lists.
    """

    wanted = {str(k).lower() for k in wanted_keys}

    if isinstance(data, dict):

        for key, value in data.items():

            if str(key).lower() in wanted:
                text = clean_text(value)

                if text:
                    return text

        for value in data.values():

            result = recursive_find(
                value,
                wanted_keys
            )

            if result:
                return result

    elif isinstance(data, list):

        for item in data:

            result = recursive_find(
                item,
                wanted_keys
            )

            if result:
                return result

    return ""


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    title = clean_text(title)

    if not title:
        return ""

    # Remove obvious publisher suffixes.
    patterns = [
        r"\s*[-|–—]\s*People Daily\s*$",
        r"\s*[-|–—]\s*The Star\s*$",
        r"\s*[-|–—]\s*Citizen Digital\s*$",
        r"\s*[-|–—]\s*Citizen\s*$",
        r"\s*[-|–—]\s*The Standard\s*$",
        r"\s*[-|–—]\s*Nation\s*$",
        r"\s*[-|–—]\s*Daily Nation\s*$",
        r"\s*[-|–—]\s*Capital News\s*$",
        r"\s*[-|–—]\s*KBC\s*$",
        r"\s*[-|–—]\s*Kenya News Agency\s*$",
        r"\s*[-|–—]\s*NTV Kenya\s*$",
        r"\s*[-|–—]\s*TV47\s*$",
        r"\s*[-|–—]\s*Kenya\s*$",
    ]

    for pattern in patterns:
        title = re.sub(
            pattern,
            "",
            title,
            flags=re.IGNORECASE
        )

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    return title


# ============================================================
# SUMMARY CLEANING
# ============================================================

def clean_summary(summary):
    summary = clean_text(summary)

    if not summary:
        return ""

    bad_phrases = [
        "google news",
        "read more on google news",
        "subscribe to google news",
        "open in google news",
        "google news app",
    ]

    lowered = summary.lower()

    for phrase in bad_phrases:

        if phrase in lowered:
            summary = re.sub(
                re.escape(phrase),
                "",
                summary,
                flags=re.IGNORECASE
            )

    summary = re.sub(
        r"\s+",
        " ",
        summary
    ).strip()

    return summary


# ============================================================
# SOURCE REMOVAL
# ============================================================

def remove_source_from_text(text, source):
    text = clean_text(text)

    if not text:
        return ""

    if source:

        source = clean_text(source)

        if source:

            text = re.sub(
                re.escape(source),
                "",
                text,
                flags=re.IGNORECASE
            )

    publisher_names = [
        "People Daily",
        "The Star",
        "Citizen Digital",
        "Citizen",
        "The Standard",
        "Daily Nation",
        "Nation",
        "Capital News",
        "KBC",
        "Kenya News Agency",
        "NTV Kenya",
        "TV47",
        "Google News",
    ]

    for publisher in publisher_names:

        text = re.sub(
            re.escape(publisher),
            "",
            text,
            flags=re.IGNORECASE
        )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# ============================================================
# STORY EXTRACTION
# ============================================================

def get_title(story):
    title = first_value(
        story,
        [
            "title",
            "headline",
            "story_title",
            "article_title",
            "news_title",
            "name",
        ]
    )

    if not title:
        title = recursive_find(
            story,
            [
                "title",
                "headline",
                "story_title",
                "article_title",
                "news_title",
            ]
        )

    return clean_title(title)


def get_summary(story):
    summary = first_value(
        story,
        [
            "summary",
            "description",
            "excerpt",
            "content",
            "body",
            "article_summary",
            "story_summary",
        ]
    )

    if not summary:
        summary = recursive_find(
            story,
            [
                "summary",
                "description",
                "excerpt",
                "content",
                "body",
            ]
        )

    return clean_summary(summary)


def get_county(story):
    county = first_value(
        story,
        [
            "county",
            "county_name",
            "location",
            "region",
        ]
    )

    if not county:
        county = recursive_find(
            story,
            [
                "county",
                "county_name",
            ]
        )

    return county


def get_source(story):
    source = first_value(
        story,
        [
            "source",
            "publisher",
            "publication",
            "source_name",
            "publisher_name",
        ]
    )

    if not source:
        source = recursive_find(
            story,
            [
                "source",
                "publisher",
                "publication",
                "source_name",
            ]
        )

    return source


def get_url(story):
    url = first_value(
        story,
        [
            "url",
            "article_url",
            "source_url",
            "link",
            "article_link",
        ]
    )

    if not url:
        url = recursive_find(
            story,
            [
                "url",
                "article_url",
                "source_url",
                "link",
            ]
        )

    return url


def get_date(story):
    value = first_value(
        story,
        [
            "date",
            "published",
            "published_at",
            "publication_date",
            "published_date",
            "datetime",
        ]
    )

    return value


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def get_image_urls(story):
    urls = []

    possible_keys = [
        "image_url",
        "image",
        "photo",
        "thumbnail",
        "imageUrl",
        "image_url",
        "og_image",
        "og:image",
        "featured_image",
        "featured_image_url",
        "article_image",
        "article_image_url",
        "photo_url",
    ]

    def add(value):

        if isinstance(value, str):

            value = value.strip()

            if value.startswith("http://") or value.startswith("https://"):

                if value not in urls:
                    urls.append(value)

        elif isinstance(value, list):

            for item in value:
                add(item)

        elif isinstance(value, dict):

            for key in [
                "url",
                "src",
                "image",
                "image_url",
                "href",
            ]:

                if key in value:
                    add(value[key])

    if isinstance(story, dict):

        for key in possible_keys:

            if key in story:
                add(story[key])

        # Search nested structures.
        def walk(value):

            if isinstance(value, dict):

                for key, item in value.items():

                    key_lower = str(key).lower()

                    if (
                        "image" in key_lower
                        or "photo" in key_lower
                        or key_lower in {"thumbnail", "src"}
                    ):
                        add(item)

                    walk(item)

            elif isinstance(value, list):

                for item in value:
                    walk(item)

        walk(story)

    return urls


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    title,
    summary,
    county
):
    title = clean_text(title)
    summary = clean_text(summary)
    county = clean_text(county)

    if summary:
        narration = (
            f"In {county}, {title}. "
            f"{summary}"
        )
    else:
        narration = (
            f"In {county}, {title}. "
            f"This is the latest development being followed "
            f"in the county."
        )

    narration = remove_source_from_text(
        narration,
        ""
    )

    return narration.strip()


# ============================================================
# NORMALIZE STORY
# ============================================================

def normalize_story(raw_story):
    log("")
    log("=" * 70)
    log("NORMALIZING SELECTED STORY")
    log("=" * 70)

    title = get_title(raw_story)
    summary = get_summary(raw_story)
    county = get_county(raw_story)
    source = get_source(raw_story)
    url = get_url(raw_story)
    date = get_date(raw_story)
    image_urls = get_image_urls(raw_story)

    # --------------------------------------------------------
    # CRITICAL TITLE FIX
    # --------------------------------------------------------

    if not title:

        raise RuntimeError(
            "Selected story has no usable title/headline."
        )

    if not county:
        county = "Rift Valley"

    narration = build_narration(
        title,
        summary,
        county
    )

    # --------------------------------------------------------
    # Write BOTH title and headline.
    # This fixes compatibility with older/newer generators.
    # --------------------------------------------------------

    normalized = dict(raw_story)

    normalized.update(
        {
            "title": title,
            "headline": title,
            "story_title": title,
            "article_title": title,

            "summary": summary,
            "description": summary,

            "county": county,

            "source": source,
            "publisher": source,

            "url": url,

            "date": date,

            "image_urls": image_urls,
            "image_url": image_urls[0] if image_urls else "",

            "narration": narration,
            "voiceover": narration,
            "voice_over": narration,
            "narration_text": narration,
            "text": narration,
            "script": narration,
        }
    )

    # Remove publisher from title.
    normalized["title"] = clean_title(
        normalized["title"]
    )

    normalized["headline"] = normalized["title"]
    normalized["story_title"] = normalized["title"]

    log("")
    log("NORMALIZED STORY")
    log(f"TITLE   : {normalized['title']}")
    log(f"COUNTY  : {normalized['county']}")
    log(f"SOURCE  : {normalized['source']}")
    log(f"IMAGES  : {len(image_urls)}")
    log(f"NARRATION LENGTH: {len(narration)} characters")

    return normalized


# ============================================================
# SELECTED SCRIPT
# ============================================================

def create_selected_script(story):
    title = clean_text(
        story.get("title")
    )

    county = clean_text(
        story.get("county")
    )

    narration = clean_text(
        story.get("narration")
    )

    if not narration or len(narration) < 20:

        narration = build_narration(
            title,
            clean_text(story.get("summary")),
            county
        )

    script = {
        "title": title,
        "headline": title,
        "county": county,

        "narration": narration,
        "voiceover": narration,
        "voice_over": narration,
        "narration_text": narration,
        "text": narration,
        "script": narration,

        "source": "",
        "publisher": "",
    }

    save_json(
        SELECTED_SCRIPT_FILE,
        script
    )

    log("")
    log("SELECTED SCRIPT CREATED")
    log(f"TITLE     : {title}")
    log(f"NARRATION : {narration}")

    return script


# ============================================================
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():
    if not NEWS_ENGINE.exists():

        log(
            "News engine not found. "
            "Using existing data/story.json."
        )

        return

    log("")
    log("=" * 70)
    log("RUNNING NEWS ENGINE")
    log("=" * 70)

    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(NEWS_ENGINE),
        ],
        cwd=str(ROOT),
        env=None,
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"News engine failed with exit code "
            f"{result.returncode}"
        )


# ============================================================
# LOAD STORY
# ============================================================

def load_selected_story():

    candidates = [
        SELECTED_STORY_FILE,
        STORY_FILE,
    ]

    for path in candidates:

        if path.exists():

            data = load_json(path)

            if data:

                log("")
                log(f"USING STORY FILE: {path}")

                return data

    raise RuntimeError(
        "No usable story JSON was found."
    )


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_video_generator():

    if not VIDEO_GENERATOR.exists():

        raise RuntimeError(
            f"Video generator not found: "
            f"{VIDEO_GENERATOR}"
        )

    log("")
    log("=" * 70)
    log("RUNNING VIDEO GENERATOR")
    log("=" * 70)

    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(VIDEO_GENERATOR),
        ],
        cwd=str(ROOT),
        env=None,
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"VIDEO GENERATOR failed with exit code "
            f"{result.returncode}"
        )


# ============================================================
# VERIFY MP4
# ============================================================

def verify_video():

    log("")
    log("=" * 70)
    log("VERIFYING FINAL MP4")
    log("=" * 70)

    if not FINAL_VIDEO.exists():

        log("Available MP4 files:")

        for mp4 in ROOT.rglob("*.mp4"):
            log(str(mp4))

        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100_000:

        raise RuntimeError(
            "Generated MP4 is suspiciously small."
        )

    log("")
    log("SUCCESS!")
    log(f"FINAL MP4 : {FINAL_VIDEO}")
    log(
        f"SIZE      : "
        f"{size / (1024 * 1024):.2f} MB"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH")
    log("=" * 70)

    log("")
    log("CONTROLLER VERSION:")
    log("RVW_MAIN_V7_TITLE_COMPATIBILITY")

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # 1. Run news engine
    # --------------------------------------------------------

    run_news_engine()

    # --------------------------------------------------------
    # 2. Load whatever story the news engine produced
    # --------------------------------------------------------

    raw_story = load_selected_story()

    # --------------------------------------------------------
    # 3. Normalize story
    # --------------------------------------------------------

    story = normalize_story(
        raw_story
    )

    # --------------------------------------------------------
    # 4. Write selected_story.json
    # --------------------------------------------------------

    save_json(
        SELECTED_STORY_FILE,
        story
    )

    log("")
    log("=" * 70)
    log("SELECTED STORY")
    log("=" * 70)

    log(
        f"HEADLINE: {story['title']}"
    )

    log(
        f"COUNTY: {story['county']}"
    )

    log(
        f"IMAGES: {len(story.get('image_urls', []))}"
    )

    # --------------------------------------------------------
    # 5. Create selected_script.json
    # --------------------------------------------------------

    create_selected_script(
        story
    )

    # --------------------------------------------------------
    # 6. Final pre-generator validation
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("PRE-GENERATOR VALIDATION")
    log("=" * 70)

    validation = load_json(
        SELECTED_STORY_FILE
    )

    if not clean_text(
        validation.get("title")
    ):

        raise RuntimeError(
            "selected_story.json still has no title."
        )

    if not clean_text(
        validation.get("headline")
    ):

        raise RuntimeError(
            "selected_story.json still has no headline."
        )

    script = load_json(
        SELECTED_SCRIPT_FILE
    )

    if not clean_text(
        script.get("narration")
    ):

        raise RuntimeError(
            "selected_script.json has no narration."
        )

    log(
        f"TITLE CHECK     : PASS"
    )

    log(
        f"HEADLINE CHECK  : PASS"
    )

    log(
        f"NARRATION CHECK : PASS"
    )

    # --------------------------------------------------------
    # 7. Generate video
    # --------------------------------------------------------

    run_video_generator()

    # --------------------------------------------------------
    # 8. Verify final MP4
    # --------------------------------------------------------

    verify_video()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH COMPLETED SUCCESSFULLY")
    log("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)
        log("")
        log(
            f"{type(exc).__name__}: {exc}"
        )
        log("")

        raise
