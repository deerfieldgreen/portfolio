# Macroeconomic Indicators for Market Regime Detection

The pipeline uses **differentials** (domestic minus foreign) for the currency pair. For **USD_JPY**, that means **US minus Japan**. The HMM uses these as additional features to separate regimes (e.g. risk-on vs risk-off, or rate-differential-driven trends).

Below: what each indicator is, why it matters for forex, units/frequency, and where to get the data so you can plug in real series.

---

## 1. interest_rate_2y — 2-year government bond yield differential

| Aspect | Detail |
|--------|--------|
| **What it is** | Yield on 2-year government bonds. Differential = US 2Y yield − Japan 2Y yield (in percentage points). |
| **Why it matters** | Short-term rate expectations drive capital flows; widening US–JP 2Y spread typically supports USD/JPY (carry/expectations). Regime shifts often align with Fed/BoJ policy or front-end repricing. |
| **Units** | Percentage (e.g. 2.5 means 2.5%). Differential in percentage points (e.g. 1.5 = US 2Y is 1.5 pp above JP 2Y). |
| **Frequency** | Daily (markets). |
| **US series (FRED)** | `DGS2` (Treasury 2Y) or `DFEDTARU` for expectations. |
| **Japan series** | BoJ/Stats: 2-year JGB yield. FRED: `IRLTLT01JPM156N` (long-term Japan gov bond, use 2Y from BoJ or Bloomberg if you need exact 2Y). For a quick FRED-only option, use a Japan short rate as proxy and document. |
| **Alternative sources** | ECB Statistical Data Warehouse (for EUR pairs), national central banks, Bloomberg, Refinitiv. |

---

## 2. interest_rate_10y — 10-year government bond yield differential

| Aspect | Detail |
|--------|--------|
| **What it is** | Yield on 10-year government bonds. Differential = US 10Y − Japan 10Y (percentage points). |
| **Why it matters** | Long end reflects growth/inflation expectations and term premium. USD/JPY often tracks 10Y differential; regime changes can coincide with bond sell-offs or flight to quality. |
| **Units** | Percentage. Differential in percentage points. |
| **Frequency** | Daily. |
| **US series (FRED)** | `DGS10` (Treasury 10Y). |
| **Japan series** | FRED: `IRLTLT01JPM156N` (Japan gov bond yield, 10Y). Or BoJ. |
| **Alternative sources** | ECB, BoJ, Bloomberg. |

---

## 3. policy_rate — Central bank policy rate differential

| Aspect | Detail |
|--------|--------|
| **What it is** | Main policy rate: Fed Funds (US) vs BoJ Policy Rate (Japan). Differential = US rate − Japan rate (percentage points). |
| **Why it matters** | Directly reflects monetary stance. Widening spread (US higher) typically supports USD/JPY; regime shifts around FOMC/BoJ meetings. |
| **Units** | Percentage (e.g. 5.25%). Differential in percentage points. |
| **Frequency** | Changes at meetings (discrete); use last announced rate and forward-fill until next meeting. |
| **US series (FRED)** | `DFF` (effective Fed Funds) or `FEDFUNDS`. |
| **Japan series** | FRED: `IRSTCB01JPM156N` (BoJ policy rate) or BoJ website. |
| **Alternative sources** | BIS, national central banks. |

---

## 4. cpi_yoy — CPI year-over-year differential

| Aspect | Detail |
|--------|--------|
| **What it is** | Consumer price index, year-over-year growth. Differential = US CPI YoY − Japan CPI YoY (percentage points). |
| **Why it matters** | Inflation differentials drive real rates and long-term rate expectations; regime changes can align with inflation surprises (e.g. US hot, Japan mild → USD strength). |
| **Units** | YoY growth in percent. Differential in percentage points. |
| **Frequency** | Monthly (US CPI, Japan CPI). Forward-fill to daily/intraday to match forex bars. |
| **US series (FRED)** | `CPIAUCSL` (index) then compute YoY, or `CPIAUCNS`; or use `T5YIE`/breakevens for inflation expectations. |
| **Japan series** | FRED: `JPNCPIALLQINMEI` or Stats Japan CPI. |
| **Alternative sources** | OECD, national statistics offices, BIS. |

---

## 5. gdp_growth — GDP growth rate differential

| Aspect | Detail |
|--------|--------|
| **What it is** | GDP growth (real). Often quarterly YoY or QoQ annualized. Differential = US growth − Japan growth. |
| **Why it matters** | Growth differentials drive capital flows and risk sentiment; strong US / weak Japan supports USD/JPY and can define “growth” vs “recession” regimes. |
| **Units** | Percent (e.g. 2.5% YoY). Differential in percentage points. |
| **Frequency** | Quarterly. Forward-fill to daily/intraday. |
| **US series (FRED)** | `A191RL1Q225SBEA` (real GDP YoY) or `GDPC1` for level and compute growth. |
| **Japan series** | FRED: `JPNRGDPQDSNAQ` or Cabinet Office. |
| **Alternative sources** | OECD, national accounts, Bloomberg. |

---

## 6. unemployment — Unemployment rate differential

| Aspect | Detail |
|--------|--------|
| **What it is** | Unemployment rate (%). Differential = US unemployment − Japan unemployment (percentage points). |
| **Why it matters** | Labor market slack affects policy and growth expectations. Falling US unemployment (tight labor market) can support Fed hikes and USD; regime shifts around NFP or BoJ view. |
| **Units** | Percent. Differential in percentage points. |
| **Frequency** | Monthly. Forward-fill to match forex. |
| **US series (FRED)** | `UNRATE`. |
| **Japan series** | FRED: `LRUN64TTJPM156S` or `LRUNTTTTJPM156S`; Stats Japan. |
| **Alternative sources** | OECD, national statistics. |

---

## 7. pmi_composite — Purchasing Managers Index differential

| Aspect | Detail |
|--------|--------|
| **What it is** | Composite PMI (manufacturing + services or manufacturing only). Differential = US PMI − Japan PMI (index points). |
| **Why it matters** | Leading indicator of growth; >50 = expansion, <50 = contraction. Divergence (e.g. US >50, Japan <50) can precede USD/JPY trends and regime shifts. |
| **Units** | Index level (typically 0–100, 50 = no change). Differential in index points. |
| **Frequency** | Monthly (usually first business day of month). Forward-fill. |
| **US series** | FRED: no single composite; use `NAPM` (old) or ISM Manufacturing `NAPM`; for composite use IHS Markit / S&P Global (subscription) or construct from manufacturing + services. |
| **Japan series** | Markit/Jibun Bank Japan PMI (subscription), or use official indices (e.g. Reuters Tankan). FRED has limited PMI for Japan. |
| **Alternative sources** | S&P Global PMI, national PMI releases, Bloomberg. |

---

## Implementation notes

1. **Pair mapping**  
   For USD_JPY, differential = US − Japan. For other pairs (e.g. EUR_USD), define domestic vs foreign and compute accordingly.

2. **Alignment with forex bars**  
   Macro data are daily or lower frequency. The pipeline uses `forward_fill: true` so the last known macro value is carried forward to each forex bar timestamp. Implement your fetcher to return a time series (date → value) and merge/forward-fill in `add_macro_features` (or a helper) so each row of the forex DataFrame has the correct differential for that bar’s date.

3. **Data source choice**  
   - **FRED**: Free, good for US and some Japan series; need API key.  
   - **National central banks / statistics**: Free, authoritative, often need scraping or manual CSV.  
   - **Bloomberg / Refinitiv**: Paid, comprehensive, stable series IDs.  
   Start with FRED for US + Japan where available; add BoJ/Stats Japan for policy and CPI; add PMI from S&P Global or similar if you need composite.

4. **Secrets**  
   Store API keys (e.g. FRED_API_KEY) in Doppler and inject into the process-step if you fetch macro inside the pipeline. Alternatively, fetch macro in a separate job or service and write to a table the process step reads.

5. **Disabling macro**  
   Set `macro_indicators.enabled: false` in `config.yaml` until real data is wired; the pipeline will skip macro features and the HMM will use only price/technical features.
