# Retrieval evaluation: real-hy-pool5

- ollama: `0.40.4`
- qwen3-embedding:0.6b: `ac6da0dfba84`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `59`
- questions: `14`
- candidate pool: top 5 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 4/4 | 2/4 | 4/4 | 4/4 | 0.71 |
| paraphrase | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| table | vector | 4 | 3/4 | 1/4 | 1/4 | 3/4 | 0.36 |
| table | rerank:default | 4 | 3/4 | 1/4 | 2/4 | 3/4 | 0.38 |
| qualitative | vector | 2 | 1/2 | 1/2 | 1/2 | 1/2 | 0.50 |
| qualitative | rerank:default | 2 | 1/2 | 1/2 | 1/2 | 1/2 | 0.50 |
| all | vector | 14 | 12/14 | 8/14 | 10/14 | 12/14 | 0.66 |
| all | rerank:default | 14 | 12/14 | 10/14 | 11/14 | 12/14 | 0.75 |

## Reranker latency

- first call (incl. any model load): 7.0s
- per pair, warm: median 4.39s, p90 5.74s (n=69)
- per query (5 pairs): median 22.1s, p90 25.1s
