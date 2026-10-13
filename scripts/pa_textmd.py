"""Generic converter: text extracted from an official PDF edition of a Spanish-language
law -> structured Markdown (headings for LIBRO/TÍTULO/CAPÍTULO/..., one heading per article).

Used by the other pa_* scripts. Heuristic, but deterministic and faithful: no text is
reworded; only running page headers/footers and page numbers are dropped, wrapped lines are
re-joined into paragraphs, and editorial footnotes are moved to Markdown footnotes.
"""
import logging
import re
from collections import Counter

import pypdf

logging.disable(logging.WARNING)

DIV_WORDS = r"(LIBRO|PARTE|SECCI[ÓO]N|T[ÍI]TULO|SUBT[ÍI]TULO|CAP[ÍI]TULO|SUBCAP[ÍI]TULO|SUBSECCI[ÓO]N)"
ORD = (r"([IVXLCDM]+|\d+|[ÚU]NIC[OA]|PRELIMINAR|PRIMER[OA]?|SEGUND[OA]|TERCER[OA]?|CUART[OA]|QUINT[OA]|"
       r"SEXT[OA]|S[ÉE]PTIM[OA]|OCTAV[OA]|NOVEN[OA]|D[ÉE]CIM[OA]|[A-ZÁÉÍÓÚ]+(?:\s+[A-ZÁÉÍÓÚ]+)?)")
RE_DIV = re.compile(r"^" + DIV_WORDS + r"\s+" + ORD + r"\b\.?\s*[-–—:.]?\s*(.*)$", re.I)
RE_PARTE = re.compile(r"^(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA)\s+PARTE\b\.?\s*(.*)$")
RE_ART = re.compile(r"^(ART[ÍI]CULO|Art[íi]culo|Art\.)\s*([IVXLC]+(?=\s*[°º]?\s*(?:\.|-|–|:|$))|\d+[\w°º\-]*(?:\s*(?:bis|ter|quater|quinquies|[A-Z])\b)?|[ÚU]NICO|[ÚU]nico|PRIMERO|Primero)"
                    r"\s*[°º]?\s*(?:\.-|\.–|\.\s*-|-|–|—|\.|:)?\s*(.*)$")
RE_DISP = re.compile(r"^(DISPOSICI[ÓO]N(ES)?\s+.*|DISPOSICIONES|DECLARACI[ÓO]N|PRE[ÁA]MBULO|T[ÍI]TULO PRELIMINAR)$")
RE_LISTITEM = re.compile(r"^(\(?[0-9]{1,3}[\.\)]|\(?[a-zñ][\.\)]|[IVX]{1,5}[\.\)]|[-•·])\s")
RE_ORDINAL_DISP = re.compile(r"^(PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|S[ÉE]PTIMA|OCTAVA|NOVENA|D[ÉE]CIMA|"
                             r"UND[ÉE]CIMA|DUOD[ÉE]CIMA|[ÚU]NICA|Primera|Segunda|Tercera|Cuarta|Quinta|Sexta|S[ée]ptima|"
                             r"Octava|Novena|D[ée]cima|[ÚU]nica|Und[ée]cima|Duod[ée]cima|Decimo\w*|D[ée]cimo\w*|Vig[ée]sim\w*|Trig[ée]sim\w*)"
                             r"([\s\w]{0,30}?)\s*(\.-|\.–|\.\s*-|-|–|\.)\s*(.*)$")


def extract_pages(path):
    r = pypdf.PdfReader(path)
    return [(p.extract_text() or "") for p in r.pages]


def pdf_ok(path):
    """True if the file looks like a complete PDF (header + EOF marker, parsable)."""
    try:
        with open(path, "rb") as f:
            head = f.read(5)
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2048))
            tail = f.read()
        if head != b"%PDF-" or b"%%EOF" not in tail:
            return False
        pypdf.PdfReader(path).pages[0]
        return True
    except Exception:
        return False


def _norm(line):
    return re.sub(r"\d+", "#", line.strip())


def clean_pages(pages, extra_drop=(), head_n=3, foot_n=2):
    """Remove running headers/footers (lines repeating on many pages) and page numbers."""
    cnt = Counter()
    for t in pages:
        ls = [l for l in t.split("\n") if l.strip()]
        for l in set(ls[:head_n] + ls[-foot_n:]):
            cnt[_norm(l)] += 1
    thr = max(3, len(pages) * 0.15)
    rep = {k for k, v in cnt.items() if v >= thr and not RE_ART.match(k.strip())}
    # running headers that change per book/part: repeated >= 4 times at the top of pages
    top = {}
    for pi, t in enumerate(pages):
        ls = [l for l in t.split("\n") if l.strip()]
        for l in set(ls[:head_n]):
            top.setdefault(l.strip(), []).append(pi)
    exact = set()
    for k, idx in top.items():
        close = sum(1 for a, b in zip(idx, idx[1:]) if b - a <= 2)
        if close >= 3 and not RE_ART.match(k):
            exact.add(k)
    out = []
    for t in pages:
        ls = [l.rstrip() for l in t.split("\n")]
        ls = [l for l in ls if l.strip()]
        keep = []
        for i, l in enumerate(ls):
            edge = i < head_n or i >= len(ls) - foot_n
            s = l.strip()
            if edge and (_norm(l) in rep or s in exact or re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", s)
                         or re.fullmatch(r"(P[áa]g(ina)?\.?\s*)?\d{1,4}(\s*(de|/)\s*\d{1,4})?", s, re.I)):
                continue
            if any(re.search(p, s) for p in extra_drop):
                continue
            keep.append(l)
        out.append(keep)
    return out


def split_footnotes(pages_lines, start=None):
    """Detect footnotes numbered sequentially across the document (``N text`` at page
    bottom). Returns (body_pages, footnotes dict)."""
    nxt = start
    notes = {}
    body = []
    for ls in pages_lines:
        cut = None
        for i in range(len(ls)):
            m = re.match(r"^\s*(\d{1,4})\s+(\S.*)$", ls[i])
            if m and nxt is None and i > 0 and re.match(r"[A-ZÁÉÍÓÚÑ“\"(]", m.group(2)) \
                    and re.search(r"(?<=[^\s\d])" + m.group(1) + r"(?=[\s.,;:)”\"]|$)", "\n".join(ls[:i])):
                nxt = int(m.group(1))
            if m and int(m.group(1)) == nxt and i > 0 and not RE_LISTITEM.match(ls[i].strip()) \
                    and re.match(r"[A-ZÁÉÍÓÚÑ“\"(]", m.group(2)):
                cut = i
                break
        if cut is None:
            body.append(ls)
            continue
        b, f = ls[:cut], ls[cut:]
        cur = None
        for l in f:
            m = re.match(r"^\s*(\d{1,4})\s+(\S.*)$", l)
            if m and int(m.group(1)) == nxt:
                cur = nxt
                notes[cur] = [m.group(2).strip()]
                nxt += 1
            elif cur is not None:
                notes[cur].append(l.strip())
        # replace markers in body
        txt = "\n".join(b)
        for n in sorted(k for k in notes if k >= nxt - 50 and k < nxt):
            txt, k = re.subn(r"(?<=[^\s\d\[])" + str(n) + r"(?=[\s.,;:)”\"]|$)", f"[^{n}]", txt, count=1)
            if not k:
                txt = re.sub(r"(?<=\])\s" + str(n) + r"(?=[\s.,;:)”\"]|$)", f"[^{n}]", txt, count=1)
        body.append(txt.split("\n"))
    return body, {k: " ".join(v) for k, v in notes.items()}


def drop_lines(pages_lines, patterns):
    """Drop lines matching any regex in patterns (e.g. decorative titles)."""
    return [[l for l in ls if not any(re.fullmatch(p, l.strip()) for p in patterns)] for ls in pages_lines]


def is_caps(s):
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) > 0.85


# a caption (sumilla) does not end with a function word; a wrapped sentence often does
STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "e", "o", "u", "en", "a", "al", "que", "por", "con", "para",
             "se", "su", "sus", "un", "una", "lo", "como", "sin", "sobre", "entre", "cuando", "no", "es", "son", "ser"}

RANK = {"PARTE": 1, "LIBRO": 2, "SECCION": 3, "TITULO": 4, "SUBTITULO": 4.5, "CAPITULO": 5,
        "SUBCAPITULO": 6, "SUBSECCION": 6.5}


class Builder:
    """Collects blocks; heading levels are assigned at the end from a fixed rank order
    (PARTE > LIBRO > SECCIÓN > TÍTULO > CAPÍTULO > SUBCAPÍTULO), with SECCIÓN demoted below
    CAPÍTULO when it occurs inside chapters, and DISPOSICIONES at the top level."""

    def __init__(self, max_level=5):
        self.max_level = max_level
        self.out = []
        self.para = []
        self.last_heading = None
        self.open = {}
        self.sec_inside = [0, 0]
        self.sec_tit = 0
        self.has_disp = False

    def flush(self):
        if self.para:
            txt = " ".join(p.strip() for p in self.para)
            txt = re.sub(r"(\w)- (\w)", lambda m: m.group(1) + m.group(2) if m.group(2).islower() else m.group(0), txt)
            txt = re.sub(r"\s{2,}", " ", txt).strip()
            if txt:
                self.out.append(txt)
            self.para = []

    def heading(self, kind, text):
        self.flush()
        key = (kind, text.upper())
        if self.last_heading == key:
            return
        r = RANK.get(kind, 0)
        if kind == "DISP":
            self.has_disp = True
        if kind == "SECCION":
            if self.open.get("CAPITULO"):
                self.sec_inside[1] += 1
            elif self.open.get("TITULO"):
                self.sec_tit += 1
            else:
                self.sec_inside[0] += 1
        elif r:
            for k in list(self.open):
                if RANK.get(k, 0) >= r:
                    self.open.pop(k)
            self.open[kind] = True
        self.out.append((kind, text))
        self.last_heading = key

    def finish(self):
        self.flush()
        rank = dict(RANK)
        top, in_cap, in_tit = self.sec_inside[0], self.sec_inside[1], self.sec_tit
        if in_cap > top and in_cap >= in_tit:
            rank["SECCION"] = 5.5
        elif in_tit > top:
            rank["SECCION"] = 4.7
        used = sorted({rank[k] for k, _ in (o for o in self.out if isinstance(o, tuple)) if k in rank})
        lvl = {r: min(2 + i, self.max_level) for i, r in enumerate(used)}
        res = []
        for o in self.out:
            if isinstance(o, tuple):
                k, t = o
                res.append("#" * (lvl[rank[k]] if k in rank else 2) + " " + t)
            else:
                res.append(o)
        return res

    def article(self, label, rest):
        self.flush()
        self.out.append("###### " + label)
        self.last_heading = None
        if rest.strip():
            self.para = [rest]

    def line(self, l):
        self.last_heading = None
        self.para.append(l)


def lines_to_md(pages_lines, article_word="Artículo"):
    lines = [l for ls in pages_lines for l in ls]
    lens = sorted(len(l.strip()) for l in lines if len(l.strip()) > 20)
    width = lens[int(len(lens) * 0.8)] if lens else 80
    b = Builder()
    last_num = [None]
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        m = RE_PARTE.match(s)
        if m:
            title = s
            j = i + 1
            names = []
            while j < n and is_caps(lines[j].strip()) and not RE_DIV.match(lines[j].strip()) \
                    and not RE_ART.match(lines[j].strip()) and len(names) < 4:
                names.append(lines[j].strip())
                j += 1
            if names and not m.group(2).strip():
                title = s + " — " + " ".join(names)
            else:
                j = i + 1
            b.heading("PARTE", re.sub(r"\s+", " ", title))
            i = j
            continue
        m = RE_DIV.match(s)
        if m and (is_caps(m.group(1)) or len(s) < 80):
            kind = re.sub(r"[ÍÓ]", lambda c: {"Í": "I", "Ó": "O"}[c.group(0)], m.group(1).upper())
            title = s
            # absorb following all-caps lines as the division name
            j = i + 1
            if not m.group(3).strip():
                names = []
                while j < n and is_caps(lines[j].strip()) and not RE_DIV.match(lines[j].strip()) \
                        and not RE_ART.match(lines[j].strip()) and len(names) < 4:
                    names.append(lines[j].strip())
                    j += 1
                if not names and j < n:
                    nl = lines[j].strip()
                    if nl and len(nl) < 120 and not RE_DIV.match(nl) and not RE_ART.match(nl) \
                            and not nl.endswith((".", ";", ":", ",")) and nl[:1].isupper():
                        names.append(nl)
                        j += 1
                if names:
                    title = s + " — " + " ".join(names)
            if (is_caps(m.group(1)) and is_caps(s)) or (not m.group(3).strip() and m.group(1)[:1].isupper()):
                b.heading(kind, re.sub(r"\s+", " ", title))
                i = j
                continue
        m = RE_ART.match(s)
        if m:
            num = re.sub(r"\s+", " ", m.group(2)).strip()
            rest = m.group(3).strip()
            # PDF text sometimes splits the number: "Artículo 16 1. Las ..." for article 161
            sp = re.match(r"^(\d{1,2})\s*(?:\.-|\.|-|–)\s*(.*)$", rest)
            if sp and num.isdigit() and last_num[0] is not None and int(num + sp.group(1)) == last_num[0] + 1:
                num, rest = num + sp.group(1), sp.group(2)
            if num.isdigit():
                last_num[0] = int(num)
            nxt_line = lines[i + 1].strip() if i + 1 < n else ""
            if rest and len(rest) < 90 and not rest.endswith((".", ":", ";", ",")) and not re.search(r"[.:;]\s+\S", rest) \
                    and rest.split()[-1].lower() not in STOPWORDS \
                    and nxt_line[:1].isupper() and not RE_ART.match(nxt_line) and not RE_DIV.match(nxt_line):
                b.article(f"{article_word} {num}. {rest}", "")
            else:
                b.article(f"{article_word} {num}", rest)
            i += 1
            continue
        if RE_DISP.match(s) and is_caps(s) and "POR TANTO" not in s:
            title = s
            j = i + 1
            while j < n and is_caps(lines[j].strip()) and not RE_DIV.match(lines[j].strip()) \
                    and not RE_ART.match(lines[j].strip()) and not RE_ORDINAL_DISP.match(lines[j].strip()) and j - i < 3:
                title += " " + lines[j].strip()
                j += 1
            b.heading("DISP", re.sub(r"\s+", " ", title))
            i = j
            continue
        m = RE_ORDINAL_DISP.match(s)
        if m and b.has_disp and len(m.group(2).strip()) < 25:
            b.article(m.group(1) + m.group(2).rstrip(), m.group(4))
            i += 1
            continue
        # paragraph logic
        if b.para:
            prev = b.para[-1].rstrip()
            new_para = False
            if RE_LISTITEM.match(s):
                new_para = True
            elif raw.startswith(" ") and prev.endswith((".", ":", ";")):
                new_para = True
            elif prev.endswith((".", ":", ";", ".”", ".\"")) and s[:1].isupper() and len(prev) < max(45, 0.8 * width):
                new_para = True
            elif re.match(r"(Considerando|CONSIDERANDO|Vista|Visto|VISTA|VISTO|POR TANTO|Por tanto|HA DADO|DADA|Dada|Dado|DADO)\b", s) \
                    and prev.endswith((".", ":", ";")):
                new_para = True
            if new_para:
                b.flush()
        b.line(s)
        i += 1
    return "\n\n".join(b.finish())


def render(front, title, body_md, notes=None, preamble=None):
    import yaml
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
    parts = ["---", fm, "---", "", f"# {title}", ""]
    if preamble:
        parts += [preamble, ""]
    parts.append(body_md)
    if notes:
        parts += ["", "---", ""]
        parts += ["## Notas de la edición", ""]
        for k in sorted(notes):
            if f"[^{k}]" in body_md:
                parts.append(f"[^{k}]: {notes[k]}")
            else:
                parts.append(f"({k}) {notes[k]}")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def blocks_to_md(blocks, article_word="Artículo"):
    """Like lines_to_md, but for already-delimited paragraphs (e.g. from HTML): each block is
    one paragraph; headings/articles are detected at block start; blocks are never joined."""
    b = Builder()
    n = len(blocks)
    i = 0
    while i < n:
        s = re.sub(r"\s+", " ", blocks[i]).strip()
        if not s:
            i += 1
            continue
        m = RE_PARTE.match(s)
        if m and is_caps(s) and len(s) < 200:
            b.heading("PARTE", s)
            i += 1
            continue
        m = RE_DIV.match(s)
        if m and is_caps(m.group(1)) and len(s) < 250 and (is_caps(s) or not m.group(3).strip() or len(s) < 120):
            kind = re.sub(r"[ÍÓ]", lambda c: {"Í": "I", "Ó": "O"}[c.group(0)], m.group(1).upper())
            title = s
            j = i + 1
            if not m.group(3).strip() and j < n:
                nl = re.sub(r"\s+", " ", blocks[j]).strip()
                if nl and len(nl) < 200 and not RE_DIV.match(nl) and not RE_ART.match(nl) and not RE_PARTE.match(nl) \
                        and (is_caps(nl) or not nl.endswith((".", ";", ":"))):
                    title = s + " — " + nl
                    j += 1
            b.heading(kind, title)
            i = j
            continue
        m = RE_ART.match(s)
        if m:
            num = re.sub(r"\s+", " ", m.group(2)).strip()
            rest = m.group(3).strip()
            b.article(f"{article_word} {num}", rest)
            b.flush()
            i += 1
            continue
        if RE_DISP.match(s) and is_caps(s) and len(s) < 150:
            b.heading("DISP", s)
            i += 1
            continue
        b.line(s)
        b.flush()
        i += 1
    return "\n\n".join(b.finish())
