"""Entry point. Auto-updates from git (if enabled) then launches the app."""
import os
import sys
import shutil
import subprocess


def _auto_update():
    if not (shutil.which("git") and os.path.isdir(".git")):
        return
    try:
        out = subprocess.check_output(["git", "pull", "--ff-only"],
                                      stderr=subprocess.STDOUT, text=True)
        if "Already up to date" not in out:
            print("Updated from git - reloading...")
            os.execv(sys.executable, [sys.executable, __file__, "--updated"])
    except Exception as e:
        print("Update check skipped:", e)


def main():
    # avoid infinite reload loop; honor user setting
    if "--updated" not in sys.argv:
        try:
            from voiceclone.storage import load_settings
            if load_settings().get("auto_update", True):
                _auto_update()
        except Exception:
            pass
    from voiceclone.app import launch
    launch()


if __name__ == "__main__":
    main()
