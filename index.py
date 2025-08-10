#!/usr/bin/env python3
# .claude/hooks/heal_claude_files.py
import os, sys, json, pathlib, re, textwrap
from datetime import datetime

# ---------- utilities ----------
def debug_log(message: str):
    """Write debug messages to a timestamped log file"""
    # Get the directory where this script is located
    script_dir = pathlib.Path(__file__).resolve().parent
    debug_dir = script_dir / "debug"
    debug_dir.mkdir(exist_ok=True)  # Ensure debug directory exists
    
    # Create or get the session log file
    # Use a global to maintain the same file for the entire hook run
    global _log_file_path
    try:
        _log_file_path
    except NameError:
        # First call - create new timestamped log file
        file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
        _log_file_path = debug_dir / f"hook_{file_timestamp}.log"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds
    try:
        with open(_log_file_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()  # Ensure immediate write
    except Exception as e:
        # Try to write error to stderr so we can see what's wrong
        sys.stderr.write(f"DEBUG_LOG_ERROR: {str(e)}\n")
        sys.stderr.flush()

def read_stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}

def load_transcript(path: str, max_bytes: int = 400_000) -> str:
    """
    Reads the JSONL transcript Claude Code writes for the session.
    Produces a compact XML-ish view of the last ~max_bytes for the LLM.
    """
    try:
        p = pathlib.Path(os.path.expanduser(path))
        if not p.exists():
            return "<transcript/>"
        data = p.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        lines = data.decode("utf-8", errors="ignore").splitlines()
        xml_chunks = ["<transcript>"]
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                # fallback: raw line
                xml_chunks.append(f"<raw>{escape_xml(ln)[:4000]}</raw>")
                continue

            role = obj.get("role") or obj.get("author") or "unknown"
            content = obj.get("content") or obj.get("text") or ""
            # Skip hidden "thinking" if present
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # concatenate text-like items
                parts = []
                for c in content:
                    if isinstance(c, dict):
                        t = c.get("text") or c.get("content") or ""
                        if t:
                            parts.append(str(t))
                text = "\n".join(parts)
            else:
                text = str(content)

            text = truncate(text, 8000)
            xml_chunks.append(f'<turn role="{escape_xml(role)}">{escape_xml(text)}</turn>')
        xml_chunks.append("</transcript>")
        return "\n".join(xml_chunks)
    except Exception as e:
        return f"<transcript error='{escape_xml(str(e))}'/>"

def escape_xml(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))

def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else (s[:n] + " …[truncated]")

# ---------- LLM call (provider-agnostic) ----------
def propose_changes_from_llm(transcript_xml: str) -> list:
    """
    Calls an LLM to decide CLAUDE.md changes.
    Returns a Python list of {path, changes} dicts.
    Provider is selected by env:
      LLM_PROVIDER = "anthropic" | "openai"
      ANTHROPIC_API_KEY / OPENAI_API_KEY must be set accordingly.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

    system_instructions = (
        "You are a codebase context maintainer. "
        "Given a Claude Code conversation transcript in XML, decide whether any CLAUDE.md "
        "(project or folder-level) files should be UPDATED to prevent future mistakes. "
        "Output ONLY JSON: an array of objects, each: "
        "{'path': '<absolute or project-relative path to the CLAUDE.md to update>', "
        "'changes': '<concise, imperative description of the edits needed>'}. "
        "If no updates are needed, return []. "
        "Do not include explanations. Only valid JSON."
    )

    user_prompt = f"""TRANSCRIPT_XML:
{transcript_xml}
"""

    # Try Anthropic first (default)
    if provider == "anthropic":
        try:
            debug_log(f"Using Anthropic provider with model: {os.getenv('LLM_MODEL', 'claude-3-5-sonnet-20240620')}")
            from anthropic import Anthropic
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20240620")
            resp = client.messages.create(
                model=model,
                max_tokens=1200,
                temperature=0,
                system=system_instructions,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join([
                block.text for block in resp.content
                if hasattr(block, "text")
            ]) or ""
            debug_log(f"Anthropic response text: {text}")
            result = coerce_json_array(text)
            debug_log(f"Coerced JSON result: {result}")
            return result
        except Exception as e:
            debug_log(f"Anthropic API error: {str(e)}")
            return []

    # OpenAI fallback
    try:
        debug_log(f"Using OpenAI provider with model: {os.getenv('LLM_MODEL', 'gpt-4o-mini')}")
        from openai import OpenAI
        client = OpenAI()
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content or ""
        debug_log(f"OpenAI response text: {text}")
        result = coerce_json_array(text)
        debug_log(f"Coerced JSON result: {result}")
        return result
    except Exception as e:
        debug_log(f"OpenAI API error: {str(e)}")
        return []

def coerce_json_array(text: str) -> list:
    # extract first JSON array from text
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        # normalize objects
        out = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            path = item.get("path") or item.get("file") or ""
            changes = item.get("changes") or item.get("diff") or ""
            if path and changes:
                out.append({"path": str(path), "changes": str(changes)})
        return out
    except Exception:
        return []

# ---------- main ----------
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
    debug_log(f"transcript_xml length: {len(transcript_xml)} chars")
    debug_log(f"transcript_xml preview: {transcript_xml[:500]}...")
    
    debug_log("Calling LLM to propose changes...")
    changes = propose_changes_from_llm(transcript_xml)
    debug_log(f"LLM proposed changes: {json.dumps(changes, indent=2)}")
    
    if not changes:
        debug_log("No changes proposed, exiting normally")
        # nothing to do; let Claude stop normally
        sys.exit(0)

    # Hand precise instructions + JSON to Claude via stderr and block stoppage.
    # Claude will continue one more turn and execute these instructions.
    instruction = textwrap.dedent(f"""
    Apply CLAUDE.md updates discovered this turn.

    Use Edit or Write tools ONLY on the listed files. For each item in CHANGES_JSON:
      1) Read the current file (create if missing).
      2) Produce a full, updated CLAUDE.md content that incorporates the described changes
         and preserves any good existing rules. Keep it concise and structured.
      3) Write the complete file content. Do NOT touch any other files.
      4) If a change is ambiguous, ask the user to confirm before writing.

    After applying all items, briefly summarize the updates, then end the turn.

    CHANGES_JSON:
    {json.dumps(changes, ensure_ascii=False, indent=2)}
    """).strip()

    debug_log(f"Sending instruction to Claude: {instruction}")
    sys.stderr.write(instruction + "\n")
    sys.stderr.flush()
    debug_log("Exiting with code 2 to block stoppage and continue with Claude")
    # Exit code 2 => for Stop: block stoppage and feed stderr to Claude.
    sys.exit(2)

if __name__ == "__main__":
    main()
