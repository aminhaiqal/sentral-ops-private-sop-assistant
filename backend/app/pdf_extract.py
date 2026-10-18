"""Run PDF parsing in a separate process with a memory and CPU budget."""
import io
import json
import sys


def extract_pdf(data: bytes) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("This PDF is password protected. Upload an unlocked copy.")
    if len(reader.pages) > 100:
        raise ValueError("Upload a PDF with 100 pages or fewer.")
    parts = []
    length = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        length += len(text)
        if length > 200_000:
            raise ValueError("This document has too much text. Split it into smaller files.")
        parts.append(text)
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("This PDF has no selectable text. Upload a text-based PDF or Markdown file.")
    return {"text": text, "pages": len(reader.pages)}


if __name__ == "__main__":
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    try:
        print(json.dumps(extract_pdf(sys.stdin.buffer.read(10 * 1024 * 1024 + 1))))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({"error": "This PDF could not be read. Try exporting a new copy."}))
        sys.exit(1)
