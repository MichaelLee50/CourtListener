# scripts/build_feed.py
# Purpose: Fetch CourtListener's live Atom docket feed, fix/normalise it,
# and publish a clean Atom feed with links pointing to the exact entry anchors (#entryNN).

import os
import re
import sys
import time
from datetime import datetime, timezone
import requests
import xml.etree.ElementTree as ET

# -------- Settings (passed via GitHub Actions env) --------
DOCKET_ID   = int(os.getenv("DOCKET_ID", "68024915"))
DOCKET_SLUG = os.getenv("DOCKET_SLUG", "alter-v-openai-inc")

SOURCE_FEED_URL = f"https://www.courtlistener.com/docket/{DOCKET_ID}/feed/"
DOCKET_HTML_URL = f"https://www.courtlistener.com/docket/{DOCKET_ID}/{DOCKET_SLUG}/"
FEED_SELF_URL   = os.getenv("FEED_SELF_URL")  # e.g. https://<username>.github.io/CourtListener/feed.xml

# -------- Namespaces --------
ATOM_NS = "http://www.w3.org/2005/Atom"
NS = {"atom": ATOM_NS}
ET.register_namespace("", ATOM_NS)

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_source(max_retries: int = 5) -> str:
    """Fetch the CourtListener Atom feed with backoff and a friendly User-Agent."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; GitHubActionsBot/1.0; "
            "+https://github.com/michaellee50/CourtListener)"
        )
    }
    backoff = 3
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(SOURCE_FEED_URL, headers=headers, timeout=30)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"Transient HTTP {r.status_code}")
            r.raise_for_status()
            return r.text
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

def extract_entry_number(entry: ET.Element) -> str | None:
    """
    Find docket entry number NN so we can link to #entryNN.

    We check:
      - atom:id for '/entryNN'
      - atom:title for 'Entry #NN'
      - any atom:link href containing '#entryNN' or '/entryNN'
    """
    candidates = []

    id_el = entry.find("atom:id", NS)
    if id_el is not None and id_el.text:
        candidates.append(id_el.text)

    title_el = entry.find("atom:title", NS)
    if title_el is not None and title_el.text:
        candidates.append(title_el.text)

    for link in entry.findall("atom:link", NS):
        href = link.get("href")
        if href:
            candidates.append(href)

    # Try multiple patterns:
    patterns = [
        r"/entry\s*(\d{1,6})",           # .../entry567  or /entry 567
        r"Entry\s*#\s*(\d{1,6})",        # Entry #567
        r"#entry\s*(\d{1,6})",           # #entry567  or #entry 567
        r"\bentry\s*(\d{1,6})\b",        # entry567 or 'entry 567' anywhere
    ]

    for text in candidates:
        for pat in patterns:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                return m.group(1)

    return None

def normalise_feed(xml_text: str) -> bytes:
    root = ET.fromstring(xml_text)

    # Add atom:link rel="self"
    if FEED_SELF_URL:
        self_link = ET.Element(f"{{{ATOM_NS}}}link", {
            "href": FEED_SELF_URL,
            "rel": "self",
            "type": "application/atom+xml"
        })
        title_el = root.find("atom:title", NS)
        if title_el is not None:
            idx = list(root).index(title_el) + 1
            root.insert(idx, self_link)
        else:
            root.insert(0, self_link)

    newest_updated = None

    for entry in root.findall("atom:entry", NS):
        # Ensure <updated>
        updated_el   = entry.find("atom:updated", NS)
        published_el = entry.find("atom:published", NS)
        if updated_el is None:
            updated_el = ET.SubElement(entry, f"{{{ATOM_NS}}}updated")
            updated_el.text = (published_el.text if (published_el is not None and published_el.text)
                               else now_utc_iso())

        if newest_updated is None or (updated_el.text and updated_el.text > newest_updated):
            newest_updated = updated_el.text

        # Remove invalid type="None" from enclosure links
        for link in entry.findall("atom:link", NS):
            if link.get("rel") == "enclosure" and link.get("type") == "None":
                link.attrib.pop("type", None)

        # Build preferred link to docket page (with #entryNN when known)
        entry_no = extract_entry_number(entry)
        preferred_href = DOCKET_HTML_URL if entry_no is None else f"{DOCKET_HTML_URL}#entry{entry_no}"

        # If any existing non-enclosure link already has a #entryNN, keep it.
        keep_existing = False
        for link in entry.findall("atom:link", NS):
            href = link.get("href", "")
            if "#entry" in href and link.get("rel") in (None, "alternate", "self"):
                keep_existing = True
                break

        if not keep_existing:
            # Update or add the alternate link to preferred_href
            alt = None
            for link in entry.findall("atom:link", NS):
                if link.get("rel") in (None, "alternate"):
                    alt = link
                    break
            if alt is None:
                alt = ET.SubElement(entry, f"{{{ATOM_NS}}}link")
            alt.set("href", preferred_href)
            alt.set("rel", "alternate")

    # Feed-level <updated>
    feed_updated = root.find("atom:updated", NS)
    if feed_updated is None:
        feed_updated = ET.SubElement(root, f"{{{ATOM_NS}}}updated")
    feed_updated.text = newest_updated or now_utc_iso()

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

def main():
    try:
        xml_text = fetch_source()
        out_xml = normalise_feed(xml_text)
        with open("feed.xml", "wb") as f:
            f.write(out_xml)
        print("feed.xml written successfully.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
