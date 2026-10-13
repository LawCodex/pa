# LawCodex — Panamá (pa)

Panamanian legislation as Markdown, from **Legispan**, the legislative information system of
the **Asamblea Nacional** (https://legispan.asamblea.gob.pa/): **constitutional texts and
amendments**, **laws** (leyes), **texts único** (official consolidations), **decree-laws** and
**cabinet decrees**, each with the text of its publication in the *Gaceta Oficial*.

Part of [LawCodex](https://github.com/LawCodex): one public repository per jurisdiction.

Retrieved: **2026-10-13**. Language: Spanish (`es`).

Status: **partial — laws mostly from the 1970s onward (texts available as text); no current Constitution**

## What is covered

| Category (Legispan type) | Directory | Files |
|---|---|---|
| Constitución Política — historical texts of 1941 and 1946 (the 1904, 1972 and 1983 texts are scanned) | `constitucion/` | 2 |
| Actos legislativos (constitutional amendments) | `actos-legislativos/` | 2 |
| Leyes | `leyes/<year>/` | 2,832 |
| Textos únicos | `textos-unicos/<year>/` | 27 |
| Decretos-ley | `decretos-ley/<year>/` | 4 |
| Decretos de gabinete | `decretos-de-gabinete/<year>/` | 96 |

Legispan lists 6,665 leyes, 628 decretos-ley, 1,809 decretos de gabinete, 49 textos únicos,
46 actos legislativos and 7 constitutional texts. For about 40% of the laws (mostly since the
1970s) Legispan's search API returns the text of the Gaceta publication; for the others the
text was extracted from the PDF stored by Legispan (its first page is Legispan's cover sheet,
which is dropped). PDFs whose pages are mostly scanned images (no text layer) were not
converted (no OCR) — this excludes most norms before the 1970s. For the norms without API text, the Legispan PDFs of the constitutional texts, actos
legislativos, leyes and textos únicos were all checked (3,975 PDFs: ~98% are scans); the PDFs
of decretos-ley and decretos de gabinete without API text were not downloaded, given that ratio.

Texts are the **original published texts** (with the Gaceta's page headers removed), not
consolidated versions; the *textos únicos* are the official consolidations ordered by law.

## What is NOT covered

- The official Gaceta Oficial website (gacetaoficial.gob.pa) is behind an Incapsula bot
  challenge; not used.
- **The Constitution in force** (1972, as reformed in 1978, 1983, 1994 and 2004; texto único
  published in Gaceta Oficial 25176 of 15 Nov 2004): Legispan has no text layer for it.
- Scanned norms (no OCR), other norm types (resoluciones, acuerdos, contratos…).

## Source

Legispan public search API: `GET https://legispan.asamblea.gob.pa/api/search/norm?type[type]=<TYPE>&page=N&limit=100`
(metadata + `content`), PDFs at `https://s3-legispan.asamblea.gob.pa/legispan/NORMAS/…`.
Each file's `source` is the norm's Legispan page and `source_pdf` the PDF.

## Copyright

Panama's Ley 64 de 2012 sobre Derecho de Autor excludes official texts (laws, decrees, judicial
decisions) from copyright protection.

## Regenerate

```
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
RAW=/path/to/scratch .venv/bin/python scripts/pa_fetch.py all
```
