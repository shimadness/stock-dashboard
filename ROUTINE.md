# デイリー株価ルーティン 手順書（クラウドエージェント用）

このリポジトリは AI サプライチェーン関連 73 社の株価ダッシュボード。
毎朝 7:00 JST にクラウドルーティンがこの手順を実行し、GitHub Pages
（https://shimadness.github.io/stock-dashboard/）を更新する。

あなた（エージェント）の仕事は **価格更新 → 分析レポート作成 → AIの見解の採点と宣言 → push** の 4 つ。
`watchlist.json` は絶対に編集しない（銘柄の追加・削除はオーナーがチャットで判断する）。

## 0. 前提
- 外部ライブラリは不要。Python 3 標準ライブラリのみ。
- 日付は **JST** を使う: `TZ=Asia/Tokyo date +%F`
- 作業ブランチは `main`。直接 commit & push する（PR は作らない）。

## 1. 価格更新
```bash
git pull --rebase origin main
python3 scripts/fetch_prices.py
```
- `data/latest.json` と `data/history.json` が更新される。
- stderr に `done: 73 items, N errors` と出る。N が 10 を超えたら 1 回だけ再実行する。それでも失敗した銘柄は `stale: true` のまま進めてよい（レポート内で触れる）。

## 2. 文脈を読む
- `watchlist.json` … 業界分類と銘柄。`core: true` はオーナーが最初に指定した 3 社（NVDA / AKAM / NET）。
- `data/latest.json` … 全銘柄の終値・騰落率（1d/5d/1m/3m/ytd）・52 週高値比。
- `data/reports/index.json` と直近 7 日分の `data/reports/YYYY-MM-DD.json` … 過去レポート。**過去 14 日以内に提案した企業は再提案しない。**

## 3. 調べる（WebSearch を使う・最大 8 回まで）
優先順位:
1. 1 日騰落率が ±4% を超えた銘柄の理由（決算、ガイダンス、規制、大型契約など）
2. 業界全体が同方向に ±2% 以上動いた場合のマクロ要因（金利、関税、輸出規制など）
3. core 3 社（NVDA / AKAM / NET）に関するニュース
4. 今日〜数日内の決算発表・イベント予定

曜日による変化（JST の曜日）:
- **火〜土**: 通常の日次レポート（前日の米国引け＋同日のアジア引けを対象）
- **日**: 「今週の振り返り」。5 日騰落率を中心に、週の勝ち組・負け組と理由。
- **月**: 「今週の注目」。今週の決算発表・経済指標・イベントを調べて列挙。1 日騰落率の解説は不要。

## 3.5 AIの見解（強気/弱気の宣言と自己採点）
オーナーの目的は「AI に売買の提案を任せてよいかの判断材料を集めること」。
そのため毎日、銘柄ごとの見解を宣言し、期限が来たら **スクリプトが機械的に採点** する。あなたが自分の成績を手で書き換えることはない。

```bash
python3 scripts/calls.py evaluate   # 期限が来た見解を閉じ、data/scorecard.json を更新
python3 scripts/calls.py list       # 進行中の見解と直近の判定結果を表示
```
その後、今日の調査結果をもとに **0〜2 件** の新しい見解を宣言する:
```bash
python3 scripts/calls.py add --ticker NVDA --stance bull --horizon 20 --confidence 2 \
  --thesis "なぜそう考えるか。今日のニュース・データ・決算予定に紐づけた具体的な理由を 1〜3 文。" \
  --invalidation "この見解を撤回すべき条件（例: 決算でガイダンス未達、◯◯ドル割れ）"
```
ルール:
- `--ticker` は `watchlist.json` にある銘柄のみ。`--stance` は `bull` / `bear`。`--horizon` は営業日で `10` / `20` / `60`。`--confidence` は 1〜3。
- 同じ銘柄に進行中の見解がある間は再宣言しない（スクリプトが拒否する）。進行中は最大 8 件。
- 強気ばかりにしない。弱気も根拠があれば宣言する。確信が持てない日は 0 件でよい。
- thesis は「上がりそう」ではなく、**何がいつ起きると株価が動くか** の機構を書く。採点は終値で機械的に行われるので、決算日や発表日が horizon 内に入るように選ぶ。
- 採点ルール（scripts/calls.py）: 期限の終値が基準比 ±1% 以上なら方向で的中/外れ、それ未満は横ばい。市場比はウォッチリスト全銘柄の同期間平均との差。
- **日曜（weekly）** はレポートの `ai_review` に、その週に判定が出た見解の振り返りを 2〜4 文で書く。外れた理由を正直に書く（「読みが甘かった点」「見落とした材料」）。的中しても偶然なら偶然と書く。

## 4. レポートを書く
`data/reports/YYYY-MM-DD.json`（JST の今日の日付）を **以下のスキーマどおり** に書く。
```json
{
  "date": "2026-10-27",
  "kind": "daily",
  "headline": "半導体が反発、Cloudflareは決算前に軟調",
  "market_summary": "3〜5 文。全体の地合い→目立った業界→core 3社の順に。",
  "movers": [
    {"ticker": "NVDA", "direction": "up", "comment": "理由を 1〜2 文で。数字は本文に書かず理由と文脈を書く。"}
  ],
  "sector_notes": [
    {"sector": "semi", "note": "業界単位での 1〜2 文。動きがない業界は省略してよい。"}
  ],
  "suggestions": [
    {"name": "企業名", "ticker": "TICKER", "sector": "既存 sector id または新規ラベル", "reason": "なぜ今チェックすべきか。今日のニュースやデータに紐づけて 1〜2 文。"}
  ],
  "watch_next": ["明日以降に見るべきイベントや数字を 2〜4 個"],
  "ai_review": "日曜のみ。今週判定が出た見解の振り返り 2〜4 文。平日は省略するか空文字。",
  "data_quality": "取得失敗があれば銘柄名。なければ \"ok\""
}
```
- `kind` は `daily` / `weekly` / `week_ahead` のいずれか。
- `movers` は 3〜8 件。`direction` は `up` / `down`。
- `suggestions` は **1〜3 件**。条件: `watchlist.json` に無い企業、過去 14 日に提案していない企業、理由が今日の出来事かデータに紐づいている。思いつかない日は空配列でよい。
- 文章はすべて日本語。簡潔で断定調。「〜と思われます」「〜かもしれません」は使わない。推測は「〜との報道」「〜と市場は見ている」と出所を添える。
- 数字（株価・騰落率）はダッシュボードの表が示すので本文で繰り返さない。本文は「なぜ」と「次に何を見るか」に集中する。

## 5. インデックス更新と push
```bash
python3 scripts/build_index.py
git add data/
git commit -m "daily: $(TZ=Asia/Tokyo date +%F)"
git push origin main
```
push が reject されたら `git pull --rebase origin main` して再 push。

## 6. 完了報告
最後に 4 行以内で: 取得件数とエラー数 / レポートの headline / 提案した企業名 / 宣言した見解（銘柄・強弱・期間）と判定が出た見解の結果。
ダッシュボード URL: https://shimadness.github.io/stock-dashboard/
