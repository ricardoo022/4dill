import os
import subprocess
import sys
from pathlib import Path

# Ensure the repository root (project workspace) is on sys.path so tests
# importing `src.*` resolve correctly when run from different CWDs.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv_if_present() -> None:
    """Load .env values into process env without overriding existing vars.

    Works for both regular checkouts and git worktrees by trying:
    1) current repository root
    2) git common-dir parent (main repo root in worktree setups)
    """
    candidates: list[Path] = [ROOT / ".env"]

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        git_common_dir = Path(result.stdout.strip()).resolve()
        candidates.append(git_common_dir.parent / ".env")
    except Exception:
        pass

    seen: set[Path] = set()
    for dotenv_path in candidates:
        if dotenv_path in seen or not dotenv_path.exists():
            continue
        seen.add(dotenv_path)

        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


_load_dotenv_if_present()
