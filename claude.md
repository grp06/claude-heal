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

## Failure Mode Prevention
- Do **not truncate** the transcript or `claude.md` content before sending to the LLM; pass the full cleaned strings.
- Ensure f‑string placeholders are written as `{variable}` (no extra parentheses) to avoid syntax errors.
- Always read the `cwd` field from the hook payload to locate project files such as `claude.md` before invoking the LLM.
- In JSON output strings, reference variables directly (`{changes}`) rather than using `{(changes)}` which produces malformed f‑strings.
