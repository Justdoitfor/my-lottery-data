# 彩票开奖数据仓库

自动抓取并维护双色球、超级大乐透的历史开奖数据。

## 数据文件

| 文件 | 说明 |
|------|------|
| `data/latest.json` | 最新一期快照，供前端优先读取 |
| `data/ssq.json` | 双色球全历史，最新在前 |
| `data/dlt.json` | 超级大乐透全历史，最新在前 |

## 数据来源

`datachart.500.com` HTML 历史数据表格，运营超过 10 年，格式稳定。

## 自动更新

GitHub Actions 每天 **北京时间 22:35** 自动触发（开奖约 21:30）。
有新数据时自动 commit，无新数据则静默跳过，不产生无效提交。

也可在 Actions 页面手动触发 `workflow_dispatch`。

## 数据格式

### latest.json
```json
{
  "updated_at": "2026-05-30T14:35:00Z",
  "lotteries": {
    "ssq": { "issue": "26060", "date": "2026-05-28", "red": ["07","09",...], "blue": ["11"] },
    "dlt": { "issue": "26062", "date": "2026-05-28", "front": ["05","11",...], "back": ["04","09"] }
  }
}
```

### ssq.json / dlt.json
```json
[
  { "issue": "26060", "date": "2026-05-28", "red": ["07","09","10","16","22","27"], "blue": ["11"] },
  ...
]
```

## 本地运行

```bash
pip install requests beautifulsoup4
python scripts/update.py        # 更新全部
python scripts/update.py ssq   # 仅双色球
python scripts/update.py dlt   # 仅大乐透
```
