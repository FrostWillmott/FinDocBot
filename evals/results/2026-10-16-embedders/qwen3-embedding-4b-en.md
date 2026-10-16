# Retrieval evaluation: real-en-qwen3-embedding-4b

- ollama: `0.40.4`
- qwen3-embedding:4b: `df5bd2e3c74c`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `547`
- questions: `14`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 3/4 | 4/4 | 4/4 | 0.88 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 4/4 | 1/4 | 2/4 | 3/4 | 0.48 |
| paraphrase | rerank:default | 4 | 4/4 | 3/4 | 4/4 | 4/4 | 0.88 |
| table | vector | 3 | 3/3 | 1/3 | 2/3 | 2/3 | 0.49 |
| table | rerank:default | 3 | 3/3 | 2/3 | 3/3 | 3/3 | 0.83 |
| qualitative | vector | 3 | 3/3 | 1/3 | 3/3 | 3/3 | 0.61 |
| qualitative | rerank:default | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 1.00 |
| all | vector | 14 | 14/14 | 6/14 | 11/14 | 12/14 | 0.62 |
| all | rerank:default | 14 | 14/14 | 12/14 | 14/14 | 14/14 | 0.93 |

## Reranker latency

- first call (incl. any model load): 2.8s
- per pair, warm: median 0.86s, p90 1.24s (n=279)
- per query (20 pairs): median 17.3s, p90 22.0s
