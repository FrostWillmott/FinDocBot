# Retrieval evaluation: real-hy-pool10

- ollama: `0.40.4`
- qwen3-embedding:0.6b: `ac6da0dfba84`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `59`
- questions: `14`
- candidate pool: top 10 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 4/4 | 2/4 | 4/4 | 4/4 | 0.71 |
| paraphrase | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| table | vector | 4 | 4/4 | 1/4 | 1/4 | 3/4 | 0.40 |
| table | rerank:default | 4 | 4/4 | 1/4 | 2/4 | 3/4 | 0.47 |
| qualitative | vector | 2 | 2/2 | 1/2 | 1/2 | 1/2 | 0.56 |
| qualitative | rerank:default | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 1.00 |
| all | vector | 14 | 14/14 | 8/14 | 10/14 | 12/14 | 0.68 |
| all | rerank:default | 14 | 14/14 | 11/14 | 12/14 | 13/14 | 0.85 |

## Reranker latency

- first call (incl. any model load): 5.5s
- per pair, warm: median 4.93s, p90 6.90s (n=139)
- per query (10 pairs): median 49.2s, p90 63.0s
