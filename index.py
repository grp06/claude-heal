import os, sys, json, pathlib
from datetime import datetime
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv


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


def remove_excluded_keys(obj, excluded_keys):
    """Recursively remove excluded keys from nested dictionaries and lists."""
    if isinstance(obj, dict):
        return {
            k: remove_excluded_keys(v, excluded_keys)
            for k, v in obj.items()
            if k not in excluded_keys
        }
    elif isinstance(obj, list):
        return [remove_excluded_keys(item, excluded_keys) for item in obj]
    else:
        return obj


def load_transcript(path: str, max_bytes: int = 400_000) -> list:
    """Load JSONL transcript and filter out unwanted keys."""
    excluded_keys = [
        "parentUuid",
        "isSidechain",
        "version",
        "gitBranch",
        "isMeta",
        "leafUuid",
        "model",
        "stop_reason",
        "stop_sequence",
        "usage",
        "sessionId",
        "uuid",
        "timestamp",
        "userType",
        "id"

    ]

    try:
        p = pathlib.Path(os.path.expanduser(path))
        if not p.exists():
            return []

        data = p.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]

        lines = data.decode("utf-8", errors="ignore").strip().split("\n")
        cleaned_records = []

        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                # Recursively remove excluded keys from all levels
                cleaned_record = remove_excluded_keys(record, excluded_keys)
                cleaned_records.append(cleaned_record)
            except json.JSONDecodeError:
                continue

        return cleaned_records
    except Exception as e:
        debug_log(f"Error loading transcript: {str(e)}")
        return []


def read_claude_md(cwd: str) -> str:
    """Read claude.md file from the given directory."""
    try:
        claude_md_path = pathlib.Path(cwd) / "claude.md"
        if claude_md_path.exists():
            content = claude_md_path.read_text(encoding="utf-8")
            debug_log(f"Successfully read claude.md from {claude_md_path}")
            return content
        else:
            debug_log(f"claude.md not found at {claude_md_path}")
            return ""
    except Exception as e:
        debug_log(f"Error reading claude.md: {str(e)}")
        return ""


def create_cerebras_client() -> Cerebras:
    load_dotenv()
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY not found in environment variables")
    return Cerebras(api_key=api_key)


def propose_changes_from_llm(transcript_jsonl: list, claude_md_content: str = "") -> str | None:
    if not transcript_jsonl:
        return None

    try:
        client = create_cerebras_client()

        # Convert cleaned JSONL to string for LLM
        transcript_str = json.dumps(transcript_jsonl, indent=2)

        # Log formatted input
        debug_log("=== INPUT TO LLM ===")
        debug_log(f"Transcript: {transcript_str}")  # Log full transcript
        debug_log(f"Claude.md content: {claude_md_content}")  # Log full claude.md

        # Simple prompt to analyze transcript and propose updates
        completion = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": """You are the Claude failure mode documenter. Your job is to identify RECURRING FAILURE PATTERNS that AI coding assistants encounter and document them to prevent future failures.

<key-principle>
DOCUMENT FAILURE MODES, NOT BUGS

We want to capture systematic issues where the AI:
- Makes wrong assumptions about the environment/codebase
- Uses deprecated patterns or APIs  
- Misunderstands project structure or conventions
- Repeatedly attempts incorrect approaches
- Lacks critical context about how things actually work

We do NOT want to document:
- One-time bugs from outdated packages
- Transient errors that won't recur
- Things that are already caught by linters/tests
- Personal preferences without concrete failure prevention value
</key-principle>

<failure-mode-categories>
1. ENVIRONMENT MISMATCHES
   - Wrong ports, paths, or environment variables
   - Incorrect assumptions about installed tools/versions
   - Misunderstanding of local vs production configs

2. TOOL USAGE ERRORS  
   - Using wrong tools for tasks (e.g., Bash(grep) instead of Grep tool)
   - Missing required follow-up actions after edits
   - Incorrect command sequences or parameters

3. ARCHITECTURAL MISUNDERSTANDINGS
   - Wrong assumptions about system design
   - Misunderstanding component relationships
   - Incorrect API usage patterns

4. PROCESS FAILURES
   - Missing required validation steps
   - Wrong order of operations
   - Skipping critical checks before actions
</failure-mode-categories>

Your goal: Analyze the chat session to identify RECURRING FAILURE PATTERNS that should be documented to prevent future AI failures. Don't document things that are obvious which might not be repeating patterns.

INPUT
1. CHAT HISTORY – complete user/assistant exchange including tool calls and outputs
2. CLAUDE.md files – existing rulefile content (may be empty)

ANALYSIS CRITERIA  
Only propose a rule if:
a) The AI made the SAME TYPE of error multiple times in the session
b) The AI wasted significant time (3+ messages) on wrong approaches  
c) The AI discovered a STABLE, NON-OBVIOUS fact about the codebase that will trip up future AI
d) The AI lacked critical context that caused incorrect implementations

DO NOT propose rules for:
- One-time package version issues
- Errors that existing linters/tests would catch
- Temporary workarounds for transient problems
- Things that are obvious from reading the code

RULE QUALITY STANDARDS
• Each rule must prevent a SPECIFIC failure mode
• Keep rules ≤ 2 lines, action-oriented
• Reference commands/processes, don't explain them
• Only add rules that will apply to FUTURE sessions

OUTPUT  (always return a xml string)

<improvements>
  <improvement>
    <filepath>relative path to CLAUDE.md</filepath>
    <improvement_content>a list of improvements to the claude.md file</improvement_content>
  </improvement>
</improvements>

• If no change is needed, return `<improvements></improvements>`.
• Keep bullets terse, e.g.  
  `- After editing files in api/, run  `make api-test` before committing.`

EXAMPLE
```
<improvements>
  <improvement>
    <filepath>CLAUDE.md</filepath>
    <improvement_content>
# Failure Mode Prevention
- Port 3000 is permanently in use by system service; always use port 3001
- When editing GraphQL schemas, must run `regen_graphql` or types will be stale
- Use Grep tool for searching, never Bash(grep) - permissions will fail
    </improvement_content>
  </improvement>
</improvements>
""",
                },
                {
                    "role": "user", 
                    "content": f"Current claude.md content:\n{claude_md_content if claude_md_content else '(No claude.md file found)'}\n\nTranscript:\n{transcript_str}"
                },
            ],
        )

        content = completion.choices[0].message.content

        # Log formatted output
        debug_log("=== OUTPUT FROM LLM ===")
        debug_log(content)

        # Extract improvements and map to expected format
        if content:
            return content
        return None

    except Exception as e:
        debug_log(f"Error: {str(e)}")
        return None


def main():
    hook = read_stdin_json()

    if hook.get("hook_event_name") != "Stop":
        sys.exit(0)
    if hook.get("stop_hook_active") is True:
        sys.exit(0)

    transcript_path = hook.get("transcript_path", "")
    transcript_jsonl = load_transcript(transcript_path)
    
    # Get current working directory and read claude.md
    cwd = hook.get("cwd", ".")
    claude_md_content = read_claude_md(cwd)

    changes = propose_changes_from_llm(transcript_jsonl, claude_md_content)

    if not changes:
        sys.exit(0)
    
    # Check if changes is just an empty improvements tag
    cleaned_changes = changes.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    if cleaned_changes == "<improvements></improvements>":
        sys.exit(0)

    # Emit JSON to block stop and instruct Claude to apply changes
    output = {
        "decision": "block",
        "reason": f"We have an LLM that is giving us recomendations for how to update our Cluade.md file. Here are their suggestions. Apply the following CLAUDE.md updates discovered this turn. For each item: use Write/Edit to update the file at the specified path with the changes described.\n\nCHANGES_XML:\n{changes}",
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
