"""Account service for data export and account deletion."""

import logging
import re
import zipfile
from datetime import datetime
from io import BytesIO

import httpx
from sqlalchemy.orm import Session

from app.core.pdf_service import PDFService
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.models.sync_record import IntegrationConfig, SyncQueue
from app.models.user import User
from app.storage import StorageService

logger = logging.getLogger(__name__)


class AccountService:
    """Handles data export and account deletion."""

    @staticmethod
    async def get_data_summary(user_id: int, db: Session) -> dict:
        """Return a summary of all data that will be deleted."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        notebooks = db.query(Notebook).filter(Notebook.user_id == user_id).all()
        notebook_ids = [n.id for n in notebooks]

        page_count = 0
        file_count = 0
        if notebook_ids:
            pages = db.query(Page).filter(Page.notebook_id.in_(notebook_ids)).all()
            page_count = len(pages)
            # Count S3 files: page PDFs + page .rm files + notebook originals + notebook combined PDFs
            for p in pages:
                if p.pdf_s3_key:
                    file_count += 1
                if p.s3_key:
                    file_count += 1
            for n in notebooks:
                if n.s3_key:
                    file_count += 1
                if n.notebook_pdf_s3_key:
                    file_count += 1

        integrations = (
            db.query(IntegrationConfig)
            .filter(IntegrationConfig.user_id == user_id)
            .all()
        )
        integration_names = [i.target_name for i in integrations]

        return {
            "notebooks": len(notebooks),
            "pages": page_count,
            "files": file_count,
            "integrations": integration_names,
            "member_since": user.created_at.isoformat() if user.created_at else None,
            "subscription": user.subscription_tier,
        }

    @staticmethod
    async def generate_data_export(
        user_id: int, db: Session, storage: StorageService
    ) -> bytes:
        """Generate a ZIP file containing all user data."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        notebooks = (
            db.query(Notebook)
            .filter(Notebook.user_id == user_id)
            .order_by(Notebook.full_path, Notebook.visible_name)
            .all()
        )

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # README
            zf.writestr(
                "rmirror-export/README.txt",
                "rMirror Data Export\n"
                "==================\n\n"
                "This archive contains all your data from rMirror Cloud.\n\n"
                "Structure:\n"
                "  notebooks/     - One folder per notebook with PDF and OCR text\n"
                "  metadata.json  - Account information and notebook index\n"
                "  README.txt     - This file\n",
            )

            notebook_index = []
            total_pages = 0

            for notebook in notebooks:
                # Skip folders
                if notebook.document_type == "folder":
                    continue

                # Build path from full_path or visible_name
                safe_name = re.sub(r"[^\w\s-]", "", notebook.visible_name or "notebook")
                safe_name = re.sub(r"\s+", "_", safe_name)[:50]

                folder_path = ""
                if notebook.full_path:
                    # Use full_path for directory structure, sanitize each segment
                    segments = notebook.full_path.split("/")
                    safe_segments = []
                    for seg in segments:
                        s = re.sub(r"[^\w\s-]", "", seg)
                        s = re.sub(r"\s+", "_", s)[:50]
                        if s:
                            safe_segments.append(s)
                    if safe_segments:
                        folder_path = "/".join(safe_segments)

                if folder_path:
                    notebook_dir = f"rmirror-export/notebooks/{folder_path}"
                else:
                    notebook_dir = f"rmirror-export/notebooks/{safe_name}"

                # Get pages in order
                notebook_pages = (
                    db.query(NotebookPage, Page)
                    .join(Page, NotebookPage.page_id == Page.id)
                    .filter(NotebookPage.notebook_id == notebook.id)
                    .order_by(NotebookPage.page_number)
                    .all()
                )

                nb_page_count = len(notebook_pages)
                total_pages += nb_page_count

                notebook_index.append(
                    {
                        "name": notebook.visible_name,
                        "uuid": notebook.notebook_uuid,
                        "type": notebook.document_type,
                        "pages": nb_page_count,
                        "path": notebook.full_path,
                    }
                )

                if not notebook_pages:
                    continue

                # Combine page PDFs into single notebook PDF
                page_pdfs = []
                for _nb_page, page in notebook_pages:
                    if page.pdf_s3_key:
                        try:
                            pdf_bytes = await storage.download_file(page.pdf_s3_key)
                            page_pdfs.append(pdf_bytes)
                        except Exception as e:
                            logger.warning(
                                f"Failed to download PDF for page {page.id}: {e}"
                            )

                if page_pdfs:
                    try:
                        combined_pdf = PDFService.combine_page_pdfs(page_pdfs)
                        zf.writestr(f"{notebook_dir}/{safe_name}.pdf", combined_pdf)
                    except Exception as e:
                        logger.warning(
                            f"Failed to combine PDFs for notebook {notebook.id}: {e}"
                        )

                # Combine OCR text
                text_lines = [f"# {notebook.visible_name or 'Untitled Notebook'}\n"]
                for nb_page, page in notebook_pages:
                    text_lines.append(f"\n## Page {nb_page.page_number}\n")
                    if page.ocr_text:
                        text_lines.append(page.ocr_text)
                    else:
                        text_lines.append("[No OCR text]")
                    text_lines.append("\n---\n")

                text_content = "\n".join(text_lines)
                zf.writestr(f"{notebook_dir}/{safe_name}.txt", text_content)

            # metadata.json
            import json

            metadata = {
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "export_timestamp": datetime.utcnow().isoformat(),
                "notebook_count": len(notebook_index),
                "total_pages": total_pages,
                "notebooks": notebook_index,
            }
            zf.writestr(
                "rmirror-export/metadata.json",
                json.dumps(metadata, indent=2, ensure_ascii=False),
            )

        zip_buffer.seek(0)
        return zip_buffer.read()

    @staticmethod
    async def delete_account(
        user_id: int, db: Session, storage: StorageService, clerk_secret_key: str | None = None
    ) -> dict:
        """Permanently delete all user data from all systems."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # 1. Cancel in-flight sync queue items
        cancelled_count = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.user_id == user_id,
                SyncQueue.status.in_(["pending", "processing"]),
            )
            .update({"status": "cancelled"}, synchronize_session="fetch")
        )
        logger.info(f"Cancelled {cancelled_count} sync queue items for user {user_id}")

        # 2. Collect S3 keys before deleting DB records
        notebooks = db.query(Notebook).filter(Notebook.user_id == user_id).all()
        notebook_ids = [n.id for n in notebooks]

        s3_keys = []
        for n in notebooks:
            if n.s3_key:
                s3_keys.append(n.s3_key)
            if n.notebook_pdf_s3_key:
                s3_keys.append(n.notebook_pdf_s3_key)

        if notebook_ids:
            pages = db.query(Page).filter(Page.notebook_id.in_(notebook_ids)).all()
            for p in pages:
                if p.s3_key:
                    s3_keys.append(p.s3_key)
                if p.pdf_s3_key:
                    s3_keys.append(p.pdf_s3_key)

        page_count = len(pages) if notebook_ids else 0

        # 3. Store Clerk ID before deletion
        clerk_user_id = user.clerk_user_id

        # 4. Delete S3 files (best-effort)
        deleted_files = 0
        for key in s3_keys:
            try:
                await storage.delete_file(key)
                deleted_files += 1
            except Exception as e:
                logger.warning(f"Failed to delete S3 file {key}: {e}")

        # 5. Delete database records (CASCADE handles all child tables)
        db.delete(user)
        db.commit()
        logger.info(f"Deleted user {user_id} and all associated data from database")

        # 6. Delete from Clerk (best-effort)
        clerk_deleted = False
        if clerk_user_id and clerk_secret_key:
            clerk_deleted = await AccountService._delete_clerk_user(
                clerk_user_id, clerk_secret_key
            )

        return {
            "deleted_notebooks": len(notebooks),
            "deleted_pages": page_count,
            "deleted_s3_files": deleted_files,
            "clerk_deleted": clerk_deleted,
        }

    @staticmethod
    async def _delete_clerk_user(clerk_user_id: str, clerk_secret_key: str) -> bool:
        """Delete user from Clerk via Backend API."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"https://api.clerk.com/v1/users/{clerk_user_id}",
                    headers={"Authorization": f"Bearer {clerk_secret_key}"},
                )
                if response.status_code == 200:
                    logger.info(f"Deleted Clerk user {clerk_user_id}")
                    return True
                else:
                    logger.warning(
                        f"Failed to delete Clerk user {clerk_user_id}: "
                        f"status={response.status_code}, body={response.text}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Error deleting Clerk user {clerk_user_id}: {e}")
            return False
