# AI Commit

A small CLI that reads `git diff --cached`, asks OpenAI for a commit message, and
optionally opens the result in your Git editor before committing.

## Installation

AI Commit requires Python 3.11+, [`uv`](https://docs.astral.sh/uv/), and an
OpenAI API key.

```sh
./install.sh
```

The installer registers both `ai-commit` and `commit` as command names. Set the
API key before generating messages:

```sh
export OPENAI_API_KEY="your-api-key"
```

`GPT_MODEL` overrides the default model, and `AI_COMMIT_ENV_FILE` can point to a
readable dotenv file containing these variables.

## Repository-specific commit rules

Place `.ai-commit.yml` at the Git repository root to add project-specific rules
to every generated commit message. AI Commit finds the repository root even
when invoked from a subdirectory. The only supported setting is
`instructions`, which must be a YAML string:

```yaml
# .ai-commit.yml
instructions: |
  Use Conventional Commits with a scope when one is clear.
  Keep the subject imperative and under 72 characters.
  Add a BREAKING CHANGE footer for incompatible API changes.
  Mention the affected command in CLI-related commits.
```

Create the default file without calling OpenAI:

```console
$ ai-commit init
Created /path/to/project/.ai-commit.yml
```

Alternatively, distill rules from the subjects and bodies of recent commits:

```console
$ ai-commit init --distill       # inspect up to 100 commits (the default)
$ ai-commit init --distill 25    # inspect up to 25 commits
```

Distillation requires `OPENAI_API_KEY` and sends the selected commit messages,
but not their diffs, to the configured model. Review the generated rules before
using them. Every `init` mode asks before replacing an existing file:

```console
$ ai-commit init --distill
.ai-commit.yml already exists. Overwrite? [y/N] y
```

Only `y` or `yes` confirms an overwrite. Pressing Enter, answering anything
else, or running without interactive input leaves the existing file unchanged.
If the file is created or edited while distillation is running, AI Commit also
preserves it and asks you to rerun the command.

## Complete example

```console
$ cd /path/to/project
$ export OPENAI_API_KEY="your-api-key"

# Learn the repository's conventions, then review the result.
$ ai-commit init --distill 50
$ ${EDITOR:-vi} .ai-commit.yml

# Stage only the changes the generated message should describe.
$ git add src/payments.py tests/test_payments.py

# Preview a message without creating a commit.
$ ai-commit --dry-run

# Generate a new message, edit it if desired, and commit.
$ ai-commit
```

The staged diff is sent to the configured model each time a message is
generated. Use `--debug` to print the loaded repository instructions,
`--no-ask` to skip opening an editor, `--no-verify` to bypass Git hooks, and
`--rewrite-head` to regenerate and amend the latest commit message. Combine
`--rewrite-head` with `--dry-run` to preview the amendment first.
