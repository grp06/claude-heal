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


def create_cerebras_client() -> Cerebras:
    api_key = "csk-kcmvvx4496h44jk5rerhcpcjrr6vjx5rvfwyd524pwk48mdr"
    return Cerebras(api_key=api_key)


def propose_changes_from_llm(transcript_jsonl: list) -> str | None:
    if not transcript_jsonl:
        return None

    try:
        client = create_cerebras_client()

        # Convert cleaned JSONL to string for LLM
        transcript_str = json.dumps(transcript_jsonl, indent=2)[
            :5000
        ]  # Limit to first 5000 chars

        # Log formatted input
        debug_log("=== INPUT TO LLM ===")
        debug_log(transcript_str)

        # Simple prompt to analyze transcript and propose updates
        completion = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": """You are the claude code rule file updater.  

<claude-md-context>
# What a rulefile is

- A repo-scoped coding rules document (`CLAUDE.md` et al.) that AI coding tools read to align with a codebase’s conventions, workflows, and guardrails.
- Can live at multiple scopes: repo root, subfolders, parent repo, or user home (`~/.claude/CLAUDE.md`).

# Why standardize a root rulefile

- Avoids fragmented local prompts and duplicated discovery work.
- Gives newcomers a single starting point.
- Reduces style/process drift across engineers and AI tools.
- Harder to agree on: every line impacts the whole org, so it needs justification and stakeholder review.

# Core principles (content, not behavior)

- Minimal, high-signal instructions only; each line should be a net win across contexts.
- Codify global processes (lint/format/typecheck/test) rather than personal preferences.
- Document recurring mistakes and their fixes so knowledge compounds.
- Defer to existing sources of truth: codebase conventions, linters, CI, scripts—don’t restate long standards; point to or invoke the process that enforces them.
- Scope specificity: put universal rules in the rulefile; push niche/flow-specific steps into the relevant files or scripts and tell readers to check file headers for follow-ups.

# Maintenance loop

Keep a separate, living table (e.g., Notion/Docs) of:
- Failure case → Proposed instruction or process change → Contributor → Decision/Status.
- Review with frequent tool users + domain owners → ensure alignment with principles → commit updates → notify users → observe and log new failures.
- Formal evaluations aren’t emphasized for small teams; prioritize that each instruction is strictly beneficial.

# Typical building blocks (section skeleton)

1. Code discovery: How to trace code and search history; which search/glob/grep tools to use (and which not).
2. Code editing: After-edit follow-ups: read file headers for required scripts (e.g., schema regen).
3. Code quality: Follow existing code style; clarify a few repo-wide norms (e.g., import placement, typing expectations).
4. Test design: How tests are structured locally (patterns, decorators, parametrization) and where to look for examples.
5. Test execution: Standard commands for lint/format/test; how to run a single file vs full suite.
6. Git operations: Don’t perform git ops automatically; outline the commit flow and checks.
7. Commit message requirements: Title schema, concise description, reviewer selection heuristics, linking tasks/threads, revision references.
8. Code review: Ordering of feedback (critical first) and expected context/linking.

# Big idea

A root `CLAUDE.md` is a thin, shared interface to the repo’s actual processes and conventions. It centralizes what’s global, pushes specifics to where they belong (tools/files/CI), and evolves via a documented failure→remedy loop.
</claude-md-context>

Goal: ONLY WHEN NECESSARY - propose tiny, high-leverage edits to repo claude.md so that the next LLM avoids the failures seen in the current session and has updated context on major new changes in the codebase based on the given chat insteraction.

INPUT  (all are raw text blobs, some are optional)
1. CHAT HISTORY    – complete user/assistant exchange that include tools calls, chnages  made in the code and other related outputs.
2. CLAUDE.md files   – map `{path, content}` of existing `CLAUDE.md` files (may be empty)

THINKING GUIDELINES
• Add a rule only if a concrete error or rework could have been prevented.  
• Keep every new rule ≤ 2 bullet lines; reference a command instead of pasting its policy.  
• Prefer folder-local claude.md when the issue is isolated to one sub-tree.  
• Never include secrets, API keys, or push/publish commands.  
• If the same idea already exists, talk about the addition details for that rule/idea.

WHEN TO PROPOSE IMPROVEMENTS
Propose an improvement if at least one of these is true:  
a) The same error (or variant) happened twice in CHAT.  
b) A missing invariant (lint/test/tool) caused wrong code or wasted >2 message.  
c) A stable repo fact (script name, env var, port) surfaced for the first time.
d) The assistant made a change to the code that is not reflected in the CLAUDE.md files.

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

EXAMPLE ITEM
```
<improvements>
  <improvement>
    <filepath>CLAUDE.md</filepath>
    <improvement_content>Prevent remote_path error when mounting source\n- Do not pass custom args to add_local_python_source\n+ When calling `add_local_python_source`, omit `remote_path` (Modal SDK >=0.58 rejects it)\n</improvement_content>
  </improvement>
</improvements>
""",
                },
                {"role": "user", "content": f"Transcript:\n{transcript_str}"},
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

    changes = propose_changes_from_llm(transcript_jsonl)

    if not changes:
        sys.exit(0)

    # Emit JSON to block stop and instruct Claude to apply changes
    output = {
        "decision": "block",
        "reason": f"We have an LLM that is giving us recomendations for how to update our Cluade.md file. Here are their suggestions. Apply the following CLAUDE.md updates discovered this turn. For each item: use Write/Edit to update the file at the specified path with the changes described.\n\nCHANGES_XML:\n{(changes)}",
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
