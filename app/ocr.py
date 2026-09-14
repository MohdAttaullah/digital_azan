"""Optional local tools adapter. Output is untrusted, editable draft text only."""
import csv
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def extract(data, filename):
    suffix = Path(filename).suffix.lower()
    signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8"}
    if suffix not in signatures or not data.startswith(signatures[suffix]):
        raise ValueError("Upload a valid PDF, PNG or JPEG")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Upload limit is 8 MB")
    if not shutil.which("tesseract"):
        raise ValueError("Local OCR unavailable: install tesseract-ocr, or use CSV/manual entry")
    with tempfile.TemporaryDirectory(prefix="azan-ocr-") as folder:
        source = Path(folder) / ("upload" + suffix)
        source.write_bytes(data)
        if suffix == ".pdf":
            if not shutil.which("pdftoppm"):
                raise ValueError("PDF OCR requires poppler-utils; CSV/manual entry remains available")
            subprocess.run(["pdftoppm", "-f", "1", "-l", "3", "-scale-to", "1800", "-png",
                            str(source), str(Path(folder) / "page")],
                           check=True, timeout=45, capture_output=True)
            pages = sorted(Path(folder).glob("page-*.png"))
        else:
            # Pillow is optional with the OCR extra; enforce a decoded pixel limit.
            try:
                from PIL import Image
            except ImportError as exc:
                raise ValueError("Image OCR requires requirements-ocr.txt; use CSV/manual entry") from exc
            Image.MAX_IMAGE_PIXELS = 20_000_000
            with Image.open(source) as img:
                if img.width * img.height > 20_000_000:
                    raise ValueError("Image exceeds 20 megapixels; resize before importing")
                img.verify()
            pages = [source]
        lines = []
        for page in pages:
            result = subprocess.run(["tesseract", str(page), "stdout", "--psm", "6", "tsv"],
                                    check=True, capture_output=True, text=True, timeout=45)
            groups = {}
            for word in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
                if not word.get("text", "").strip():
                    continue
                key = tuple(word.get(k) for k in ("block_num", "par_num", "line_num"))
                groups.setdefault(key, []).append(word)
            for words in groups.values():
                text = " ".join(w["text"] for w in words)
                confidence = min(float(w["conf"]) for w in words)
                day = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
                times = re.findall(r"\b\d{1,2}:\d{2}\b", text)
                lines.append({"text": text, "confidence": round(confidence),
                              "date": day.group() if day else "", "times": times})
        return {"lines": lines, "active": False,
                "warnings": ["OCR is a draft. Confirm column meanings; Sehri is not automatically Fajr.",
                             "Only ISO Gregorian dates are detected. Enter other date formats manually.",
                             "PDF extraction is limited to the first three pages."]}
