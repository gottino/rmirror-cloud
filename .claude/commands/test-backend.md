# /test-backend

Run backend tests with pytest.

## Usage

```
/test-backend [optional: specific test file or pattern]
```

## Instructions

1. Change to backend directory: `cd backend`
2. If specific test file provided:
   - Run: `poetry run pytest tests/[filename] -v`
3. If no argument:
   - Run all tests: `poetry run pytest -v`
4. Report results:
   - Number of tests passed/failed
   - Any failures with details
   - Total execution time

## Examples

```
/test-backend                          # Run all tests
/test-backend test_quota_service.py    # Run specific test file
```
