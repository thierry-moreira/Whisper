"""Small, dependency-free updater for the application's ``.env`` file.

The tray dialog uses this to persist the OpenAI key/model without destroying
the comments and ordering of the user's existing configuration.
"""

from __future__ import annotations

from pathlib import Path


def update_env_file(path: str | Path, updates: dict[str, str]) -> None:
    """Update ``KEY=value`` entries in *path*, appending missing keys.

    Existing comments and unrelated lines are preserved.  The write is
    atomic (temporary file + ``Path.replace``) so a crash cannot leave a
    half-written ``.env``.
    """
    env_path = Path(path)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(updates)
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={_format_value(remaining.pop(key))}")
                continue
        output.append(line)

    if remaining:
        if output and output[-1].strip():
            output.append("")
        output.append("# --- OpenAI (transcrição via API) ---")
        for key, value in remaining.items():
            output.append(f"{key}={_format_value(value)}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = env_path.with_suffix(env_path.suffix + ".tmp")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    temporary.replace(env_path)


def _format_value(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").strip()
