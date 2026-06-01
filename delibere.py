import csv
import html
import json
import re
import time
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests


SITE_URL = "https://trasparenza.regione.puglia.it"
BURP_URL = "https://burp.regione.puglia.it"
LIST_PATH = "/provvedimenti/provvedimenti-organi-indirizzo-politico/provvedimenti-della-giunta-regionale"
LIST_URL = f"{SITE_URL}{LIST_PATH}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}

FIELDNAMES = [
    "regione",
    "anno_ricerca",
    "keyword_ricerca",
    "pagina",
    "id",
    "proponente",
    "struttura",
    "assessorato",
    "tipo_atto",
    "numero_adozione",
    "codice_approvazione",
    "numero_seduta",
    "numero_delibera",
    "data_adozione",
    "data_seduta",
    "protocollo",
    "id_doc_info",
    "oggetto",
    "pubblicazione_bur",
    "data_pubblicazione_bur",
    "data_pubblicazione",
    "dettaglio_url",
    "burp_url",
    "pdf_url",
    "pdf_nome",
    "allegati_url",
    "allegati_nomi",
    "programma",
    "azioni",
    "priorita",
    "cup",
    "dgr",
    "determinazioni",
    "tipo_manovra",
    "beneficiario",
    "importi",
]


class DelibereListParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {
                "headers": attrs.get("headers", ""),
                "text": [],
                "hrefs": [],
                "datetime": "",
            }
        elif tag == "a" and self.cell is not None:
            href = attrs.get("href")
            if href:
                self.cell["hrefs"].append(html.unescape(href))
        elif tag == "time" and self.cell is not None:
            self.cell["datetime"] = attrs.get("datetime", "")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cell["text"] = cleantext(" ".join(self.cell["text"]))
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any("view-field-numero-del-provvedimento" in cell["headers"] for cell in self.row):
                self.rows.append(self.row)
            self.row = None


def cleantext(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def absolutetrasparenza(url):
    return urljoin(SITE_URL, html.unescape(url or ""))


def absoluteburp(url):
    absolute = urljoin(BURP_URL, html.unescape(url or ""))
    return absolute.replace("http://burp.regione.puglia.it", BURP_URL, 1)


def datebounds(anno):
    if not anno:
        return "", ""
    return f"{anno}-01-01", f"{anno}-12-31"


def buildparams(anno, keyword, page):
    startdate, enddate = datebounds(anno)
    params = {
        "field_numero_del_provvedimento_value": "",
        "field_oggetto_value": keyword or "",
        "field_struttura_value": "",
        "field_codice_cifra_value": "",
        "field_data_del_provvedimento_value[min]": startdate,
        "field_data_del_provvedimento_value[max]": enddate,
        "page": str(max(0, page - 1)),
    }
    return params


def fetchpage(session, anno, keyword, page, timeout):
    response = session.get(LIST_URL, params=buildparams(anno, keyword, page), timeout=timeout)
    response.raise_for_status()
    return {"html": response.text}


def findall(pattern, text):
    values = re.findall(pattern, text or "", flags=re.I)
    cleaned = []
    for value in values:
        if isinstance(value, tuple):
            value = next((item for item in value if item), "")
        value = cleantext(value).upper()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def classifymanovra(text):
    upper = (text or "").upper()
    checks = [
        ("revoca", ["REVOCA"]),
        ("liquidazione saldo", ["LIQUIDAZIONE SALDO", "SALDO IN UNICA SOLUZIONE"]),
        ("liquidazione sal", ["LIQUIDAZIONE SAL"]),
        ("liquidazione", ["LIQUIDAZIONE"]),
        ("concessione", ["CONCESSIONE", "CONCESSO"]),
        ("approvazione", ["APPROVAZIONE", "APPROVATO"]),
        ("impegno", ["IMPEGNO", "IMPEGNARE"]),
        ("accertamento", ["ACCERTAMENTO"]),
        ("proroga", ["PROROGA"]),
        ("rideterminazione", ["RIDETERMINAZIONE"]),
        ("modifica", ["MODIFICA", "VARIAZIONE"]),
        ("scorrimento", ["SCORRIMENTO"]),
        ("ammissione", ["AMMISSIONE", "AMMESS"]),
    ]
    for label, keywords in checks:
        if any(keyword in upper for keyword in keywords):
            return label
    return "altro"


def extractbeneficiario(text):
    patterns = [
        r"A FAVORE (?:DEL|DELLA|DELL'|DEI|DEGLI|DELLE|DI)\s+(.+?)(?:\s+PER\s+LA|\s+PER\s+IL|\s+CUP\b|\s+-\s+|\.$)",
        r"BENEFICIARI(?:O|A)?\s+(.+?)(?:\s+PER\s+LA|\s+PER\s+IL|\s+CUP\b|\s+-\s+|\.$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.I)
        if match:
            return cleantext(match.group(1).strip(" .;:-\"'"))
    return ""


def extractprogramma(text):
    upper = (text or "").upper()
    if "PR" in upper and "FESR" in upper and ("2021" in upper or "21-27" in upper):
        return "PR Puglia FESR-FSE+ 2021-2027"
    if "POC PUGLIA" in upper:
        return "POC Puglia FESR-FSE 2014-2020"
    if "POR PUGLIA" in upper:
        return "POR Puglia FESR-FSE 2014-2020"
    if "FESR" in upper:
        return "FESR"
    return ""


def enrichrecord(record):
    text = record.get("oggetto", "")
    record["programma"] = extractprogramma(text)
    record["azioni"] = ";".join(
        findall(r"(?:SUB[\s-]*AZ\.?|SUB[\s-]*AZIONE|AZ\.?|AZIONE)\s*(\d+(?:\.\d+){1,2})", text)
    )
    record["priorita"] = ";".join(findall(r"PRIORIT[ÀA']?[\s.:-]*([IVXLCDM]+|\d+)", text))
    record["cup"] = ";".join(findall(r"\b[A-Z][0-9]{2}[A-Z0-9]{12}\b", text))
    record["dgr"] = ";".join(findall(r"D\.?\s*G\.?\s*R\.?\s*(?:N\.?\s*)?(\d+(?:/\d{2,4})?)", text))
    record["determinazioni"] = ";".join(findall(r"DET(?:ERMINAZION(?:E|I))?\.?\s*(?:N\.?\s*)?(\d+(?:/\d{4})?)", text))
    record["tipo_manovra"] = classifymanovra(text)
    record["beneficiario"] = extractbeneficiario(text)
    record["importi"] = ";".join(findall(r"(?:EURO|EUR|€)\s*([0-9][0-9.\s]*,\d{2})", text))
    return record


def cellbyheader(row, headerpart):
    for cell in row:
        if headerpart in cell["headers"]:
            return cell
    return {"text": "", "hrefs": [], "datetime": ""}


def deliberaid(url):
    match = re.search(r"/(\d+)(?:[/?#]|$)", url or "")
    return match.group(1) if match else ""


def datefromdatetime(value):
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    if match:
        return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    return ""


def parserow(row, anno, keyword, page):
    numero = cleantext(cellbyheader(row, "view-field-numero-del-provvedimento")["text"])
    oggettocell = cellbyheader(row, "view-field-oggetto-table-column")
    strutturacell = cellbyheader(row, "view-nothing-table-column")
    datacell = cellbyheader(row, "view-field-data-del-provvedimento")
    linkcell = cellbyheader(row, "view-nothing-1-table-column")

    dettaglio = absolutetrasparenza(next(iter(oggettocell["hrefs"]), ""))
    burpurl = absoluteburp(next(iter(linkcell["hrefs"]), ""))
    data = cleantext(datacell["text"]) or datefromdatetime(datacell["datetime"])
    struttura = cleantext(strutturacell["text"])
    oggetto = cleantext(oggettocell["text"])

    record = {
        "regione": "Puglia",
        "anno_ricerca": str(anno),
        "keyword_ricerca": keyword,
        "pagina": str(page),
        "id": deliberaid(dettaglio),
        "proponente": struttura,
        "struttura": struttura,
        "assessorato": struttura,
        "tipo_atto": "Deliberazione della Giunta regionale",
        "numero_adozione": numero,
        "codice_approvazione": numero,
        "numero_seduta": "",
        "numero_delibera": numero,
        "data_adozione": data,
        "data_seduta": data,
        "protocollo": numero,
        "id_doc_info": "",
        "oggetto": oggetto,
        "pubblicazione_bur": "",
        "data_pubblicazione_bur": "",
        "data_pubblicazione": "",
        "dettaglio_url": dettaglio,
        "burp_url": burpurl,
        "pdf_url": "",
        "pdf_nome": "",
        "allegati_url": "",
        "allegati_nomi": "",
    }
    return enrichrecord(record)


def parserows(payload, anno, keyword, page):
    parser = DelibereListParser()
    parser.feed(payload.get("html", ""))
    return [parserow(row, anno, keyword, page) for row in parser.rows]


def totalpages(payload):
    htmltext = html.unescape(payload.get("html", ""))
    pageindexes = [int(value) for value in re.findall(r"[?&]page=(\d+)", htmltext)]
    if pageindexes:
        return max(pageindexes) + 1
    return 1


def totalrecords(payload, records):
    return len(records)


def contentfilename(response, fallback):
    header = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header)
    if match:
        return Path(unquote(match.group(1))).name
    return fallback


def filenamefromurl(url, fallback):
    match = re.search(r"/([^/?]+\.pdf)(?:[/?#]|$)", url or "", flags=re.I)
    if match:
        return unquote(match.group(1))
    return fallback


def fetchpdfurl(session, burpurl, timeout):
    if not burpurl:
        return ""
    response = session.get(burpurl, timeout=timeout)
    response.raise_for_status()
    match = re.search(r'var\s+url\s*=\s*"([^"]*)"', response.text)
    if not match:
        return ""
    url = html.unescape(match.group(1)).strip()
    if not url or url.lower() == "null":
        return ""
    return absoluteburp(url)


def downloadpdf(session, url, folder, fallback, timeout):
    folder.mkdir(parents=True, exist_ok=True)
    response = session.get(url, stream=True, timeout=timeout)
    response.raise_for_status()
    filename = contentfilename(response, fallback)
    path = folder / filename
    with path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                handle.write(chunk)
    return str(path)


def downloadrecordpdf(session, record, folder, timeout):
    files = []
    if record.get("pdf_url"):
        fallback = f"Delibera {record['codice_approvazione']}-{record['anno_ricerca']}.pdf"
        files.append(downloadpdf(session, record["pdf_url"], folder, fallback, timeout))
    for index, url in enumerate(splitvalues(record.get("allegati_url")), start=1):
        fallback = f"Delibera {record['codice_approvazione']}-{record['anno_ricerca']}-allegato-{index}.pdf"
        files.append(downloadpdf(session, url, folder, fallback, timeout))
    return files


def scraperesults(
    anno,
    keyword,
    maxpages=None,
    delay=0.4,
    includelinks=False,
    download=False,
    maxpdf=None,
    timeout=30,
    outputfolder="data",
):
    session = requests.Session()
    session.headers.update(HEADERS)
    allrecords = []
    pdfcount = 0
    page = 1
    pages = None

    while True:
        payload = fetchpage(session, anno, keyword, page, timeout)
        records = parserows(payload, anno, keyword, page)
        if pages is None:
            pages = totalpages(payload)
            print(f"Trovate {pages} pagine di risultati.")

        for record in records:
            if includelinks or download:
                pdfurl = fetchpdfurl(session, record.get("burp_url"), timeout)
                record["pdf_url"] = pdfurl
                record["pdf_nome"] = filenamefromurl(
                    pdfurl,
                    f"Delibera {record['codice_approvazione']}-{record['anno_ricerca']}.pdf",
                ) if pdfurl else ""

            fileurls = [record.get("pdf_url", "")] + splitvalues(record.get("allegati_url", ""))
            if download and any(fileurls) and (maxpdf is None or pdfcount < maxpdf):
                files = downloadrecordpdf(session, record, Path(outputfolder) / "pdf", timeout)
                record["pdf_file"] = ";".join(files)
                pdfcount += 1
                time.sleep(delay)

        allrecords.extend(records)
        print(f"Pagina {page}/{pages}: {len(records)} righe, totale {len(allrecords)}.")
        if page >= pages:
            break
        if maxpages is not None and page >= maxpages:
            break
        page += 1
        time.sleep(delay)

    return allrecords


def writecsv(path, records, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or FIELDNAMES
    extras = sorted({key for record in records for key in record.keys()} - set(names))
    names = names + extras
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(records)


def writejson(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def splitvalues(value):
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def countfield(records, field):
    counter = Counter()
    for record in records:
        values = splitvalues(record.get(field, ""))
        if not values:
            values = ["non rilevato"]
        for value in values:
            counter[value] += 1
    return [{"valore": value, "conteggio": count} for value, count in counter.most_common()]


def writesummary(path, rows):
    writecsv(path, rows, ["valore", "conteggio"])


def writesummaries(records, anno, keyword, folder):
    suffix = f"{anno}_{keyword.lower()}".replace(" ", "_")
    writesummary(folder / f"riepilogo_azioni_{suffix}.csv", countfield(records, "azioni"))
    writesummary(folder / f"riepilogo_manovre_{suffix}.csv", countfield(records, "tipo_manovra"))
    writesummary(folder / f"riepilogo_beneficiari_{suffix}.csv", countfield(records, "beneficiario"))
    writesummary(folder / f"riepilogo_proponenti_{suffix}.csv", countfield(records, "proponente"))
