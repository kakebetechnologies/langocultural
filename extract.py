# scrape_sites.py
import os
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time

START_URLS = [
    "https://langoculturalfoundation.org/",
    "https://laanculturalfoundation.org/"  # include both in case both work
]

# change these if you want
OUTPUT_DIR = "scraped_sites"
MAX_PAGES_PER_SITE = 200
DELAY = 1.0  # polite delay between requests (seconds)

def same_domain(u, base):
    return urlparse(u).netloc == urlparse(base).netloc

def sanitize_filename(s):
    return "".join([c if c.isalnum() or c in "-_." else "_" for c in s])[:200]

def fetch_site(start_url):
    visited = set()
    to_visit = [start_url]
    site_dir = os.path.join(OUTPUT_DIR, sanitize_filename(urlparse(start_url).netloc))
    os.makedirs(site_dir, exist_ok=True)
    images_dir = os.path.join(site_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    count = 0
    while to_visit and count < MAX_PAGES_PER_SITE:
        url = to_visit.pop(0)
        if url in visited:
            continue
        try:
            print("Fetching:", url)
            r = requests.get(url, timeout=15, headers={"User-Agent":"LCI-Scraper/1.0 (+your-email@example.com)"})
            time.sleep(DELAY)
            if r.status_code != 200:
                continue
            visited.add(url)
            soup = BeautifulSoup(r.text, "html.parser")

            title = (soup.title.string or "").strip()
            meta_desc = ""
            desc_tag = soup.find("meta", {"name":"description"})
            if desc_tag and desc_tag.get("content"):
                meta_desc = desc_tag["content"].strip()

            # find main content: try common containers
            main = None
            for sel in ["main", "article", "#content", ".content", ".post", ".page"]:
                main = soup.select_one(sel)
                if main:
                    break
            if not main:
                # fallback to body text
                main = soup.body

            # remove scripts/styles
            for s in main(["script","style","noscript"]):
                s.decompose()

            text = "\n\n".join([p.get_text(strip=True) for p in main.find_all(["p","h1","h2","h3","li"]) if p.get_text(strip=True)])
            # save images referenced inside main
            imgs = main.find_all("img")
            img_map = {}
            for i, img in enumerate(imgs, start=1):
                src = img.get("src") or img.get("data-src")
                if not src:
                    continue
                abs_src = urljoin(url, src)
                try:
                    img_r = requests.get(abs_src, timeout=15, stream=True)
                    if img_r.status_code == 200:
                        ext = os.path.splitext(urlparse(abs_src).path)[1] or ".jpg"
                        fname = f"{sanitize_filename(str(i))}{ext}"
                        fpath = os.path.join(images_dir, fname)
                        with open(fpath, "wb") as fh:
                            for chunk in img_r.iter_content(1024):
                                fh.write(chunk)
                        img_map[abs_src] = os.path.join("images", fname)
                except Exception as e:
                    print("Image fetch error:", abs_src, e)

            # save markdown
            safe_name = sanitize_filename(urlparse(url).path or "home")
            md_name = os.path.join(site_dir, safe_name + ".md")
            with open(md_name, "w", encoding="utf-8") as fh:
                fh.write(f"# {title}\n\n")
                fh.write(f"- Source: {url}\n")
                if meta_desc:
                    fh.write(f"- Meta: {meta_desc}\n\n")
                fh.write("## Extracted Text\n\n")
                fh.write(text + "\n\n")
                if img_map:
                    fh.write("## Images\n\n")
                    for src, local in img_map.items():
                        fh.write(f"![{local}]({local})  \nOriginal: {src}\n\n")

            # enqueue internal links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                abs_href = urljoin(url, href.split("#")[0])
                if same_domain(abs_href, start_url) and abs_href not in visited and abs_href not in to_visit:
                    to_visit.append(abs_href)

            count += 1
        except Exception as e:
            print("Error fetching", url, e)
    print("Done scraping", start_url, "saved to", site_dir)

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for u in START_URLS:
        try:
            fetch_site(u)
        except Exception as e:
            print("Site error:", u, e)
