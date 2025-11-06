"""Extract metadata from PDF and EPUB files."""

from io import BytesIO
from typing import BinaryIO

from pypdf import PdfReader


class MetadataExtractor:
    """Extract title, author, and other metadata from documents."""

    def extract_pdf_metadata(self, file: BinaryIO) -> dict[str, str | None]:
        """
        Extract metadata from PDF file.

        Args:
            file: PDF file object

        Returns:
            Dictionary with 'title', 'author', and other metadata
        """
        try:
            pdf = PdfReader(file)
            metadata = pdf.metadata or {}

            # Reset file pointer
            file.seek(0)

            return {
                "title": metadata.get("/Title"),
                "author": metadata.get("/Author"),
                "subject": metadata.get("/Subject"),
                "creator": metadata.get("/Creator"),
                "producer": metadata.get("/Producer"),
                "page_count": len(pdf.pages),
            }
        except Exception as e:
            # If extraction fails, return empty metadata
            file.seek(0)
            return {
                "title": None,
                "author": None,
                "page_count": None,
                "error": str(e),
            }

    def extract_epub_metadata(self, file: BinaryIO) -> dict[str, str | None]:
        """
        Extract metadata from EPUB file.

        Args:
            file: EPUB file object

        Returns:
            Dictionary with 'title', 'author', and other metadata
        """
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            # EPUB is a ZIP file
            with zipfile.ZipFile(file) as epub_zip:
                # Find content.opf (metadata file)
                # Usually in META-INF/container.xml -> points to content.opf
                container = epub_zip.read("META-INF/container.xml")
                container_root = ET.fromstring(container)

                # Find rootfile path
                rootfile = container_root.find(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                )
                if rootfile is None:
                    raise ValueError("Could not find rootfile in container.xml")

                opf_path = rootfile.get("full-path")
                if not opf_path:
                    raise ValueError("Rootfile missing full-path")

                # Read OPF file
                opf_content = epub_zip.read(opf_path)
                opf_root = ET.fromstring(opf_content)

                # Define namespaces
                namespaces = {
                    "opf": "http://www.idpf.org/2007/opf",
                    "dc": "http://purl.org/dc/elements/1.1/",
                }

                # Extract metadata
                metadata = opf_root.find("opf:metadata", namespaces)
                if metadata is None:
                    return {"title": None, "author": None}

                title = metadata.find("dc:title", namespaces)
                author = metadata.find("dc:creator", namespaces)

                # Reset file pointer
                file.seek(0)

                return {
                    "title": title.text if title is not None else None,
                    "author": author.text if author is not None else None,
                }

        except Exception as e:
            file.seek(0)
            return {
                "title": None,
                "author": None,
                "error": str(e),
            }

    def extract_metadata(self, file: BinaryIO, file_type: str) -> dict[str, str | None]:
        """
        Extract metadata based on file type.

        Args:
            file: File object
            file_type: 'pdf' or 'epub'

        Returns:
            Dictionary with metadata
        """
        if file_type == "pdf":
            return self.extract_pdf_metadata(file)
        elif file_type == "epub":
            return self.extract_epub_metadata(file)
        else:
            return {"title": None, "author": None}
