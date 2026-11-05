# Column reading order (FD-04): known limitation and design proposal

Status: **not fixed**. This note records the defect, why the current parser
cannot fix it where it stands, and what a fix would have to look like.

## Problem

A two-column page whose content stream draws the columns *row by row* (left
line, right line, next left line, ...) is extracted with both columns mixed
into every line. Reproduction with fpdf2 (A4, Helvetica 10, four rows of
`set_xy(10, y); cell(90, 5, L_i); set_xy(110, y); cell(90, 5, R_i)`):

```text
Revenue grew strongly during the year The board approved a new dividend
thanks to higher volumes across all policy after reviewing the capital
regions and a better product mix in plan and the liquidity forecast for
the second half of the fiscal period. the next three years of operations.
```

The chunker then embeds sentences that never existed, so retrieval and
quoting suffer on such pages. The same text drawn *column by column* (the
left `multi_cell`, then the right one) is already correct: the jump back up
the page becomes a paragraph break
(`test_extract_text_two_columns_keep_reading_order`).

## Why `join_lines` cannot fix it

- pypdf's plain `page.extract_text()` (no visitor) returns the identical
  interleaved string: pypdf merges fragments on the same baseline into one
  line, adds a `" "` to the start of the right fragment and puts no `"\n"`
  between the two.
- Our visitor does get the two fragments separately, each with its text
  matrix (`tm[4]` = 31.2 pt for the left one, 314.6 pt for the right one), but
  `_extract_page` keeps only `y` and concatenates the text, so `join_lines`
  receives one `TextLine` per row. By then the order is already lost.
- So a fix belongs in the visitor/line-assembly step, not in `join_lines`.
  Font-size and gap thresholds there are unrelated to this defect.

## The ambiguity: tables look the same

A two-column table with the *same geometry* is extracted exactly as wanted:

```text
Revenue 1,284
Operating costs 912
Net profit 372
Dividend 120
```

(`test_extract_text_two_column_table_rows_keep_row_order`.) Geometry alone
cannot tell "two prose columns" from "label | value". So sorting all
fragments by x (column first) is ruled out: it would break every table
in every report.

## Options

| Option | What | Pro | Con |
|---|---|---|---|
| a. Document only | Keep the behaviour, record it here | No risk, no code | Row-by-row two-column pages stay mixed |
| b. Fragment x + gated reorder | Keep x per fragment; reorder only runs of rows that look like prose columns | Fixes the prose case, tables untouched | Heuristic; new parser state; wide tables with prose cells may be split |
| c. Separator between same-baseline fragments | Join fragments with `" \| "` or a tab | Trivial | Content is still mixed; the chunker and embedder see the same broken sentences |
| `extraction_mode="layout"` | pypdf's layout renderer | Built in | Pads with spaces, does not segment columns; changes output on every page and breaks the paragraph logic (already rejected 2026-10-01) |

## Recommended approach (if evidence justifies it): option b

1. The visitor records fragments `(text, x, y, font_size)` instead of joined
   text, stripping the leading space pypdf adds to a same-baseline fragment.
   Physical lines are grouped by baseline as today.
2. A line is a **split row** when it has exactly two fragments, the first
   starts left of 40 % of the page width and the second right of it, and
   **both** fragments are prose: at least 30 characters and at least 4 words
   each, and not mostly digits.
3. A **column run** is at least 3 consecutive split rows whose second-fragment
   x agrees within 2 pt and whose line pitch is uniform (the same test
   `join_lines` uses for "same paragraph").
4. Inside a run only: emit the left fragments as lines, then a paragraph
   break, then the right fragments. Everything outside a run (headings,
   single-column text, tables, short runs) keeps today's order, so the
   change is a no-op on pages without a run.
5. `join_lines` and the chunker contract do not change.

Acceptance tests it must pass (fpdf-built, in `test_pdf_parser.py`):

- prose columns written row by row → left column, `"\n\n"`, right column;
- the two-column table → unchanged rows (existing test);
- wrapped single column → unchanged
  (`test_extract_text_wrapped_lines_stay_in_one_paragraph`);
- columns written column by column → unchanged (existing test);
- mixed page: full-width heading, a prose column run, then a label/value
  table → heading, left column, right column, table rows in order;
- two long cells on only one or two rows (a table with a description
  column) → unchanged.

Known residual risk: a table of three or more rows with two long prose cells
per row passes the gate and would be split into columns.

## Evidence that would justify building it

The defect is reproduced on fpdf2 output only. Many real producers (LaTeX,
InDesign, Word) write each column as its own block, which already works.
Before building option b, run the reports in `evals/documents.md` through the
parser and count the pages that have column runs as defined above. Build it
only if real pages are affected and the retrieval eval's misses on them trace
back to interleaved chunks.
