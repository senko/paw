# Paw 🐾

A minimal, self-contained AI agent with filesystem and shell access. Paw is an interactive command-line assistant that can read files (including images and PDFs), write code, execute shell commands, and maintain a memory of past interactions.

## Features

- **Filesystem Operations**: Read, write, and update files with surgical precision
- **Multimodal Support**: Read and understand images (PNG, JPG, GIF, WebP) and PDF documents
- **Shell Access**: Execute arbitrary shell commands with confirmation prompts
- **Persistent Memory**: Automatically maintains a memory log of past interactions for context
- **Interactive Confirmation**: Prompts for approval before executing potentially destructive operations
- **Self-Contained**: Automatically creates its own system prompt on first run

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd paw

# Install dependencies (using uv, or your preferred Python package manager)
uv pip install -e .
```

### Configuration

Paw requires an LLM provider. Set the following environment variables:

```bash
# Primary LLM (defaults to Claude Sonnet 4.5)
export LLM_URL="anthropic:///claude-sonnet-4-5-20250929"

# Memory summarization LLM (defaults to Claude Haiku 4.5)
export MEMORY_LLM_URL="anthropic:///claude-haiku-4-5-20251001"

# Required: Anthropic API key
export ANTHROPIC_API_KEY="your-api-key-here"
```

The `LLM_URL` format follows the `think-llm` library's URL scheme. See the [think-llm documentation](https://github.com/senko/think-llm) for more provider options.

### Usage

```bash
paw "Your request here"
```

#### Examples

```bash
# File operations
paw "Read the contents of main.py and explain what it does"
paw "Create a Python script that sorts a list of numbers"
paw "Update config.json to set the timeout to 30 seconds"

# Shell commands
paw "What Python packages are installed?"
paw "Find all TODO comments in Python files"
paw "Show me the git commit history for the last week"

# Multimodal
paw "Analyze this screenshot and describe what you see" # (reads image files)
paw "Summarize this PDF document"

# Using memory
paw "What did we work on yesterday?"
paw "Continue the refactoring we started last time"
```

## How It Works

### Tools

Paw has access to four core tools:

1. **read_file(path)** - Reads text files, images, or PDFs
2. **write_file(path, content)** - Creates or overwrites a file
3. **update_file(path, old, new)** - Replaces the first occurrence of a string
4. **bash(command)** - Executes a shell command and returns output

### Confirmation System

For safety, Paw prompts for confirmation before:
- Writing or updating files
- Executing shell commands

Read-only operations (like `read_file`) execute immediately without confirmation.

### Memory System

Paw automatically maintains a memory log at `MEMORY.md`:

- After each interaction, a summary is generated and appended
- Recent memory entries are loaded on startup to provide context
- Entries are timestamped and include concise summaries of what was accomplished
- The agent can search its memory using the `bash` tool with `rg` or `tail`

### Agent Prompt

The agent's system prompt is stored in `AGENT.md` and is automatically created on first run. You can customize this file to modify Paw's behavior and personality.

### CLI Tools

Paw is aware of useful CLI tools listed in `CLI-TOOLS.md`. This file is empty by default. If you want Paw to remember using a tool, tell it to store the info about the tool there.

## Architecture

Paw is built on the [think-llm](https://github.com/senko/think-llm) library, which provides:
- Unified interface for multiple LLM providers
- Tool/function calling support
- Multimodal content handling
- Streaming and async support

The main loop:
1. Sends user prompt with tools to LLM
2. Displays any text response
3. Executes approved tool calls
4. Returns results to LLM
5. Repeats until the task is complete (max 20 steps)
6. Generates and saves a memory summary

## Configuration Files

- **AGENT.md** - System prompt for the agent (auto-created)
- **CLI-TOOLS.md** - List of useful CLI tools the agent can use (empty at start)
- **MEMORY.md** - Persistent memory log (auto-created)
- **.python-version** - Python version specification
- **pyproject.toml** - Project metadata and dependencies

## Requirements

- Python 3.13+
- `think-llm` (>=0.0.11)
- `anthropic` (>=0.83.0)
- An Anthropic API key (or alternative LLM provider with think-llm support)

## Development

The entire agent is implemented in a single file (`paw.py`) for simplicity and ease of understanding. The codebase is intentionally minimal to serve as both a useful tool and an educational example of AI agent architecture.

## Safety & Limitations

This agent is a research project and has **known significant security vulnerabilities** that make it unsuitable for use in untrusted environments or with sensitive data. The main issues are:

1. **Full system access with minimal safeguards**
2. **Reliance on LLM decision-making for security**
3. **No sandboxing or privilege separation**

The confirmation prompts provide some protection against accidents but are **not sufficient security controls** against:
- Social engineering of the LLM
- Malicious prompts designed to extract data
- Accidental exposure of sensitive information

**Use Case Recommendation:** This tool should **only be used**:
- In isolated development environments
- With non-sensitive data
- By users who understand the risks
- Never on production systems or with access to credentials

Use at your own risk!

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
