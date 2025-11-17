#!/usr/bin/env python3
"""
Upload reMarkable metadata files to the API for testing.

Usage:
    python upload_metadata.py --token YOUR_JWT_TOKEN [--base-url http://167.235.74.51]
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import httpx

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def get_document_type(metadata_dir: Path, uuid: str) -> str:
    """
    Determine document type by reading .content file.

    Returns: 'notebook', 'pdf', 'epub', 'folder', or 'unknown'
    """
    content_file = metadata_dir / f"{uuid}.content"

    # Check if it's a folder (no .content file)
    if not content_file.exists():
        return 'folder'

    try:
        with open(content_file, 'r') as f:
            content_data = json.load(f)

        file_type = content_data.get('fileType', '')

        if file_type == '' or file_type == 'notebook':
            return 'notebook'
        elif file_type == 'pdf':
            return 'pdf'
        elif file_type == 'epub':
            return 'epub'
        else:
            logger.debug(f"Unknown fileType '{file_type}' for {uuid}")
            return 'unknown'

    except Exception as e:
        logger.debug(f"Could not read content file for {uuid}: {e}")
        return 'unknown'


def upload_metadata(
    metadata_file: Path,
    base_url: str,
    token: str,
    metadata_dir: Path,
) -> Optional[dict]:
    """Upload a single metadata file to the API."""

    try:
        # Read metadata
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        uuid = metadata_file.stem
        visible_name = metadata.get('visibleName', 'Unknown')
        parent_uuid = metadata.get('parent', '')

        # Determine document type
        document_type = get_document_type(metadata_dir, uuid)

        # Prepare request data
        request_data = {
            'notebook_uuid': uuid,
            'visible_name': visible_name,
            'parent_uuid': parent_uuid if parent_uuid else None,
            'document_type': document_type,
        }

        # Add optional fields
        if 'lastModified' in metadata:
            request_data['last_modified'] = metadata['lastModified']
        if 'lastOpened' in metadata:
            request_data['last_opened'] = metadata['lastOpened']
        if 'lastOpenedPage' in metadata:
            request_data['last_opened_page'] = metadata['lastOpenedPage']
        if 'pinned' in metadata:
            request_data['pinned'] = metadata['pinned']
        if 'deleted' in metadata:
            request_data['deleted'] = metadata['deleted']
        if 'version' in metadata:
            request_data['version'] = metadata['version']

        # Make API request
        response = httpx.post(
            f"{base_url}/v1/processing/metadata/update",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            json=request_data,
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(
                f"✅ {visible_name} ({document_type}) -> {result.get('full_path', 'N/A')}"
            )
            return result
        else:
            logger.error(
                f"❌ Failed to upload {visible_name}: "
                f"{response.status_code} - {response.text}"
            )
            return None

    except Exception as e:
        logger.error(f"❌ Error processing {metadata_file}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Upload reMarkable metadata to API')
    parser.add_argument(
        '--token',
        required=True,
        help='JWT authentication token',
    )
    parser.add_argument(
        '--base-url',
        default='http://167.235.74.51',
        help='API base URL (default: http://167.235.74.51)',
    )
    parser.add_argument(
        '--metadata-dir',
        default='test_data/rm_files',
        help='Directory containing .metadata files (default: test_data/rm_files)',
    )

    args = parser.parse_args()

    # Find metadata directory
    metadata_dir = Path(args.metadata_dir)
    if not metadata_dir.exists():
        logger.error(f"Metadata directory not found: {metadata_dir}")
        sys.exit(1)

    # Find all .metadata files
    metadata_files = list(metadata_dir.glob("*.metadata"))

    if not metadata_files:
        logger.error(f"No .metadata files found in {metadata_dir}")
        sys.exit(1)

    logger.info(f"Found {len(metadata_files)} metadata files")
    logger.info(f"API: {args.base_url}")
    logger.info("")

    # Upload in two passes:
    # Pass 1: Upload folders first (so parents exist for documents)
    # Pass 2: Upload documents

    folders = []
    documents = []

    for metadata_file in metadata_files:
        uuid = metadata_file.stem
        doc_type = get_document_type(metadata_dir, uuid)

        if doc_type == 'folder':
            folders.append(metadata_file)
        else:
            documents.append(metadata_file)

    logger.info(f"📁 Uploading {len(folders)} folders first...")
    success_count = 0
    for metadata_file in folders:
        result = upload_metadata(metadata_file, args.base_url, args.token, metadata_dir)
        if result:
            success_count += 1

    logger.info("")
    logger.info(f"📄 Uploading {len(documents)} documents...")
    for metadata_file in documents:
        result = upload_metadata(metadata_file, args.base_url, args.token, metadata_dir)
        if result:
            success_count += 1

    logger.info("")
    logger.info(f"✅ Successfully uploaded {success_count}/{len(metadata_files)} items")

    # Rebuild paths to ensure everything is correct
    logger.info("")
    logger.info("🔄 Rebuilding all paths...")
    try:
        response = httpx.post(
            f"{args.base_url}/v1/processing/metadata/rebuild-paths",
            headers={'Authorization': f'Bearer {args.token}'},
        )
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ {result.get('message', 'Paths rebuilt')}")
        else:
            logger.warning(f"⚠️  Path rebuild returned {response.status_code}")
    except Exception as e:
        logger.warning(f"⚠️  Could not rebuild paths: {e}")


if __name__ == '__main__':
    main()
