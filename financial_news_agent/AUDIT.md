# Financial News Scoring API – Cervid API Audit

**Audit date:** 2026-02-11  
**Source:** `src/financial_news_scoring_api/` (Financial News Scoring API)  
**Pipeline:** `argo_pipelines/financial_news_agent/` (Financial News Agent)  
**Rules:** `.cursor/rules/auditing-cervid-apis.mdc`

---

## Naming Convention

| Component | Name | Location |
|-----------|------|----------|
| Argo pipeline | financial-news-agent | argo_pipelines/financial_news_agent |
| FastAPI | financial-news-scoring-api | src/financial_news_scoring_api |
| Pipeline image | financial-news-agent | DO registry |
| API image | financial-news-scoring-api | DO registry |
| Pipeline Doppler | financial_news_agent | K8s secret financial-news-agent (argo-workflows) |
| API Doppler | financial_news_scoring_api | K8s secret financial-news-scoring-api (cervid) |

---

## 1. API URL Path Must Use v1 Prefix ✅ PASS

| Requirement | Status | Notes |
|-------------|--------|-------|
| All public routes start with /v1/ | ✅ | Router uses `prefix="/v1/news"` |
| Hard-coded URLs use api.cervid.deerfieldgreen.com/v1 | N/A | No hard-coded external URLs |
| OpenAPI/docs reflect same base URL | ✅ | Docs at `/v1/news/docs`, `/v1/news/redoc` |

---

## 2. Secrets Managed with Doppler ✅ PASS

| Requirement | Status | Notes |
|-------------|--------|-------|
| No hard-coded secrets in source | ✅ | Config has no secrets |
| Secrets via env or Doppler injection | ✅ | API reads from env; config.yaml has no secrets |
| New secrets documented as Doppler-managed | ✅ | doppler/env.* documents env vars |

---

## 3. FastAPI and RESTful Conventions ✅ PASS

| Requirement | Status | Notes |
|-------------|--------|-------|
| FastAPI, APIRouter, Pydantic | ✅ | FastAPI, APIRouter used |
| Nouns for resources, correct HTTP verbs | ✅ | `/currencies`, `/health`, `POST /score/trigger` |
| GET endpoints idempotent | ✅ | GETs are read-only |
| Request/response models | ⚠️ | Most endpoints return untyped dicts; Pydantic models would improve type safety |

---

## 4. LRU Caching with Doppler-Configured TTL ✅ IMPLEMENTED

| Requirement | Status | Notes |
|-------------|--------|-------|
| LRU caching on read-heavy endpoints | ✅ | TTLCache on currencies, recent-trends, recent-trend-decay, hourly-trends, hourly-trend-decay, articles |
| TTL ≥ 36,000 seconds from Doppler | ✅ | `CERVID_CACHE_TTL_SECONDS` (default 36000) |
| Doppler-managed CACHE_TTL | ✅ | `CERVID_CACHE_TTL_SECONDS`, `CERVID_CACHE_MAX_SIZE` in API Doppler project |

---

## 5. GitHub Actions CI ✅ IMPLEMENTED

| Requirement | Status | Notes |
|-------------|--------|-------|
| CI workflow exists | ✅ | `financial-news-agent-ci.yaml` (pipeline), `financial-news-scoring-api-ci.yaml` (API) |
| Builds pipeline container | ✅ | Dockerfile → financial-news-agent |
| Builds API container | ✅ | src/financial_news_scoring_api/Dockerfile → financial-news-scoring-api |
| Pushes to DigitalOcean registry | ✅ | Both images pushed to DO |
| Secrets from Doppler/env | ✅ | Uses `DIGITALOCEAN_ACCESS_TOKEN` |

---

## 6. K8 Secrets ✅ PASS

| Requirement | Status | Notes |
|-------------|--------|-------|
| Pipeline DopplerSecret | ✅ | `financial-news-agent-doppler.yaml` → financial-news-agent in argo-workflows |
| API DopplerSecret | ✅ | `financial-news-scoring-api-doppler.yaml` → financial-news-scoring-api in cervid |
| No plaintext secrets | ✅ | DopplerSecret references Doppler projects |

---

## 7. Application Setup in Production ✅ PASS

| Requirement | Status | Notes |
|-------------|--------|-------|
| Application in tetrux | ✅ | `financial-news-scoring-api` in applications/ |
| Manifests reference correct image | ✅ | Uses `financial-news-scoring-api` |
| Secrets via Doppler | ✅ | `envFrom: financial-news-scoring-api` |

---

## 8. Test Compatibility ✅ PASS

Tests in `audit_apis.py` use `/v1/news` so paths resolve correctly.

---

## Summary

| Rule | Status |
|------|--------|
| API URL path | ✅ |
| Secrets | ✅ |
| FastAPI/RESTful | ✅ |
| LRU caching | ✅ |
| CI | ✅ |
| K8 secrets | ✅ |
| Application manifests | ✅ |
