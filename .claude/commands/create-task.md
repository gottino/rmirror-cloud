# /create-task

Create a development task in Notion linked to "Building a Remarkable data pipeline" project.

## Usage

```
/create-task <task-name> [--status STATUS] [--tags TAG1,TAG2] [--description DESC]
```

## Arguments

- `task-name` (required): Name/title of the task
- `--status` (optional): Task status. Options: Backlog (default), Prioritized, In Progress, Paused
- `--tags` (optional): Comma-separated tags. Options: development, remarkable, feature, bug, ops, marketing, learning, test
- `--description` (optional): Detailed description of the task

## Instructions

1. Parse the command arguments to extract:
   - Task name (everything before first `--` flag, or entire argument if no flags)
   - Status (from `--status` flag, default: "Backlog")
   - Tags (from `--tags` flag, split by comma into array)
   - Description (from `--description` flag)

2. Build the Notion API request body:
   ```json
   {
     "parent": {"database_id": "8e7d9a88-05d3-4cd7-bede-6e464740f48a"},
     "properties": {
       "Name": {"title": [{"text": {"content": "<task-name>"}}]},
       "Status": {"status": {"name": "<status>"}},
       "Tags": {"multi_select": [{"name": "<tag1>"}, {"name": "<tag2>"}]},
       "Project": {"relation": [{"id": "178a6c5d-acd0-803b-8231-eed2928b5319"}]},
       "Description": {"rich_text": [{"text": {"content": "<description>"}}]}
     }
   }
   ```

3. Create task using curl with Notion API:
   ```bash
   curl -X POST https://api.notion.com/v1/pages \
     -H "Authorization: Bearer $NOTION_TOKEN" \
     -H "Notion-Version: 2025-09-03" \
     -H "Content-Type: application/json" \
     -d '<request-body>'
   ```

4. Parse the response to extract:
   - Task ID
   - Task URL
   - Confirmation of properties set

5. Report success with:
   - Task name
   - Task URL from response
   - Status set
   - Tags assigned

6. Handle errors gracefully:
   - Invalid status values → suggest valid options
   - Invalid tag values → suggest valid tags
   - Notion API errors → show error message with details
   - Missing NOTION_TOKEN → explain token setup

## Examples

```
# Simple task (Backlog, no tags)
/create-task Fix OCR timeout issue

# Task with status and tags
/create-task Add dark mode to dashboard --status "Prioritized" --tags feature,ops

# Full task with description
/create-task Implement Stripe webhooks --status "In Progress" --tags feature,ops --description "Set up webhook endpoints for subscription events: payment_intent.succeeded, customer.subscription.updated, customer.subscription.deleted"

# Bug report
/create-task Agent crashes on malformed .rm files --status Prioritized --tags bug,ops
```

## Valid Status Options

- `Backlog` (default)
- `Prioritized`
- `In Progress`
- `Paused`
- `Completed` (for marking existing work)
- `Cancelled`

## Valid Tags

- `development` - Development work
- `remarkable` - reMarkable tablet specific
- `feature` - New features
- `bug` - Bug fixes
- `ops` - Operations/infrastructure
- `marketing` - Marketing/growth
- `learning` - Learning/research tasks
- `test` - Testing tasks

## Technical Details

**Tasks Database ID**: `3cfcca1b-a8d1-4cad-a63b-fbdbf05835e7`
**Project ID**: `178a6c5d-acd0-803b-8231-eed2928b5319` (Building a Remarkable data pipeline)

The task will be automatically linked to the project through the `Project` relation property, making it visible in the project's task list.
