import hashlib
import json
import re

import requests
from bs4 import BeautifulSoup

BASE = "https://www.jobkorea.co.kr"
LIST_URL = BASE + "/Recruit/Home/_GI_List/"

# '결과 없음' 화면의 문구 추정값(공백 제거 기준). 실제 화면을 확인한 뒤 맞춰야 함
EMPTY_MARKS = ("검색결과가없", "결과가없습니다", "조건에맞는공고가없")


def clean(s):
    return " ".join(s.split())


def fetch(cfg):
    payload = dict(cfg["payload"])
    sig = hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:12]

    r = requests.post(
        LIST_URL,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; okky-watch/1.0)",
            "Accept": "text/html, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE + "/recruit/joblist",
        },
        timeout=(10, 30),
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items = {}
    for tr in soup.select("tr.devloopArea"):
        gno = tr.get("data-gno")
        if not gno:
            continue
        a = tr.select_one("td.tplTit a.link")
        title = clean(a.get("title") or a.get_text()) if a else ""
        co = tr.select_one("td.tplCo a.link")
        company = clean(co.get_text()) if co else ""
        cells = [clean(c.get_text(" ")) for c in tr.select("td.tplTit p.etc span.cell")]
        cells = [c for c in cells if c]
        date = tr.select_one("td.odd span.date")
        deadline = clean(date.get_text()) if date else ""

        info = " · ".join(x for x in [company, *cells, deadline] if x)
        items[f"{BASE}/Recruit/GI_Read/{gno}"] = f"{title}\n{info}".strip()

    if items:
        return items, True, sig

    plain = re.sub(r"\s", "", soup.get_text())
    return {}, any(m in plain for m in EMPTY_MARKS), sig