# ============================================================
# RIFT VALLEY WATCH V2
# VERIFIED NEWS SCRIPT ENGINE
# ============================================================

import json
import re
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent

STORY_FILE = BASE_DIR / "data" / "story.json"
SCRIPT_FILE = BASE_DIR / "data" / "script.json"


# ============================================================
# SETTINGS
# ============================================================

MIN_WORDS = 90
MAX_WORDS = 190

FORBIDDEN_PHRASES = [
    "in a significant development",
    "this is expected to transform",
    "residents are expected to benefit",
    "the project will boost the economy",
    "this marks a major milestone",
    "will greatly improve",
    "is set to transform",
    "promises to transform",
]


# ============================================================
# LOAD STORY
# ============================================================

def load_story():
    if not STORY_FILE.exists():
        raise RuntimeError(
            f"Story file not found: {STORY_FILE}"
        )

    try:
        with open(STORY_FILE, "r", encoding="utf-8") as f:
            story = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Invalid story.json: {e}"
        )

    if not isinstance(story, dict):
        raise RuntimeError(
            "story.json must contain a JSON object."
        )

    return story


# ============================================================
# BASIC TEXT CLEANING
# ============================================================

def clean_text(text):
    if text is None:
        return ""

    text = str(text)

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"<[^>]+>", "", text)

    return text.strip()


# ============================================================
# REQUIRED FIELD CHECK
# ============================================================

def validate_required_fields(story):

    required = [
        "title",
        "county",
        "category",
        "date",
        "source",
        "summary",
        "verified_facts",
    ]

    missing = []

    for field in required:
        if field not in story:
            missing.append(field)

    if missing:
        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            f"Missing required fields: {', '.join(missing)}"
        )


# ============================================================
# SOURCE VALIDATION
# ============================================================

def validate_source(story):

    source = story.get("source")

    if not isinstance(source, dict):
        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            "Source must be an object containing name, url and type."
        )

    source_name = clean_text(source.get("name"))

    if not source_name:
        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            "A source name is required."
        )

    source_type = clean_text(
        source.get("type")
    ).upper()

    if not source_type:
        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            "Source type is required."
        )

    return {
        "name": source_name,
        "url": clean_text(source.get("url")),
        "type": source_type,
    }


# ============================================================
# VERIFIED FACTS
# ============================================================

def validate_facts(story):

    facts = story.get("verified_facts")

    if not isinstance(facts, list):
        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            "verified_facts must be a list."
        )

    cleaned = []

    for fact in facts:

        if not isinstance(fact, dict):
            continue

        label = clean_text(
            fact.get("label")
        ).upper()

        value = clean_text(
            fact.get("value")
        )

        if label and value:
            cleaned.append({
                "label": label,
                "value": value
            })

    if len(cleaned) < 2:
        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            "At least two verified facts are required."
        )

    return cleaned


# ============================================================
# OFFICIAL STATEMENT
# ============================================================

def get_official_statement(story):

    statement = story.get(
        "official_statement",
        {}
    )

    if not isinstance(statement, dict):
        return {
            "available": False,
            "speaker": "",
            "quote": ""
        }

    available = bool(
        statement.get("available", False)
    )

    speaker = clean_text(
        statement.get("speaker")
    )

    quote = clean_text(
        statement.get("quote")
    )

    if not available:
        return {
            "available": False,
            "speaker": "",
            "quote": ""
        }

    if not speaker or not quote:
        return {
            "available": False,
            "speaker": "",
            "quote": ""
        }

    return {
        "available": True,
        "speaker": speaker,
        "quote": quote
    }


# ============================================================
# FIND FACT
# ============================================================

def find_fact(facts, label):

    label = label.upper()

    for fact in facts:

        if fact["label"] == label:
            return fact["value"]

    return ""


# ============================================================
# BUILD HOOK
# ============================================================

def build_hook(story, facts):

    title = clean_text(
        story["title"]
    )

    county = clean_text(
        story["county"]
    )

    status = find_fact(
        facts,
        "STATUS"
    )

    if status:
        return (
            f"{county}: {title}. "
            f"Current status: {status}."
        )

    return (
        f"{county}: {title}."
    )


# ============================================================
# BUILD WHAT HAPPENED
# ============================================================

def build_what_happened(story, facts):

    summary = clean_text(
        story["summary"]
    )

    return summary


# ============================================================
# BUILD KEY FACTS
# ============================================================

def build_key_facts(facts):

    lines = []

    for fact in facts:

        lines.append(
            f"{fact['label'].title()}: "
            f"{fact['value']}."
        )

    return " ".join(lines)


# ============================================================
# BUILD CONTEXT
# ============================================================

def build_context(story):

    editorial = story.get(
        "editorial",
        {}
    )

    unconfirmed = editorial.get(
        "unconfirmed",
        []
    )

    if not isinstance(
        unconfirmed,
        list
    ):
        unconfirmed = []

    if not unconfirmed:
        return (
            "The available information confirms "
            "the reported development."
        )

    names = []

    for item in unconfirmed[:4]:

        item = clean_text(item)

        if item:
            names.append(item)

    if not names:
        return (
            "The available information confirms "
            "the reported development."
        )

    if len(names) == 1:

        missing = names[0]

    elif len(names) == 2:

        missing = (
            f"{names[0]} and {names[1]}"
        )

    else:

        missing = (
            ", ".join(names[:-1])
            + " and "
            + names[-1]
        )

    return (
        "Some project details remain unconfirmed "
        f"from the available source, including {missing}."
    )


# ============================================================
# BUILD OFFICIAL ATTRIBUTION
# ============================================================

def build_attribution(
    story,
    source,
    statement
):

    source_name = source["name"]

    if statement["available"]:

        return (
            f'{source_name}, through '
            f'{statement["speaker"]}, said: '
            f'"{statement["quote"]}"'
        )

    return (
        f"The information is attributed to "
        f"{source_name}."
    )


# ============================================================
# BUILD IMPACT
# ============================================================

def build_impact(story):

    summary = clean_text(
        story["summary"]
    )

    # Only use impact language already present
    # in the supplied story.
    sentences = re.split(
        r"(?<=[.!?])\s+",
        summary
    )

    impact_sentences = []

    keywords = [
        "improve",
        "support",
        "movement",
        "transport",
        "business",
        "residents",
        "economic",
        "access",
        "connect"
    ]

    for sentence in sentences:

        lower = sentence.lower()

        if any(
            keyword in lower
            for keyword in keywords
        ):
            impact_sentences.append(
                sentence.strip()
            )

    if impact_sentences:
        return " ".join(
            impact_sentences
        )

    return (
        "The reported impact will depend on "
        "implementation of the project and "
        "the availability of further verified details."
    )


# ============================================================
# BUILD CLOSE
# ============================================================

def build_close(story, source):

    county = clean_text(
        story["county"]
    )

    source_name = source["name"]

    return (
        f"Rift Valley Watch will track further "
        f"updates from {source_name} on the project "
        f"in {county}."
    )


# ============================================================
# CLEAN GENERATED SECTION
# ============================================================

def clean_section(text):

    text = clean_text(text)

    for phrase in FORBIDDEN_PHRASES:

        pattern = re.compile(
            re.escape(phrase),
            re.IGNORECASE
        )

        text = pattern.sub(
            "",
            text
        )

    text = re.sub(
        r"\s+([,.!?])",
        r"\1",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# BUILD SCRIPT
# ============================================================

def build_script(story):

    validate_required_fields(
        story
    )

    source = validate_source(
        story
    )

    facts = validate_facts(
        story
    )

    statement = get_official_statement(
        story
    )

    hook = clean_section(
        build_hook(
            story,
            facts
        )
    )

    what_happened = clean_section(
        build_what_happened(
            story,
            facts
        )
    )

    key_facts = clean_section(
        build_key_facts(
            facts
        )
    )

    context = clean_section(
        build_context(
            story
        )
    )

    attribution = clean_section(
        build_attribution(
            story,
            source,
            statement
        )
    )

    impact = clean_section(
        build_impact(
            story
        )
    )

    close = clean_section(
        build_close(
            story,
            source
        )
    )

    sections = {
        "hook": hook,
        "what_happened": what_happened,
        "key_facts": key_facts,
        "context": context,
        "attribution": attribution,
        "impact": impact,
        "close": close
    }

    full_text = " ".join(
        sections.values()
    )

    words = full_text.split()

    word_count = len(words)

    if word_count < MIN_WORDS:

        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            f"Script contains only {word_count} words.\n"
            f"Minimum required: {MIN_WORDS}.\n"
            "Add more verified facts to story.json."
        )

    if word_count > MAX_WORDS:

        raise RuntimeError(
            "EDITORIAL QC FAILED.\n"
            f"Script contains {word_count} words.\n"
            f"Maximum allowed: {MAX_WORDS}."
        )

    return {
        "version": "RIFT VALLEY WATCH V2",
        "generated_at": datetime.utcnow().isoformat()
        + "Z",

        "title": clean_text(
            story["title"]
        ),

        "county": clean_text(
            story["county"]
        ),

        "category": clean_text(
            story["category"]
        ).upper(),

        "date": clean_text(
            story["date"]
        ),

        "source": source,

        "official_statement": statement,

        "verified_facts": facts,

        "editorial": story.get(
            "editorial",
            {}
        ),

        "sections": sections,

        "full_script": full_text,

        "word_count": word_count,

        "visual_plan": [
            {
                "sequence": 1,
                "type": "HOOK",
                "purpose": "Open with the strongest verified fact."
            },
            {
                "sequence": 2,
                "type": "VISUAL_EVIDENCE",
                "purpose": "Show an available official/project visual."
            },
            {
                "sequence": 3,
                "type": "KEY_FACTS",
                "purpose": "Display verified project information."
            },
            {
                "sequence": 4,
                "type": "CONTEXT",
                "purpose": "Clearly separate confirmed and unconfirmed information."
            },
            {
                "sequence": 5,
                "type": "IMPACT",
                "purpose": "Use only impact information supported by the source."
            },
            {
                "sequence": 6,
                "type": "SOURCE",
                "purpose": "Display source and publication date."
            }
        ],

        "caption_required": True,

        "qc": {
            "source_present": True,
            "verified_facts_present": True,
            "official_statement_available":
                statement["available"],
            "boilerplate_removed": True,
            "word_count_passed": True,
            "ready_for_video": True
        }
    }


# ============================================================
# SAVE SCRIPT
# ============================================================

def save_script(script):

    SCRIPT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            script,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("RIFT VALLEY WATCH V2")
    print("VERIFIED NEWS SCRIPT ENGINE")
    print("=" * 60)

    print()
    print("[1/5] Loading story...")

    story = load_story()

    print(
        f"      Title: {story.get('title', '')}"
    )

    print(
        f"      County: {story.get('county', '')}"
    )

    print(
        f"      Category: {story.get('category', '')}"
    )

    print()
    print("[2/5] Validating editorial fields...")

    validate_required_fields(
        story
    )

    source = validate_source(
        story
    )

    facts = validate_facts(
        story
    )

    print(
        f"      Source: {source['name']}"
    )

    print(
        f"      Verified facts: {len(facts)}"
    )

    print()
    print("[3/5] Building verified script...")

    script = build_script(
        story
    )

    print(
        f"      Word count: {script['word_count']}"
    )

    print()
    print("[4/5] Running editorial QC...")

    if not script["qc"]["ready_for_video"]:

        raise RuntimeError(
            "Editorial QC failed."
        )

    print(
        "      Source check: PASS"
    )

    print(
        "      Facts check: PASS"
    )

    print(
        "      Boilerplate check: PASS"
    )

    print(
        "      Word count check: PASS"
    )

    print()
    print("[5/5] Saving script...")

    save_script(
        script
    )

    print()
    print(
        f"[SAVED] {SCRIPT_FILE}"
    )

    print()
    print(
        "RIFT VALLEY WATCH V2 SCRIPT ENGINE COMPLETE."
    )


if __name__ == "__main__":
    main()
