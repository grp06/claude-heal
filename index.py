import os, sys, json, pathlib
from debug_utils import debug_log
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
from prompts import CLAUDE_FAILURE_MODE_PROMPT


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
    # Load .env from repo root regardless of caller CWD, then optional user-global file.
    repo_root = pathlib.Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(pathlib.Path.home() / ".claude-self-heal.env", override=False)

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
                    "content": CLAUDE_FAILURE_MODE_PROMPT,
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
