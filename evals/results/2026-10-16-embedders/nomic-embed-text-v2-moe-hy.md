# Retrieval evaluation: real-hy-nomic-embed-text-v2-moe

- ollama: `0.40.4`
- nomic-embed-text-v2-moe: `?`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `59`
- questions: `14`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| table | vector | 4 | 4/4 | 0/4 | 2/4 | 2/4 | 0.24 |
| table | rerank:default | 4 | 4/4 | 2/4 | 3/4 | 3/4 | 0.61 |
| qualitative | vector | 2 | 2/2 | 1/2 | 2/2 | 2/2 | 0.75 |
| qualitative | rerank:default | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 1.00 |
| all | vector | 14 | 14/14 | 9/14 | 12/14 | 12/14 | 0.75 |
| all | rerank:default | 14 | 14/14 | 12/14 | 13/14 | 13/14 | 0.89 |

## Reranker latency

- first call (incl. any model load): 4.9s
- per pair, warm: median 4.34s, p90 5.67s (n=279)
- per query (20 pairs): median 90.1s, p90 94.8s
