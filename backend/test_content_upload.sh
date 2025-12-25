#!/bin/bash
# Test script to upload .content file to the new endpoint

NOTEBOOK_UUID="00c53f0f-d16a-4ecf-8456-3d1eff39b2ab"
CONTENT_FILE="/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop/${NOTEBOOK_UUID}.content"

# Get session token from .env
cd /Users/gabriele/Documents/Development/rmirror-cloud/backend
source .env

echo "Testing .content file upload for notebook: $NOTEBOOK_UUID"
echo ""
echo "Content file pages count:"
poetry run python -c "import json; print(len(json.load(open('$CONTENT_FILE')).get('pages', [])))"
echo ""

# Test the upload
curl -X POST "http://localhost:8000/v1/notebooks/${NOTEBOOK_UUID}/content" \
  -H "Authorization: Bearer ${CLERK_API_KEY}" \
  -F "content_file=@${CONTENT_FILE}" \
  | jq '.'

echo ""
echo "Checking database after upload:"
sqlite3 rmirror.db "SELECT COUNT(*) as pages_mapped FROM notebook_pages WHERE notebook_id = 346"
