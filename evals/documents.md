# Real documents for the retrieval evaluation

Public annual reports, one per language, used with `evals/questions/real-*.jsonl`.
The PDFs are **not** committed (`evals/data/` is git-ignored); download each
into its own empty directory and check the SHA-256 so the questions match the
exact file.

| Language | Document | Pages | Source | SHA-256 |
|----------|----------|-------|--------|---------|
| en | Berkshire Hathaway, 2024 annual report | 150 | https://www.berkshirehathaway.com/2024ar/2024ar.pdf | `6aa0a501680c50a57e0a1a2e841b46800e1fed828a8a7889d83d8eae7953e4bb` |
| ru | Eurasian Development Bank (ЕАБР), annual report 2024, public version | 95 | https://eabr.org/upload/iblock/096/ls634ofb1g4wdgwc0m1gqwyr1nfw8r5p/GO2024_publichnaya_versiya.pdf (listed on https://eabr.org/investors/annual-report/) | `702eb51e9d702413b8c8daabaf28265bab16616a8b691793605fa5dffe70b1f4` |
| hy | IDBank, 2024 annual report (Armenian) | 48 | https://idbank.am/documents/Annual%20report%202024-Arm.pdf | `733644ee24af8135bd305c454f39283ee4e53aee21a337b30ca260ea5919457c` |

```bash
mkdir -p evals/data/real && mkdir evals/data/real/en evals/data/real/ru evals/data/real/hy
curl -L -o evals/data/real/en/berkshire-hathaway-2024-annual-report.pdf \
    https://www.berkshirehathaway.com/2024ar/2024ar.pdf
curl -L -e https://eabr.org/investors/annual-report/ \
    -o evals/data/real/ru/eabr-annual-report-2024.pdf \
    https://eabr.org/upload/iblock/096/ls634ofb1g4wdgwc0m1gqwyr1nfw8r5p/GO2024_publichnaya_versiya.pdf
curl -L -o evals/data/real/hy/idbank-annual-report-2024.pdf \
    "https://idbank.am/documents/Annual%20report%202024-Arm.pdf"
shasum -a 256 evals/data/real/*/*.pdf
```

The EDB server cuts a slow download short; compare the size with
`curl -sIL` or resume with `curl -C -` (the complete file is 6,908,625 bytes).

Run each language on its own (one document per directory, so the question is
only ever retrieved from its own report):

```bash
uv run python -m evals.retrieval_eval --pdf-dir evals/data/real/en \
    --questions evals/questions/real-en.jsonl --gold any --label real-en
```

- `--gold any`: a figure may sit in several chunks (the chunker copies the text
  at a chunk boundary into both neighbours, and reports repeat facts); every
  chunk that contains it counts as a hit.
- `--validate-only` checks the questions against the PDFs without calling Ollama.
- The `titled` variant is pointless here: with one report per directory every
  chunk would get the same title.

## Questions

14 per document, in the document's own language, in four categories:
`exact` (the document's wording, a figure in prose), `paraphrase` (different
wording, same fact), `table` (a figure read from a financial table) and
`qualitative` (a name or a short statement). I wrote them after reading the
reports, so they are not independent of me; the Armenian ones in particular
deserve a native speaker's review.
