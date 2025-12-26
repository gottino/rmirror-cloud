#!/usr/bin/env python3
"""Show notebooks with the most missing pages."""

import json
import sys
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

notebooks = db.query(Notebook).filter(Notebook.document_type.in_(['notebook', 'DocumentType'])).all()

results = []
for notebook in notebooks:
    content_file = source_path / f'{notebook.notebook_uuid}.content'
    if not content_file.exists():
        continue

    with open(content_file, 'r') as f:
        content_json = json.load(f)

    pages_array = content_json.get('pages', [])
    if not pages_array and 'cPages' in content_json:
        c_pages = content_json['cPages'].get('pages', [])
        pages_array = [p['id'] for p in c_pages if isinstance(p, dict) and 'id' in p]

    content_page_uuids = set(pages_array)
    db_pages = db.query(Page).filter(Page.notebook_id == notebook.id).all()
    db_page_uuids = set(p.page_uuid for p in db_pages if p.page_uuid)

    missing_in_db = content_page_uuids - db_page_uuids

    if missing_in_db:
        results.append((notebook.visible_name, notebook.notebook_uuid, len(content_page_uuids), len(db_page_uuids), len(missing_in_db)))

results.sort(key=lambda x: x[4], reverse=True)

print(f"{'Notebook':<30} {'Content':>8} {'DB':>8} {'Missing':>8}")
print('='*60)
for name, uuid, content_count, db_count, missing_count in results[:20]:
    print(f"{name[:30]:<30} {content_count:>8} {db_count:>8} {missing_count:>8}")

print(f"\nTotal notebooks with missing pages: {len(results)}")
print(f"Total missing pages: {sum(r[4] for r in results)}")

db.close()
