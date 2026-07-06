# 協定層驗證補強 — 新增內容與規格出處（2026-07）

> 本文件補充說明 2026-07 在既有 scaffold 上新增的**協定層輸入驗證**,以及每項檢查所依據的
> 規格出處(NIST ACVP 規格文件與 ACVP-Server 範例向量)。原開發流程與 sprint 計劃見
> `dev-process.md`(本文件不取代它);協定守則見 `.claude/skills/acvp-protocol/SKILL.md`。

---

## 1. 本次新增了什麼

### 1.1 交卷(result submission)的結構驗證 — `POST/PUT .../vectorSets/{vsId}/results`

| 檢查 | 違反時 | 之前的行為 |
| --- | --- | --- |
| body 的 `vsId` 必須等於 URL 的 vectorSet id | 400 | 不檢查,照收 |
| 必須有 `testGroups` 陣列,每組帶整數 `tgId` 與 `tests` 陣列,每題帶整數 `tcId` | 400 | 不檢查,照收 |
| 交卷的 `tcId` 不得包含考卷(prompt)中不存在的題號 | 400 | 不檢查,照收 |
| 交卷缺考卷中的題號(答不完整) | 收下(200),disposition 判 **`missing`** | 一律 passed |

實作:`backend/app/api/vector_sets.py`(`_validate_submission`)、`backend/app/store.py`
(`missing_tc_ids`、`disposition()`)。

### 1.2 狀態機防呆

考卷尚未取得(vectorSet 仍在 `generating` 或 `ready`、prompt 從未被 GET)就交卷 →
**409 Conflict**。理由:client 不可能對一份沒拿到的考卷算出答案,此為非法狀態轉換
(對應 `dev-process.md` §5「409 / 422 狀態機非法轉換」checklist)。

### 1.3 註冊能力(registration capability)的 per-mode 驗證 — `POST /testSessions`

新增 `backend/app/models/registration.py`:五種 mode 各一個 Pydantic 模型,對
`algorithms[]` 中的每個能力聲明做完整 schema 驗證(`extra="forbid"`,未知欄位即拒):

| Mode | 必填欄位 | 值域 |
| --- | --- | --- |
| ML-KEM keyGen | `parameterSets` | ML-KEM-512 / 768 / 1024 |
| ML-KEM encapDecap | `parameterSets`、`functions` | functions: encapsulation / decapsulation / encapsulationKeyCheck / decapsulationKeyCheck |
| ML-DSA keyGen | `parameterSets` | ML-DSA-44 / 65 / 87 |
| ML-DSA sigGen | `capabilities`(parameterSets + messageLength(+hashAlgs、contextLength))、`deterministic`、`externalMu`、`signatureInterfaces`、`preHash` | signatureInterfaces: external / internal;preHash: pure / preHash;hashAlgs: SHA2/SHA3/SHAKE 家族 12 種 |
| ML-DSA sigVer | 同 sigGen 但無 `deterministic` | 同上 |

違反 → 400,錯誤訊息指出欄位路徑與原因(例:`capabilities.0.parameterSets.0: Input should be 'ML-DSA-44' ...`)。

### 1.4 能力下傳(為接真模組預留)

驗證通過的能力物件存於 `VectorSet.capabilities` — 這就是將來 crypto boundary
`generate()` 的輸入(203/204 gen-val 依能力出題)。**注意:目前 stub 的 `generate()`
尚未使用它**(仍回傳整份 NIST 考卷),真模組接上時才生效。

### 1.5 測試基礎設施

- `backend/tests/helpers.py`:`registration(mode)` / `golden_response(vsId, mode)` —
  從 NIST fixtures 產生合法的註冊與交卷 body。
- 新增 `backend/tests/test_registration.py`(17 測試)、
  `backend/tests/test_results_validation.py`(7 測試)。
- 既有測試與 `scripts/demo_flow.py` 全面改為提交**完整的 NIST 黃金答案**
  (不再是 `{"results": []}` 空卷)。測試數 47 → **71**。

---

## 2. 規格出處(我們依據什麼做這些檢查)

兩個 NIST repo 的分工:**usnistgov/ACVP** 是規格文件(格式的正式定義),
**usnistgov/ACVP-Server** 是 NIST 參考實作,其 `gen-val/json-files/` 範例檔是照規格產出
的具體實例 — 我們逐字 vendor 為 `tests/fixtures/nist/`(pin 於 commit `15c0f3d`,見
`tests/fixtures/nist/SOURCE.md`),作為測試的正向 oracle。

### 2.1 usnistgov/ACVP(https://pages.nist.gov/ACVP/)

**`draft-fussell-acvp-spec`(協定總規格)**

| 我們的實作 | 規格位置 |
| --- | --- |
| `[{"acvVersion"}, {payload}]` 訊息信封 | §10.2(login response 首次定義,全文件一致沿用) |
| `POST /testSessions` 註冊(algorithms 陣列) | §12.16.2 Create a New Test Session |
| `PUT /testSessions/{id}` 認證 | §12.16.4 Submit For Validation |
| `GET /requests/{id}` 狀態 `initial / processing / approved / rejected` | §12.7.2 Request Information |
| vectorSet 過期 | §14 Vector Set Expiration |
| 取考卷 retry、交卷 no-content、disposition 詞彙(passed / fail / incomplete / unreceived / missing / expired / error) | vectorSet 取得與 results 相關小節(§12.17.x);詳細訊息範例同時參照 ACVP-Server 的實際行為與範例檔 |
| large submission(未實作,已延後) | §13 Large Submission |

**`draft-celi-acvp-ml-kem`(ML-KEM JSON 子規格)** — 1.3 節註冊驗證的 ML-KEM 部分依據:

| 內容 | 規格位置 |
| --- | --- |
| 註冊屬性(`parameterSets`、`functions` 及其值域) | §7.3 ML-KEM Algorithm Registration Properties(Table 3),範例 §7.3.1–7.3.2 |
| 考卷結構(keyGen:`d`/`z`;encapDecap:`ek`/`m`/`c`…) | §8.1(Tables 5–6)、§8.2(Tables 7–8) |
| 答案結構(keyGen:`ek`/`dk`;encapDecap:`c`/`k`/`testPassed`) | §9 Test Vector Responses(Tables 9–13) |

**`draft-celi-acvp-ml-dsa`(ML-DSA JSON 子規格)** — 1.3 節的 ML-DSA 部分依據:

| 內容 | 規格位置 |
| --- | --- |
| keyGen 註冊屬性(`parameterSets`) | §7.3(範例 §7.3.1) |
| sigGen 註冊屬性(`capabilities`/`messageLength`/`hashAlgs`/`contextLength`/`deterministic`/`signatureInterfaces`/`preHash`/`externalMu`) | §7.4(範例 §7.4.1) |
| sigVer 註冊屬性(同上,無 deterministic) | §7.5(範例 §7.5.1) |
| 考卷結構(各 mode 的 testGroup / testCase schema) | §8.1–8.3 |
| 答案結構 | §9.1–9.3 |

### 2.2 usnistgov/ACVP-Server

- `gen-val/json-files/<MODE>/registration.json` — 各 mode 合法註冊的具體範例。
  **測試 `test_registration.py` 直接以這五份檔案為「必須被接受」的正向案例**;
  1.3 節模型的欄位與值域即由這些檔案與上述子規格對照建成。
- `gen-val/json-files/<MODE>/prompt.json` / `expectedResults.json` — 交卷結構驗證
  (1.1 節)比對的題號來源與合法交卷範例;`expectedResults` 同時是
  `golden_response()` 的答案來源。
- `gen-val/json-files/<MODE>/validation.json` — disposition 回應格式的實例。

> 通用欄位字彙(`vsId`/`tgId`/`tcId`/`testGroups`/`tests`)同見 usnistgov/ACVP 的
> `draft-vassilev-acvp-terminology`;本次實作以上述兩份演算法子規格與範例檔為準。

---

## 3. 已知仍為替身(stub)的部分 — 讀本文件時的邊界

1. **對答案是假的**:`crypto_boundary.validate()` 不看交卷內容,固定回傳 NIST
   `validation.json`(全 passed)。`failed` disposition 目前做不出來。真模組接上後,
   驗收標準為:餵 NIST `prompt` 必須重現 NIST `expectedResults`(黃金向量驗收,見
   `dev-process.md` §3)。
2. **能力尚未驅動出題**:註冊時縮小 `parameterSets` 不會讓考卷變小(1.4 節)。
3. **certify 的 `moduleUrl`/`oeUrl` 不核對**:metadata 資源(`/modules`、`/oes`)仍為
   空 stub,任何格式合法的 URL 都會被接受。
4. **過期無觸發機制**:`expiresOn` 有記錄,但沒有排程將 vectorSet 轉為 `expired`;
   該狀態目前僅能由測試手動設定。
5. **session 授權未隔離**:任何有效 JWT 可操作任何 session(per-session accessToken
   已簽發但未用於授權判斷)。

---

## 4. 測試對應

| 規則 | 測試 |
| --- | --- |
| 五份 NIST 註冊範例必須被接受、壞註冊必須 400、能力必須被儲存 | `backend/tests/test_registration.py` |
| 交卷結構驗證、`missing`、409 防呆、重送清除 missing | `backend/tests/test_results_validation.py` |
| 全流程(login→註冊→取考卷→交卷→disposition→certify) | `backend/tests/test_flow.py`、`scripts/demo_flow.py` |

執行:`cd backend && python -m pytest`(71 passed)。
