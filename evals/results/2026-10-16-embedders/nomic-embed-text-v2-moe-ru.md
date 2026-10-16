# Retrieval evaluation: real-ru-nomic-embed-text-v2-moe

- ollama: `0.40.4`
- nomic-embed-text-v2-moe: `?`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `130`
- questions: `14`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 2/4 | 1/4 | 1/4 | 2/4 | 0.30 |
| exact | rerank:default | 4 | 2/4 | 1/4 | 2/4 | 2/4 | 0.38 |
| paraphrase | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| table | vector | 4 | 4/4 | 2/4 | 2/4 | 2/4 | 0.54 |
| table | rerank:default | 4 | 4/4 | 3/4 | 3/4 | 4/4 | 0.81 |
| qualitative | vector | 2 | 2/2 | 1/2 | 2/2 | 2/2 | 0.67 |
| qualitative | rerank:default | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 1.00 |
| all | vector | 14 | 12/14 | 8/14 | 9/14 | 10/14 | 0.62 |
| all | rerank:default | 14 | 12/14 | 10/14 | 11/14 | 12/14 | 0.77 |

## Reranker latency

- first call (incl. any model load): 1.8s
- per pair, warm: median 1.89s, p90 2.32s (n=279)
- per query (20 pairs): median 39.0s, p90 42.4s
