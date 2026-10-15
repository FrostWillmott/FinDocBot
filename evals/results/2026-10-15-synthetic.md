# Retrieval evaluation: synthetic

- ollama: `0.40.4`
- nomic-embed-text:latest: `0a109f422b47`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `18`
- chunks: `108`
- questions: `40`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact_wording | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| exact_wording | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| exact_wording | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| paraphrase | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| paraphrase | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| paraphrase | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| year_only_context | vector | 8 | 8/8 | 0/8 | 0/8 | 0/8 | 0.08 |
| year_only_context | rerank:default | 8 | 8/8 | 1/8 | 1/8 | 4/8 | 0.28 |
| year_only_context | rerank:task | 8 | 8/8 | 0/8 | 2/8 | 7/8 | 0.27 |
| no_company_or_year | vector | 8 | 8/8 | 0/8 | 0/8 | 2/8 | 0.13 |
| no_company_or_year | rerank:default | 8 | 8/8 | 3/8 | 8/8 | 8/8 | 0.60 |
| no_company_or_year | rerank:task | 8 | 8/8 | 4/8 | 7/8 | 8/8 | 0.70 |
| topical | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| topical | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| topical | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| all | vector | 40 | 40/40 | 24/40 | 24/40 | 26/40 | 0.64 |
| all | rerank:default | 40 | 40/40 | 28/40 | 33/40 | 36/40 | 0.78 |
| all | rerank:task | 40 | 40/40 | 28/40 | 33/40 | 39/40 | 0.79 |

## Variant: titled

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact_wording | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| exact_wording | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| exact_wording | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| paraphrase | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| paraphrase | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| paraphrase | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| year_only_context | vector | 8 | 8/8 | 6/8 | 8/8 | 8/8 | 0.88 |
| year_only_context | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| year_only_context | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| no_company_or_year | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| no_company_or_year | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| no_company_or_year | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| topical | vector | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| topical | rerank:default | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| topical | rerank:task | 8 | 8/8 | 8/8 | 8/8 | 8/8 | 1.00 |
| all | vector | 40 | 40/40 | 38/40 | 40/40 | 40/40 | 0.97 |
| all | rerank:default | 40 | 40/40 | 40/40 | 40/40 | 40/40 | 1.00 |
| all | rerank:task | 40 | 40/40 | 40/40 | 40/40 | 40/40 | 1.00 |

## Reranker latency

- first call (incl. any model load): 0.7s
- per pair, warm: median 0.40s, p90 0.59s (n=3199)
- per query (20 pairs): median 9.0s, p90 10.3s
