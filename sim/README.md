# sim — 用本地 LLM 跑模擬來調參數

本地工具，**不會被部署**，後端也不會 import 它。目的只有一個：在 LLM 正常玩的前提下，
找出讓兩隊結束時差距最小的參數（兩隊初始代幣、各任務獎勵）。

```
sim/
  config.py      ← 你要調的所有參數都在這
  challenges.py  ← 每個任務要花多久、成功率多少
  network.py     ← 捷運網路／走路時間（直接讀 backend 的 seed 檔）
  engine.py      ← 一分鐘一分鐘跑的模擬引擎
  agent.py       ← LLM 玩家 ＋ 不用模型的貪婪基準玩家
  run.py         ← CLI
```

只用 Python 標準函式庫，不用裝任何套件。

## 跑起來

```bash
cd sim

# 先用貪婪基準玩家確認引擎正常（很快，不需要模型）
python3 run.py --games 20 --agent heuristic

# 接本地模型跑一場，並印出每一次的 prompt 跟回覆
python3 run.py --games 1 --agent llm --model qwen2.5:7b --verbose

# 掃初始代幣，找差距最小的設定
python3 run.py --games 10 --agent heuristic --sweep-start-chips 30,40,50,60

# 看完整的逐分鐘過程
python3 run.py --games 1 --minutes 60 --transcript
```

接 Ollama 或 LM Studio 都可以，兩邊都是 OpenAI 相容介面，只差網址跟模型名稱：

| | `--base-url` | `--model` |
|---|---|---|
| Ollama | `http://localhost:11434/v1`（預設） | `qwen2.5:7b` 之類 |
| LM Studio | `http://localhost:1234/v1` | 介面上載入的那個名字 |

模型連不上或回了看不懂的東西時，那一步會自動退回貪婪玩家而不是整場掛掉。

## 模擬的規則

**移動**（`config.py`）：站間行駛 2 分、等車 2 分、轉乘額外 +2 分走路 +2 分等車。
平行轉乘站（`CROSS_PLATFORM_TRANSFERS`）省掉走路那 2 分。
下車走去任務地點是用實際座標算直線距離 × 1.3 繞路係數 ÷ 80 公尺/分。

**任務**：LLM 不會真的去「玩」任務，只決定要不要走過去、以及 call your shot 要喊多少。
實際花多少時間、成功與否，是由 `challenges.py` 的 profile 抽樣決定的。

**決策點**：每當一隊閒下來（到站、走到了、任務做完），引擎就把當下狀態和一份
合法動作清單丟給模型，請它回一個 JSON：
```json
{"option": 2, "amount": 3, "call": 40, "notes": "先把南邊的站吃完再往北"}
```
`notes` 不會被解析，純粹讓它自己寫策略筆記，下一輪會回傳給它看。

**計分**：跟線上一樣，先比車站數再比代幣（`game_logic.get_ranking` 的排序）。

## 調參數的順序

1. **先修 `challenges.py` 的 profile**。裡面的時間和成功率目前是我估的——時間是照
   各任務寫的時限加上來回折騰，成功率是純粹的判斷。這些數字錯了，後面調什麼都是白調。
2. **再掃初始代幣**：`--sweep-start-chips`。
3. **最後調個別任務獎勵**：改 `config.py` 的 `challenge_reward_overrides`，
   例如 `{"西門町任務": {"chips": 60}}`，不用動 `seed_challenges.py`。

## 已知的簡化

- 任務池預設全部開放（`all_challenges_active`），不模擬 3 個起始＋補充的節奏——
  這樣雜訊小很多，也剛好對應你加的「上架所有任務」按鈕。
- call your shot 的數字是在「決定要走過去」時就喊，不是抵達後才喊，省一次模型呼叫。
- 偷竊任務固定偷代幣最多的對手（只有兩隊，所以就是對方）。
- 沒有模擬通行費、負餘額、午休時段。
- 一個任務成功後就下架，失敗則對手還能挑戰（跟線上規則一致），但沒有模擬
  「所有隊都失敗後才下架」的細節。

`CROSS_PLATFORM_TRANSFERS` 那份清單請你確認一下，我不確定每一站都對，而它每用到一次
就少算 2 分鐘。
