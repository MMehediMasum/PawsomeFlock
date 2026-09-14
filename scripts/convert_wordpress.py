#!/usr/bin/env python3
"""WordPress (WXR) -> Astro content collection converter, with image download."""
 
import json
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse
 
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown
 
WXR_PATH = "wordpress-export.xml"
BLOG_DIR = Path("src/content/blog")
AUTHORS_DIR = Path("src/content/authors")
IMAGES_DIR = Path("public/images")
ERROR_LOG = Path("conversion-errors.json")
 
NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
 
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (WordPress-to-Astro migration script)"})
 
 
def slugify(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"
 
 
def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
 
 
def download_image(url, dest_dir, filename_hint=None):
    """Download one image, return its local /images/... path, or None if it fails."""
    try:
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1].split("?")[0] or ".jpg"
        base = slugify(filename_hint or os.path.splitext(os.path.basename(parsed.path))[0])[:60]
        filename = f"{base}{ext}"
        dest_path = dest_dir / filename
        local_url = f"/images/{dest_dir.name}/{filename}"
 
        if dest_path.exists():
            return local_url
 
        dest_dir.mkdir(parents=True, exist_ok=True)
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        dest_path.write_bytes(resp.content)
        return local_url
    except Exception:
        return None
 
 
def process_post_images(content_html, slug, hero_url, errors):
    """Download featured + inline images, rewrite <img> src attributes to local paths."""
    post_image_dir = IMAGES_DIR / slug
    local_hero = None
 
    if hero_url:
        local_hero = download_image(hero_url, post_image_dir, "featured")
        if not local_hero:
            errors.append({"slug": slug, "image": hero_url, "error": "featured image download failed"})
 
    soup = BeautifulSoup(content_html or "", "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or not src.startswith("http"):
            continue
        local_path = download_image(src, post_image_dir)
        if local_path:
            img["src"] = local_path
        else:
            errors.append({"slug": slug, "image": src, "error": "inline image download failed"})
 
    return str(soup), local_hero
 
 
def main():
    if not os.path.exists(WXR_PATH):
        print(f"ERROR: {WXR_PATH} not found. Place the exported XML file here first.")
        sys.exit(1)
 
    tree = ET.parse(WXR_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    items = channel.findall("item")
 
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    AUTHORS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
 
    attachment_map = {}
    for item in items:
        post_type = item.find("wp:post_type", NS)
        if post_type is not None and post_type.text == "attachment":
            post_id = item.find("wp:post_id", NS)
            url = item.find("wp:attachment_url", NS)
            if post_id is not None and url is not None:
                attachment_map[post_id.text] = url.text
 
    authors_seen = {}
    converted = 0
    skipped = 0
    errors = []
 
    posts = [
        item for item in items
        if (item.find("wp:post_type", NS) is not None and item.find("wp:post_type", NS).text == "post")
        and (item.find("wp:status", NS) is not None and item.find("wp:status", NS).text == "publish")
    ]
 
    print(f"Found {len(posts)} published posts to convert.")
 
    for i, item in enumerate(posts, 1):
        slug = "unknown"
        try:
            title_el = item.find("title")
            title = html.unescape((title_el.text or "Untitled").strip()) if title_el is not None else "Untitled"
 
            slug_el = item.find("wp:post_name", NS)
            slug = (slug_el.text or "").strip() if slug_el is not None else ""
            slug = slug or slugify(title)
 
            md_path = BLOG_DIR / f"{slug}.md"
            if md_path.exists():
                skipped += 1
                continue
 
            date_el = item.find("wp:post_date", NS)
            pub_date = date_el.text.split(" ")[0] if date_el is not None and date_el.text else "2024-01-01"
 
            author_el = item.find("dc:creator", NS)
            author_login = (author_el.text or "unknown").strip() if author_el is not None else "unknown"
            author_slug = slugify(author_login)
            authors_seen[author_slug] = author_login
 
            categories = []
            for cat in item.findall("category"):
                if cat.get("domain") == "category" and cat.text:
                    categories.append(html.unescape(cat.text.strip()))
 
            content_el = item.find("content:encoded", NS)
            content_html = content_el.text or "" if content_el is not None else ""
 
            excerpt_el = item.find("excerpt:encoded", NS)
            excerpt_html = excerpt_el.text or "" if excerpt_el is not None else ""
 
            thumb_id = None
            for meta in item.findall("wp:postmeta", NS):
                key = meta.find("wp:meta_key", NS)
                if key is not None and key.text == "_thumbnail_id":
                    val = meta.find("wp:meta_value", NS)
                    thumb_id = val.text if val is not None else None
                    break
            hero_url = attachment_map.get(thumb_id) if thumb_id else None
 
            rewritten_html, local_hero = process_post_images(content_html, slug, hero_url, errors)
 
            description = strip_html(excerpt_html or content_html)[:160]
            markdown_body = html_to_markdown(rewritten_html, heading_style="ATX")
 
            frontmatter_lines = [
                "---",
                f"title: {json.dumps(title)}",
                f"description: {json.dumps(description)}",
                f"pubDate: {pub_date}",
                f"author: {json.dumps(author_slug)}",
                f"categories: {json.dumps(categories)}",
            ]
            if local_hero:
                frontmatter_lines.append(f"heroImage: {json.dumps(local_hero)}")
            frontmatter_lines.append("---")
 
            file_content = "\n".join(frontmatter_lines) + "\n\n" + markdown_body + "\n"
            md_path.write_text(file_content, encoding="utf-8")
            converted += 1
 
            if i % 100 == 0:
                print(f"Progress: {i}/{len(posts)} processed, {converted} converted")
 
        except Exception as e:
            errors.append({"slug": slug, "error": str(e)})
 
    for aslug, name in authors_seen.items():
        author_file = AUTHORS_DIR / f"{aslug}.json"
        if not author_file.exists():
            author_file.write_text(
                json.dumps({"name": name, "bio": "", "avatar": ""}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
 
    print("---")
    print(f"Converted: {converted}")
    print(f"Skipped (already existed): {skipped}")
    print(f"Authors: {len(authors_seen)}")
    print(f"Errors: {len(errors)}")
    if errors:
        ERROR_LOG.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Error details saved to {ERROR_LOG}")
 
 
if __name__ == "__main__":
    main()
