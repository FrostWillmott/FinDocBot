# Retrieval evaluation: real-en-bge-m3

- ollama: `0.40.4`
- bge-m3: `?`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `547`
- questions: `14`
- candidate pool: top 20 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 2/4 | 2/4 | 2/4 | 0.54 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 3/4 | 1/4 | 2/4 | 2/4 | 0.38 |
| paraphrase | rerank:default | 4 | 3/4 | 2/4 | 3/4 | 3/4 | 0.62 |
| table | vector | 3 | 3/3 | 1/3 | 2/3 | 2/3 | 0.53 |
| table | rerank:default | 3 | 3/3 | 2/3 | 3/3 | 3/3 | 0.83 |
| qualitative | vector | 3 | 3/3 | 2/3 | 2/3 | 3/3 | 0.75 |
| qualitative | rerank:default | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 1.00 |
| all | vector | 14 | 13/14 | 6/14 | 8/14 | 9/14 | 0.53 |
| all | rerank:default | 14 | 13/14 | 11/14 | 13/14 | 13/14 | 0.86 |

## Reranker latency

- first call (incl. any model load): 1.5s
- per pair, warm: median 1.00s, p90 1.42s (n=279)
- per query (20 pairs): median 19.4s, p90 23.8s
