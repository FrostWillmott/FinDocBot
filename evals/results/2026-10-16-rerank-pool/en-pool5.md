# Retrieval evaluation: real-en-pool5

- ollama: `0.40.4`
- qwen3-embedding:0.6b: `ac6da0dfba84`
- awenleven/Qwen3-Reranker-4B:Q4_K_M: `086092f9af6f`
- documents: `1`
- chunks: `547`
- questions: `14`
- candidate pool: top 5 by exact cosine (not pgvector HNSW)
- counts are hits/questions; `pool` is how many questions have the gold chunk in the pool, the ceiling for any reranker

## Variant: plain

| category | method | n | pool | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|---|
| exact | vector | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| exact | rerank:default | 4 | 4/4 | 4/4 | 4/4 | 4/4 | 1.00 |
| paraphrase | vector | 4 | 3/4 | 2/4 | 3/4 | 3/4 | 0.62 |
| paraphrase | rerank:default | 4 | 3/4 | 2/4 | 3/4 | 3/4 | 0.62 |
| table | vector | 3 | 2/3 | 0/3 | 1/3 | 2/3 | 0.23 |
| table | rerank:default | 3 | 2/3 | 1/3 | 2/3 | 2/3 | 0.50 |
| qualitative | vector | 3 | 3/3 | 1/3 | 3/3 | 3/3 | 0.67 |
| qualitative | rerank:default | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 1.00 |
| all | vector | 14 | 12/14 | 7/14 | 11/14 | 12/14 | 0.66 |
| all | rerank:default | 14 | 12/14 | 10/14 | 12/14 | 12/14 | 0.79 |

## Reranker latency

- first call (incl. any model load): 2.8s
- per pair, warm: median 0.81s, p90 1.18s (n=69)
- per query (5 pairs): median 4.4s, p90 5.6s
