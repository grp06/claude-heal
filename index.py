import os, sys, json, pathlib
from datetime import datetime
from cerebras.cloud.sdk import Cerebras

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
        'parentUuid', 'isSidechain', 'version', 'gitBranch', 'isMeta', 
        'leafUuid', 'model', 'stop_reason', 'stop_sequence', 'usage'
    ]
    
    try:
        p = pathlib.Path(os.path.expanduser(path))
        if not p.exists():
            return []
        
        data = p.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        
        lines = data.decode("utf-8", errors="ignore").strip().split('\n')
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

def create_cerebras_client() -> Cerebras:
    api_key = "csk-kcmvvx4496h44jk5rerhcpcjrr6vjx5rvfwyd524pwk48mdr"
    return Cerebras(api_key=api_key)

def propose_changes_from_llm(transcript_jsonl: list) -> list:
    if not transcript_jsonl:
        return []
    
    try:
        client = create_cerebras_client()
        
        # Convert cleaned JSONL to string for LLM
        transcript_str = json.dumps(transcript_jsonl, indent=2)[:5000]  # Limit to first 5000 chars
        
        # Log formatted input
        debug_log("=== INPUT TO LLM ===")
        debug_log(transcript_str)
        
        # Simple prompt to analyze transcript and propose updates
        completion = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": "Analyze the conversation transcript (JSONL format) and return JSON with any needed updates to CLAUDE.md files. Return empty array if no updates needed."
                },
                {"role": "user", "content": f"Transcript:\n{transcript_str}"}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "changes_schema",
                    "schema": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "changes": {"type": "string"},
                            },
                            "required": ["path", "changes"],
                        },
                    },
                },
            },
        )
        
        content = completion.choices[0].message.content
        result = json.loads(content)
        
        # Log formatted output
        debug_log("=== OUTPUT FROM LLM ===")
        debug_log(json.dumps(result, indent=2))
        
        return result if isinstance(result, list) else []
        
    except Exception as e:
        debug_log(f"Error: {str(e)}")
        return []


def main():
    hook = read_stdin_json()

    if hook.get("hook_event_name") != "Stop":
        sys.exit(0)
    if hook.get("stop_hook_active") is True:
        sys.exit(0)

    transcript_path = hook.get("transcript_path", "")
    transcript_jsonl = load_transcript(transcript_path)

    changes = propose_changes_from_llm(transcript_jsonl)

    if not changes:
        sys.exit(0)

    # Emit JSON to block stop and instruct Claude to apply changes
    output = {
        "decision": "block",
        "reason": f"Apply the following CLAUDE.md updates discovered this turn. For each item: use Write/Edit to update the file at the specified path with the changes described.\n\nCHANGES_JSON:\n{json.dumps(changes)}"
    }
    
    print(json.dumps(output))
    sys.exit(0)

if __name__ == "__main__":
    main()
