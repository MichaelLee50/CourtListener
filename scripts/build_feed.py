import os
import re
import sys
from datetime import datetime, timezone
import requests
import xml.etree.ElementTree as ET

DOCKET_ID = int(os.getenv("DOCKET_ID", "68024915"))
DOCKET_SLUG = os.getenv("DOCKET_SLUG", "alter-v-openai-inc")
SOURCE_FEED_URL = f"https://www.courtlistener.com/docket/{DOCKET_ID}/feed/"
DOCKET_HTML_URL = f"https://www.courtlistener.com/docket/{DOCKET_ID}/{DOCKET_SLUG}/"
FEED_SELF_URL = os.getenv("FEED_SELF_URL")  # e.g., https://<username>.github.io/CourtListener/feed.xml

ATOM_NS = "http://www.w3.org/2005/Atom"
NS = {"atom": ATOM_NS}
ET.register_namespace("", ATOM_NS)

def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_source():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; GitHubActionsBot/1.0; +https://github.com)"
    }
    r = requests.get(SOURCE_FEED_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def extract_entry_number(entry):
    patterns = []
    for tag in ["atom:id", "atom:title"]:
        el = entry.find(tag, NS)
        if el is not None and el.text:
            patterns.append(el.text)
    for text in patterns:
        m = re.search(r"(?:entry|#)\\s*(\\d{1,6})", text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def normalise_feed(xml_text):
    root = ET.fromstring(xml_text)
    feed_updated = root.find("atom:updated", NS)
    newest = None

    if FEED_SELF_URL:
        atom_link_self = ET.Element(f"{{{ATOM_NS}}}link", {
            "href": FEED_SELF_URL,
            "rel": "self",
            "type": "application/atom+xml"
        })
        root.insert(1, atom_link_self)

    for entry in root.findall("atom:entry", NS):
        updated_el = entry.find("atom:updated", NS)
        published_el = entry.find("atom:published", NS)
        if updated_el is None:
            updated_el = ET.SubElement(entry, f"{{{ATOM_NS}}}updated")
            updated_el.text = published_el.text if published_el is not None else now_utc_iso()
        if newest is None or updated_el.text > newest:
            newest = updated_el.text

        for link in entry.findall("atom:link", NS):
            if link.get("rel") == "enclosure" and link.get("type") == "None":
                link.attrib.pop("type", None)

        entry_number = extract_entry_number(entry)
        preferred_href = DOCKET_HTML_URL if entry_number is None else f"{DOCKET_HTML_URL}#entry{entry_number}"
        link_el = None
        for link in entry.findall("atom:link", NS):
            if link.get("rel") in (None, "alternate"):
                link_el = link
                break
        if link_el is None:
            link_el = ET.SubElement(entry, f"{{{ATOM_NS}}}link")
        link_el.set("href", preferred_href)
        link_el.set("rel", "alternate")

    if feed_updated is None:
        feed_updated = ET.SubElement(root, f"{{{ATOM_NS}}}updated")
    feed_updated.text = newest or now_utc_iso()

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

def main():
    try:
        xml_text = fetch_source()
        out = normalise_feed(xml_text)
        with open("feed.xml", "wb") as f:
            f.write(out)
        print("feed.xml written successfully.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
