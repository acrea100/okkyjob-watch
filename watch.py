import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://jobs.okky.kr"
TOPIC = os.environ["NTFY_TOPIC"]          # 추측하기 어려운 긴 문자열로 설정
SEEN_FILE = Path("seen.json")

# 공고 상세 링크 패턴 (브라우저에서 실제 링크를 보고 필요하면 수정)
LINK_RE = re.compile(r"^/recruits/\d+$")

DISTRICTS = ["경산시", "고령군", "구미시", "군위군", "김천시", "성주군",
             "영천시", "의성군", "청도군", "칠곡군"]


def build_url():
    params = [("location[0].city", "대구")]
    for i, d in enumerate(DISTRICTS, start=1):
        params.append((f"location[{i}].city", "경북"))
        params.append((f"location[{i}].district", d))
    return f"{BASE}/contract?{urlencode(params)}"


def fetch_items():
    r = requests.get(
        build_url(),
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
    return items

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


def main():
    items = fetch_items()
    if not items:
        # 구조가 바뀌었거나 차단된 경우 → 워크플로우 실패로 알 수 있게 함
        print("공고를 하나도 찾지 못했습니다. LINK_RE 확인 필요.")
        sys.exit(1)

    first_run = not SEEN_FILE.exists()
    seen = set(json.loads(SEEN_FILE.read_text())) if not first_run else set()

    new = {l: t for l, t in items.items() if l not in seen}
    if not first_run:                      # 첫 실행은 기준선만 저장 (알림 폭탄 방지)
        for link, title in new.items():
            notify(title, link)
            print("알림:", title, link)

    SEEN_FILE.write_text(
        json.dumps(sorted(seen | set(items)), ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()