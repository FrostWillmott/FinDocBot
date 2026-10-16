# Retrieval evaluation: real-ru-qwen3-embedding-4b

- ollama: `0.40.4`
- qwen3-embedding:4b: `df5bd2e3c74c`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `130`
- questions: `14`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 1/4 | 1/4 | 1/4 | 0.33 |
| exact | rerank:default | 4 | 4/4 | 3/4 | 4/4 | 4/4 | 0.88 |
| paraphrase | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| table | vector | 4 | 4/4 | 2/4 | 4/4 | 4/4 | 0.75 |
| table | rerank:default | 4 | 4/4 | 3/4 | 3/4 | 4/4 | 0.81 |
| qualitative | vector | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 1.00 |
| qualitative | rerank:default | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 1.00 |
| all | vector | 14 | 14/14 | 9/14 | 11/14 | 11/14 | 0.74 |
| all | rerank:default | 14 | 14/14 | 12/14 | 13/14 | 14/14 | 0.91 |

## Reranker latency

- first call (incl. any model load): 3.7s
- per pair, warm: median 1.90s, p90 2.35s (n=279)
- per query (20 pairs): median 39.6s, p90 42.0s
