"""GitHub integration — secure token handling + repo operations.

Token security model:
  * The PAT is stored via the OS credential vault (Windows Credential Manager
    through ``keyring``).  It is NEVER written to project files, settings JSON,
    the HTML preview, or the git repository.
  * Git pushes use a temporary GIT_ASKPASS helper so the token never appears
    in remote URLs or .git/config.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple

import requests

KEYRING_SERVICE = "NTH — Blox Fruits Automation Suite"
KEYRING_USER = "github_pat"
API = "https://api.github.com"
TIMEOUT = 20


class TokenStore:
    """OS-keyring backed token storage with a guarded file fallback."""

    def __init__(self):
        self._backend = "keyring"
        try:
            import keyring
            keyring.get_password(KEYRING_SERVICE, KEYRING_USER)  # probe
        except Exception:
            self._backend = "none"

    @property
    def backend(self) -> str:
        return self._backend

    def save(self, token: str) -> bool:
        token = (token or "").strip()
        if not token:
            return False
        if self._backend == "keyring":
            import keyring
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, token)
            return True
        return False

    def load(self) -> Optional[str]:
        if self._backend == "keyring":
            import keyring
            return keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        return None

    def clear(self) -> None:
        if self._backend == "keyring":
            import keyring
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
            except Exception:
                pass


class GitHubClient:
    def __init__(self, token: str):
        self.token = (token or "").strip()
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })

    # ------------------------------------------------------------------ API
    def whoami(self) -> Tuple[bool, str]:
        """(ok, login or error message)."""
        try:
            r = self.session.get(f"{API}/user", timeout=TIMEOUT)
            if r.status_code == 200:
                return True, r.json().get("login", "")
            return False, f"HTTP {r.status_code}: {r.json().get('message', 'auth failed')}"
        except Exception as exc:      # noqa: BLE001
            return False, str(exc)

    def repo_exists(self, login: str, name: str) -> Optional[bool]:
        try:
            r = self.session.get(f"{API}/repos/{login}/{name}", timeout=TIMEOUT)
            return r.status_code == 200
        except Exception:
            return None

    def create_repo(self, name: str, description: str = "", private: bool = True
                    ) -> Tuple[bool, str]:
        try:
            r = self.session.post(f"{API}/user/repos", json={
                "name": name, "description": description, "private": private,
                "auto_init": False,
            }, timeout=TIMEOUT)
            if r.status_code in (200, 201):
                html = r.json().get("html_url", "")
                return True, html
            if r.status_code == 422:
                return False, "Repository already exists"
            return False, f"HTTP {r.status_code}: {r.json().get('message', 'error')}"
        except Exception as exc:      # noqa: BLE001
            return False, str(exc)

    # ------------------------------------------------------------------- git
    def push_repo(self, repo_dir: Path, repo_name: str, commit_message: str,
                  progress=lambda s: None) -> Tuple[bool, str]:
        """Create/ensure repo, commit everything and push. Token-safe."""
        repo_dir = Path(repo_dir)
        ok, login = self.whoami()
        if not ok:
            return False, f"Authentication failed: {login}"

        if not self.repo_exists(login, repo_name):
            progress("Creating repository…")
            ok, msg = self.create_repo(repo_name,
                                       "NTH — Blox Fruits Automation Suite", True)
            if not ok and "already exists" not in msg:
                return False, msg

        env_base = dict(os.environ)
        env_base["GIT_TERMINAL_PROMPT"] = "0"

        def git(*args: str) -> Tuple[bool, str]:
            r = subprocess.run(["git", *args], cwd=repo_dir, env=env_base,
                               capture_output=True, text=True, timeout=180)
            return r.returncode == 0, (r.stdout + r.stderr).strip()

        for step in (["init", "-b", "main"], ["add", "-A"],):
            ok, out = git(*step)
            if not ok:
                return False, f"git {step[0]} failed: {out}"

        status_ok, out = git("diff", "--cached", "--quiet")
        if not status_ok:                     # something staged -> commit
            git("config", "user.name", "NTH")
            git("config", "user.email", "nth@users.noreply.github.com")
            ok, out = git("commit", "-m", commit_message)
            progress("Committed")

        url = f"https://github.com/{login}/{repo_name}.git"
        git("remote", "remove", "origin")
        ok, out = git("remote", "add", "origin", url)
        if not ok:
            return False, f"remote failed: {out}"

        # Token via temporary askpass helper — never in args/URL/config.
        askpass_dir = tempfile.mkdtemp(prefix="nth-git-")
        try:
            helper = Path(askpass_dir) / ("askpass.cmd" if os.name == "nt" else "askpass.sh")
            token = self.token
            if os.name == "nt":
                helper.write_text("@echo off\n"
                                  "if /I \"%~1\"==\"Username for https://github.com: \" "
                                  "echo x-access-token\r\n"
                                  f"if /I \"%~1\"==\"Password for https://x-access-token@github.com: \" "
                                  "echo " + token + "\r\n", encoding="utf-8")
            else:
                helper.write_text(
                    "#!/bin/sh\n"
                    'case "$1" in\n'
                    '  Username*) echo "x-access-token" ;;\n'
                    '  Password*) echo "%s" ;;\n'
                    "esac\n" % token, encoding="utf-8")
                helper.chmod(0o700)
            env = dict(env_base)
            env["GIT_ASKPASS"] = str(helper)
            env["GIT_USERNAME"] = "x-access-token"
            env["GIT_PASSWORD"] = token
            progress("Pushing to GitHub…")
            r = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_dir,
                               env=env, capture_output=True, text=True, timeout=300)
            out = (r.stdout + r.stderr).strip()
            # never leak the token through git output
            out = out.replace(token, "***")
            if r.returncode != 0:
                return False, f"push failed: {out}"
            return True, f"Pushed to https://github.com/{login}/{repo_name}"
        finally:
            shutil.rmtree(askpass_dir, ignore_errors=True)
