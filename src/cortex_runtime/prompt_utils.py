"""Shared prompt formatting utilities for cortex_runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def format_attachment_text(attachments: Sequence[Any]) -> str:
    """Format a list of attachments into human-readable label lines.

    Accepts both dataclass instances (attribute access) and plain dicts
    (from ``dataclasses.asdict`` serialization).
    """
    lines: list[str] = []
    for att in attachments:
        if isinstance(att, dict):
            title = att.get("title", "")
            url = att.get("url", "")
            description = att.get("description", "")
            mime_type = att.get("mime_type", "")
            is_image = mime_type.startswith("image/") if mime_type else False
        else:
            title = att.title
            url = att.url
            description = att.description
            is_image = att.is_image

        if is_image:
            label = f"[Image: {title}]" if title else "[Image attached]"
        else:
            label = f"[File: {title}]" if title else "[File attached]"
        if url:
            label += f" ({url})"
        if description:
            label += f" — {description}"
        lines.append(label)

    return "\n".join(lines)


def append_attachments_to_prompt(attachments: Sequence[Any], prompt: str) -> str:
    """Format attachments and append to the prompt text."""
    attachment_text = format_attachment_text(attachments)
    if not attachment_text:
        return prompt
    if prompt.strip():
        return f"{prompt}\n\n{attachment_text}"
    return attachment_text


def format_thread_context(
    thread_context: list[dict[str, str]],
    sender: str,
    prompt: str,
) -> str:
    """Format thread conversation history into a prompt string."""
    context_lines = ["[Thread conversation history]"]
    for msg in thread_context:
        msg_sender = msg.get("sender", "unknown")
        text = msg.get("text", "")
        context_lines.append(f"{msg_sender}: {text}")
    context_lines.extend(
        [
            "[End of thread history]",
            "",
            f"[New message from {sender}]",
            prompt,
        ]
    )
    return "\n".join(context_lines)
