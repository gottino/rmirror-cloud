#!/usr/bin/env python3
"""Generate hash coverage report by notebook."""

import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import get_settings
from app.models.notebook import Notebook
from app.models.page import Page

settings = get_settings()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

source_path = Path('/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop')

notebooks = db.query(Notebook).filter(
    Notebook.document_type.in_(['notebook', 'DocumentType'])
).order_by(Notebook.visible_name).all()

results = []
total_pages = 0
total_with_hash = 0
total_without_hash = 0
total_with_text = 0
total_missing = 0

for notebook in notebooks:
    # Skip QuickSheets
    if notebook.visible_name.lower() == 'quick sheets':
        continue

    # Get pages from database
    db_pages = db.query(Page).filter(Page.notebook_id == notebook.id).all()
    db_page_uuids = set(p.page_uuid for p in db_pages if p.page_uuid)

    pages_with_hash = sum(1 for p in db_pages if p.file_hash)
    pages_without_hash = len(db_pages) - pages_with_hash
    pages_with_text = sum(1 for p in db_pages if p.ocr_text and p.ocr_text.strip())

    # Get pages from .content file
    missing_in_db = 0
    content_file = source_path / f'{notebook.notebook_uuid}.content'
    if content_file.exists():
        try:
            with open(content_file, 'r') as f:
                content_json = json.load(f)

            pages_array = content_json.get('pages', [])
            if not pages_array and 'cPages' in content_json:
                c_pages = content_json['cPages'].get('pages', [])
                pages_array = [p['id'] for p in c_pages if isinstance(p, dict) and 'id' in p]

            content_page_uuids = set(pages_array)
            missing_in_db = len(content_page_uuids - db_page_uuids)
        except Exception:
            pass

    if len(db_pages) > 0 or missing_in_db > 0:
        results.append((
            notebook.visible_name,
            len(db_pages),
            pages_with_hash,
            pages_without_hash,
            pages_with_text,
            missing_in_db
        ))

        total_pages += len(db_pages)
        total_with_hash += pages_with_hash
        total_without_hash += pages_without_hash
        total_with_text += pages_with_text
        total_missing += missing_in_db

# Print header
print(f"{'Notebook':<35} {'Pages':>7} {'w/ Hash':>8} {'w/o Hash':>9} {'w/ Text':>8} {'Missing':>9}")
print('='*90)

# Print rows
for name, pages, with_hash, without_hash, with_text, missing in results:
    print(f"{name[:35]:<35} {pages:>7} {with_hash:>8} {without_hash:>9} {with_text:>8} {missing:>9}")

# Print totals
print('='*90)
print(f"{'TOTAL':<35} {total_pages:>7} {total_with_hash:>8} {total_without_hash:>9} {total_with_text:>8} {total_missing:>9}")
print()

# Print percentage
if total_pages > 0:
    pct_with_hash = (total_with_hash / total_pages) * 100
    print(f"Hash coverage: {pct_with_hash:.1f}% ({total_with_hash}/{total_pages} pages)")
    print(f"Pages missing in DB: {total_missing}")

db.close()
