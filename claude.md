# Claude Self-Healing Context Updater

note: I ran `ln -sf "$(pwd)/index.py" ~/.claude/hooks/heal_claude_files.py` early on, so this index.py file is mapped to the right place in the hooks directory

## Purpose
Automatically keep `claude.md` (Claude context/rules) files accurate and up-to-date by analyzing each Claude Code session, detecting newly learned project facts, and applying updates without manual intervention.

## How It Works
- A **Stop hook** runs after every Claude Code conversation turn.
- The hook:
  1. Reads the session transcript JSONL from `transcript_path`.
  2. Cleans and serializes it into XML.
  3. Sends it to an LLM (Anthropic or OpenAI) with instructions to propose updates to `claude.md` files.
  4. Receives a JSON array of `{path, changes}` objects.
  5. Blocks stoppage (`exit 2`) and sends Claude instructions to apply those changes via Write/Edit tools.

## Goals
- Ensure Claude always has correct persistent context (ports, env details, architecture facts, style rules).
- Reduce repeated mistakes caused by outdated `claude.md` files.
- Keep edits scoped only to relevant `claude.md` files.

## Constraints
- Must only edit files specified in the `changes` JSON.
- Preserve good existing rules when updating.
- If change is ambiguous, ask user for confirmation.
- Never touch unrelated files.

## Hook Configuration
- Hook type: `Stop`
- Command: `python3 ~/.claude/hooks/heal_claude_files.py`
- Timeout: 120 seconds

## Example
1. `claude.md` says: “App runs on port 3000.”
2. In session, Claude discovers: “Port 3000 is in use, run on 3001.”
3. Hook detects this, LLM proposes:
   ```json
   [{"path": "claude.md", "changes": "never run the app on port 3000, always run it on port 3001"}]
````

4. Claude updates `claude.md` accordingly before the next turn.

### Stop Hook Communication

When implementing a **Stop hook** (or SubagentStop), the hook can instruct Claude to apply file edits discovered during the turn.  To do this, the hook must output **structured JSON** to **stdout** (or stderr with exit code 2) in the following shape:

```json
{
  "decision": "block",
  "reason": "Apply the following `claude.md` updates discovered this turn. For each item: use Write/Edit to update the file; if content is ambiguous, ask for confirmation. After applying, briefly summarize what changed, then continue the normal flow.\n\nCHANGES_JSON:\n[{\"path\":\"path/to/file1\",\"changes\":\"description of change 1\"},{\"path\":\"path/to/file2\",\"changes\":\"description of change 2\"}]"
}
```

* **`decision: "block"`** prevents Claude from stopping the turn and feeds the `reason` string back as the next instruction.
* The **`reason`** must contain a clear, imperative instruction for Claude to **Write/Edit** the listed files, followed by an inline payload named `CHANGES_JSON` that is a JSON array of objects with the keys `path` (relative to `$CLAUDE_PROJECT_DIR`) and `changes` (the exact text to write or a description of the edit).
* Use **stdout** with exit code 0 for the above JSON, or **stderr** with exit code 2 if you prefer that channel (Claude will still see the output).
* Guard against infinite loops by checking the `stop_hook_active` flag in the input JSON and exiting early when it is `true`.

#### Permissions
Ensure the session has **Write/Edit** permissions for the target files (via `/permissions` or the project settings) so Claude can apply the edits without additional prompts.

#### Example Hook Flow
1. Hook receives `{ "transcript_path": "...", "stop_hook_active": false }` via stdin.
2. Loads and cleans the transcript, runs LLM analysis, produces an array of change objects.
3. Emits the JSON block shown above, then exits with code 0.
4. Claude receives the `reason`, executes the specified edits, and continues the conversation.

This documentation clarifies the exact format and behavior expected from Stop hooks to reliably trigger file updates.
