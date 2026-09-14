from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus, urljoin, urlparse
import hashlib
import json
import re
import shutil
import time
import xml.etree.ElementTree as ET

import requests
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE
# VERSION: V15_REAL_ARTICLE_PHOTO_RECOVERY
#
# PURPOSE
# ------------------------------------------------------------
# - Fetch fresh Rift Valley news
# - Resolve article URLs
# - Extract real article photographs
# - Validate downloaded images with Pillow
# - Reject placeholders / logos / screenshots / search images
# - Create data/story.json
# - Create data/script.json
#
# IMPORTANT
# ------------------------------------------------------------
# This engine DOES NOT create fake images.
# A story is accepted only when at least one real image
# successfully downloads and passes Pillow validation.
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

REQUEST_TIMEOUT = 25

MAX_RSS_ITEMS = 100
MAX_STORIES_TO_TEST = 60
MAX_IMAGES_PER_STORY = 5

MIN_IMAGE_BYTES = 8000
MIN_IMAGE_WIDTH = 240
MIN_IMAGE_HEIGHT = 160
MIN_IMAGE_PIXELS = 60000


# ============================================================
# HTTP HEADERS
# ============================================================

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Safari/605.1.15"
    ),
]


def build_headers(user_agent=None, image=False):
    if user_agent is None:
        user_agent = USER_AGENTS[0]

    if image:
        accept = (
            "image/avif,image/webp,image/apng,image/svg+xml,"
            "image/*,*/*;q=0.8"
        )
    else:
        accept = (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        )

    return {
        "User-Agent": user_agent,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9,en-GB;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


# ============================================================
# COUNTIES
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
    "Trans Nzoia",
    "Samburu",
    "Turkana",
    "Laikipia",
    "Kajiado",
]


COUNTY_ALIASES = {
    "uasin gishu": "Uasin Gishu",
    "elgeyo marakwet": "Elgeyo-Marakwet",
    "trans nzoia": "Trans Nzoia",
    "west pokot": "West Pokot",
}


# ============================================================
# STORY FILTERS
# ============================================================

FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# IMAGE FILTERS
# ============================================================

FORBIDDEN_IMAGE_TERMS = [
    "google.com",
    "googleusercontent",
    "news.google.com",
    "bing.com",
    "search result",
    "search-result",
    "search_result",
    "screenshot",
    "screen-shot",
    "screen_shot",
    "citizen",
    "ctv",
    "world cup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "defaultimage",
    "no-image",
    "no_image",
    "noimage",
    "favicon",
    "logo",
    "logos",
    "advert",
    "advertisement",
    "adsense",
    "social-share",
    "social_share",
    "share-image",
    "share_image",
    "thumbnail-placeholder",
    "thumbnail_placeholder",
]


# ============================================================
# RSS FEEDS
# ============================================================

SEARCH_TERMS = [
    "Rift Valley Kenya news",
    "Bomet Kenya news",
    "Kericho Kenya news",
    "Nakuru Kenya news",
    "Nandi Kenya news",
    "Uasin Gishu Kenya news",
    "Narok Kenya news",
    "West Pokot Kenya news",
    "Trans Nzoia Kenya news",
    "Elgeyo Marakwet Kenya news",
    "Samburu Kenya news",
    "Turkana Kenya news",
    "Laikipia Kenya news",
    "Kajiado Kenya news",
]


def build_feed_url(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:3d")
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


RSS_FEEDS = [build_feed_url(query) for query in SEARCH_TERMS]


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
       
