"""PDF manipulation service for combining page PDFs into notebook PDFs."""

import logging
from io import BytesIO

from pypdf import PdfMerger, PdfReader

logger = logging.getLogger(__name__)


class PDFService:
    """Service for PDF operations like merging and manipulation."""

    @staticmethod
    def combine_page_pdfs(page_pdfs: list[bytes]) -> bytes:
        """
        Combine multiple page PDFs into a single notebook PDF.

        Args:
            page_pdfs: List of PDF bytes, one per page (in order)

        Returns:
            Combined PDF as bytes

        Raises:
            Exception: If PDF combination fails
        """
        if not page_pdfs:
            raise ValueError("No PDFs provided to combine")

        try:
            merger = PdfMerger()

            for page_pdf_bytes in page_pdfs:
                pdf_stream = BytesIO(page_pdf_bytes)
                merger.append(pdf_stream)

            # Write combined PDF to bytes
            output_stream = BytesIO()
            merger.write(output_stream)
            merger.close()

            output_stream.seek(0)
            combined_pdf = output_stream.read()

            logger.info(f"Combined {len(page_pdfs)} pages into PDF ({len(combined_pdf)} bytes)")
            return combined_pdf

        except Exception as e:
            logger.error(f"Failed to combine PDFs: {e}")
            raise

    @staticmethod
    def create_placeholder_pdf(text: str) -> bytes:
        """
        Create a minimal single-page PDF with centered text.

        Args:
            text: The placeholder text to display on the page

        Returns:
            PDF bytes for a single-page placeholder
        """
        # US Letter: 612 x 792 points
        width, height = 612, 792
        font_size = 14
        # Approximate text width for centering (Helvetica ~0.5 * font_size per char)
        text_width = len(text) * font_size * 0.5
        x = (width - text_width) / 2
        y = height / 2

        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        content_stream = (
            f"BT /F1 {font_size} Tf 0.6 0.6 0.6 rg "
            f"{x:.1f} {y:.1f} Td ({safe_text}) Tj ET"
        )
        stream_bytes = content_stream.encode("latin-1")
        stream_len = len(stream_bytes)

        # Build a minimal valid PDF manually
        pdf_parts = []
        pdf_parts.append(b"%PDF-1.4\n")

        # Object 1: Catalog
        pdf_parts.append(b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")

        # Object 2: Pages
        pdf_parts.append(b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n")

        # Object 3: Page
        pdf_parts.append(
            f"3 0 obj<</Type/Page/Parent 2 0 R"
            f"/MediaBox[0 0 {width} {height}]"
            f"/Resources<</Font<</F1 4 0 R>>>>>>"
            f"/Contents 5 0 R>>endobj\n".encode("latin-1")
        )

        # Object 4: Font
        pdf_parts.append(
            b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        )

        # Object 5: Content stream
        pdf_parts.append(
            f"5 0 obj<</Length {stream_len}>>stream\n".encode("latin-1")
        )
        pdf_parts.append(stream_bytes)
        pdf_parts.append(b"\nendstream\nendobj\n")

        # Calculate xref offsets
        body = b"".join(pdf_parts)
        offsets = []
        pos = 0
        full = body
        for i in range(1, 6):
            marker = f"{i} 0 obj".encode("latin-1")
            offset = full.find(marker, pos)
            offsets.append(offset)
            pos = offset + 1

        xref_offset = len(body)
        xref = "xref\n0 6\n0000000000 65535 f \n"
        for off in offsets:
            xref += f"{off:010d} 00000 n \n"
        xref += f"trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF"

        return body + xref.encode("latin-1")

    @staticmethod
    def get_page_count(pdf_bytes: bytes) -> int:
        """
        Get the number of pages in a PDF.

        Args:
            pdf_bytes: PDF content as bytes

        Returns:
            Number of pages
        """
        try:
            pdf_stream = BytesIO(pdf_bytes)
            reader = PdfReader(pdf_stream)
            return len(reader.pages)
        except Exception as e:
            logger.error(f"Failed to get page count: {e}")
            return 0
