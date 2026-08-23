"""Git auto-update helpers."""
import os
import shutil
import subprocess


def git_available():
    return shutil.which("git") is not None and os.path.isdir(".git")


def current_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "unknown"


def pull():
    """Return (changed: bool, message: str)."""
    if not git_available():
        return False, "Not a git clone (or git not installed)."
    try:
        out = subprocess.check_output(
            ["git", "pull", "--ff-only"], stderr=subprocess.STDOUT, text=True)
        return ("Already up to date" not in out), out.strip()
    except subprocess.CalledProcessError as e:
        return False, f"git pull failed:\n{e.output}"
