import importlib
import json
import os
import sys
import traceback
from pathlib import Path

import requests

TOPIC = os.environ["NTFY_TOPIC"]
CONFIG_FILE = Path("config.json")
SEEN_DIR = Path("seen")

SOURCES = {            # 모듈 이름: 알림에 표시할 사이트 이름
    "okky": "OKKY",
    "jobkorea": "잡코리아",
}


def load_config():
    text = CONFIG_FILE.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    return json.loads("\n".join(lines))


def load_state(path):
    if not path.exists():
        return None, set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return None, set(data)
    return data.get("sig") or data.get("url"), set(data.get("seen", []))


def save_state(path, sig, seen):
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps({"sig": sig, "seen": sorted(seen)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def notify(label, title, link):
    requests.post(
        "https://ntfy.sh",
        json={
            "topic": TOPIC,
            "title": f"[{label}] 새 공고",
            "message": title[:300],
            "click": link,
            "priority": 4,
        },
        timeout=30,
    )


def run_source(name, label, scfg):
    mod = importlib.import_module(f"sources.{name}")
    items, ok, sig = mod.fetch(scfg)
    print(f"[{label}] 검색조건: {sig} | 수집 {len(items)}건")

    if not items and not ok:
        raise RuntimeError("공고도 없고 '결과 없음' 화면도 아닙니다. 구조 변경이나 차단 의심")
    if not items:
        print(f"[{label}] 현재 조건에 맞는 공고가 없습니다.")

    path = SEEN_DIR / f"{name}.json"
    saved_sig, seen = load_state(path)

    if saved_sig != sig:
        # 첫 실행이거나 검색 조건이 바뀐 경우: 알림 없이 기준선만 저장
        print(f"[{label}] 기준선 저장 (알림 없음): {len(items)}건")
        seen = set(items)
    else:
        for link, title in items.items():
            if link not in seen:
                notify(label, title, link)
                print(f"[{label}] 알림: {title.splitlines()[0]} {link}")
        seen |= set(items)

    save_state(path, sig, seen)


def main():
    cfg = load_config()
    errors = []
    for name, label in SOURCES.items():
        scfg = cfg.get(name)
        if not scfg or scfg.get("enabled", True) is False:
            continue
        try:
            run_source(name, label, scfg)
        except Exception:
            print(f"[{label}] 실패:")
            traceback.print_exc()
            errors.append(label)

    if errors:                       # 한 사이트가 실패해도 나머지는 끝까지 처리한 뒤 실패 표시
        print("실패한 사이트:", ", ".join(errors))
        sys.exit(1)


if __name__ == "__main__":
    main()