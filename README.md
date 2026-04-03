# pia

Terminal AI agent — execute and automate tasks from the console.

pia connects to any OpenAI-compatible API (OpenRouter, OpenAI, Anthropic, Ollama, etc.) and can run commands, read/write/edit files, search your codebase, and orchestrate multi-step workflows autonomously.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/FrancoAA/pia/main/install.sh | bash
```

The installer checks prerequisites (Python 3.10+, pip, git), installs pia, and walks you through configuring your LLM provider.

### Manual install

```bash
git clone https://github.com/FrancoAA/pia.git
cd pia
pip install -e .
pia init
```

## Usage

```bash
# Interactive mode
pia

# Single-prompt mode
pia "find all TODO comments in this project"

# Pipe mode
cat error.log | pia "explain these errors"
git diff | pia "write a commit message for this"
```

### Options

```
pia --model/-m <model>      Use a specific model
pia --profile/-p <name>     Use a named profile
pia --dry-run               Preview commands without executing
pia --debug                 Enable debug output
pia --version/-v            Show version
```

### REPL commands

Once in interactive mode:

| Command | Description |
|-----------|--------------------------------------|
| `/help` | Show available commands |
| `/reset` | Clear conversation history |
| `/compact` | Summarize conversation to save context |
| `/memory add <fact>` | Save a fact across sessions |
| `/memory show` | Show saved memories |
| `/memory remove <text>` | Remove a memory |
| `/memory clear` | Clear all memories |
| `/history list` | List past sessions |
| `/history resume <id>` | Resume a previous session |
| `/history clear` | Delete session history |
| `/plugins` | List loaded plugins |
| `/exit` | Quit |

## Tools

pia has 7 built-in tools that the LLM can use autonomously:

| Tool | Description |
|---|---|
| `run_command` | Execute shell commands with timeout |
| `read_file` | Read files with line numbers, or list directories |
| `write_file` | Create or overwrite files |
| `edit_file` | Find-and-replace with atomic writes |
| `search_files` | Find files by glob pattern |
| `search_content` | Regex search with ripgrep (grep fallback) |
| `delegate_task` | Spawn a focused sub-agent for complex sub-tasks |

## Configuration

Configuration is loaded in order of priority (highest first):

1. CLI flags (`--model`, `--dry-run`, etc.)
2. Environment variables (`PIA_API_KEY`, `PIA_MODEL`, etc.)
3. Config file (`~/.config/pia/config.toml`)
4. Defaults

### Config file

```toml
# ~/.config/pia/config.toml
api_url = "https://openrouter.ai/api/v1"
api_key = "your-key-here"
model = "openai/gpt-4o"
max_tokens = 4096
temperature = 0.7
max_iterations = 100
```

### Environment variables

| Variable | Description |
|---|---|
| `PIA_API_URL` | API endpoint URL |
| `PIA_API_KEY` | API key |
| `PIA_MODEL` | Model name |
| `PIA_MAX_TOKENS` | Max tokens per response |
| `PIA_TEMPERATURE` | Sampling temperature |
| `PIA_MAX_ITERATIONS` | Max tool-use loop iterations |
| `PIA_DRY_RUN` | Preview mode (`true`/`false`) |
| `PIA_DEBUG` | Debug output (`true`/`false`) |

### Profiles

Manage multiple LLM providers:

```bash
pia profiles --add         # Add a new profile
pia profiles --switch fast # Switch active profile
pia profiles --remove old  # Remove a profile
pia profiles               # List all profiles
pia -p fast "do something" # Use a profile for one command
```

## Safety

pia detects dangerous commands (e.g. `rm -rf /`, `mkfs`, `dd`, `reboot`) and prompts for confirmation before executing them. You can add custom patterns in `~/.config/pia/dangerous_commands`:

```
# one pattern per line
DROP TABLE
TRUNCATE
```

## Plugins

pia ships with 4 built-in plugins:

| Plugin | Description |
|---|---|
| **core** | `/help`, `/plugins`, `/compact` commands |
| **safety** | Dangerous command detection and blocking |
| **memory** | Persistent cross-session memory (`/memory`) |
| **history** | Session tracking and resume (`/history`) |

Plugins hook into the agent lifecycle (init, shutdown, before/after API calls, before/after tool calls, prompt building, user/assistant messages).

## Development

```bash
git clone https://github.com/FrancoAA/pia.git
cd pia
pip install -e ".[dev]"
bash scripts/install-hooks.sh
```

### Running tests

```bash
python -m unittest discover -s tests -v
```

### Pre-commit hook

The project includes a pre-commit hook (installed via `scripts/install-hooks.sh`) that runs before every commit:

1. **Test suite** — all tests must pass
2. **Coverage** — must stay at or above 80%
3. **Pylint** — no errors allowed in staged Python files

### Project structure

```
src/pia/
  cli.py            # CLI entry point (Click)
  api.py            # API client, Message, chat_loop
  config.py         # Config loading (TOML/env/CLI)
  app.py            # App dataclass
  display.py        # Terminal UI (Rich)
  executor.py       # Dangerous command detection
  prompt.py         # System prompt builder
  repl.py           # Interactive REPL
  profiles.py       # Multi-profile management
  tools/            # Built-in tools
  plugins/          # Plugin system
tests/              # Test suite (122 tests)
scripts/            # Git hooks and install script
```

## License

MIT
