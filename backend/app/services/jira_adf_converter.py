"""Convert Atlassian Document Format (ADF) JSON to Markdown.

ADF is the structured document format used by Jira Cloud for issue
descriptions and comments. This module provides a recursive converter
that walks the ADF node tree and produces clean Markdown output.

Reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/

Usage::

    from app.services.jira_adf_converter import adf_to_markdown

    markdown = adf_to_markdown(adf_json_dict)
"""

from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)


def adf_to_markdown(doc: dict | None) -> str:
    """Convert an ADF document to Markdown.

    Args:
        doc: ADF document root (``{"type": "doc", "content": [...]}``)
             or None.

    Returns:
        Markdown string. Empty string if doc is None or empty.
    """
    if not doc or doc.get("type") != "doc":
        return ""
    return _convert_nodes(doc.get("content", []))


def _convert_nodes(nodes: list[dict]) -> str:
    """Convert a list of ADF nodes to Markdown."""
    parts: list[str] = []
    for node in nodes:
        converted = _convert_node(node)
        if converted is not None:
            parts.append(converted)
    return "\n\n".join(parts)


def _convert_node(node: dict) -> str | None:
    """Dispatch a single ADF node to its type-specific handler."""
    node_type = node.get("type", "")
    handler = _NODE_HANDLERS.get(node_type)
    if handler:
        return handler(node)
    logger.debug("adf_unknown_node_type", node_type=node_type)
    return _fallback_text(node)


# ── Inline text + marks ───────────────────────────────────────────


def _convert_text(node: dict) -> str:
    """Convert a text node, applying any inline marks (bold, italic, etc.)."""
    text = node.get("text", "")
    for mark in node.get("marks", []):
        text = _apply_mark(text, mark)
    return text


def _apply_mark(text: str, mark: dict) -> str:
    """Wrap text with Markdown formatting for a given mark."""
    mark_type = mark.get("type", "")
    if mark_type == "strong":
        return f"**{text}**"
    if mark_type == "em":
        return f"*{text}*"
    if mark_type == "code":
        return f"`{text}`"
    if mark_type == "strike":
        return f"~~{text}~~"
    if mark_type == "underline":
        return text  # Markdown has no underline — pass through
    if mark_type == "link":
        href = mark.get("attrs", {}).get("href", "")
        return f"[{text}]({href})"
    if mark_type == "subsup":
        return text  # Superscript/subscript — pass through
    return text


def _convert_inline_content(node: dict) -> str:
    """Convert a node's inline children (text, mention, emoji, etc.)."""
    parts: list[str] = []
    for child in node.get("content", []):
        child_type = child.get("type", "")
        if child_type == "text":
            parts.append(_convert_text(child))
        elif child_type == "hardBreak":
            parts.append("  \n")
        elif child_type == "mention":
            parts.append(f"@{child.get('attrs', {}).get('text', 'user')}")
        elif child_type == "emoji":
            parts.append(child.get("attrs", {}).get("shortName", ""))
        elif child_type == "inlineCard":
            url = child.get("attrs", {}).get("url", "")
            parts.append(f"[{url}]({url})" if url else "")
        elif child_type == "status":
            text = child.get("attrs", {}).get("text", "")
            parts.append(f"[{text}]")
        elif child_type == "date":
            ts = child.get("attrs", {}).get("timestamp", "")
            parts.append(ts)
        else:
            # Recurse for any nested inline-like node
            parts.append(_fallback_text(child))
    return "".join(parts)


# ── Block-level handlers ──────────────────────────────────────────


def _handle_paragraph(node: dict) -> str:
    return _convert_inline_content(node)


def _handle_heading(node: dict) -> str:
    level = node.get("attrs", {}).get("level", 1)
    text = _convert_inline_content(node)
    return f"{'#' * level} {text}"


def _handle_blockquote(node: dict) -> str:
    inner = _convert_nodes(node.get("content", []))
    return "\n".join(f"> {line}" for line in inner.splitlines())


def _handle_code_block(node: dict) -> str:
    lang = node.get("attrs", {}).get("language", "")
    code = _convert_inline_content(node)
    return f"```{lang}\n{code}\n```"


def _handle_bullet_list(node: dict) -> str:
    return _convert_list_items(node, ordered=False)


def _handle_ordered_list(node: dict) -> str:
    return _convert_list_items(node, ordered=True)


def _convert_list_items(node: dict, *, ordered: bool) -> str:
    """Convert list items with proper bullet/number prefixes."""
    lines: list[str] = []
    for i, item in enumerate(node.get("content", []), start=1):
        if item.get("type") != "listItem":
            continue
        prefix = f"{i}." if ordered else "-"
        item_text = _convert_nodes(item.get("content", []))
        # Indent continuation lines for nested content
        item_lines = item_text.splitlines()
        if item_lines:
            lines.append(f"{prefix} {item_lines[0]}")
            for continuation in item_lines[1:]:
                lines.append(f"  {continuation}")
    return "\n".join(lines)


def _handle_table(node: dict) -> str:
    """Convert an ADF table to Markdown pipe table."""
    rows: list[list[str]] = []
    for row_node in node.get("content", []):
        if row_node.get("type") not in ("tableRow", "tableHeader"):
            continue
        cells: list[str] = []
        for cell in row_node.get("content", []):
            cell_text = _convert_nodes(cell.get("content", []))
            # Flatten multiline cell content to single line
            cells.append(cell_text.replace("\n", " ").strip())
        rows.append(cells)

    if not rows:
        return ""

    # Build markdown table
    lines: list[str] = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    for row in rows[1:]:
        # Pad row to match header width
        padded = row + [""] * (len(rows[0]) - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _handle_rule(node: dict) -> str:
    return "---"


def _handle_panel(node: dict) -> str:
    """Convert a panel (info/warning/error/note) to a blockquote."""
    panel_type = node.get("attrs", {}).get("panelType", "info")
    prefix_map = {"info": "Info", "warning": "Warning", "error": "Error", "note": "Note"}
    prefix = prefix_map.get(panel_type, panel_type.title())
    inner = _convert_nodes(node.get("content", []))
    lines = [f"> **{prefix}:**"]
    for line in inner.splitlines():
        lines.append(f"> {line}")
    return "\n".join(lines)


def _handle_media_single(node: dict) -> str:
    """Convert a media node to an image reference or placeholder."""
    for child in node.get("content", []):
        if child.get("type") == "media":
            attrs = child.get("attrs", {})
            alt = attrs.get("alt", "image")
            url = attrs.get("url", "")
            media_id = attrs.get("id", "")
            if url:
                return f"![{alt}]({url})"
            return f"[Attachment: {media_id or alt}]"
    return ""


def _handle_media_group(node: dict) -> str:
    """Convert a group of media items to a list of references."""
    parts: list[str] = []
    for child in node.get("content", []):
        if child.get("type") == "media":
            attrs = child.get("attrs", {})
            alt = attrs.get("alt", "attachment")
            media_id = attrs.get("id", "")
            parts.append(f"- [Attachment: {media_id or alt}]")
    return "\n".join(parts)


def _handle_expand(node: dict) -> str:
    """Convert an expand/collapse section to a details summary."""
    title = node.get("attrs", {}).get("title", "Details")
    inner = _convert_nodes(node.get("content", []))
    return f"**{title}**\n\n{inner}"


def _handle_task_list(node: dict) -> str:
    """Convert ADF action items to Markdown checkboxes."""
    lines: list[str] = []
    for item in node.get("content", []):
        if item.get("type") != "taskItem":
            continue
        state = item.get("attrs", {}).get("state", "TODO")
        checked = "x" if state == "DONE" else " "
        text = _convert_inline_content(item)
        lines.append(f"- [{checked}] {text}")
    return "\n".join(lines)


def _handle_decision_list(node: dict) -> str:
    """Convert ADF decision items to a bulleted list."""
    lines: list[str] = []
    for item in node.get("content", []):
        if item.get("type") != "decisionItem":
            continue
        text = _convert_inline_content(item)
        lines.append(f"- {text}")
    return "\n".join(lines)


# ── Fallback ──────────────────────────────────────────────────────


def _fallback_text(node: dict) -> str:
    """Extract any readable text from an unknown node via recursion."""
    if "text" in node:
        return node["text"]
    content = node.get("content", [])
    if content:
        return _convert_inline_content(node)
    return ""


# ── Handler registry ──────────────────────────────────────────────

_NODE_HANDLERS: dict[str, Callable[[dict], str]] = {
    "paragraph": _handle_paragraph,
    "heading": _handle_heading,
    "blockquote": _handle_blockquote,
    "codeBlock": _handle_code_block,
    "bulletList": _handle_bullet_list,
    "orderedList": _handle_ordered_list,
    "table": _handle_table,
    "rule": _handle_rule,
    "panel": _handle_panel,
    "mediaSingle": _handle_media_single,
    "mediaGroup": _handle_media_group,
    "expand": _handle_expand,
    "nestedExpand": _handle_expand,
    "taskList": _handle_task_list,
    "decisionList": _handle_decision_list,
}
