from pathlib import Path
from typing import Any, Dict
import shutil
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Sandbox Configuration
#
# All file operations are restricted to the `data/` directory at the project
# root. This prevents tools from accidentally reading or writing outside the
# project, acting as an explicit safety boundary.
#
# Directory layout:
#   equity-pilot/
#   ├── mcp_server/
#   │   └── file_access_mcp_tools.py  ← this file
#   └── data/                         ← SANDBOX root
# ---------------------------------------------------------------------------

# Resolve SANDBOX relative to this file: mcp_server/ -> project root -> data/
SANDBOX = Path(__file__).parent.parent / "data"
SANDBOX.mkdir(exist_ok=True)  # Create data/ if it does not already exist


def _safe_path(relative: str) -> Path:
    """Resolve *relative* inside SANDBOX and reject any path that escapes it.

    Parameters
    ----------
    relative : str
        A relative path string (e.g. "reports/2024/summary.txt").

    Returns
    -------
    Path
        The fully-resolved absolute path, guaranteed to be inside SANDBOX.

    Raises
    ------
    ValueError
        If the resolved path falls outside the SANDBOX directory (e.g. via
        ".." traversal or an absolute path injection).
    """
    p = (SANDBOX / relative).resolve()
    if SANDBOX.resolve() not in p.parents and p != SANDBOX.resolve():
        raise ValueError(f"Path '{relative}' escapes the sandbox")
    return p


# ===========================================================================
# File CRUD Tools
#
# These five primitives mirror the standard file operations an LLM agent
# needs: list, read, write, edit (patch), and delete.
# Each function is intentionally kept small so that tool docstrings serve as
# the sole source of truth for the MCP schema exposed to the model.
# ===========================================================================

def list_files(subdir: str = "") -> list[str]:
    """List all files and folders inside the sandbox (or an optional sub-directory).

    Parameters
    ----------
    subdir : str, optional
        A relative path within the sandbox to list. Defaults to the sandbox
        root when empty.

    Returns
    -------
    list[str]
        Sorted list of paths relative to the sandbox root.
    """
    target = _safe_path(subdir) if subdir else SANDBOX
    return sorted(str(p.relative_to(SANDBOX)) for p in target.iterdir())


def read_file(path: str) -> str:
    """Read and return the full text content of a sandbox file.

    Parameters
    ----------
    path : str
        Relative path to the file within the sandbox.

    Returns
    -------
    str
        UTF-8 decoded file contents.
    """
    return _safe_path(path).read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    """Create or overwrite a text file inside the sandbox.

    Any missing parent directories are created automatically.

    Parameters
    ----------
    path : str
        Relative path for the file to write (e.g. "reports/out.txt").
    content : str
        Full text content to write to the file.

    Returns
    -------
    str
        Confirmation message including the number of characters written.
    """
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


def edit_file(path: str, old: str, new: str) -> str:
    """Replace the first (and only) occurrence of *old* with *new* in a file.

    The strict single-match requirement forces the caller to supply enough
    context to uniquely identify the target, avoiding silent multi-site edits.

    Parameters
    ----------
    path : str
        Relative path to the file within the sandbox.
    old : str
        Exact substring to find and replace. Must appear exactly once.
    new : str
        Replacement string.

    Returns
    -------
    str
        Confirmation message on success.

    Raises
    ------
    ValueError
        If *old* is not found, or if it appears more than once.
    """
    p = _safe_path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        raise ValueError("old string not found")
    if count > 1:
        raise ValueError(f"old string matches {count} locations — make it unique")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"Edited {path}"


def delete_file(path: str) -> str:
    """Delete a file or directory (including all contents) inside the sandbox.

    Parameters
    ----------
    path : str
        Relative path to the file or directory to delete.

    Returns
    -------
    str
        Confirmation message on success.
    """
    p = _safe_path(path)
    if p.is_dir():
        shutil.rmtree(p)  # Recursively remove non-empty directories
    else:
        p.unlink()
    return f"Deleted {path}"


# ---------------------------------------------------------------------------
# Tool Registry
#
# ALL_TOOLS maps each tool name (as it will appear in the MCP schema) to its
# implementing function. Add new file-access tools here to make them
# available for auto-registration via `register_all_file_access_tools`.
# ---------------------------------------------------------------------------

ALL_TOOLS: Dict[str, Any] = {
    "list_files": list_files,
    "read_file":  read_file,
    "write_file": write_file,
    "edit_file":  edit_file,
    "delete_file": delete_file,
}


def register_all_file_access_tools(mcp) -> None:
    """Register every tool in ALL_TOOLS with a FastMCP server instance.

    This is the preferred entry point for including file-access tools in the
    equity-pilot MCP server. Iterate over ALL_TOOLS so that adding a new tool
    only requires a single entry in the dict above.

    Usage example (from mcp_server.py)::

        from fastmcp import FastMCP
        from mcp_server.file_access_mcp_tools import register_all_file_access_tools

        mcp = FastMCP("equity-pilot")
        register_all_file_access_tools(mcp)
        mcp.run()

    Parameters
    ----------
    mcp : FastMCP
        Any MCP server object that exposes a ``.tool(name=...)`` decorator
        method (e.g. a ``FastMCP`` instance).
    """
    for name, fn in ALL_TOOLS.items():
        mcp.tool(name=name)(fn)


if __name__ == "__main__":
    # Stand-alone mode: spin up a dedicated MCP server exposing only the
    # file-access tools. In production, mcp_server.py aggregates tools from
    # multiple modules (screener + file access) into a single server.
    mcp = FastMCP("equity-pilot")
    register_all_file_access_tools(mcp)
    mcp.run()