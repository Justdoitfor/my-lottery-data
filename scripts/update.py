#!/usr/bin/env python3
"""
彩票历史开奖数据抓取脚本
数据源: datachart.500.com (HTML 表格)
支持: 双色球(ssq) / 超级大乐透(dlt)

用法:
  python scripts/update.py           # 更新全部
  python scripts/update.py ssq       # 仅更新双色球
  python scripts/update.py dlt       # 仅更新大乐透
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 路径 ──────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# ── 请求头（模拟浏览器，避免被拦截） ──────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer":         "https://www.500.com/",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ── 彩票配置 ──────────────────────────────────────────────────────
CONFIGS = {
    "ssq": {
        "name":        "双色球",
        "start_issue": "03001",   # 2003年第001期，有史以来第一期
        "url":         "https://datachart.500.com/ssq/history/newinc/history.php",
        "red_count":   6,
        "blue_count":  1,
        "red_range":   (1, 33),
        "blue_range":  (1, 16),
    },
    "dlt": {
        "name":        "超级大乐透",
        "start_issue": "07001",
        "url":         "https://datachart.500.com/dlt/history/newinc/history.php",
        "red_count":   5,
        "blue_count":  2,
        "red_range":   (1, 35),
        "blue_range":  (1, 12),
    },
}


# ── 工具函数 ──────────────────────────────────────────────────────
def current_end_issue() -> str:
    """本年度安全上限，格式 YYNNN，如 26200"""
    return f"{datetime.now().year % 100:02d}200"


def norm_ball(text: str) -> str:
    """提取数字并补零为两位，如 '7' → '07'"""
    v = re.sub(r"\D", "", text or "")
    if not v:
        raise ValueError(f"无法解析球号: {text!r}")
    return f"{int(v):02d}"


def validate_balls(values: list[str], lo: int, hi: int, label: str) -> None:
    nums = [int(v) for v in values]
    if len(nums) != len(set(nums)):
        raise ValueError(f"{label} 号码重复: {values}")
    for n in nums:
        if not (lo <= n <= hi):
            raise ValueError(f"{label} 号码超出范围 {lo}-{hi}: {n}")


# ── 抓取 HTML ─────────────────────────────────────────────────────
def fetch_html(cfg: dict, start: str, end: str) -> str:
    url    = cfg["url"]
    params = {"start": start, "end": end}
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=40)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            if "tdata" not in resp.text:
                raise RuntimeError("响应中未找到 tbody#tdata")
            return resp.text
        except Exception as e:
            print(f"  [第{attempt}次] 请求失败: {e}", file=sys.stderr)
            if attempt < 3:
                time.sleep(3 * attempt)
    raise RuntimeError(f"连续 3 次请求失败: {url}")


# ── 解析 HTML 表格 ────────────────────────────────────────────────
def parse_rows(code: str, cfg: dict, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tbody#tdata tr")
    if not rows:
        raise RuntimeError(f"{code}: 未解析到任何数据行")

    records = []
    for row in rows:
        cols = [td.get_text(strip=True).replace("\xa0", "")
                for td in row.select("td")]
        if not cols:
            continue

        issue = cols[0]
        if not re.fullmatch(r"\d{5}", issue):  # 期次必须是5位数字
            continue

        date = cols[-1]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue

        try:
            if code == "ssq":
                if len(cols) < 8:
                    continue
                red  = [norm_ball(v) for v in cols[1:7]]
                blue = [norm_ball(cols[7])]
                validate_balls(red,  *cfg["red_range"],  "ssq红球")
                validate_balls(blue, *cfg["blue_range"], "ssq蓝球")
                records.append({"issue": issue, "date": date,
                                 "red": red, "blue": blue})

            elif code == "dlt":
                if len(cols) < 8:
                    continue
                front = [norm_ball(v) for v in cols[1:6]]
                back  = [norm_ball(v) for v in cols[6:8]]
                validate_balls(front, *cfg["red_range"],  "dlt前区")
                validate_balls(back,  *cfg["blue_range"], "dlt后区")
                records.append({"issue": issue, "date": date,
                                 "front": front, "back": back})
        except ValueError as e:
            print(f"  跳过期次 {issue}: {e}", file=sys.stderr)
            continue

    if not records:
        raise RuntimeError(f"{code}: 解析出 0 条有效记录")
    return records


# ── 合并（以期次去重） ─────────────────────────────────────────────
def merge(existing: list[dict], fresh: list[dict]) -> list[dict]:
    pool = {}
    for item in existing + fresh:
        issue = str(item.get("issue", "")).strip()
        if issue:
            pool[issue] = item
    return sorted(pool.values(), key=lambda x: int(x["issue"]), reverse=True)


# ── JSON 读写（原子写入，防止中途崩溃导致文件损坏） ───────────────
def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


# ── 更新单个彩票 ──────────────────────────────────────────────────
def update_one(code: str, end_issue: str) -> dict:
    cfg      = CONFIGS[code]
    out_path = DATA_DIR / f"{code}.json"

    print(f"\n[{code}] {cfg['name']} 抓取中 ({cfg['start_issue']} → {end_issue}) …")
    html     = fetch_html(cfg, cfg["start_issue"], end_issue)
    fresh    = parse_rows(code, cfg, html)
    existing = read_json(out_path)
    merged   = merge(existing, fresh)
    write_json(out_path, merged)

    latest = merged[0]
    new_cnt = len({r["issue"] for r in fresh} - {r.get("issue") for r in existing})
    print(f"  ✓ 新增 {new_cnt} 期，共 {len(merged)} 期，最新: {latest['issue']} ({latest['date']})")
    return {"code": code, "name": cfg["name"], "total": len(merged),
            "new": new_cnt, "latest": latest}


# ── 写 latest.json ────────────────────────────────────────────────
def write_latest(summaries: list[dict]) -> None:
    latest = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lotteries": {s["code"]: s["latest"] for s in summaries},
        "summary": [
            {"code": s["code"], "name": s["name"],
             "total": s["total"], "latest_issue": s["latest"]["issue"],
             "latest_date": s["latest"]["date"]}
            for s in summaries
        ],
    }
    write_json(DATA_DIR / "latest.json", latest)
    print(f"\n✓ latest.json 已更新")


# ── 入口 ──────────────────────────────────────────────────────────
def main() -> int:
    arg   = sys.argv[1] if len(sys.argv) > 1 else "all"
    codes = list(CONFIGS.keys()) if arg == "all" else [arg]

    for code in codes:
        if code not in CONFIGS:
            print(f"未知彩票代码: {code}，可用: {list(CONFIGS.keys())}", file=sys.stderr)
            return 1

    end_issue = current_end_issue()
    summaries = []
    for code in codes:
        try:
            summaries.append(update_one(code, end_issue))
        except Exception as e:
            print(f"[{code}] 失败: {e}", file=sys.stderr)
            return 1

    write_latest(summaries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
