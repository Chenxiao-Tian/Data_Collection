"""Publish only generated summaries on a dedicated branch; never force-push."""
from pathlib import Path
import shutil
import subprocess
import tempfile


def git(*args, **kw):
    return subprocess.run(["git", *args], check=True, text=True, **kw)


def main():
    branch = "ai-radar-data"
    root = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="radar-publish-") as tmp:
        target = Path(tmp) / "output"
        # checkout's credential helper remains associated with the parent repository.
        exists = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"]).returncode == 0
        if exists:
            git("worktree", "add", "--detach", str(target), f"origin/{branch}")
        else:
            git("worktree", "add", "--detach", str(target), "HEAD")
            git("checkout", "--orphan", branch, cwd=target)
            git("rm", "-rf", ".", cwd=target)
        try:
            for name in ("index.html", "companies.json", "companies.csv", "README.md"):
                shutil.copyfile(root / "radar-output" / name, target / name)
            git("add", "index.html", "companies.json", "companies.csv", "README.md", cwd=target)
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=target).returncode:
                git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m", "data: refresh AI company evidence snapshot", cwd=target)
                git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=target)
        finally:
            git("worktree", "remove", "--force", str(target))


if __name__ == "__main__":
    main()
