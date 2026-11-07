#!/usr/bin/env python3
"""
Parsing of saved LinkedIn profile pages.

The browser extension (browser_extension/) saves each profile's main page and its five
"details" pages to raw_live/<slug>/<section>.html; this module turns them into records.
LinkedIn's markup uses generated class names, so the parser relies on what stays stable:
card titles, `componentkey` attributes, `data-testid="expandable-text-box"` and line order.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("LinkedInExtractor")

SECTIONS = {
    "profile": "",
    "experience": "details/experience/",
    "education": "details/education/",
    "skills": "details/skills/",
    "interests": "details/interests/",
    "activity": "recent-activity/all/",
}


def normalize_profile_url(line: str) -> Optional[str]:
    """Extracts a URL from a line, dropping list numbering and tracking parameters."""
    if line.lstrip().startswith("#"):
        return None
    match = re.search(r"https?://\S+", line)
    if not match:
        return None
    parts = urlparse(match.group(0))
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}/"


def read_urls_file(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        urls = [normalize_profile_url(line) for line in f]
    return list(dict.fromkeys(u for u in urls if u))  # Drops blank lines and repeated URLs.


def slug_of(url: str) -> str:
    return unquote(urlparse(url).path.rstrip("/").split("/")[-1])


# ---------------------------------------------------------------------------
# Parsing saved pages
#
# LinkedIn's profile markup (late 2026) uses generated class names, so the parser relies on
# what stays stable: each card's <h2> title, `componentkey` attributes on list entries and
# activity cards, `data-testid="expandable-text-box"` on long text, and the order of <p> lines.
# ---------------------------------------------------------------------------

TEXT_BOX = '[data-testid="expandable-text-box"]'
SKILL_ITEM = '[componentkey^="com.linkedin.sdui.profile.skill"]'
ACTIVITY_CARD = '[componentkey^="update-card"]'
EMPLOYMENT_TYPES = {
    "Full-time", "Part-time", "Self-employed", "Freelance", "Contract", "Internship",
    "Apprenticeship", "Seasonal", "Permanent", "Temporary", "Trainee",
}
UI_TEXT = {"Show all", "…", "more", "see more", "Follow", "Connect", "Message", "·", "Present"}
# Tab labels on /details/skills/; on a page saved before its list loaded, they are all that shows.
SKILL_TABS = {"All", "Industry Knowledge", "Tools & Technologies", "Interpersonal Skills", "Other Skills", "Languages"}


def _root(html: str) -> Tag:
    soup = BeautifulSoup(html or "", "lxml")
    return soup.select_one("main") or soup


def _card_of(h2: Tag) -> Tag:
    """Widest ancestor of a card title that holds no other card title."""
    node = h2
    while node.parent is not None and node.parent.name not in ("main", "body", "[document]") \
            and len(node.parent.find_all("h2")) == 1:
        node = node.parent
    return node


def _card(root: Tag, title: str) -> Optional[Tag]:
    """
    The card titled `title`. On the main profile page the title is an <h2>. Details pages
    (e.g. /details/skills/) title their one card with a <p> instead, and the rest of those pages
    is a sidebar of other people plus footer links, which must not be parsed.
    """
    for h2 in root.find_all("h2"):
        if re.sub(r"\s*\(\d+\)$", "", h2.get_text(" ", strip=True)) == title:
            return _card_of(h2)
    for p in root.find_all("p"):
        if p.get_text(" ", strip=True) != title:
            continue
        card = p.find_parent(attrs={"componentkey": re.compile(r"^com\.linkedin\.sdui\.profile\.card")})
        if card is not None:
            return card
        node = p  # No card wrapper: widen until the next step would take in other headed sections.
        while node.parent is not None and node.parent.name not in ("main", "body", "[document]") \
                and node.parent.find(["h1", "h2"]) is None:
            node = node.parent
        return node
    return None


def _p_lines(el: Tag, skip: Optional[Tag] = None) -> List[str]:
    """Short <p> field lines of an element; long text boxes and one optional nested part are left out."""
    lines = []
    for p in el.find_all("p"):
        if (skip is not None and skip in p.parents) or p.find_parent(attrs={"data-testid": "expandable-text-box"}):
            continue
        if p.find_parent(attrs={"role": "dialog"}):  # e.g. the name-pronunciation audio player
            continue
        text = p.get_text(" ", strip=True).replace("\u200b", "").strip()
        if text and text not in UI_TEXT:
            lines.append(text)
    return lines


def _long_text(el: Tag, skip: Optional[Tag] = None) -> Optional[str]:
    parts = []
    for box in el.select(TEXT_BOX):
        if skip is not None and skip in box.parents:
            continue
        text = re.sub(r"\s*…\s*more$", "", box.get_text(" ", strip=True)).strip()
        if text:
            parts.append(text)
    return "\n".join(parts) or None


def _entries(card: Tag) -> List[Tag]:
    """
    List entries of a card: the largest group of sibling elements that carry a `componentkey`
    and contain field lines. Grouping by parent avoids treating a wrapper as a single entry.
    """
    groups: Dict[int, List[Tag]] = {}
    for item in card.select("[componentkey]"):
        if item.name != "h2" and item.find("p") and item.parent is not None:
            groups.setdefault(id(item.parent), []).append(item)
    if not groups:
        return []
    # The biggest group wins; on a tie, the one that appears first in the page.
    return max(groups.values(), key=len)


def _top_level(el: Tag, selector: str) -> List[Tag]:
    items = el.select(selector)
    return [i for i in items if not any(parent in items for parent in i.parents)]


def _duration_months(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    years = re.search(r"(\d+)\s*yrs?", text)
    months = re.search(r"(\d+)\s*mos?", text)
    if not years and not months:
        return None
    return (int(years.group(1)) if years else 0) * 12 + (int(months.group(1)) if months else 0)


def _is_date_line(line: str) -> bool:
    return bool(re.search(r"(\d{4}|Present)\s*[-–]\s*(\w+\s)?(\d{4}|Present)", line))


def _date_fields(lines: List[str]) -> Tuple[Optional[str], Optional[str], Optional[int], int]:
    """Reads 'Jan 2020 - Present · 2 yrs 3 mos'. Returns start, end, months and the line index."""
    for idx, line in enumerate(lines):
        if _is_date_line(line):
            dates, _, duration = line.partition("·")
            parts = re.split(r"\s*[-–]\s*", dates.strip(), maxsplit=1)
            return parts[0], parts[1] if len(parts) > 1 else None, _duration_months(duration), idx
    return None, None, None, -1


def _org_url(el: Tag) -> Optional[str]:
    """Stable company or school link, e.g. https://www.linkedin.com/company/1441/ (Google in any language)."""
    for a in el.find_all("a", href=True):
        match = re.search(r"https://www\.linkedin\.com/(company|school)/[^/?#]+/", a["href"])
        if match:
            return match.group(0)
    return None


def _looks_like_location(line: str, description: Optional[str]) -> bool:
    """Short place names; the start of a description sometimes shows up as a field line too."""
    if len(line) > 70 or line[:1] in "-•*" or ". " in line:
        return False
    return not (description and description.startswith(line[:40]))


def _role(lines: List[str], company: Optional[str], description: Optional[str],
          default_location: Optional[str] = None, company_url: Optional[str] = None) -> Dict[str, Any]:
    start, end, months, date_idx = _date_fields(lines)
    location = default_location
    if date_idx >= 0:
        after = [l for l in lines[date_idx + 1:] if l not in EMPLOYMENT_TYPES]
        if after and _looks_like_location(after[0], description):
            location = after[0]
    return {
        "title": lines[0] if lines else None,
        "company": company,
        "company_url": company_url,
        "start_date": start,
        "end_date": end,
        "duration_months": months,
        "location": location,
        "description": description,
    }


def parse_experiences(root: Tag) -> List[Dict[str, Any]]:
    card = _card(root, "Experience")
    if card is None:
        return []
    experiences = []
    for item in _entries(card):
        roles = item.select("ul > li")
        if roles:  # One company with several roles: the header names the company, maybe a location.
            role_list = item.find("ul")
            header = _p_lines(item, skip=role_list)
            company = header[0] if header else None
            header_location = next(
                (l for l in header[1:] if _duration_months(l) is None and l not in EMPLOYMENT_TYPES), None
            )
            experiences += [_role(_p_lines(li), company, _long_text(li), header_location, _org_url(item)) for li in roles]
        else:
            lines = _p_lines(item)
            company = lines[1].split("·")[0].strip() if len(lines) > 1 and not _is_date_line(lines[1]) else None
            experiences.append(_role(lines, company, _long_text(item), company_url=_org_url(item)))
    return experiences


def parse_educations(root: Tag) -> List[Dict[str, Any]]:
    card = _card(root, "Education")
    if card is None:
        return []
    educations = []
    for item in _entries(card):
        lines = _p_lines(item)
        if not lines:
            continue
        degree_line = next((l for l in lines[1:2] if not _is_date_line(l)), None)
        degree, field = None, None
        if degree_line:
            degree, _, field = (part.strip() for part in degree_line.partition(","))
        years = re.findall(r"\d{4}", next((l for l in lines if _is_date_line(l)), ""))
        educations.append({
            "school": lines[0],
            "school_url": _org_url(item),
            "degree": degree or None,
            "field_of_study": field or None,
            "start_year": int(years[0]) if years else None,
            "end_year": int(years[1]) if len(years) > 1 else None,
        })
    return educations


def parse_skills(root: Tag) -> List[str]:
    """Reads skill names from the Skills card or the dedicated details/skills page."""
    card = _card(root, "Skills")
    if card is None:
        return []
    skills: List[str] = []

    def add(name: str) -> None:
        name = name.replace("\u200b", "").strip()
        if (
            name
            and name not in UI_TEXT
            and name not in SKILL_TABS
            and name not in skills
            and not name.lower().startswith(("endorsed", "show all", "skills"))
            and "endorsement" not in name.lower()
            and len(name) <= 80
        ):
            skills.append(name)

    # Current markup: every skill has its own `componentkey="com.linkedin.sdui.profile.skill(...)"`,
    # and the first plain <span> of the innermost one is the name. Tab labels ("All", "Industry
    # Knowledge") and "Software Engineer at Google" associations sit outside or after it.
    skill_items = card.select(SKILL_ITEM)
    for item in skill_items:
        if item.select(SKILL_ITEM):
            continue
        spans = [sp for sp in item.find_all("span")
                 if not sp.find("span") and not sp.find_parent("a") and sp.get_text(strip=True)]
        if spans:
            add(spans[0].get_text(" ", strip=True))
    if skills:
        return skills

    # Detail pages and main-card previews put each skill in a list entry; first line is the name.
    for item in _entries(card):
        lines = _p_lines(item)
        if lines:
            add(lines[0])
    if skills:
        return skills

    for span in card.find_all("span"):
        if span.find("span") or span.find_parent(attrs={"role": "list"}) or span.find_parent("a"):
            continue
        add(span.get_text(" ", strip=True))
    return skills


def parse_interests(root: Tag) -> List[Dict[str, Any]]:
    """Reads followed companies/schools/newsletters from Interests card or details page."""
    card = _card(root, "Interests")
    if card is None:
        return []

    def clean(text: str) -> str:
        return text.replace("\u200b", "").strip()

    category_labels = ("Company", "School", "Newsletter", "Influencer", "Group", "Top Voice", "Top Voices")
    labels = {clean(span.get_text(" ", strip=True)) for span in card.find_all("span") if not span.find("span")}
    interests: List[Dict[str, Any]] = []

    def add(name: str, category: Optional[str] = None) -> None:
        name = clean(name)
        if not name or name in UI_TEXT or name.lower().startswith(("show all", "follow")):
            return
        if any(ch.isdigit() for ch in name) and "follower" in name.lower():
            return
        if any(i["name"] == name for i in interests):
            return
        if category == "Top Voices":
            category = "Top Voice"
        interests.append({"name": name, "category": category, "type": "following"})

    # LinkedIn marks the display name with aria-hidden; category often sits in a sibling "Name, Company" label.
    for hidden in card.select('span[aria-hidden="true"]'):
        name = clean(hidden.get_text(" ", strip=True))
        category = next(
            (label.rsplit(", ", 1)[1] for label in labels if label.startswith(name + ", ") and label.rsplit(", ", 1)[1] in category_labels),
            None,
        )
        add(name, category)

    # The default "Top Voices" tab lists followed people: plain links to their /in/ profiles.
    for link in card.find_all("a", href=re.compile(r"/in/[^/?#]+")):
        name = clean(link.get_text(" ", strip=True))
        if name and len(name) <= 80 and not re.search(r"\d", name):
            add(name, "Top Voice")
    if interests:
        return interests

    # Fallback for sparse fixtures / older markup without aria-hidden names.
    for item in _entries(card):
        lines = _p_lines(item)
        if not lines:
            continue
        raw_name = lines[0]
        category = None
        for label in category_labels:
            suffix = f", {label}"
            if raw_name.endswith(suffix):
                raw_name, category = raw_name[: -len(suffix)], label
                break
        add(raw_name, category)
    return interests


def _activity_time(urn: str) -> Optional[str]:
    """LinkedIn activity IDs embed their creation time in the top bits (milliseconds)."""
    match = re.search(r"activity:(\d+)", urn)
    if not match:
        return None
    moment = dt.datetime.fromtimestamp((int(match.group(1)) >> 22) / 1000, tz=dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_before(word: str, text: str) -> Optional[int]:
    match = re.search(rf"(\d[\d,]*)\+?\s+{word}", text)
    return int(match.group(1).replace(",", "")) if match else None


EMPTY_SECTION_TEXT = ("Nothing to see for now", "hasn’t posted", "hasn't posted", "No skills", "No interests")


def heading_counts(profile_html: str) -> Dict[str, int]:
    """Counts LinkedIn prints in main-page card titles, e.g. {"Skills": 80} from "Skills (80)"."""
    counts = {}
    for h2 in _root(profile_html).find_all("h2"):
        match = re.match(r"(.+?)\s*\((\d+)\)$", h2.get_text(" ", strip=True))
        if match:
            counts[match.group(1)] = int(match.group(2))
    return counts


def page_is_complete(section: str, html: str, expected: Optional[int] = None) -> bool:
    """
    True when a saved page shows its content. LinkedIn loads each section only once it is on
    screen, so a page saved while its window was hidden can hold just the page shell, and a long
    list can stop after its first batch. `expected` is the count from the main page's card title.
    """
    root = _root(html)
    text = root.get_text(" ", strip=True)
    if any(marker in text for marker in EMPTY_SECTION_TEXT):
        return True
    if section == "profile":  # Section titles are <h2>; footer links such as "About" are not.
        titles = {re.sub(r"\s*\(\d+\)$", "", h2.get_text(" ", strip=True)) for h2 in root.find_all("h2")}
        return bool(titles & {"Experience", "Education", "About"})
    parsers = {
        "experience": parse_experiences,
        "education": parse_educations,
        "skills": parse_skills,
        "interests": parse_interests,
        "activity": lambda r: parse_activities(r, "check"),
    }
    if section not in parsers:
        return True
    found = len(parsers[section](root))
    return found >= expected if expected else found > 0


def parse_activities(root: Tag, profile_id: str) -> List[Dict[str, Any]]:
    card = _card(root, "Activity") or root
    activities = []
    for item in _top_level(card, ACTIVITY_CARD):
        text = item.get_text(" ", strip=True)
        header = text[:160].lower()
        activity_type = (
            "repost" if "reposted" in header else
            "comment" if "commented" in header else
            "reaction" if re.search(r"\b(likes|liked|celebrates|loves|supports|finds|reacted)\b", header) else
            "post"
        )
        urn = re.search(r"urn:li:activity:\d+", str(item))
        content = _long_text(item)
        activities.append({
            "activity_id": urn.group(0) if urn else item.get("componentkey"),
            "type": activity_type,
            "content": content,
            "timestamp": _activity_time(urn.group(0)) if urn else None,
            "likes_count": _count_before("reactions?", text),
            "comments_count": _count_before("comments?", text),
            "interacted_with": sorted({  # Slugs here; resolved to profile IDs in parse_capture_dir.
                slug_of(a["href"].split("?")[0]) for a in item.select('a[href*="/in/"]')
            }),
            "hashtags": sorted(set(re.findall(r"#\w+", content or ""))),
        })
    return activities


def _top_card(root: Tag) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """Name, headline, location and connection count from the card holding the first <h2>."""
    name_h2 = root.find("h2")
    if name_h2 is None:
        return None, None, None, None
    card = _card_of(name_h2)
    lines = [l for l in _p_lines(card) if not l.startswith("·")]
    headline = lines[0] if lines else None
    # The location is the last line before the "Contact info" link.
    before_contact = lines[1:lines.index("Contact info")] if "Contact info" in lines else []
    location = before_contact[-1] if before_contact else None
    return name_h2.get_text(" ", strip=True), headline, location, _count_before("connections", card.get_text(" ", strip=True))


def parse_profile(sections: Dict[str, str], slug: str, profile_id: str) -> Dict[str, Any]:
    """Builds one profile record from its saved pages. Anything not found stays null or empty."""
    main = _root(sections.get("profile", ""))
    full_name, headline, location, connections = _top_card(main)
    if not full_name:
        raise ValueError(f"No profile name found for '{slug}' (changed markup or blocked page)")

    def richer(parse, name: str) -> list:
        """Parses the main page and the section's own details page (when saved); keeps the longer result."""
        results = [parse(main)]
        if sections.get(name):
            results.append(parse(_root(sections[name])))
        return max(results, key=len)

    about_card = _card(main, "About")
    activity_card = _card(main, "Activity")
    experiences = richer(parse_experiences, "experience")
    parsed = {
        "profile_id": profile_id,
        "public_identifier": slug,
        "full_name": full_name,
        "headline": headline,
        "current_company": experiences[0]["company"] if experiences else None,
        "current_role": experiences[0]["title"] if experiences else None,
        "department": None,
        "seniority": None,
        "location": location,
        "about": _long_text(about_card) if about_card is not None else None,
        "connections_count": connections,
        "followers_count": _count_before("followers", activity_card.get_text(" ", strip=True)) if activity_card else None,
        "experiences": experiences,
        "educations": richer(parse_educations, "education"),
        "skills": richer(parse_skills, "skills"),
        "interests": richer(parse_interests, "interests"),
        "activities": richer(lambda root: parse_activities(root, profile_id), "activity"),
        "data_source": "live",
        # Counts LinkedIn prints in card titles, e.g. "Skills (26)"; tests compare them with what was parsed.
        "linkedin_counts": heading_counts(sections.get("profile", "")),
    }
    parsed["missing_sections"] = [
        key for key in ("experiences", "educations", "skills", "interests", "activities") if not parsed[key]
    ]
    return parsed


def parse_capture_dir(urls: List[str], capture_dir: str) -> List[Dict[str, Any]]:
    """
    Parses saved pages for all URLs and links activity mentions between listed profiles.
    A profile whose main page shows no profile (wrong URL, deleted account) is skipped and logged;
    fewer than two usable profiles is an error.
    """
    profiles, skipped = [], []
    for url in urls:
        slug = slug_of(url)
        sections = {}
        for section in SECTIONS:
            path = os.path.join(capture_dir, slug, f"{section}.html")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    sections[section] = f.read()
        try:
            profiles.append(parse_profile(sections, slug, f"p{len(profiles) + 1:02d}"))
        except ValueError as exc:
            skipped.append(slug)
            logger.warning(f"Skipped {slug}: {exc}")
    if skipped:
        logger.warning(f"{len(skipped)} profile(s) skipped: {', '.join(skipped)}")
    if len(profiles) < 2:
        raise ValueError(f"Only {len(profiles)} usable profile(s); at least 2 are needed")

    slug_to_id = {p["public_identifier"]: p["profile_id"] for p in profiles}
    for p in profiles:
        for activity in p["activities"]:
            linked = {slug_to_id.get(slug) for slug in activity["interacted_with"]}
            activity["interacted_with"] = sorted(pid for pid in linked if pid and pid != p["profile_id"])
    return profiles
