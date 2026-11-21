import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://jobs.okky.kr"
TOPIC = os.environ["NTFY_TOPIC"]
CONFIG_FILE = Path("config.json")
SEEN_FILE = Path("seen.json")

LINK_RE = re.compile(r"^/recruits/\d+$")


def load_config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def build_url(cfg):
    params = []
    idx = 0
    for loc in cfg.get("locations", []):
        city = loc["city"]
        districts = loc.get("districts") or []
        if not districts:
            params.append((f"location[{idx}].city", city))
            idx += 1
        else:
            for d in districts:
                params.append((f"location[{idx}].city", city))
                params.append((f"location[{idx}].district", d))
                idx += 1
    query = f"?{urlencode(params)}" if params else ""
    return f"{BASE}/contract{query}"


def fetch_items(url):
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; okky-watch/1.0)"},
        timeout=30,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items = {}
    for a in soup.find_all("a", href=True):
        path = a["href"].split("?")[0]
        if not LINK_RE.match(path):
            continue
        link = urljoin(BASE, path)
        h2 = a.find("h2")
        title = " ".join((h2 or a).get_text(" ", strip=True).split())
        if link not in items or len(title) > len(items[link]):
            items[link] = title or link
    return items, len(r.text)

def load_state():
    """저장된 (검색 URL, 본 공고 링크 집합)을 돌려준다."""
    if not SEEN_FILE.exists():
        return None, set()
    data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    if isinstance(data, list):          # 예전 형식 호환
        return None, set(data)
    return data.get("url"), set(data.get("seen", []))


def notify(title, link):
    requests.post(
        "https://ntfy.sh",
        json={
            "topic": TOPIC,
            "title": "OKKY 새 공고",
            "message": title[:200],
            "click": link,
            "priority": 4,
        },
        timeout=30,
    )


MIN_HTML_LEN = 3000   # 이보다 짧으면 정상 페이지가 아니라고 판단

def main():
    cfg = load_config()
    url = build_url(cfg)
    print("검색 URL:", url)

    items, html_len = fetch_items(url)

    if not items:
        if html_len < MIN_HTML_LEN:
            print(f"응답이 비정상적으로 짧습니다({html_len}자). 차단/점검 가능성.")
            sys.exit(1)
        print("현재 조건에 맞는 공고가 없습니다.")

    saved_url, seen = load_state()

    if saved_url != url:
        # 첫 실행이거나 지역 설정이 바뀐 경우: 알림 없이 기준선만 저장
        print("기준선 저장 (알림 없음):", len(items), "건")
        seen = set(items)
    else:
        for link, title in items.items():
            if link not in seen:
                notify(title, link)
                print("알림:", title, link)
        seen |= set(items)

    SEEN_FILE.write_text(
        json.dumps({"url": url, "seen": sorted(seen)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()