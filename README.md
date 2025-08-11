# Claude Self-Healing Context Updater

Automatically updates `claude.md` files after each Claude Code session by analyzing conversations and applying learned facts.

## Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url> ~/claude-self-heal
   cd ~/claude-self-heal
   ```

2. **Create Python virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up API key**
   The hook reads `API_KEY` in this order:
   - Process environment variables
   - `.env` in the repo root (`~/claude-self-heal/.env`)
   - Optional user-global `~/.claude-self-heal.env`

   Choose one:
   - Shell
     ```bash
     export API_KEY="your-api-key-here"
     ```
   - Repo `.env`
     ```bash
     echo 'API_KEY=your-api-key-here' >> ~/claude-self-heal/.env
     ```
   - User-global
     ```bash
     echo 'API_KEY=your-api-key-here' >> ~/.claude-self-heal.env
     ```

5. **Create symlink**
   ```bash
   mkdir -p ~/.claude/hooks
   ln -sf ~/claude-self-heal/index.py ~/.claude/hooks/heal_claude_files.py
   ```

6. **Configure Claude Code hook**
   
   Add to your `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "~/claude-self-heal/venv/bin/python ~/.claude/hooks/heal_claude_files.py",
               "timeout": 120
             }
           ]
         }
       ]
     }
   }
   ```
   
   Note: If you already have other settings in the file, merge this configuration appropriately.

## How It Works

After each conversation turn, the hook:
1. Reads the session transcript
2. Sends it to an LLM to identify outdated information in `claude.md` files
3. Proposes updates as JSON
4. Claude applies the updates automatically

## Files

- `index.py` - Main hook script
- `claude.md` - Project context file that gets auto-updated
- `requirements.txt` - Python dependencies