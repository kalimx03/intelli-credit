import pdfplumber
import io
import logging
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AUDIT FIX 8: Input size limits and safe chunking for large PDFs.
# Per-page extraction is isolated — one corrupt page cannot abort the job.
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES  = 20 * 1024 * 1024   # 20 MB hard limit
MAX_PAGES_TO_PROCESS = 60                  # beyond this, yield diminishing returns
MAX_OUTPUT_CHARS     = 60_000             # ~15k tokens; safe for Claude context
MAX_CHARS_PER_PAGE   = 4_000             # prevent one page swamping the budget


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF supplied as bytes.

    Hardening:
    - Rejects files over MAX_FILE_SIZE_BYTES.
    - Processes at most MAX_PAGES_TO_PROCESS pages.
    - Isolates each page in its own try/except — corrupt page != total failure.
    - Deduplicates table rows that pdfplumber also captures in page text.
    - Hard-caps total output at MAX_OUTPUT_CHARS with a clear truncation marker.
    """
    size = len(file_bytes)
    if size == 0:
        raise ValueError("Uploaded file is empty (0 bytes).")
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size {size / 1024 / 1024:.1f} MB exceeds the "
            f"{MAX_FILE_SIZE_BYTES // 1024 // 1024} MB limit. "
            "Please upload a smaller document or extract the relevant sections."
        )

    text_parts: List[str] = []
    pages_processed = 0
    pages_failed = 0

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                raise ValueError("PDF contains no pages.")

            pages_to_read = min(total_pages, MAX_PAGES_TO_PROCESS)
            if total_pages > MAX_PAGES_TO_PROCESS:
                logger.warning(
                    "PDF has %d pages; processing only first %d.",
                    total_pages, MAX_PAGES_TO_PROCESS
                )

            for page_num in range(pages_to_read):
                page = pdf.pages[page_num]
                page_label = f"--- Page {page_num + 1} of {total_pages} ---"
                page_text = ""

                try:
                    raw = page.extract_text()
                    if raw:
                        page_text = raw[:MAX_CHARS_PER_PAGE]
                        if len(raw) > MAX_CHARS_PER_PAGE:
                            page_text += f"\n[Page {page_num+1} text truncated]"
                except Exception as e:
                    pages_failed += 1
                    logger.warning("Page %d text extraction failed: %s", page_num + 1, e)

                table_lines: List[str] = []
                try:
                    tables = page.extract_tables()
                    for table in (tables or []):
                        if not table:
                            continue
                        for row in table:
                            if not row:
                                continue
                            cells = [str(c).strip() if c else "" for c in row]
                            # Skip rows whose content already appears in page text
                            row_line = " | ".join(c for c in cells if c)
                            if row_line and row_line not in page_text:
                                table_lines.append(row_line)
                except Exception as e:
                    logger.warning("Page %d table extraction failed: %s", page_num + 1, e)

                parts: List[str] = [page_label]
                if page_text:
                    parts.append(page_text)
                if table_lines:
                    parts.append("[TABLES]\n" + "\n".join(table_lines))
                if len(parts) > 1:
                    text_parts.append("\n".join(parts))
                    pages_processed += 1

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"PDF could not be opened or parsed: {e}") from e

    if not text_parts:
        hint = ""
        if pages_failed > 0:
            hint = f" ({pages_failed} pages failed — document may be image-based.)"
        raise ValueError(
            "No extractable text found in the PDF." + hint +
            " Ensure the document is text-based, not a scanned image."
        )

    full_text = "\n\n".join(text_parts)

    if len(full_text) > MAX_OUTPUT_CHARS:
        cut = full_text[:MAX_OUTPUT_CHARS]
        last_nl = cut.rfind("\n", MAX_OUTPUT_CHARS - 200)
        if last_nl > MAX_OUTPUT_CHARS // 2:
            cut = cut[:last_nl]
        full_text = cut + (
            f"\n\n[DOCUMENT TRUNCATED: first {MAX_OUTPUT_CHARS:,} chars of "
            f"{len(full_text):,} processed. Later figures may be missing.]"
        )
        logger.info("PDF text truncated to %d chars.", MAX_OUTPUT_CHARS)

    logger.info(
        "PDF extraction: %d pages processed, %d failed, %d chars output.",
        pages_processed, pages_failed, len(full_text)
    )
    return full_text
