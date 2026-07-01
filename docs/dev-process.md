# ACVP 驗證平台 — Server / Client 開發流程與 Checklist

> 適用範圍：CAVP 產學合作計劃（FIPS 203 / 204）中，**我們這組負責的 server-client 部分**。
> 不含 FIPS 203（ML-KEM 密碼）與 FIPS 204（ML-DSA 密碼）的演算法實作——那是另外兩組。
> 時程：10 個單週 sprint，2026/06/22 – 08/28。
> 貼進 Notion 後：`- [ ]` 會變成 to-do 方塊、表格會變表格、`>` 會變 callout。

---

## ★ 本階段優先指令（2026/06 更新 — 最新共識，優先於下方 §10 排程）

> 經與教授及三組討論定案：**先把完整的 ACVP 流程建到 spec-faithful，並留好 203/204 的接點；等他們交付 gen-val 後直接插上、整條跑起來。** 本段為當前第一優先，順序高於 §10 的原始 sprint。

### 角色定位（務必先懂）
- **Server（我們）= 出考卷 + 改考卷**：產生/發放向量、握有標準答案、驗證 client 送回的答案。
- **Client / DUT = 算考卷**：被驗證的密碼實作，對著向量算出答案。
- **203/204 的 gen-val 插在 server 側的 `app/crypto_boundary/`**（出題＋改考卷的密碼學）。目前用 `tests/fixtures/nist` 當替身，整條流程現在就能跑；真模組到位後只換 boundary 後面，流程與端點不動。

### 完整流程（依 NIST messaging 規格，client ↔ server）
1. `POST /login` → 拿 JWT，之後每請求帶 `Authorization: Bearer`。
2. `POST /testSessions`（**註冊**：宣告要測的演算法）→ 回 session URL + `vectorSetUrls` + `accessToken`。
3. `GET /testSessions/{id}/vectorSets/{vsId}`（**取考卷**）→ 回向量；**若還沒生好，回 `{"vsId":N,"retry":30}`，client 等 N 秒再取**。
4. `POST .../vectorSets/{vsId}/results`（**送答案**）→ **只回 HTTP 狀態碼，不含對錯**。
5. `GET .../vectorSets/{vsId}/results`（**拉結果 / disposition**）→ 回逐 test case 結果。
6. `GET /testSessions/{id}/results` → session 層總表（`passed` + 每個 vectorSet 的 status）。
7. `PUT /testSessions/{id}`（**認證 certify**）→ 回 request id；再 `GET /requests/{id}` 取 validation id。

### 三個最容易建錯的點（規格明文，務必照做）
- **結果是「client 去拉」不是「server 推」**：送完答案要再發 GET 才拿得到分數。
- **送答案只回 HTTP status（no-content）**：disposition 要用另一個 GET 取。
- **取考卷也是非同步**：server 來不及生考卷時回 `retry`，這跟結果輪詢是**兩個不同的輪詢點**，都要做。

### disposition 七種狀態（結果畫面要能顯示，不是只有過/不過）
`passed` / `failed` / `incomplete`（驗證中，尚無錯）/ `unreceived` / `missing` / `expired` / `error`。

### 本階段要補齊的（在現有 scaffold 上往下長，優先做這些）
- [ ] **取考卷的 `retry` 路徑**：未生好回 `{vsId, retry:N}`。
- [ ] **disposition 完整七狀態**（含 `incomplete` 部分完成、`expired`、`error`）。
- [ ] **session 層結果總表** `GET /testSessions/{id}/results`。
- [ ] **`isSample` 流程**：建 session 帶 `isSample:true` 時，`GET .../expected` 回標準答案（正式驗證不給）。
- [ ] **認證收尾** `PUT /testSessions/{id}`（綁 module/OE，回 request id）。
- [ ] **失敗重送** `PUT .../results`（整個 vectorSet 重送）。
- [ ] **次要**：paging（清單分頁）、`POST /large`（可延後）。

### 已知現況（2026/06）
- **ML-KEM（203 組）語言已確定：C#/.NET 10**（內建 `System.Security.Cryptography.MLKem`）。⚠️ **macOS 不支援 ML-KEM**，他們的模組需在 **Linux / Docker** 跑；對我們無影響（仍經 JSON 行程邊界），但整合測試環境要備 Docker。
- **ML-DSA（204 組）語言**：尚未確認（.NET 的 ML-DSA 仍 experimental）。
- **接點機制已對齊**：203/204 用 **stdin 收 JSON prompt → stdout 吐 JSON response** 的 CLI，由 `SUT_COMMAND` 環境變數指定執行檔。
- ⚠️ **待釘合約風險**：ML-KEM 的 encapsulation / keyCheck 方向，.NET 原生 API 無法注入隨機數 `m`，KAT 受限——列為 M3「全模式」的風險。

---

## 0. 範圍與責任邊界（先讀這段）

我們做的是 ACVP 的**協定層 + 前端 client**，是**演算法無關**的。密碼數學切給 203/204。

| 我們負責（server-client） | 不負責（203 / 204） |
| --- | --- |
| HTTP 端點、路由、REST 語意 | ML-KEM / ML-DSA 的 keyGen / encap / sign 等運算 |
| 登入 / JWT 認證 | 測試向量的密碼學產生（真正的數學） |
| testSession / vectorSet 生命週期與狀態機 | response 正確性的密碼學比對 |
| 非同步 request-retry 輪詢 | — |
| prompt / response / validation 的 JSON 信封 | prompt / validation 的**演算法欄位內容** |
| 全部前端 client（SPA、流程 UI、UX） | — |
| Docker 封裝、英文使用手冊 | — |

> **黃金原則**：203/204 用什麼語言交付，對我們必須透明。我們透過「JSON 進、JSON 出」的行程邊界呼叫他們，而不是 import。如果他們的語言會卡住我們，代表介面切錯了。

---

## 1. 技術選型（決議）

### 後端
- [ ] 框架：**FastAPI**（async 原生，對映 request-retry 輪詢；Pydantic 直接做 ACVP JSON schema 驗證）
- [ ] 資料驗證：**Pydantic v2**（registration / prompt / response / validation 全部建模）
- [ ] ASGI server：**uvicorn**
- [ ] 認證：**PyJWT**（HS256，**不可用 `alg:none`**）
- [ ] 非同步任務佇列：**arq**（async 原生，跑 generate / validate 慢工作）；備案 Celery / RQ
- [ ] DB：prototype 用 **SQLite**，正式用 **PostgreSQL**（存 session / vectorSet 狀態）

### 前端
- [ ] 框架：**React + Vite + TypeScript**
- [ ] 資料抓取 / 輪詢：**TanStack Query**（內建 polling，對映 `GET /requests/{id}`）
- [ ] UI：**Tailwind + 元件庫**（shadcn/ui 或 Mantine）

### 前後端綜效
- [ ] FastAPI 自動產生 OpenAPI → 用 **openapi-typescript** 生成前端 TS 型別，前後端共用同一份 schema 真相

> **語言現況**：ML-KEM（203 組）已確定用 **C#/.NET 10**；ML-DSA（204 組）未定。**對我們無影響**——兩者都經「JSON 進、JSON 出」的行程邊界呼叫（`SUT_COMMAND` 指定執行檔），語言對我們透明。我們維持 FastAPI，不因對方語言改棧。**這也不阻塞我們開工**（見 §3 stub-first，用 NIST fixtures 當替身）。

---

## 2. 架構原則

- [ ] **REST 不是選項，是規格**：端點、HTTP 動詞、resource URI 全照 `draft-fussell-acvp-spec`
- [ ] **只做 Server/Client，不做 Proxy**
- [ ] **realtime 與 not-realtime 共用同一套端點**；差別主要在 client 側 + 兩個機制：
  - [ ] not-realtime 需要 vectorSet 過期處理（`status: expired`）
  - [ ] not-realtime 的輪詢視窗要能撐長時間離線
- [ ] **stub-first 開發**：後端先用 NIST `gen-val/json-files` 的固定 JSON 當測試樁，不等 203/204
- [ ] **行程邊界整合**：203/204 = 語言無關黑盒，經 JSON 呼叫
- [ ] **訊息信封格式**：每則 ACVP 訊息是陣列，第一元素是版本物件
  ```json
  [
    {"acvVersion": "1.0"},
    { "...payload..." }
  ]
  ```
- [ ] **版本釘選**：建在 ACVP version 1.0 + 某個 master 快照，專案進行中不追草案改版

---

## 3. 對 203/204 的介面合約（I0 的交付物，W2 定版）

我們交給他們的不是「請問你們用什麼語言」，而是這份規格：請實作兩個操作，輸入輸出照 NIST `json-files` 的 schema。

| 操作 | 輸入 | 輸出 |
| --- | --- | --- |
| **generate** | algorithm / mode / parameterSet（registration 能力） | `prompt`（測試案例）＋ 內部正解（`internalProjection` / `expectedResults`） |
| **validate** | `prompt` ＋ client 的 `response` | `validation`（逐 test case 的 pass/fail / disposition） |

包裝形式（兩階段，JSON 合約不變）：
- [ ] 階段一：**CLI / subprocess**（`genval generate < in.json > prompt.json`）——任何語言都能做，門檻最低
- [ ] 階段二（需要時）：升級成 **HTTP 小服務**（`POST /generate`、`POST /validate`），arq worker 改呼叫即可

合約定版 checklist：
- [ ] 確定 generate 的輸入欄位（對齊各演算法 `registration.json`）
- [ ] 確定 prompt 輸出 schema（對齊 `prompt.json`）
- [ ] 確定 validate 輸入（prompt + response）與輸出 schema（對齊 `validation.json`）
- [ ] 約定錯誤回報格式（演算法不支援 / 參數非法 / 內部錯誤）
- [ ] 約定以 **NIST 範例檔當驗收**：餵 NIST `prompt` → 必須重現 NIST `expectedResults` / `validation`
- [ ] 三方在 kickoff 會議簽署這份合約

---

## 4. 端點 Checklist（依 `draft-fussell-acvp-spec`）

### 核心（MVP 必做）
- [ ] `POST /login`（initial：password → JWT；renewal：password + 舊 JWT → 新 JWT）
- [ ] `POST /testSessions`（建立 session、解析 registration 能力）
- [ ] `GET /testSessions/{id}`（session 資訊：createdOn / expiresOn / vectorSetsUrl / passed…）
- [ ] `GET /testSessions/{id}/vectorSets`（列出此 session 的 vectorSet）
- [ ] `GET /testSessions/{id}/vectorSets/{vsId}`（發 prompt 給 client）
- [ ] `POST /testSessions/{id}/vectorSets/{vsId}/results`（收 client 的 response）
- [ ] `GET /testSessions/{id}/vectorSets/{vsId}/results`（回 validation / disposition）
- [ ] `PUT /testSessions/{id}`（送驗證 / certify test session）
- [ ] `GET /testSessions/{id}/results`（整個 session 的 disposition）
- [ ] `GET /requests/{requestId}`（非同步 request-retry 輪詢）
- [ ] `GET /algorithms`（列出 server 支援哪些演算法 / mode / revision）

### 次要（時間允許）
- [ ] `GET /testSessions/{id}/vectorSets/{vsId}/expected`（sample 模式取得正解）
- [ ] `PUT /testSessions/{id}/vectorSets/{vsId}/results`（失敗後重送整個 vectorSet）
- [ ] metadata 群（prototype 可先 stub）：`/vendors`、`/persons`、`/oes`、`/modules`、`/dependencies`

### 可延後
- [ ] `POST /large`（large submission；ML-KEM/ML-DSA 向量不大，初版 `largeEndpointRequired=false` 跳過）

---

## 5. 協定機制 Checklist

### 認證 / JWT
- [ ] JWT 用 **HS256**（header `alg:HS256`、`typ:JWT`），secret 妥善管理
- [ ] payload 含 `iss` / `nbf` / `exp` / `iat`（過期時間要設）
- [ ] 後續請求帶 `Authorization: Bearer <JWT>`
- [ ] 中介層驗 JWT（簽章、過期、nbf）
- [ ] JWT 過期 → renewal 流程（帶舊 JWT 換新）
- [ ] **絕不在 log / 錯誤訊息印出 JWT 或 secret**

### 非同步 request-retry
- [ ] 慢工作（generate / validate）走任務佇列，POST 立即回 requestId
- [ ] client `GET /requests/{id}`：未完成回「retry」、完成回資源 URL
- [ ] 狀態機：`processing` → `approved` / `rejected` / `error`
- [ ] 設定合理的 retry-after 與逾時
- [ ] **取考卷也要 retry**：`GET vectorSets/{vsId}` 在向量還沒生好時回 `{"vsId":N,"retry":N秒}`（與上面的結果輪詢是兩個獨立輪詢點）

### vectorSet 生命週期與 disposition
- [ ] 狀態：`created` → `prompt 已取` → `response 已交` → `disposition` → `certified`
- [ ] 過期判定：`GET vectorSets/{id}` 過期時回 `{"vsId":N,"status":"expired"}`
- [ ] **disposition 七狀態都要支援**：`passed` / `failed` / `incomplete` / `unreceived` / `missing` / `expired` / `error`
- [ ] **送答案 `POST .../results` 回 no-content（只 HTTP status）；分數由 `GET .../results` 拉**
- [ ] **結果是 client 主動拉，不是 server 推**
- [ ] not-realtime 場景的長離線輪詢測過

### 信封 / 版本
- [ ] 每則請求 / 回應都帶 `[{"acvVersion":...}, {payload}]` 結構
- [ ] 版本不符的請求要拒絕並回明確錯誤

### 錯誤處理
- [ ] 401 未認證 / JWT 失效
- [ ] 400 schema 驗證失敗（Pydantic 錯誤轉成 ACVP 格式）
- [ ] 404 資源不存在
- [ ] 409 / 422 狀態機非法轉換
- [ ] 一致的錯誤回應格式

---

## 6. 前端 client Checklist

- [ ] SPA 骨架（路由、版面、狀態管理）
- [ ] 設計系統 / 元件庫接好
- [ ] 登入畫面（password → 取 JWT，存於記憶體 / 安全儲存）
- [ ] JWT 自動續期（過期前 renewal）
- [ ] 核心流程 UI：
  - [ ] 選演算法 / mode / parameterSet（產生 registration）
  - [ ] 建立 test session
  - [ ] 輪詢 vectorSet 就緒（TanStack Query polling）
  - [ ] 下載 / 顯示 prompt
  - [ ] realtime：觸發後端呼叫 crypto module；not-realtime：下載向量、離線處理、上傳 response
  - [ ] 上傳 response
  - [ ] 輪詢並顯示 validation 結果（逐 test case pass/fail）
  - [ ] 送出 session 驗證（certify）
- [ ] 結果 / 報告畫面（disposition、pass/fail 統計、可匯出）
- [ ] 錯誤訊息（非專家看得懂、可操作）
- [ ] UX 打磨（loading / 空狀態 / 過期提示）
- [ ] **非專家可獨立操作**驗證（找非工程背景的人實測一遍）

> **觀念對齊**：realtime 下密碼不在瀏覽器跑。crypto module（203/204）在伺服器端或獨立行程，client 是控制台 + 檔案上下傳。

---

## 7. 整合與測試 Checklist

- [ ] 用 NIST `json-files` 當 stub，後端全流程先跑通（不等 203/204）
- [ ] 單元測試：每個端點、Pydantic 模型、JWT 中介層
- [ ] 整合測試：login → session → vectorSet → result → validation 全鏈
- [ ] **黃金向量驗收**：餵 NIST `prompt` 給 203/204 模組 → 輸出須重現 NIST `expectedResults` / `validation`
- [ ] realtime 全鏈端到端測試
- [ ] not-realtime（含過期）端到端測試
- [ ] 五種 mode 覆蓋：ML-KEM keyGen / encapDecap、ML-DSA keyGen / sigGen / sigVer
- [ ] 前端端到端（瀏覽器跑完整流程）
- [ ] 與真實 client 互通測試（選做：libacvp，確認 HTTP 狀態碼 / retry 格式對齊）

---

## 8. 安全 Checklist

- [ ] TLS（建議）作為傳輸層
- [ ] JWT 用 HS256，**禁用 `alg:none`**
- [ ] secret / token 不進 log、不進 URL query string
- [ ] 輸入全經 Pydantic 驗證（拒絕未知 / 超大 payload）
- [ ] 認證失敗給明確但不洩漏資訊的回應
- [ ] DB 存取參數化（防注入）
- [ ] CORS 設定（前端網域）

---

## 9. 封裝與交付 Checklist

- [ ] 後端 Dockerfile（含 uvicorn / arq worker）
- [ ] 前端 Dockerfile / 靜態建置
- [ ] docker-compose（server + worker + DB + 前端 + 203/204 stub）
- [ ] `.env` 範例 / 設定文件
- [ ] **英文使用手冊**（安裝、啟動、跑一輪驗證的步驟）
- [ ] API 文件（FastAPI 自動 OpenAPI 匯出）
- [ ] README（架構圖、模組邊界、對 203/204 的合約連結）
- [ ] 自裝包交付 + 簽核

---

## 10. Sprint 計劃（10 週，對映甘特圖）

> 後端 stub-first，所以 W1–W4 不依賴 203/204。★ = 依賴另外兩組交付。

### Sprint 1（W1, 06/22）— 地基
- [ ] B0 Server 骨架：FastAPI + 路由 + DB + JWT login
- [ ] 環境 / repo / CI 建好

### Sprint 2（W2, 06/29）— 信封 + 合約
- [ ] B1 `POST /testSessions` + registration 解析 + 信封
- [ ] **I0 介面合約定版（與 203/204）★ 最優先**
- **里程碑 M1：協定骨架 + login 打通**

### Sprint 3（W3, 07/06）— vectorSet 端點
- [ ] B2 `vectorSets` / `results` 端點 + 接 NIST stub 向量
- [ ] F0 設計系統 + 線框 + SPA 骨架（W3–W4）

### Sprint 4（W4, 07/13）— 非同步
- [ ] B3 非同步 request-retry 輪詢 + vsId 狀態機 + 過期
- [ ] F0 續
- **里程碑 M2：stub 全流程跑通（login→session→vectorSet→result→validation）**

### Sprint 5（W5, 07/20）— 強化 + 前端核心
- [ ] B4 錯誤碼 + 安全強化（TLS / JWT）
- [ ] F1 核心流程 UI（選→產生→下載→上傳→結果）（W5–W6）
- [ ] I1 端到端整合測試（NIST 範例向量 golden）

### Sprint 6（W6, 07/27）— 接真模組
- [ ] B5 接 203/204 真模組 + 全 5 模式 ★（W6–W7）
- [ ] F1 續

### Sprint 7（W7, 08/03）— 端到端
- [ ] B5 續
- [ ] F2 前端端到端接後端全模式
- **里程碑 M3：後端全模式（真模組）驗證 ★**
- **里程碑 M4：瀏覽器端到端跑通**

### Sprint 8（W8, 08/10）— UX + 封裝起頭
- [ ] F3 UX 打磨 + 報告 + 錯誤訊息
- [ ] I2 Docker 封裝 + 英文手冊（W8–W9）
- **里程碑 M5：非專家可獨立操作**

### Sprint 9（W9, 08/17）— 封裝 + 驗收
- [ ] I2 續
- [ ] I3 UAT + 驗收 + 修 bug（W9–W10）

### Sprint 10（W10, 08/24）— 交付
- [ ] I3 續
- [ ] 自裝包交付 + 簽核
- **里程碑 M6：自裝包交付 + 簽核**

---

## 11. 里程碑驗收標準（Definition of Done）

| 里程碑 | 完成定義 |
| --- | --- |
| M1 | 能 `POST /login` 取得有效 JWT，帶 Bearer 通過認證中介層 |
| M2 | 用 NIST stub，client 能跑完 login→建 session→取 prompt→交 response→收 validation 全鏈 |
| M3 | 後端接上 203/204 真模組，5 種 mode 都能重現 NIST 黃金向量結果 ★ |
| M4 | 在瀏覽器用前端 client 完成一次完整 realtime 驗證 |
| M5 | 非工程背景者依英文手冊獨立跑完一輪驗證 |
| M6 | docker-compose 一鍵起，文件齊全，三方簽核 |

---

## 12. 風險 / 依賴登記

| 項目 | 風險 | 對策 |
| --- | --- | --- |
| 203/204 語言未定 | 可能拖延整合 | 行程邊界 + JSON 合約吸收掉；後端 stub-first 不等待 |
| 203/204 交付延遲 | B5 / M3 卡關 | W1–W4 全用 NIST stub；合約 W2 先定 |
| 草案改版 | 規格漂移 | 釘住 ACVP 1.0 + master 快照 |
| not-realtime 過期 | 離線久向量失效 | 實作 `status:expired` + 長輪詢視窗測試 |
| 與真實 client 互通 | HTTP 細節對不上 | 選做 libacvp 互通測試，及早發現 |
| JWT 安全 | `alg:none` 誤用 | 強制 HS256，code review 把關 |