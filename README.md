# Claude Self-Healing Context Updater

Automatically updates `claude.md` files after each Claude Code session by analyzing conversations and applying learned facts.

## Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd claude-self-heal
   ```

2. **Create Python virtual environment**
   ```bash
   python3 -m venv claude-self-heal-venv
   source claude-self-heal-venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up API key**
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   # Or use OPENAI_API_KEY if using OpenAI
   ```

5. **Create symlinks**
   ```bash
   # Create symlink in project directory (required for hook to find it)
   ln -sf index.py heal_claude_files.py
   
   # Create symlink in Claude hooks directory
   mkdir -p ~/.claude/hooks
   ln -sf "$(pwd)/index.py" ~/.claude/hooks/heal_claude_files.py
   ```

6. **Configure Claude Code hook**
   
   Add to your Claude Code settings:
   - Hook type: `Stop`
   - Command: `~/claude-self-heal-venv/bin/python $CLAUDE_PROJECT_DIR/heal_claude_files.py`
   - Timeout: 120 seconds

## How It Works

After each conversation turn, the hook:
1. Reads the session transcript
2. Sends it to an LLM to identify outdated information in `claude.md` files
3. Proposes updates as JSON
4. Claude applies the updates automatically

## Files

- `index.py` - Main hook script
- `healer.py` - Core logic for analyzing transcripts
- `claude.md` - Project context file that gets auto-updated
- `requirements.txt` - Python dependencies