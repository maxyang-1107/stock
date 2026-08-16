# 台股/美股/日韓股 自動推播工具

每天固定時間,自動抓取你的自選股資訊(股價/漲跌幅/成交量、大盤指數、相關新聞),
透過 Telegram Bot 推播到你的手機。完全免費,靠 GitHub Actions 排程執行,
不需要自己的電腦或伺服器一直開機。

推播時間(可在 `.github/workflows/*.yml` 裡調整):

| 時間(台灣) | 內容 | 對應檔案 |
|---|---|---|
| 每天 22:00 | 台股今日收盤總結 + 大盤指數 + 新聞 | `night_tw.yml` |
| 每天 08:00 | 日韓龍頭股 + 日經/KOSPI 指數 | `jpkr_morning.yml` |
| 每天 09:00 | 美股收盤總結 + S&P500/那斯達克/道瓊 + 新聞 | `us_morning.yml` |
| 每週日 12:00 | 本週自選股新聞 + 三大法人/外資買賣超回顧 | `weekly_tw.yml` |

---

## Step 1. 申請 Telegram Bot(取代已停用的 LINE Notify)

1. 在 Telegram 搜尋 **@BotFather**,傳送 `/newbot`,依指示取得一組
   `TELEGRAM_BOT_TOKEN`(長得像 `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)。
2. 跟你剛建立的 Bot 對話視窗傳送任意一句話(例如「hi」),讓它知道有人跟它說話。
3. 用瀏覽器打開下面網址(把 `<TOKEN>` 換成你的 token):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   在回傳的 JSON 裡找到 `"chat":{"id": 數字, ...}`,這串數字就是你的
   `TELEGRAM_CHAT_ID`。

## Step 2. 建立 GitHub Repository

1. 到 GitHub 建立一個新的 repository(公開或私人都可以,公開的話 Actions 分鐘數無限制)。
2. 把這個資料夾裡的所有檔案上傳上去(或是用 `git push`)。

## Step 3. 設定 GitHub Secrets

到 repo 頁面 → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**,新增兩筆:

- `TELEGRAM_BOT_TOKEN`:剛剛申請到的 Bot Token
- `TELEGRAM_CHAT_ID`:剛剛查到的 Chat ID

## Step 4. 完成!

- 三個排程會依 `.github/workflows/` 裡設定的時間自動執行。
- 也可以到 repo 的 **Actions** 分頁,手動點 **Run workflow** 立刻測試,
  確認訊息有沒有正常送到 Telegram。

---

## 自訂追蹤清單

打開 `config.py`,可以直接增減股票:

- `TW_STOCKS`:台股,格式是 `"股票代號": "名稱"`,不用加 `.TW`
- `US_STOCKS`:美股代號清單(Yahoo Finance 格式,如 `NVDA`)
- `JP_STOCKS` / `KR_STOCKS`:日韓龍頭股,代號結尾要有 `.T`(日股)或 `.KS`(韓股)
- `INDICES`:大盤指數,一般不用改

> 截圖中的 `SPCX` 這個代號在 Yahoo Finance 查不到,先移除了,
> 你可以自行確認正確代號後補回 `US_STOCKS`。

## 關於「每週日本週回顧」的重要說明

這個功能會呼叫台灣證交所(TWSE)的公開資料 API,抓取每檔自選股本週的
三大法人(外資、投信、自營商)買賣超,以及大盤整體買賣超金額。

**2026-08-14 更新:已經用 web_fetch 實際打過一次 TWSE 正式 API 驗證欄位格式**,
過程中抓出並修正了 3 個問題:

1. TWSE 回傳的是**繁體中文**欄位名稱,舊版程式誤用簡體字比對,完全抓不到資料
2. `T86` 的 `selectType` 參數要用 `ALLBUT0999`(全部,不含權證/牛熊證),不是 `ALL`
3. `BFI82U` 正確路徑是 `https://www.twse.com.tw/fund/BFI82U`(不是 `/rwd/zh/fund/BFI82U`)

目前的欄位對應邏輯已經用真實抓到的資料驗證過(自己加總的外資+投信+自營商
= 官方公布的三大法人合計欄位,兩者完全一致),可信度比之前高很多。

不過還是有一個小提醒:`selectType=ALLBUT0999` 這個參數值是依照多篇第三方
技術文章及一個 GitHub 上的實際爬蟲專案交叉確認的,但受限於我這邊 fetch 工具
的快取行為,沒辦法用不同參數重新驗證同一個網址拿到不同結果來 100% 確認
「真的會回傳全部股票」。如果第一次執行時 Telegram 收到的三大法人資料
只有寥寥幾檔或明顯不齊全,把 Actions 的 log 貼給 Claude,可以馬上排查。

另外要注意:TWSE 的 T86 三大法人資料只涵蓋**上市(TWSE)股票**,如果你自選股
裡有上櫃(TPEx)的股票,會抓不到資料而顯示「可能為上櫃股」,這是正常現象,
不是程式壞掉——上櫃股票的三大法人資料需要另外串接 TPEx 的 API,目前版本
還沒有支援,之後有需要可以再擴充。

## 已知限制

- **資料來源**:股價來自 Yahoo Finance(`yfinance` 套件),屬於免費公開資料,
  偶爾會有延遲或短暫抓取失敗(程式會顯示「資料取得失敗」而不會整支程式中斷)。
- **排程精準度**:GitHub Actions 的 `schedule` 是儘量準時,但官方說明可能有
  幾分鐘到十幾分鐘的延遲,尤其在使用尖峰時段。
- **假日**:程式沒有自動判斷台股/美股/日韓股的休市日,遇到休市日還是會照樣執行,
  只是抓到的會是上一個交易日的收盤價。
- **新聞來源**:用 Google News RSS 搜尋,標題與連結由 Google 提供,程式不會
  重製新聞全文,只列標題和連結。

## 之後可以擴充的方向

- 加上技術指標(均線、RSI、KD)—— 可以用 `pandas` + `ta` 套件在抓到歷史股價後計算
- 加上基本面資料(本益比、殖利率、EPS)—— `yfinance` 的 `Ticker().info` 也有這些欄位
- 把統計資料存成 CSV/資料庫,累積每日紀錄做長期分析
