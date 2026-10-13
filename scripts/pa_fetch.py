#!/usr/bin/env python3
"""Panama: Legispan, the legislative information system of the Asamblea Nacional
(https://legispan.asamblea.gob.pa/). Its public search API returns, for every norm, metadata
and the text of the Gaceta Oficial publication ("content").

  fetch:   GET /api/search/norm?type[type]=<TYPE>&page=N&limit=100  -> $RAW/json/<type>/<page>.json
  convert: -> constitucion/, actos-legislativos/, leyes/<year>/, decretos-ley/<year>/, ...
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date

import requests
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pa_textmd as T  # noqa: E402

RAW = os.environ.get("RAW", "/Users/magicaltux/projects/lawcodex/_raw/pa")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "LawCodex/1.0 (+https://github.com/LawCodex)"
API = "https://legispan.asamblea.gob.pa/api/search/norm"
PUBLIC = "https://legispan.asamblea.gob.pa/norms/"
TODAY = date.today().isoformat()
TYPES = {"CONSTITUCION POLITICA": ("constitucion", "constitution"),
         "ACTO LEGISLATIVO": ("actos-legislativos", "constitutional-amendment"),
         "ACTO CONSTITUCIONAL": ("actos-constitucionales", "constitutional-act"),
         "LEY": ("leyes", "act"),
         "TEXTO UNICO": ("textos-unicos", "consolidated-text"),
         "DECRETO LEY": ("decretos-ley", "decree-law"),
         "DECRETO DE GABINETE": ("decretos-de-gabinete", "decree")}
LIMIT = 100
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "application/json"})


def get(params):
    for k in range(5):
        try:
            r = s.get(API, params=params, timeout=(30, 600))
            if r.status_code == 200:
                time.sleep(1)
                return r.json()
            print("HTTP", r.status_code, params, file=sys.stderr, flush=True)
        except (requests.RequestException, ValueError) as e:
            print("ERR", e, file=sys.stderr, flush=True)
        time.sleep(15 * (k + 1))
    raise RuntimeError(str(params))


def slug(t, n=60):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:n].rstrip("-")


def fetch():
    for t in TYPES:
        d = os.path.join(RAW, "json", slug(t))
        os.makedirs(d, exist_ok=True)
        page = 1
        while True:
            p = os.path.join(d, f"{page:04d}.json")
            if os.path.exists(p):
                data = json.load(open(p))
            else:
                data = get({"page": page, "limit": LIMIT, "type[type]": t, "sortKey": "publishedAt", "sortOrder": "asc"})
                json.dump(data, open(p, "w"), ensure_ascii=False)
            n = len(data.get("data", []))
            print(t, page, n, data.get("count"), flush=True)
            if n < LIMIT or page * LIMIT >= int(data.get("count") or 0):
                break
            page += 1


def pdfs():
    """For norms whose search record has no text ("content"), fetch the PDF stored by Legispan
    (normUrl), extract its text (the first page is Legispan's cover sheet) -> $RAW/pdftext/<id>.json."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(RAW, "pdftext")
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(RAW, "tmp.pdf")
    todo = []
    for t in TYPES:
        jd = os.path.join(RAW, "json", slug(t))
        for f in sorted(os.listdir(jd)) if os.path.isdir(jd) else []:
            for item in json.load(open(os.path.join(jd, f))).get("data", []):
                o = item.get("original", item)
                if len((o.get("content") or "").strip()) < 50 and o.get("normUrl") not in (None, "None", ""):
                    todo.append((o["id"], o["normUrl"]))
    print("pdfs to fetch", len(todo), flush=True)
    import threading
    from concurrent.futures import ThreadPoolExecutor
    local = threading.local()

    def one(item):
        nid, url = item
        out = os.path.join(d, nid + ".json")
        if os.path.exists(out):
            return
        if not hasattr(local, "s"):
            local.s = requests.Session()
            local.s.headers["User-Agent"] = UA
        tmp = os.path.join(RAW, f"tmp-{nid}.pdf")
        res = {"url": url, "pages": None}
        for k in range(3):
            try:
                r = local.s.get(url, timeout=(30, 600))
                time.sleep(1)
            except requests.RequestException as e:
                print("ERR", url, e, file=sys.stderr)
                time.sleep(15)
                continue
            if r.status_code != 200:
                res["error"] = r.status_code
                break
            open(tmp, "wb").write(r.content)
            if T.pdf_ok(tmp):
                try:
                    res["pages"] = T.extract_pages(tmp)
                except Exception as e:
                    res["error"] = str(e)
                break
        json.dump(res, open(out, "w"), ensure_ascii=False)
        if os.path.exists(tmp):
            os.remove(tmp)

    n = 0
    with ThreadPoolExecutor(3) as ex:
        for _ in ex.map(one, todo):
            n += 1
            if n % 250 == 0:
                print("pdf", n, len(todo), flush=True)


CONST_URL = "https://www.sinaproc.gob.pa/wp-content/uploads/2026/08/constitucion-politica-de-la-republica-de-panama.pdf"


def constitution():
    """Constitution in force: Legispan has no text for it; use the Asamblea Nacional's edition
    (1972 Constitution adjusted to the 1978, 1983, 1993, 1994 and 2004 reforms, after the Texto
    Único of Gaceta Oficial 25176 of 15-11-2004) as published on sinaproc.gob.pa."""
    d = os.path.join(RAW, "const")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "c.pdf")
    if not T.pdf_ok(p):
        open(p, "wb").write(s.get(CONST_URL, timeout=600).content)
    pages = T.extract_pages(p)
    start = next(i for i, t in enumerate(pages) if re.search(r"PRE[ÁA]MBULO", t))
    md = T.lines_to_md(T.clean_pages(pages[start:]))
    front = {"title": "Constitución Política de la República de Panamá", "identifier": "Texto Único, Gaceta Oficial 25176 (15-11-2004)",
             "type": "constitution", "jurisdiction": "pa", "language": "es", "date": "1972-10-11", "last_amended": "2004-11-15",
             "status": "in_force", "source": CONST_URL, "retrieved": TODAY}
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
    path = os.path.join(REPO, "constitucion", "constitucion-politica-1972-texto-unico-2004.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(["---", fm, "---", "", "# Constitución Política de la República de Panamá", "",
        "> Edición de la Asamblea Nacional: Constitución Política de 1972 ajustada a los Actos Reformatorios de 1978, al Acto "
        "Constitucional de 1983, a los Actos Legislativos No. 1 de 1993, No. 2 de 1994 y No. 1 de 2004, tomando como referencia "
        "el Texto Único publicado en la Gaceta Oficial No. 25176 del 15 de noviembre de 2004 (PDF publicado en sinaproc.gob.pa).",
        "", md, ""]))
    print("constitution", md.count("###### "))


DROP = [r"No\.\s*\d+[-\s]*[A-Z]?\s*Gaceta Oficial Digital,.*", r"Gaceta Oficial Digital", r"Para verificar la autenticidad de una representación",
        r"en el sitio web www\.gacetaoficial\.gob\.pa/validar-gaceta", r"GO[0-9A-F]{10,}"]


def as_obj(v):
    if isinstance(v, (dict, list)) or v is None:
        return v
    return v


def convert():
    counts = {}
    used = set()
    for t, (folder, typ) in TYPES.items():
        d = os.path.join(RAW, "json", slug(t))
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            for item in json.load(open(os.path.join(d, f))).get("data", []):
                o = item.get("original", item)
                content = o.get("content") or ""
                via_pdf = False
                if len(content.strip()) < 50:
                    pt = os.path.join(RAW, "pdftext", (o.get("id") or "") + ".json")
                    pages = json.load(open(pt)).get("pages") if os.path.exists(pt) else None
                    if not pages:
                        continue
                    if "LEGISPAN" in pages[0][:400]:
                        pages = pages[1:]
                    if not pages or sum(1 for p in pages if len(p.strip()) < 150) > 0.3 * len(pages):
                        counts["_scanned"] = counts.get("_scanned", 0) + 1
                        continue
                    content = "\n".join(pages)
                    via_pdf = True
                num = str(o.get("number") or "").strip()
                year = str(o.get("year") or (o.get("publishedAt") or "")[:4] or "s-f")
                pub = (o.get("publishedAt") or "")[:10] or None
                prom = o.get("promulgation") or {}
                gaceta = prom.get("number") if isinstance(prom, dict) else None
                title_txt = re.sub(r"\s+", " ", o.get("title") or "").strip()
                label = {"LEY": "Ley", "DECRETO LEY": "Decreto Ley", "DECRETO DE GABINETE": "Decreto de Gabinete",
                         "TEXTO UNICO": "Texto Único", "ACTO LEGISLATIVO": "Acto Legislativo",
                         "ACTO CONSTITUCIONAL": "Acto Constitucional", "CONSTITUCION POLITICA": "Constitución Política"}[t]
                title = f"{label} {num} de {year}".strip() + (f" — {title_txt}" if title_txt else "")
                base = f"{slug(num, 20) or 'sn'}-de-{year}"
                fn = os.path.join(folder, year, f"{base}.md") if folder not in ("constitucion",) else os.path.join(folder, f"{year}-{slug(title_txt, 50)}.md")
                k = 2
                while fn in used:
                    fn = re.sub(r"(-v\d+)?\.md$", f"-v{k}.md", fn)
                    k += 1
                used.add(fn)
                lines = [l.rstrip() for l in content.replace("\r", "").split("\n")]
                lines = [l for l in lines if l.strip() and not any(re.fullmatch(p, l.strip()) for p in DROP)]
                md = T.lines_to_md([lines])
                front = {"title": title, "identifier": f"{label} N° {num} de {year}", "type": typ, "jurisdiction": "pa",
                         "language": "es", "date": pub, "gaceta_oficial": gaceta, "status": "unknown",
                         "source": PUBLIC + o.get("id", ""), "source_pdf": o.get("normUrl") if o.get("normUrl") not in (None, "None") else None,
                         "retrieved": TODAY}
                fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000).strip()
                path = os.path.join(REPO, fn)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w", encoding="utf-8").write("\n".join(["---", fm, "---", "", f"# {title}", "",
                    ("> Texto extraído del PDF de la Gaceta Oficial almacenado por Legispan (Asamblea Nacional); texto original, no consolidado."
                     if via_pdf else "> Texto de la publicación en la Gaceta Oficial según Legispan (Asamblea Nacional); texto original, no consolidado."),
                    "", md, ""]))
                counts[folder] = counts.get(folder, 0) + 1
    print(counts)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("fetch", "all"):
        fetch()
    if cmd in ("pdfs", "all"):
        pdfs()
    if cmd in ("convert", "all"):
        convert()
    if cmd in ("constitution", "all"):
        constitution()
