#!/usr/bin/env python3
import subprocess
import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

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
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

# print("Using OpenAI API key:", OPENAI_API_KEY)
# print("Using GPT model:", GPT_MODEL)
client = OpenAI(api_key=OPENAI_API_KEY)


def create_temp_commit_msg_file(commit_msg, file_path="/tmp/commitmsg.txt"):
    with open(file_path, "w") as file:
        file.write(commit_msg)
    return file_path


def commit_with_editor(file_path):
    subprocess.run(
        ["git", "commit", "-e", "-F", file_path],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def get_git_diff():
    result = subprocess.run(
        ["git", "diff", "--cached"], stdout=subprocess.PIPE, text=True
    )
    return result.stdout


def generate_commit_message(diff):
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are an expert at reading python git diffs and know how to create conventional commit messages. You only talk about the added or deleted lines, not about surrounding context.",
            },
            {
                "role": "user",
                "content": f"Write a (zsh compatible) commit message for the following changes, return text without tripple backticks:\n\n{diff}",
            },
        ],
    )

    return response.choices[0].message.content


def main():
    diff = get_git_diff()
    if len(diff) > 16000:
        print("Diff too large to process. I'm goint to cut it down to 12000 chars.")
        diff = diff[:12000]
    if diff:
        commit_message = generate_commit_message(diff)
        print("Commit message suggestion:")
        print(commit_message)

        # use_message = (
        #     input("Do you want to use this commit message? (Yes/No): ").strip().lower()
        # )
        use_message = "yes"
        if use_message == "yes":
            # Create a temporary file with the commit message
            temp_file_path = create_temp_commit_msg_file(commit_message)
            # Run git commit and open the editor
            commit_with_editor(temp_file_path)
        else:
            print("Commit message not used.")
    else:
        print("No changes to commit.")


if __name__ == "__main__":
    main()
