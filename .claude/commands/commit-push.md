# /commit-push

Create a conventional commit and push to current branch (with user review).

## Usage

```
/commit-push
```

## Instructions

1. Run `git status` and `git diff` to see what changed
2. Analyze the changes and determine:
   - Type: feat, fix, chore, docs, refactor, test, style
   - Scope: backend, dashboard, agent, or none
   - Description: concise summary of changes (keep it short!)
3. **IMPORTANT: Draft the commit message and show it to the user for review**
   - Format:
     ```
     type(scope): description

     🤖 Generated with Claude Code (https://claude.com/claude-code)

     Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
     ```
   - **DO NOT commit yet - wait for user confirmation**
   - Ask: "Does this commit message look good? Reply 'yes' to commit and push, or suggest edits."
4. **After user confirms:**
   - Stage all changes: `git add .`
   - Commit with the approved message
   - Push to current branch: `git push`
   - Report the commit hash and branch

## Examples

- `feat(backend): add retroactive OCR processing`
- `fix(dashboard): resolve quota percentage NaN bug`
- `chore(agent): update dependencies`
- `docs: update CLAUDE.md with multi-instance workflow`

## Important Notes

- Keep descriptions short and concise (not long paragraphs)
- Never include sensitive data (API keys, passwords, personal info)
- Always get user approval before committing
