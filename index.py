import os, sys, json, pathlib
from datetime import datetime

def debug_log(message: str):
    script_dir = pathlib.Path(__file__).resolve().parent
    debug_dir = script_dir / "debug"
    debug_dir.mkdir(exist_ok=True)
    global _log_file_path
    try:
        _log_file_path
    except NameError:
        file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        _log_file_path = debug_dir / f"hook_{file_timestamp}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with open(_log_file_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
    except Exception as e:
        sys.stderr.write(f"DEBUG_LOG_ERROR: {str(e)}\n")
        sys.stderr.flush()

def read_stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}

def load_transcript(path: str, max_bytes: int = 400_000) -> str:
    try:
        p = pathlib.Path(os.path.expanduser(path))
        if not p.exists():
            return ""
        data = p.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

 

def propose_changes_from_llm(transcript_xml: str) -> list:
    # TODO: Integrate with an LLM provider to analyze transcript_xml and propose changes
    # - Decide whether any CLAUDE.md files should be updated
    # - Return a list of objects: {"path": "...", "changes": "..."}
    # For now, no external calls or prompts are executed.
    return []

# TODO: If/when parsing free-form LLM output is reintroduced, add a helper to coerce
# responses into a structured list of {path, changes} dicts.

def main():
    debug_log("=== HOOK START ===")
    hook = read_stdin_json()
    debug_log(f"Hook input: {json.dumps(hook, indent=2)}")

    if hook.get("hook_event_name") != "Stop":
        debug_log("hook_event_name is not Stop")
        debug_log(f"hook_event_name: {hook.get('hook_event_name')}")
        sys.exit(0)
    if hook.get("stop_hook_active") is True:
        debug_log("stop_hook_active is True")
        sys.exit(0)

    transcript_path = hook.get("transcript_path", "")
    debug_log(f"transcript_path: {transcript_path}")
    transcript_xml = load_transcript(transcript_path)

    debug_log("Calling LLM to propose changes...")
    changes = propose_changes_from_llm(transcript_xml)
    debug_log(f"LLM proposed changes: {json.dumps(changes, indent=2)}")

    if not changes:
        debug_log("No changes proposed, exiting normally")
        sys.exit(0)

    # TODO: If changes are produced in the future, emit actionable instructions here
    # to guide an automated follow-up step.

if __name__ == "__main__":
    main()
