"""Convert reMarkable .rm files to PDF using rmscene and SVG.

This module uses rmscene to parse .rm files, renders them as SVG,
converts to PDF, and sends to Claude Vision for OCR.

Includes monkey patching for additional highlight colors not in rmscene.
"""

import io
from pathlib import Path

import rmscene
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg


class RMConverter:
    """Convert reMarkable annotations to OCR-ready PDFs."""

    def __init__(self):
        """Initialize converter and apply monkey patches."""
        self._apply_color_patches()

    def _apply_color_patches(self):
        """
        Monkey patch rmscene to support additional highlight colors.

        TODO: Add the specific color codes that were patched in remarkable-integration.
        The user mentioned needing to patch for additional highlight colors.
        """
        # Placeholder for monkey patch
        # Original rmscene might not know about all highlight colors
        # Need to get the actual patch from remarkable-integration
        pass

    def rm_to_svg(self, rm_path: Path) -> str:
        """
        Convert .rm file to SVG string.

        Args:
            rm_path: Path to .rm file

        Returns:
            SVG content as string
        """
        # Parse .rm file with rmscene
        with open(rm_path, "rb") as f:
            scene = rmscene.read_blocks(f)

        # Render to SVG
        svg = rmscene.scene_stream.render_to_svg(scene)
        return svg

    def svg_to_pdf_bytes(self, svg_content: str) -> bytes:
        """
        Convert SVG to PDF bytes.

        Args:
            svg_content: SVG content as string

        Returns:
            PDF as bytes
        """
        # Parse SVG
        svg_io = io.StringIO(svg_content)
        drawing = svg2rlg(svg_io)

        if drawing is None:
            raise ValueError("Failed to parse SVG")

        # Render to PDF
        pdf_io = io.BytesIO()
        renderPDF.drawToFile(drawing, pdf_io, fmt="PDF")
        pdf_io.seek(0)

        return pdf_io.read()

    def rm_to_pdf_bytes(self, rm_path: Path) -> bytes:
        """
        Convert .rm file directly to PDF bytes.

        Args:
            rm_path: Path to .rm file

        Returns:
            PDF as bytes
        """
        svg = self.rm_to_svg(rm_path)
        return self.svg_to_pdf_bytes(svg)

    def has_content(self, rm_path: Path) -> bool:
        """
        Check if .rm file has any content.

        Args:
            rm_path: Path to .rm file

        Returns:
            True if file has strokes/content
        """
        try:
            with open(rm_path, "rb") as f:
                scene = rmscene.read_blocks(f)

            # Check if any scene items exist
            return len(scene) > 0
        except Exception:
            return False
