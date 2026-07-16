import argparse
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml

from ai_commit import commit


def openai_client_with(*, content=None, side_effect=None):
    """Build a mock matching the portion of the OpenAI client that we use."""
    create = Mock(side_effect=side_effect)
    if side_effect is None:
        create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return client, create


class PositiveIntegerTests(unittest.TestCase):
    def test_accepts_positive_integer(self):
        self.assertEqual(commit.positive_int("17"), 17)

    def test_rejects_non_positive_and_non_numeric_values(self):
        for value in ("0", "-1", "not-a-number"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    commit.positive_int(value)


class InitParserTests(unittest.TestCase):
    def test_top_level_help_lists_init_and_distill(self):
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["ai-commit", "--help"]),
            patch("sys.stdout", new=output),
            self.assertRaises(SystemExit) as raised,
        ):
            commit.main()

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("init", output.getvalue())
        self.assertIn("--distill [N]", output.getvalue())

    def test_init_help_documents_distill_without_initializing(self):
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["ai-commit", "init", "--help"]),
            patch.object(commit, "init_config") as init_config,
            patch("sys.stdout", new=output),
            self.assertRaises(SystemExit) as raised,
        ):
            commit.main()

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("[--distill [N]]", output.getvalue())
        self.assertIn("default: 100", output.getvalue())
        init_config.assert_not_called()

    def test_init_without_distill_uses_default_template(self):
        with (
            patch.object(sys, "argv", ["ai-commit", "init"]),
            patch.object(commit, "init_config", return_value=True) as init_config,
        ):
            commit.main()

        init_config.assert_called_once_with(distill_count=None)

    def test_distill_without_count_defaults_to_100(self):
        with (
            patch.object(sys, "argv", ["ai-commit", "init", "--distill"]),
            patch.object(commit, "init_config", return_value=True) as init_config,
        ):
            commit.main()

        init_config.assert_called_once_with(distill_count=100)

    def test_distill_accepts_custom_count(self):
        with (
            patch.object(sys, "argv", ["ai-commit", "init", "--distill", "23"]),
            patch.object(commit, "init_config", return_value=True) as init_config,
        ):
            commit.main()

        init_config.assert_called_once_with(distill_count=23)

    def test_distill_rejects_invalid_count_before_initializing(self):
        for value in ("0", "-2", "invalid"):
            with self.subTest(value=value):
                with (
                    patch.object(
                        sys, "argv", ["ai-commit", "init", "--distill", value]
                    ),
                    patch.object(commit, "init_config") as init_config,
                    patch("sys.stderr", new=io.StringIO()),
                    self.assertRaises(SystemExit) as raised,
                ):
                    commit.main()

                self.assertEqual(raised.exception.code, 2)
                init_config.assert_not_called()


class OverwriteConfirmationTests(unittest.TestCase):
    def test_accepts_yes_case_insensitively(self):
        for answer in ("y", "YES", " yes "):
            with self.subTest(answer=answer):
                with patch("builtins.input", return_value=answer) as prompt:
                    self.assertTrue(commit.confirm_overwrite("/repo/.ai-commit.yml"))
                prompt.assert_called_once()

    def test_declines_non_affirmative_answers(self):
        for answer in ("", "n", "maybe"):
            with self.subTest(answer=answer):
                with patch("builtins.input", return_value=answer):
                    self.assertFalse(
                        commit.confirm_overwrite("/repo/.ai-commit.yml")
                    )

    def test_eof_declines_overwrite(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("builtins.print"),
        ):
            self.assertFalse(commit.confirm_overwrite("/repo/.ai-commit.yml"))


class GitHistoryTests(unittest.TestCase):
    def test_reads_subjects_and_bodies_with_requested_limit(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "feat(cli): add init\n\nExplain the new command.\x1e\n"
                "fix: preserve config\x1e\n"
            ),
            stderr="",
        )
        with patch.object(commit.subprocess, "run", return_value=completed) as run:
            messages = commit.get_recent_commit_messages(12, "/work/repository")

        self.assertEqual(
            messages,
            [
                "feat(cli): add init\n\nExplain the new command.",
                "fix: preserve config",
            ],
        )
        run.assert_called_once_with(
            ["git", "log", "-n", "12", "--format=%B%x1e"],
            cwd="/work/repository",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_command_failure_raises_user_facing_error(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="fatal: bad revision"
        )
        with patch.object(commit.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(commit.AICommitError, "bad revision"):
                commit.get_recent_commit_messages(10, "/work/repository")

    def test_empty_history_raises_user_facing_error(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=" \n\x1e\n", stderr=""
        )
        with patch.object(commit.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(commit.AICommitError, "no commits"):
                commit.get_recent_commit_messages(10, "/work/repository")


class DistillationTests(unittest.TestCase):
    def test_sends_commit_messages_and_returns_stripped_rules(self):
        fake_client, create = openai_client_with(
            content="\nUse Conventional Commit types.\nKeep subjects imperative.\n"
        )
        messages = [
            "feat(cli): add init\n\nDocument the flag.",
            "fix: preserve existing config",
        ]

        with patch.object(commit, "get_openai_client", return_value=fake_client):
            rules = commit.distill_commit_rules(messages)

        self.assertEqual(
            rules, "Use Conventional Commit types.\nKeep subjects imperative."
        )
        create.assert_called_once()
        request = create.call_args.kwargs
        self.assertEqual(request["model"], commit.GPT_MODEL)
        roles = [item["role"] for item in request["messages"]]
        self.assertEqual(roles, ["system", "user"])
        prompt = request["messages"][1]["content"]
        for message in messages:
            self.assertIn(message, prompt)

    def test_empty_model_output_is_rejected(self):
        fake_client, _ = openai_client_with(content="  \n")
        with patch.object(commit, "get_openai_client", return_value=fake_client):
            with self.assertRaisesRegex(
                commit.AICommitError, "no commit-message rules"
            ):
                commit.distill_commit_rules(["feat: example"])

    def test_malformed_model_response_is_rejected(self):
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(return_value=SimpleNamespace(choices=[]))
                )
            )
        )
        with patch.object(commit, "get_openai_client", return_value=fake_client):
            with self.assertRaisesRegex(commit.AICommitError, "invalid.*response"):
                commit.distill_commit_rules(["feat: example"])

    def test_api_errors_propagate(self):
        fake_client, _ = openai_client_with(side_effect=RuntimeError("offline"))
        with patch.object(commit, "get_openai_client", return_value=fake_client):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                commit.distill_commit_rules(["feat: example"])


class ConfigRenderingTests(unittest.TestCase):
    def test_default_config_is_valid_yaml(self):
        config = yaml.safe_load(commit.render_config())

        self.assertEqual(set(config), {"instructions"})
        self.assertIn("conventional commit", config["instructions"].lower())

    def test_distilled_config_preserves_yaml_sensitive_text(self):
        rules = (
            "Use feat(scope): imperative summary # under 72 chars.\n"
            "\n"
            "Mention café changes and O'Reilly references in the body."
        )

        rendered = commit.render_config(rules, sample_count=7)
        config = yaml.safe_load(rendered)

        self.assertEqual(config, {"instructions": rules + "\n"})
        self.assertIn("# Distilled from 7 recent commit messages.", rendered)

    def test_distilled_config_rejects_invalid_yaml_characters(self):
        with self.assertRaisesRegex(commit.AICommitError, "cannot be stored in YAML"):
            commit.render_config("Use feat subjects.\x00")


class ConfigLoadingTests(unittest.TestCase):
    def load_config_text(self, text):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        Path(directory.name, commit.CONFIG_FILE).write_text(text)
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=directory.name, stderr=""
        )
        with patch.object(commit.subprocess, "run", return_value=completed):
            return commit.load_repo_config()

    def test_requires_top_level_mapping(self):
        with self.assertRaisesRegex(commit.AICommitError, "YAML mapping"):
            self.load_config_text("- one\n- two\n")

    def test_requires_string_instructions(self):
        with self.assertRaisesRegex(commit.AICommitError, "YAML string"):
            self.load_config_text("instructions: 42\n")

    def test_reports_malformed_yaml(self):
        with self.assertRaisesRegex(commit.AICommitError, "could not read"):
            self.load_config_text("instructions: [unterminated\n")


class InitConfigTests(unittest.TestCase):
    def test_creates_default_config_without_prompt_git_history_or_api(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(commit, "confirm_overwrite") as confirm,
                patch.object(commit, "get_recent_commit_messages") as history,
                patch.object(commit, "get_openai_client") as get_client,
            ):
                created = commit.init_config()

            self.assertTrue(created)
            self.assertTrue(config_path.is_file())
            self.assertIn("instructions", yaml.safe_load(config_path.read_text()))
            confirm.assert_not_called()
            history.assert_not_called()
            get_client.assert_not_called()

    def test_declined_overwrite_preserves_exact_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            original = b"instructions: |\n  Keep this exact config.\n"
            config_path.write_bytes(original)

            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(
                    commit, "confirm_overwrite", return_value=False
                ) as confirm,
                patch.object(commit, "get_recent_commit_messages") as history,
                patch.object(commit, "distill_commit_rules") as distill,
                patch("builtins.print"),
            ):
                created = commit.init_config(distill_count=100)

            self.assertFalse(created)
            self.assertEqual(config_path.read_bytes(), original)
            confirm.assert_called_once_with(str(config_path))
            history.assert_not_called()
            distill.assert_not_called()

    def test_confirmed_overwrite_replaces_default_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            config_path.write_text("instructions: old\n")

            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(commit, "confirm_overwrite", return_value=True) as confirm,
            ):
                created = commit.init_config()

            self.assertTrue(created)
            confirm.assert_called_once_with(str(config_path))
            self.assertIn(
                "conventional commit",
                yaml.safe_load(config_path.read_text())["instructions"].lower(),
            )

    def test_distillation_writes_rules_and_uses_actual_history_count(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            messages = ["feat: one", "fix: two"]
            rules = "Use feat and fix types.\nKeep subjects concise."

            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(
                    commit, "get_recent_commit_messages", return_value=messages
                ) as history,
                patch.object(
                    commit, "distill_commit_rules", return_value=rules
                ) as distill,
            ):
                created = commit.init_config(distill_count=25)

            self.assertTrue(created)
            history.assert_called_once_with(25, directory)
            distill.assert_called_once_with(messages)
            loaded = yaml.safe_load(config_path.read_text())
            self.assertEqual(loaded["instructions"].rstrip("\n"), rules)
            self.assertIn(
                "Distilled from 2 recent commit messages", config_path.read_text()
            )

    def test_api_failure_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            original = b"instructions: |\n  Never truncate me.\n"
            config_path.write_bytes(original)
            fake_client, _ = openai_client_with(side_effect=RuntimeError("offline"))

            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(commit, "confirm_overwrite", return_value=True),
                patch.object(
                    commit,
                    "get_recent_commit_messages",
                    return_value=["feat: example"],
                ),
                patch.object(commit, "get_openai_client", return_value=fake_client),
                patch("builtins.print"),
            ):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    commit.init_config(distill_count=1)

            self.assertEqual(config_path.read_bytes(), original)

    def test_config_created_during_distillation_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            concurrent = "instructions: created concurrently\n"

            def create_config(_messages):
                config_path.write_text(concurrent)
                return "Use feat subjects."

            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(
                    commit,
                    "get_recent_commit_messages",
                    return_value=["feat: example"],
                ),
                patch.object(
                    commit, "distill_commit_rules", side_effect=create_config
                ),
                patch("builtins.print"),
            ):
                with self.assertRaisesRegex(commit.AICommitError, "appeared"):
                    commit.init_config(distill_count=1)

            self.assertEqual(config_path.read_text(), concurrent)

    def test_config_edited_during_distillation_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory, commit.CONFIG_FILE)
            config_path.write_text("instructions: original\n")
            concurrent = "instructions: edited concurrently\n"

            def edit_config(_messages):
                config_path.write_text(concurrent)
                return "Use feat subjects."

            with (
                patch.object(commit, "get_repo_root", return_value=directory),
                patch.object(commit, "confirm_overwrite", return_value=True),
                patch.object(
                    commit,
                    "get_recent_commit_messages",
                    return_value=["feat: example"],
                ),
                patch.object(commit, "distill_commit_rules", side_effect=edit_config),
                patch("builtins.print"),
            ):
                with self.assertRaisesRegex(commit.AICommitError, "changed"):
                    commit.init_config(distill_count=1)

            self.assertEqual(config_path.read_text(), concurrent)


if __name__ == "__main__":
    unittest.main()
