"""Convert reMarkable .rm files to PDF using rmscene and rmc.

This module uses rmscene to parse .rm files, rmc to render as SVG,
converts to PDF, and sends to Claude Vision for OCR.

Includes automatic color patching via rm_color_patch module.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

import rmc
import rmscene

# Import color patch module - this auto-patches on import
from app.core import rm_color_patch

logger = logging.getLogger(__name__)


class RMConverter:
    """Convert reMarkable annotations to OCR-ready PDFs."""

    def __init__(self):
        """Initialize converter and ensure color patches are applied."""
        # Color patch is auto-applied on import, but verify
        self._verify_patches()

    def _verify_patches(self):
        """Verify that color patches were successfully applied."""
        try:
            import rmc.exporters.writing_tools as writing_tools

            if not hasattr(writing_tools, "_rmc_color_patched"):
                logger.warning("Color patch not applied, attempting to patch now")
                rm_color_patch.patch_rmc_colors()
        except ImportError:
            logger.warning("rmc library not available, color patching skipped")

    def rm_to_svg(self, rm_path: Path) -> str:
        """
        Convert .rm file to SVG string using rmc.

        Args:
            rm_path: Path to .rm file

        Returns:
            SVG content as string

        Raises:
            FileNotFoundError: If .rm file doesn't exist
            ValueError: If .rm file is invalid or empty
        """
        if not rm_path.exists():
            raise FileNotFoundError(f"File not found: {rm_path}")

        logger.info(f"Converting {rm_path.name} to SVG")

        try:
            # Create temporary SVG file
            with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as svg_file:
                svg_path = svg_file.name

            try:
                # Convert .rm file to SVG using rmc (uses patched color palette)
                rmc.rm_to_svg(str(rm_path), svg_path)

                # Read SVG content
                svg = Path(svg_path).read_text()

                if not svg:
                    raise ValueError(f"Empty SVG generated from: {rm_path}")

                logger.debug(f"Generated SVG with {len(svg)} characters")
                return svg

            finally:
                # Clean up temp file
                Path(svg_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to convert {rm_path.name} to SVG: {e}")
            raise

    def svg_to_pdf_bytes(self, svg_content: str) -> bytes:
        """
        Convert SVG to PDF bytes using rsvg-convert command-line tool.

        This matches the approach used in remarkable-integration.

        Args:
            svg_content: SVG content as string

        Returns:
            PDF as bytes

        Raises:
            ValueError: If SVG cannot be parsed or converted
            RuntimeError: If rsvg-convert is not available
        """
        if not svg_content or not svg_content.strip():
            raise ValueError("Empty SVG content")

        logger.debug("Converting SVG to PDF with rsvg-convert")

        try:
            # Write SVG to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False) as svg_file:
                svg_file.write(svg_content)
                svg_path = svg_file.name

            # Create temporary PDF file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_file:
                pdf_path = pdf_file.name

            try:
                # Convert using rsvg-convert command
                subprocess.run(
                    ['rsvg-convert', '-f', 'pdf', '-o', pdf_path, svg_path],
                    capture_output=True,
                    check=True
                )

                # Read PDF bytes
                pdf_bytes = Path(pdf_path).read_bytes()

                if not pdf_bytes:
                    raise ValueError("rsvg-convert returned empty PDF")

                logger.debug(f"Generated PDF with {len(pdf_bytes)} bytes")
                return pdf_bytes

            finally:
                # Clean up temporary files
                Path(svg_path).unlink(missing_ok=True)
                Path(pdf_path).unlink(missing_ok=True)

        except subprocess.CalledProcessError as e:
            logger.error(f"rsvg-convert failed: {e.stderr.decode() if e.stderr else str(e)}")
            raise RuntimeError(f"SVG to PDF conversion failed: {e.stderr.decode() if e.stderr else str(e)}")
        except FileNotFoundError:
            raise RuntimeError(
                "rsvg-convert not found. Install with: brew install librsvg"
            )
        except Exception as e:
            logger.error(f"Failed to convert SVG to PDF: {e}")
            raise

    def rm_to_pdf_bytes(self, rm_path: Path) -> bytes:
        """
        Convert .rm file directly to PDF bytes.

        This uses rmc to convert to SVG, then rsvg-convert to generate PDF.

        Args:
            rm_path: Path to .rm file

        Returns:
            PDF as bytes

        Raises:
            FileNotFoundError: If .rm file doesn't exist
            ValueError: If conversion fails
        """
        logger.info(f"Converting {rm_path.name} to PDF")
        svg = self.rm_to_svg(rm_path)
        return self.svg_to_pdf_bytes(svg)

    def has_content(self, rm_path: Path) -> bool:
        """
        Check if .rm file has any content (strokes, text, etc.).

        Args:
            rm_path: Path to .rm file

        Returns:
            True if file has strokes/content, False if empty or invalid
        """
        if not rm_path.exists():
            logger.warning(f"File does not exist: {rm_path}")
            return False

        try:
            with open(rm_path, "rb") as f:
                scene_blocks = list(rmscene.read_blocks(f))

            # Check if any scene items exist
            has_items = len(scene_blocks) > 0
            logger.debug(
                f"{rm_path.name} has {'content' if has_items else 'no content'} "
                f"({len(scene_blocks)} blocks)"
            )
            return has_items

        except Exception as e:
            logger.warning(f"Failed to check content in {rm_path.name}: {e}")
            return False
