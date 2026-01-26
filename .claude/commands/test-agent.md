# /test-agent

Test the agent locally in foreground mode.

## Usage

```
/test-agent
```

## Instructions

1. **Check backend is running**
   - Verify backend on port 8000
   - If not: remind user to start it

2. **Start agent in foreground**
   - Run: `cd agent && poetry run python -m app.main --foreground --debug`
   - Agent will start in terminal with logs

3. **Monitor for:**
   - Flask web UI starts on localhost:9090
   - File watcher initializes
   - reMarkable folder path detected
   - Cloud sync ready

4. **Test steps to suggest:**
   - Open http://localhost:9090 in browser
   - Check quota display
   - Trigger initial sync (if needed)
   - Copy test .rm file to reMarkable folder
   - Watch upload logs

5. **Report:**
   - Agent status (running/failed)
   - Web UI accessible
   - Any errors in logs

## Notes

- Agent runs in foreground (Ctrl+C to stop)
- Logs appear in terminal
- Use for development/debugging only
