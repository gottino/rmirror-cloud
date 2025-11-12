"""PDF manipulation service for combining page PDFs into notebook PDFs."""

import logging
from io import BytesIO

from pypdf import PdfMerger, PdfReader, PdfWriter

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
