"""
news_parser.py
爬取時尚新聞 RSS，回傳清理後的文章摘要列表。
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# 時尚新聞 RSS 來源
RSS_FEEDS = [
    {
        "name": "Vogue",
        "url": "https://www.vogue.com/feed/rss",
    },
    {
        "name": "Hypebeast",
        "url": "https://hypebeast.com/feed",
    },
    {
        "name": "WWD",
        "url": "https://wwd.com/feed/",
    },
    {
        "name": "ELLE",
        "url": "https://www.elle.com/rss/all.xml/",
    },
    {
        "name": "Google News Fashion",
        "url": "https://news.google.com/rss/search?q=fashion+trend+2026&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    },
]

# 只抓過去 7 天內的文章（每週執行）
DAYS_LOOKBACK = 7
MAX_ARTICLES_PER_SOURCE = 3  # 每個來源最多取 3 篇
MAX_CONTENT_CHARS = 1000     # 每篇文章最多擷取 1000 字


def clean_html(html_text: str) -> str:
    """移除 HTML 標籤，只留純文字。"""
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def fetch_article_content(url: str) -> str:
    """嘗試抓取文章全文（簡易版），失敗時回傳空字串。"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IGBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 嘗試常見的文章容器 selector
        for selector in ["article", "main", ".article-body", ".post-content", ".entry-content"]:
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator=" ", strip=True)
                return text[:MAX_CONTENT_CHARS]

        # fallback：取 <p> 標籤的文字
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs[:10])
        return text[:MAX_CONTENT_CHARS]

    except Exception:
        return ""


def parse_feeds() -> list[dict]:
    """
    爬取所有 RSS 來源，回傳過去 7 天內的文章列表。
    每個元素格式：
    {
        "source": 來源名稱,
        "title": 標題,
        "summary": 摘要或內文片段,
        "url": 文章網址,
        "published": 發布日期字串,
    }
    """
    cutoff = datetime.now() - timedelta(days=DAYS_LOOKBACK)
    articles = []

    for feed_info in RSS_FEEDS:
        print(f"正在抓取 {feed_info['name']}...")
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0

            for entry in feed.entries:
                if count >= MAX_ARTICLES_PER_SOURCE:
                    break

                # 解析發布時間
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])

                # 只收 7 天內的文章
                if published and published < cutoff:
                    continue

                # 取得摘要
                summary = ""
                if hasattr(entry, "summary"):
                    summary = clean_html(entry.summary)
                if len(summary) < 100 and hasattr(entry, "link"):
                    # 摘要太短，嘗試抓全文
                    summary = fetch_article_content(entry.link) or summary

                articles.append({
                    "source": feed_info["name"],
                    "title": entry.get("title", "（無標題）"),
                    "summary": summary[:MAX_CONTENT_CHARS],
                    "url": entry.get("link", ""),
                    "published": published.strftime("%Y-%m-%d") if published else "未知",
                })
                count += 1

        except Exception as e:
            print(f"  ⚠️  {feed_info['name']} 抓取失敗：{e}")
            continue

    print(f"\n共抓到 {len(articles)} 篇文章。")
    return articles


def build_articles_summary(articles: list[dict]) -> str:
    """將文章列表整理成給 Claude 的純文字摘要。"""
    if not articles:
        return "本週未找到相關時尚趨勢文章。"

    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"【文章 {i}】{a['source']} — {a['published']}")
        lines.append(f"標題：{a['title']}")
        lines.append(f"內容：{a['summary']}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # 直接執行此檔案時，印出抓到的文章摘要（測試用）
    articles = parse_feeds()
    print("\n" + "=" * 60)
    print(build_articles_summary(articles))
