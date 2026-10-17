import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


SOURCE_URL = "https://kantogakuin-rugby.jp/newsreports/"
BASE_URL = "https://kantogakuin-rugby.jp/"
OUTPUT_FILE = Path("kantogakuin_rugby.xml")

FEED_TITLE = "関東学院大学ラグビー部 NEWS REPORTS"
FEED_LINK = SOURCE_URL
FEED_DESCRIPTION = "関東学院大学ラグビー部公式サイト NEWS REPORTS"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

RETRIES = 3
TIMEOUT = 30
WAIT_SECONDS = 10


def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip()


def fetch_page(session, url):
    last_error = None

    for attempt in range(1, RETRIES + 1):
        try:
            print(f"取得 {attempt}/{RETRIES}: {url}")

            response = session.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            print(
                f"HTTP: {response.status_code} / "
                f"{len(response.content)} bytes"
            )

            response.raise_for_status()

            response.encoding = (
                response.apparent_encoding or "utf-8"
            )

            return response.text

        except requests.RequestException as e:
            last_error = e
            print(f"取得失敗: {e}")

            if attempt < RETRIES:
                print(f"{WAIT_SECONDS}秒待って再試行します")
                time.sleep(WAIT_SECONDS)

    raise RuntimeError(
        f"ページを取得できませんでした: {last_error}"
    )


def parse_date(text):
    match = re.search(
        r"(20\d{2})/(\d{1,2})/(\d{1,2})",
        text,
    )

    if not match:
        return None

    try:
        year, month, day = map(int, match.groups())

        return datetime(
            year,
            month,
            day,
            0,
            0,
            0,
            tzinfo=JST,
        )

    except ValueError:
        return None


def clean_title(text):
    text = normalize_text(text)

    text = re.sub(
        r"^[\">'\s]*20\d{2}/\d{1,2}/\d{1,2}\s*",
        "",
        text,
    )

    text = re.sub(
        r"^CATEGORY\s*[:：]\s*NEWS\s+REPORTS\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return normalize_text(text)


def parse_articles(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    articles = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        if not href:
            continue

        absolute_url = urljoin(
            BASE_URL,
            href,
        )

        if not re.search(
            r"https://kantogakuin-rugby\.jp/newsreports/\d+/",
            absolute_url,
        ):
            continue

        raw_text = normalize_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not raw_text:
            continue

        pub_date = parse_date(raw_text)

        if not pub_date:
            continue

        title = clean_title(raw_text)

        if not title:
            continue

        articles[absolute_url] = {
            "title": title,
            "link": absolute_url,
            "pub_date": pub_date,
            "description": "",
        }

    return list(articles.values())


def load_existing():
    if not OUTPUT_FILE.exists():
        return {}

    try:
        tree = ET.parse(OUTPUT_FILE)
        root = tree.getroot()

        existing = {}

        for item in root.findall("./channel/item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date_text = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()

            if not title or not link or not pub_date_text:
                continue

            try:
                pub_date = parsedate_to_datetime(
                    pub_date_text
                )

                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(
                        tzinfo=JST
                    )

                pub_date = pub_date.astimezone(JST)

            except Exception:
                continue

            existing[link] = {
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "description": description,
            }

        return existing

    except Exception as e:
        raise RuntimeError(
            f"既存RSSを正常に読み込めませんでした: {e}"
        )


def make_guid(link):
    return hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()


def write_rss(items):
    rss = ET.Element(
        "rss",
        {"version": "2.0"},
    )

    channel = ET.SubElement(
        rss,
        "channel",
    )

    ET.SubElement(
        channel,
        "title",
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link",
    ).text = FEED_LINK

    ET.SubElement(
        channel,
        "description",
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language",
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(JST)
    )

    for article in items:
        item = ET.SubElement(
            channel,
            "item",
        )

        ET.SubElement(
            item,
            "title",
        ).text = article["title"]

        ET.SubElement(
            item,
            "link",
        ).text = article["link"]

        guid = ET.SubElement(
            item,
            "guid",
            {"isPermaLink": "false"},
        )

        guid.text = make_guid(
            article["link"]
        )

        ET.SubElement(
            item,
            "pubDate",
        ).text = format_datetime(
            article["pub_date"]
        )

        ET.SubElement(
            item,
            "description",
        ).text = article.get(
            "description",
            "",
        )

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    print("=" * 70)
    print("関東学院大学ラグビー部 NEWS REPORTS RSS")
    print("=" * 70)

    existing = load_existing()

    print(f"既存RSS件数: {len(existing)}")

    session = requests.Session()

    try:
        html = fetch_page(
            session,
            SOURCE_URL,
        )

        current_articles = parse_articles(
            html
        )

    except Exception as e:
        print()
        print(f"取得処理でエラー: {e}")
        print("既存RSSは変更せず終了します")
        raise

    print(
        f"公式サイト取得件数: "
        f"{len(current_articles)}"
    )

    if not current_articles:
        raise RuntimeError(
            "記事を1件も取得できませんでした。"
            "既存RSSは変更しません。"
        )

    current = {
        article["link"]: article
        for article in current_articles
    }

    new_links = set(current) - set(existing)

    merged = dict(existing)
    merged.update(current)

    items = list(merged.values())

    items.sort(
        key=lambda x: x["pub_date"],
        reverse=True,
    )

    print(f"新規記事数: {len(new_links)}")
    print(f"累積RSS件数: {len(items)}")

    print()
    print("取得記事（最新30件）:")

    for i, article in enumerate(
        items[:30],
        start=1,
    ):
        date_text = (
            article["pub_date"]
            .astimezone(JST)
            .strftime("%Y-%m-%d")
        )

        marker = (
            " [NEW]"
            if article["link"] in new_links
            else ""
        )

        print(
            f"{i:2d}. "
            f"{date_text} "
            f"{article['title']}"
            f"{marker}"
        )

        print(
            f"    {article['link']}"
        )

    write_rss(items)

    print()
    print(f"保存完了: {OUTPUT_FILE}")
    print(f"RSS総件数: {len(items)}")


if __name__ == "__main__":
    main()