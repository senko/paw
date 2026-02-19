import sys
import asyncio
import subprocess
from base64 import b64encode
from datetime import datetime
from pathlib import Path
from os import environ

from think.llm import LLM
from think.llm.chat import Chat, ContentPart, ContentType, Message, Role
from think.llm.tool import ToolKit, ToolError, ToolResponse


# --- Multimodal support ---

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf"}

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}

_pending_images: list[str] = []
_pending_documents: list[str] = []


def _to_data_url(path: Path) -> str:
    data = b64encode(path.read_bytes()).decode("ascii")
    mime = MIME_TYPES[path.suffix.lower()]
    return f"data:{mime};base64,{data}"


# --- Tools ---


def read_file(path: str) -> str:
    """Read the contents of a file. Supports text files, images, and PDFs.

    :param path: Path to the file to read
    :return: The file contents or a confirmation that the file was loaded
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        _pending_images.append(_to_data_url(p))
        return f"Image loaded: {path}"
    if ext in DOCUMENT_EXTENSIONS:
        _pending_documents.append(_to_data_url(p))
        return f"Document loaded: {path}"
    return p.read_text()


def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with the given content.

    :param path: Path to the file to write
    :param content: The full content to write
    :return: Confirmation message
    """
    Path(path).write_text(content)
    return f"Written {len(content)} bytes to {path}"


def update_file(path: str, old: str, new: str) -> str:
    """Update a file by replacing the first occurrence of a string.

    :param path: Path to the file to update
    :param old: The exact string to find and replace
    :param new: The replacement string
    :return: Confirmation message
    """
    text = Path(path).read_text()
    if old not in text:
        raise ToolError(f"String not found in {path}")
    Path(path).write_text(text.replace(old, new, 1))
    return f"Updated {path}"


def bash(command: str) -> str:
    """Execute a shell command and return its output.

    :param command: The shell command to execute
    :return: Combined stdout and stderr output
    """
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=120
    )
    output = result.stdout
    if result.stderr:
        output += result.stderr
    if result.returncode != 0:
        output += f"\n(exit code: {result.returncode})"
    return output or "(no output)"


# --- Confirmation ---

CONFIRM_TOOLS = {"write_file", "update_file", "bash"}


def display_tool_call(name, args):
    print(f"\n  ── {name} ──")
    for k, v in args.items():
        s = str(v)
        if len(s) > 300:
            s = s[:300] + "…"
        if "\n" in s:
            print(f"  {k}:")
            for line in s.splitlines():
                print(f"    {line}")
        else:
            print(f"  {k}: {s}")


def confirm_tool(name, args):
    display_tool_call(name, args)
    if name not in CONFIRM_TOOLS:
        return True
    answer = input("  Allow? [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


# --- Agent loop ---

MAX_STEPS = 20
MAX_TOKENS = 16384


async def run(llm, chat, toolkit):
    adapter = llm.adapter_class(toolkit)

    for _ in range(MAX_STEPS):
        message = await llm._internal_call(
            chat, temperature=None, max_tokens=MAX_TOKENS, adapter=adapter
        )
        chat.messages.append(message)

        text_parts = []
        tool_calls = []
        for part in message.content:
            if part.type == ContentType.text and part.text:
                text_parts.append(part.text)
            elif part.type == ContentType.tool_call:
                tool_calls.append(part.tool_call)

        if text_parts:
            print("\n" + "".join(text_parts))

        if not tool_calls:
            break

        responses = []
        for tc in tool_calls:
            if confirm_tool(tc.name, tc.arguments):
                tr = await toolkit.execute_tool_call(tc)
                if tr.error:
                    print(f"  ERROR: {tr.error}")
                else:
                    preview = (
                        tr.response
                        if len(tr.response) <= 500
                        else tr.response[:500] + "…"
                    )
                    print(f"  -> {preview}")
            else:
                tr = ToolResponse(call=tc, error="User denied this action.")
                print("  DENIED")
            responses.append(tr)

        chat.messages.append(
            Message(
                role=Role.tool,
                content=[
                    ContentPart(type=ContentType.tool_response, tool_response=tr)
                    for tr in responses
                ],
            )
        )

        if _pending_images or _pending_documents:
            chat.messages.append(
                Message.user(
                    "Here are the requested files:",
                    images=_pending_images or None,
                    documents=_pending_documents or None,
                )
            )
            _pending_images.clear()
            _pending_documents.clear()
    else:
        print("\n(max steps reached)")


MEMORY_FILE = Path("MEMORY.md")


def load_recent_memory(n=3):
    if not MEMORY_FILE.exists():
        return ""
    text = MEMORY_FILE.read_text().strip()
    if not text:
        return ""
    entries = [e.strip() for e in text.split("---") if e.strip()]
    recent = entries[-n:]
    return "---\n" + "\n---\n".join(recent) + "\n---"


MEMORY_PROMPT = """\
Summarize the above interaction in one or two entries for a memory log.
Each entry MUST follow this EXACT format (including the --- separators):

---
# [YYYY-MM-DD HH:MM:SS] One-line summary title

Optional short summary if there's more to say than the title.
---

Rules:
- Use timestamp: {timestamp}
- Focus on WHAT was done and the OUTCOME, not the process
- If the task was simple, the title alone is enough (no body)
- If it was complex, add a 1-3 sentence body
- Output ONLY the entry/entries, nothing else"""


async def save_memory(chat, timestamp):
    memory_url = environ.get(
        "MEMORY_LLM_URL", "anthropic:///claude-haiku-4-5-20251001"
    )
    memory_llm = LLM.from_url(memory_url)

    summary_chat = chat.clone()
    summary_chat.user(MEMORY_PROMPT.format(timestamp=timestamp))
    entry = await memory_llm(summary_chat)

    with open(MEMORY_FILE, "a") as f:
        if MEMORY_FILE.stat().st_size > 0 and not entry.startswith("\n"):
            f.write("\n")
        f.write(entry)
        if not entry.endswith("\n"):
            f.write("\n")


AGENT_TEMPLATE = """# Agent

You are Paw, a helpful AI assistant with access to the local filesystem and shell.

## Tools

You have 4 tools available:

- **read_file**: Read the contents of a file (text, images, and PDFs)
- **write_file**: Create or overwrite a file
- **update_file**: Replace a string in a file (for surgical edits)
- **bash**: Execute a shell command

## Memory

You have a persistent memory log at `MEMORY.md`. It contains timestamped summaries of past interactions. Since this file grows large over time:
- Use `bash` with `tail -n 30 MEMORY.md` to see recent entries
- Use `bash` with `rg "search term" MEMORY.md` to search for specific topics

Consult your memory when it might be relevant to the current task.

## Guidelines

- Read files before modifying them
- Use update_file for small changes, write_file for creating new files or full rewrites
- Keep changes minimal and focused
- Explain what you're doing and why

## Available CLI Tools

See [CLI-TOOLS.md](CLI-TOOLS.md) for a list of useful command-line tools available for use with the bash tool.
"""


async def main():
    if len(sys.argv) < 2:
        print("Usage: paw <prompt>")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])

    agent_md = Path("AGENT.md")
    if not agent_md.exists():
        agent_md.write_text(AGENT_TEMPLATE)
    system = agent_md.read_text()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cwd = Path.cwd().resolve()
    system += f"\n\n## Environment\n\n- Working directory: {cwd}\n- Date/time: {now}"

    recent_memory = load_recent_memory()
    if recent_memory:
        system += f"\n\n## Recent Memory\n\n{recent_memory}"

    llm_url = environ.get("LLM_URL", "anthropic:///claude-sonnet-4-5-20250929")
    llm = LLM.from_url(llm_url)

    toolkit = ToolKit([read_file, write_file, update_file, bash])
    chat = Chat(system)
    chat.user(prompt)

    await run(llm, chat, toolkit)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        await save_memory(chat, timestamp)
    except Exception as e:
        print(f"\n(failed to save memory: {e})")


def main_sync():
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
