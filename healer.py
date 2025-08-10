import argparse
import json
import os
import sys
from typing import Any, Dict
from cerebras.cloud.sdk import Cerebras


def create_cerebras_client() -> Cerebras:
    api_key = os.getenv("CEREBRAS_API_KEY")
    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY environment variable is not set")
    return Cerebras(api_key=api_key)


def build_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "improvements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filepath": {"type": "string"},
                        "improvement": {"type": "string"},
                    },
                    "required": ["filepath", "improvement"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["improvements"],
        "additionalProperties": False,
    }


def generate_filepath_json(prompt: str, model: str) -> Dict[str, str]:
    client = create_cerebras_client()

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": """You are the Rulefile-Updater.  
Goal: propose tiny, high-leverage edits to repo rulefiles so that the next AI run avoids the failures seen in the current session and has updated context on major new changes in the codebase based on the given chat insteraction.

INPUT  (all are raw text blobs, some are optional)
1. CHAT    – complete user/assistant exchange  
2. DIFFS   – list of files touched or unified diff for this session  
3. RULES   – map `{path, content}` of existing `CLAUDE.md` (may be empty)  
4. META    – language(s), build / lint commands if known

THINKING GUIDELINES
- Add a rule only if a concrete error or rework could have been prevented.  
- Keep every new rule ≤ 2 bullet lines; reference a command instead of pasting its policy.  
- Prefer folder-local rulefiles when the issue is isolated to one sub-tree.  
- If the same idea already exists, modify/clarify the old line instead of adding a duplicate.

WHEN TO EDIT
Propose an edit if at least one of these is true:  
a) The same error (or variant) happened twice in CHAT or EVENTS.  
b) A missing invariant (lint/test/tool) caused wrong code or wasted >1 message.  
c) A stable repo fact (script name, env var, port) surfaced for the first time.

WHAT NOT TO INCLUDE:
- secrets, API keys, or push/publish commands.
- things that are too trivial to be worth adding a rule for.

OUTPUT  (always return a JSON dict)

```
{
  "improvements": [
    {
      "filepath": "<relative path to CLAUDE.md>",
      "improvement": "<a list of improvements to the rulefile>"
    }
  ]
}
```

- If no change is needed, return `"improvements": []`.
- Keep bullets terse, e.g.  
  `- After editing files in api/, run  `make api-test` before committing.`

EXAMPLE ITEM
```
{
  "filepath": "CLAUDE.md",
  "improvement": "Prevent remote_path error when mounting source\n- Do not pass custom args to add_local_python_source\n+ When calling `add_local_python_source`, omit `remote_path` (Modal SDK >=0.58 rejects it)\n"
}
""",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "filepath_schema",
                # "strict": True, # we cant use it wih the current model
                "schema": build_schema(),
            },
        },
    )

    try:
        content = completion.choices[0].message.content
        data = json.loads(content)
    except Exception as e:  # noqa: BLE001 - we capture and rethrow
        raise

    if not isinstance(data, dict):
        raise ValueError("Model response was not a JSON object")
    if "improvements" not in data or not isinstance(data["improvements"], list):
        raise ValueError("Missing or invalid 'improvements' list in response")
    for improvement_item in data["improvements"]:
        if not isinstance(improvement_item, dict):
            raise ValueError("Each improvement must be an object")
        if "improvement" not in improvement_item or not isinstance(
            improvement_item["improvement"], str
        ):
            raise ValueError(
                "Each improvement must include string 'filepath' and 'improvement'"
            )

    return {"improvements": data["improvements"]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a filepath JSON via Cerebras Inference"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Return a plausible repo-relative filepath for a newly added feature.",
        help="User prompt to guide the model",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-oss-120b",
        help="Cerebras model id to use",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="-",
        help="Output path for JSON; '-' for stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        result = generate_filepath_json(prompt=args.prompt, model=args.model)
    except Exception as e:  # noqa: BLE001 - captured and surfaced
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_str = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if args.output == "-":
        print(output_str)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)


if __name__ == "__main__":
    main()
