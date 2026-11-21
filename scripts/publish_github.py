"""Create a new public repository only after staged-file review and local verification."""

import argparse
import os
import re
import subprocess

import httpx

from marketing.config import ROOT


def git(*args, **kwargs):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, **kwargs
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.publish:
        raise SystemExit("Review files and tests first, then pass --publish explicitly.")
    env = {**os.environ, "GCM_INTERACTIVE": "Never", "GIT_TERMINAL_PROMPT": "0"}
    credentials = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )
    values = dict(line.split("=", 1) for line in credentials.stdout.splitlines() if "=" in line)
    if not values.get("password"):
        raise SystemExit("No authenticated GitHub credential available.")
    with httpx.Client(
        headers={"Authorization": "Bearer " + values["password"], "Accept": "application/vnd.github+json"},
        timeout=30,
    ) as client:
        response = client.get("https://api.github.com/user")
        response.raise_for_status()
        account = response.json()
        login = account["login"]
        git("add", ".")
        staged = git("diff", "--cached", "--name-only", "-z").split("\0")
        sensitive = re.compile(
            rb"(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
        )
        for name in filter(None, staged):
            if name == ".env" or name.startswith(("data/", "artifacts/", ".venv/", "web/node_modules/")):
                raise SystemExit("Private/runtime file staged: " + name)
            file = ROOT / name
            if file.exists() and file.stat().st_size < 5_000_000 and sensitive.search(file.read_bytes()):
                raise SystemExit("Possible credential in staged file: " + name)
        git("config", "user.name", login)
        git("config", "user.email", f"{account['id']}+{login}@users.noreply.github.com")
        git("branch", "-M", "main")
        git("commit", "-m", "Build marketing report skill and evidence-grounded research agent")
        name = "marketing-analysis-agent"
        for candidate in [name, name + "-portfolio"]:
            exists = client.get(f"https://api.github.com/repos/{login}/{candidate}")
            if exists.status_code == 404:
                name = candidate
                break
            exists.raise_for_status()
        else:
            raise SystemExit("Both repository names already exist; nothing overwritten.")
        response = client.post(
            "https://api.github.com/user/repos",
            json={
                "name": name,
                "description": "Evidence-grounded marketing analysis agent: report Skill, research Loop, durable execution and reproducible evaluations.",
                "private": False,
                "auto_init": False,
            },
        )
        response.raise_for_status()
        repo = response.json()
        git("remote", "add", "origin", repo["clone_url"])
        git("push", "-u", "origin", "main", env=env)
        print(repo["html_url"])


if __name__ == "__main__":
    main()
