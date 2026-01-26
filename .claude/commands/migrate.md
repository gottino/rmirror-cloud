# /migrate

Create or apply database migrations using Alembic.

## Usage

```
/migrate create "description"    # Create new migration
/migrate up                       # Apply pending migrations
/migrate down                     # Rollback one migration
/migrate status                   # Show current migration status
```

## Instructions

### Create Migration
1. Change to backend: `cd backend`
2. Run: `poetry run alembic revision -m "description"`
3. Report the new migration file path
4. Remind user to edit the migration file

### Apply Migrations
1. Change to backend: `cd backend`
2. Show current status: `poetry run alembic current`
3. Show pending: `poetry run alembic heads`
4. Apply: `poetry run alembic upgrade head`
5. Confirm new status: `poetry run alembic current`

### Rollback
1. Change to backend: `cd backend`
2. Run: `poetry run alembic downgrade -1`
3. Confirm status

### Status
1. Change to backend: `cd backend`
2. Run: `poetry run alembic current`
3. Run: `poetry run alembic history --verbose`

## Examples

```
/migrate create "add user preferences table"
/migrate up
/migrate down
/migrate status
```

## Important Notes

- ALWAYS use `poetry run alembic` (never bare `alembic`)
- Test migrations on local SQLite before deploying to production PostgreSQL
- Migrations should be idempotent (safe to run multiple times)
