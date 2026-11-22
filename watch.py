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

def find_content(node):
    """파싱된 JSON 안에서 result.content(공고 배열)를 재귀적으로 찾는다."""
    if isinstance(node, dict):
        res = node.get("result")
        if isinstance(res, dict) and isinstance(res.get("content"), list):
            return res["content"]
        for v in node.values():
            found = find_content(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = find_content(v)
            if found is not None:
                return found
    return None


def pay_text(rr):
    lo, hi = rr.get("minPay"), rr.get("maxPay")
    if lo is None and hi is None:
        return ""
    if lo == hi:
        return f"{lo}만원"
    return f"{lo}~{hi}만원"


def fetch_items(url):
    r = requests.get(
        url + ("&" if "?" in url else "?") + "_rsc=okkywatch",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; okky-watch/1.0)",
            "RSC": "1",
            "Accept": "*/*",
            "Next-Url": "/contract",
        },
        timeout=30,
    )
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="replace")   # 인코딩 깨짐 방지

    content = None
    for line in text.splitlines():
        if '"result"' not in line:
            continue
        _, _, body = line.partition(":")
        try:
            content = find_content(json.loads(body))
        except ValueError:
            continue
        if content is not None:
            break

    if content is None:
        return {}, False          # 응답 구조를 못 찾음 → 구조 변경/차단 의심

    items = {}
    for job in content:
        link = f"{BASE}/recruits/{job['id']}"
        rr = job.get("recruitResponse") or {}
        company = (rr.get("company") or {}).get("name", "")
        place = " ".join(x for x in [rr.get("city"), rr.get("district")] if x)
        info = " · ".join(
            x for x in [company, place, pay_text(rr),
                        f"마감 {rr['deadline']}" if rr.get("deadline") else ""]
            if x
        )
        items[link] = f"{job.get('title', '')}\n{info}".strip()
    return items, True            # True = 구조 확인됨 (0건이어도 정상)

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


def main():
    cfg = load_config()
    url = build_url(cfg)
    print("검색 URL:", url)

    items, is_empty_page = fetch_items(url)

    if not items:
        if is_empty_page:
            print("현재 조건에 맞는 공고가 없습니다.")
        else:
            print("공고도, '검색결과가 존재하지 않습니다' 문구도 없습니다. "
                  "사이트 구조 변경이나 차단을 의심하세요.")
            sys.exit(1)

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