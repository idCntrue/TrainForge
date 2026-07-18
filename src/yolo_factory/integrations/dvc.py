import subprocess
import sys
from pathlib import Path


class DvcAdapter:
    def __init__(self, repository: Path) -> None:
        self.repository = repository

    def add(self, path: Path) -> None:
        subprocess.run(
            [sys.executable, "-m", "dvc", "add", str(path)],
            cwd=self.repository,
            check=True,
            text=True,
            capture_output=True,
        )

    def initialize(self) -> None:
        if not (self.repository / ".dvc").exists():
            subprocess.run(
                [sys.executable, "-m", "dvc", "init", "--no-scm"],
                cwd=self.repository,
                check=True,
                text=True,
                capture_output=True,
            )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "dvc",
                "config",
                "cache.dir",
                "dvc-cache",
            ],
            cwd=self.repository,
            check=True,
            text=True,
            capture_output=True,
        )
