import json
from urllib.parse import urlencode

import requests

BASE = "https://jobs.okky.kr"


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


def fetch(cfg):
    """(공고 {링크: 설명}, 응답 구조 확인 여부, 검색조건 식별자)를 돌려준다."""
    url = build_url(cfg)
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
    text = r.content.decode("utf-8", errors="replace")

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
        return {}, False, url

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
    return items, True, url