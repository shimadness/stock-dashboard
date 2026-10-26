# AI Stock Watch

AI サプライチェーン関連 61 社（米国・日本・韓国・香港）の株価を業界別に追う日次ダッシュボード。

- ダッシュボード: https://shimadness.github.io/stock-dashboard/
- 更新: 毎朝 7:00 JST、Claude Code のクラウドルーティンが [ROUTINE.md](ROUTINE.md) の手順で自動実行
- データ: Yahoo Finance（終値ベース）

## 構成
| パス | 役割 |
|---|---|
| `watchlist.json` | 銘柄と業界分類。**オーナーのみ編集**（ルーティンは触らない） |
| `scripts/fetch_prices.py` | 全銘柄の 1 年分の終値を取得し `data/latest.json` / `data/history.json` を生成 |
| `scripts/build_index.py` | `data/reports/index.json` を再生成 |
| `data/reports/YYYY-MM-DD.json` | ルーティンが書く日次レポート（動向・注目銘柄・チェック候補の提案） |
| `index.html` | ダッシュボード本体（静的・依存なし） |

## 手元で動かす
```bash
python3 scripts/fetch_prices.py
python3 -m http.server 8787   # http://localhost:8787
```

## 銘柄を追加する
`watchlist.json` の `companies` に `{"ticker","name","sector","market"}` を追記して push するだけ。次回ルーティンから反映される。
