#!/usr/bin/env python3
"""
Claude CLI `--effort` pass-through — argv contract + fail-loud validation.

Companion to test_claude_primary_e2e.py, which proves the claude-primary ROUTE
works end to end. This one pins the narrower question that route can't see: does
the effort level reach argv, and does a bad value get refused instead of quietly
dropped?

WHY fail-loud validation is load-bearing (not defensive decoration). Measured
against the installed CLI on 2026-07-30:

    $ printf 'hi' | claude --print --model sonnet --effort xhgih
    Warning: Unknown --effort value 'xhgih' — ignoring it and using the default
    effort. Valid values: low, medium, high, xhigh, max.
    <normal response>                                        # ← exit 0

So a typo is not a crash, it is a SILENT DEGRADE: the pipeline runs at default
effort, exits 0, produces a plausible report, and the only evidence is a warning
on stderr — which run_pipeline_bg redirects into a per-pipeline log nobody reads
on a green run. A gate-feeding pipeline would ship a verdict synthesized below
its intended floor with no signal. Hence: refuse at import.

Isolation: config.py reads the env at import and caches module-level constants,
so each case reloads the module under a patched environ rather than mutating
state in place. HOME/cwd are left alone — these cases touch no dotenv-sensitive
values (config.py's load_dotenv only supplies GEMINI_API_KEY, unused here).
"""

import importlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_with_effort(value):
    """Reload config+claude with CLAUDE_CLI_EFFORT set to `value`.

    `value=None` removes the var entirely (the unset case, which must be
    distinguishable from the empty string). Returns the reloaded claude module.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CLI_EFFORT"}
    if value is not None:
        env["CLAUDE_CLI_EFFORT"] = value
    with mock.patch.dict(os.environ, env, clear=True):
        config = importlib.reload(importlib.import_module("src.rdg.config"))
        claude = importlib.reload(importlib.import_module("src.rdg.claude"))
        return config, claude


class TestEffortArgv(unittest.TestCase):
    def test_unset_omits_the_flag_entirely(self):
        """Unset must not become a default we picked — the flag is absent."""
        _, claude = _reload_with_effort(None)
        argv = claude.build_argv("/usr/bin/claude")
        self.assertNotIn("--effort", argv)
        self.assertEqual(argv[:2], ["/usr/bin/claude", "--print"])

    def test_valid_effort_is_appended_after_model(self):
        """Order (model, then effort) matches spawn-claude.ts's canonical argv."""
        for level in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(level=level):
                _, claude = _reload_with_effort(level)
                argv = claude.build_argv("/usr/bin/claude")
                self.assertIn("--effort", argv)
                self.assertEqual(argv[argv.index("--effort") + 1], level)
                self.assertLess(argv.index("--model"), argv.index("--effort"))

    def test_invalid_effort_raises_rather_than_degrading(self):
        """The regression this file exists for: a typo must not reach the CLI.

        'xhgih' is the exact transposition probed above — the CLI accepts the
        process, warns, and runs at default effort. Import must refuse first.
        """
        with self.assertRaises(ValueError) as ctx:
            _reload_with_effort("xhgih")
        self.assertIn("xhgih", str(ctx.exception))

    def test_empty_string_is_invalid_not_unset(self):
        """`CLAUDE_CLI_EFFORT=` in a wrapper is a mistake, not a request for
        default behavior. Matches spawn-claude.ts, which also rejects it."""
        with self.assertRaises(ValueError):
            _reload_with_effort("")

    def test_effort_does_not_disturb_the_rest_of_argv(self):
        """Negative control: the model half of the contract is unchanged.

        Without this, a build_argv that dropped --model while adding --effort
        would still pass every assertion above.
        """
        config, claude = _reload_with_effort("max")
        argv = claude.build_argv("/usr/bin/claude")
        self.assertEqual(
            argv,
            ["/usr/bin/claude", "--print", "--model", config.CLAUDE_CLI_MODEL,
             "--effort", "max"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
