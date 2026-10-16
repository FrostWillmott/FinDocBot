# Retrieval evaluation: real-en-nomic-embed-text-v2-moe

- ollama: `0.40.4`
- nomic-embed-text-v2-moe: `?`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `547`
- questions: `14`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 1/4 | 3/4 | 3/4 | 0.52 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 2/4 | 0/4 | 1/4 | 2/4 | 0.19 |
| paraphrase | rerank:default | 4 | 2/4 | 1/4 | 2/4 | 2/4 | 0.38 |
| table | vector | 3 | 3/3 | 2/3 | 2/3 | 2/3 | 0.69 |
| table | rerank:default | 3 | 3/3 | 2/3 | 3/3 | 3/3 | 0.83 |
| qualitative | vector | 3 | 3/3 | 1/3 | 1/3 | 1/3 | 0.39 |
| qualitative | rerank:default | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 1.00 |
| all | vector | 14 | 12/14 | 4/14 | 7/14 | 8/14 | 0.43 |
| all | rerank:default | 14 | 12/14 | 10/14 | 12/14 | 12/14 | 0.79 |

## Reranker latency

- first call (incl. any model load): 2.1s
- per pair, warm: median 0.90s, p90 1.34s (n=279)
- per query (20 pairs): median 18.2s, p90 22.8s
