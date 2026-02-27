#!/usr/bin/env python3
import subprocess
import os
import sys
from openai import OpenAI, APIConnectionError
from dotenv import load_dotenv
import argparse
import yaml

# follow symlink to get the parent directory of the script
PARENT_DIR = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(PARENT_DIR, ".env")
AI_COMMIT_ENV_FILE = os.getenv("AI_COMMIT_ENV_FILE", None)

if os.access(env_path, os.R_OK):
    load_dotenv(env_path, verbose=True)  # Load environment variables from .env file
if AI_COMMIT_ENV_FILE:
    # Check if the file exists and is readable
    if not os.path.isfile(AI_COMMIT_ENV_FILE) or not os.access(
        AI_COMMIT_ENV_FILE, os.R_OK
    ):
        print(
            f"Error: The file {AI_COMMIT_ENV_FILE} does not exist or is not readable."
        )
        sys.exit(1)
    load_dotenv(
        AI_COMMIT_ENV_FILE, verbose=True
    )  # Load environment variables from .env file

try:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
except KeyError:
    print(
        "Please set the OPENAI_API_KEY environment variable or create a .env file with the key."
    )
    sys.exit(1)
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-5-nano-2025-08-07")

client = OpenAI(api_key=OPENAI_API_KEY)

CONFIG_FILE = ".ai-commit.yml"

DEFAULT_CONFIG_CONTENT = """\
# AI Commit Configuration
# Place this file at the root of your repository.
# Instructions here will be included in the prompt when generating commit messages.

instructions: |
  Use conventional commit format (feat, fix, chore, docs, refactor, test, style, ci).
  Keep the subject line under 72 characters.
  # Add more custom instructions for this repository below:
"""


def load_repo_config():
    """Load .ai-commit.yml from the current git repo root, if present."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            return None
        repo_root = result.stdout.strip()
        config_path = os.path.join(repo_root, CONFIG_FILE)
        if not os.path.isfile(config_path):
            return None
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def init_config(force=False):
    """Create .ai-commit.yml in the current git repo root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print("Error: not inside a git repository.")
            sys.exit(1)
        repo_root = result.stdout.strip()
    except Exception as e:
        print(f"Error determining repo root: {e}")
        sys.exit(1)

    config_path = os.path.join(repo_root, CONFIG_FILE)
    existed = os.path.isfile(config_path)

    if existed and not force:
        print(f"{CONFIG_FILE} already exists. Use --force to overwrite.")
        sys.exit(0)

    with open(config_path, "w") as f:
        f.write(DEFAULT_CONFIG_CONTENT)

    action = "Overwrote" if existed else "Created"
    print(f"{action} {config_path}")


def create_temp_commit_msg_file(commit_msg, file_path="/tmp/commitmsg.txt"):
    with open(file_path, "w") as file:
        file.write(commit_msg)
    return file_path


def commit_with_editor(file_path, edit_commit: bool = True, verify: bool = True):
    command = ["git", "commit"]
    if edit_commit:
        command.append("-e")
    if not verify:
        command.append("--no-verify")
    command += ["-F", file_path]
    subprocess.run(
        command,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def get_git_diff():
    result = subprocess.run(
        ["git", "diff", "--cached"], stdout=subprocess.PIPE, text=True
    )
    return result.stdout


def get_head_diff():
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        # Might be the first commit
        result = subprocess.run(
            ["git", "show", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    return result.stdout


def amend_with_editor(file_path, edit_commit: bool = True, verify: bool = True):
    command = ["git", "commit", "--amend"]
    if edit_commit:
        command.append("-e")
    if not verify:
        command.append("--no-verify")
    command += ["-F", file_path]
    subprocess.run(
        command,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def generate_commit_message(diff, config=None):
    system_prompt = (
        "You are an expert at reading python git diffs and know how to create "
        "conventional commit messages. You only talk about the added or deleted "
        "lines, not about surrounding context."
    )

    if config and config.get("instructions"):
        system_prompt += f"\n\nAdditional instructions:\n{config['instructions']}"

    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": f"Write a (zsh compatible) commit message for the following changes, return text without tripple backticks:\n\n{diff}",
            },
        ],
    )

    return response.choices[0].message.content


def main():
    # Handle 'init' subcommand before the main argument parser
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_parser = argparse.ArgumentParser(
            prog="ai-commit init",
            description=f"Initialize {CONFIG_FILE} configuration file in the current repo.",
        )
        init_parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help=f"Overwrite existing {CONFIG_FILE}",
        )
        init_opts = init_parser.parse_args(sys.argv[2:])
        init_config(force=init_opts.force)
        return

    parser = argparse.ArgumentParser(
        prog="ai-commit",
        description="Let AI write your commit message.",
        epilog="Because you've got better things to do than writing commit messages.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Only create the commit message, but does not actually create a git commit",
    )
    parser.add_argument(
        "--ask",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Ask to use commit message before actually creating the commit, only use on an interactive terminal",
    )
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether or not to verify commit",
    )
    parser.add_argument(
        "--rewrite-head",
        action="store_true",
        default=False,
        help="Rewrite the HEAD commit message using AI (amends the last commit)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Print debug information, including instructions from .ai-commit.yml",
    )
    opts = parser.parse_args()

    config = load_repo_config()

    if opts.debug and config and config.get("instructions"):
        print(f"[debug] Loaded instructions from {CONFIG_FILE}:")
        print(config["instructions"])

    if opts.rewrite_head:
        diff = get_head_diff()
        if not diff:
            print("No diff found for HEAD commit.")
            sys.exit(1)
        max_length = (400000 * 0.9) / 4
        if len(diff) > max_length:
            print("Diff too large to process. Truncating.")
            diff = diff[:max_length]
        try:
            commit_message = generate_commit_message(diff, config=config)
        except APIConnectionError:
            print("connection error, could not generate a commit message at this point")
            sys.exit(1)
        print("Proposed commit message:")
        print(commit_message)
        if opts.dry_run:
            sys.exit(0)
        temp_file_path = create_temp_commit_msg_file(commit_message)
        amend_with_editor(temp_file_path, edit_commit=opts.ask, verify=opts.verify)
        sys.exit(0)

    diff = get_git_diff()

    max_length = (
        400000 * 0.9
    ) / 4  # gpt-5-nano-2025-08-07 has 400K context window, take 90% then divide by 4 to get rough max str length
    if len(diff) > max_length:
        print("Diff too large to process. I'm goint to cut it down to 12000 * 4 chars.")
        diff = diff[:max_length]
    if diff:
        try:
            commit_message = generate_commit_message(diff, config=config)
        except APIConnectionError:
            print("connection error, could not generate a commit message at this point")
            sys.exit(1)

        print("Commit message suggestion:")
        print(commit_message)
        if opts.dry_run:
            sys.exit(0)

        # Create a temporary file with the commit message
        temp_file_path = create_temp_commit_msg_file(commit_message)
        # Run git commit and open the editor
        commit_with_editor(temp_file_path, edit_commit=opts.ask, verify=opts.verify)
        sys.exit(0)
    else:
        print("No changes to commit.")
        sys.exit(0)


if __name__ == "__main__":
    main()
