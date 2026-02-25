#!/usr/bin/env python3
"""
Tests for the RDG template engine.

Covers:
- Mustache-style {{variable}} rendering
- Legacy $variable backward compatibility
- Automatic syntax detection
- Dollar sign in financial content (the root cause this fix addresses)
- Error handling for missing placeholders
- Edge cases
"""

import sys
import os
import unittest
import tempfile
import shutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rdg.template import render_template, _render_mustache, _render_legacy


class TestMustacheRendering(unittest.TestCase):
    """Tests for {{variable}} placeholder syntax."""

    def test_single_placeholder(self):
        result = render_template("Hello {{name}}", {"name": "World"})
        self.assertEqual(result, "Hello World")

    def test_multiple_placeholders(self):
        result = render_template(
            "{{greeting}} {{name}}, welcome to {{place}}",
            {"greeting": "Hello", "name": "Alice", "place": "RtB"}
        )
        self.assertEqual(result, "Hello Alice, welcome to RtB")

    def test_repeated_placeholder(self):
        result = render_template(
            "{{x}} + {{x}} = 2 * {{x}}",
            {"x": "5"}
        )
        self.assertEqual(result, "5 + 5 = 2 * 5")

    def test_underscore_in_variable_name(self):
        result = render_template(
            "{{code_primary}} and {{code_secondary}}",
            {"code_primary": "Component A", "code_secondary": "Component B"}
        )
        self.assertEqual(result, "Component A and Component B")

    def test_numeric_suffix_in_variable_name(self):
        result = render_template(
            "{{barrels_lifecycle}} {{barrels_strategy}}",
            {"barrels_lifecycle": "exports1", "barrels_strategy": "exports2"}
        )
        self.assertEqual(result, "exports1 exports2")


class TestFinancialContentWithMustache(unittest.TestCase):
    """Tests proving dollar signs in financial content don't collide with mustache syntax.

    This is the ROOT CAUSE this fix addresses: prompt templates discussing
    financial values ($85K, ~$1.2M, viewModel$) crashed with string.Template.
    """

    def test_dollar_amounts_preserved(self):
        """Dollar amounts like $85,077 must pass through unchanged."""
        template = "The salary is $85,077/year. Analysis: {{analysis}}"
        result = render_template(template, {"analysis": "looks good"})
        self.assertEqual(result, "The salary is $85,077/year. Analysis: looks good")

    def test_tilde_dollar_notation(self):
        """~$1.2M notation used in probabilistic language must be preserved."""
        template = "Median outcome: ~$1.2M advantage. Source: {{source}}"
        result = render_template(template, {"source": "Monte Carlo"})
        self.assertEqual(result, "Median outcome: ~$1.2M advantage. Source: Monte Carlo")

    def test_rxjs_observable_suffix(self):
        """viewModel$ (RxJS convention) must not be treated as a placeholder."""
        template = "Bind via viewModel$ | async. Review: {{code}}"
        result = render_template(template, {"code": "component.ts"})
        self.assertEqual(result, "Bind via viewModel$ | async. Review: component.ts")

    def test_mixed_dollar_content(self):
        """Real-world behavior-alignment.md content that previously crashed."""
        template = (
            "Template line 47 says 'median outcome suggests ~$1.2M'. "
            "The salary is $60,320/year. "
            "Phase: {{phase}}"
        )
        result = render_template(template, {"phase": "Onboarding"})
        self.assertIn("~$1.2M", result)
        self.assertIn("$60,320", result)
        self.assertIn("Onboarding", result)

    def test_dollar_in_code_examples(self):
        """Code examples with $variable syntax preserved in template content."""
        template = (
            'Check: `$code_primary` is placeholder syntax.\n'
            'Use branded types: `const salary = nominalDollars(100000);`\n'
            'Analysis: {{analysis}}'
        )
        result = render_template(template, {"analysis": "PASS"})
        self.assertIn("$code_primary", result)
        self.assertIn("PASS", result)

    def test_multiple_financial_values(self):
        """Template with many dollar values and few placeholders."""
        template = (
            "Compare:\n"
            "- 4% rule: $40,000/yr\n"
            "- RtB simulation: ~$52K/yr at P50\n"
            "- Difference: ~$12K/yr\n"
            "- 25x rule: $1,000,000\n"
            "- RtB target: ~$1.3M at 85% confidence\n"
            "\nVerdict: {{verdict}}"
        )
        result = render_template(template, {"verdict": "Simulation wins"})
        self.assertIn("$40,000", result)
        self.assertIn("~$52K", result)
        self.assertIn("$1,000,000", result)
        self.assertIn("~$1.3M", result)
        self.assertIn("Simulation wins", result)


class TestLegacyBackwardCompatibility(unittest.TestCase):
    """Tests that $variable syntax still works when no {{...}} present."""

    def test_simple_legacy_placeholder(self):
        result = render_template("Hello $name", {"name": "World"})
        self.assertEqual(result, "Hello World")

    def test_multiple_legacy_placeholders(self):
        result = render_template(
            "$greeting $name, welcome to $place",
            {"greeting": "Hello", "name": "Alice", "place": "RtB"}
        )
        self.assertEqual(result, "Hello Alice, welcome to RtB")

    def test_legacy_with_braces(self):
        """${variable} syntax also works in legacy mode."""
        result = render_template("Hello ${name}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")


class TestSyntaxAutoDetection(unittest.TestCase):
    """Tests that the engine correctly chooses mustache vs legacy mode."""

    def test_mustache_detected_when_present(self):
        """If ANY {{...}} exists, mustache mode is used."""
        result = render_template("{{greeting}} $literal_dollar", {"greeting": "Hi"})
        # In mustache mode, $literal_dollar is plain text — NOT a placeholder
        self.assertEqual(result, "Hi $literal_dollar")

    def test_legacy_used_when_no_mustache(self):
        """If no {{...}} exists, legacy mode is used."""
        result = render_template("$greeting world", {"greeting": "Hi"})
        self.assertEqual(result, "Hi world")

    def test_mustache_mode_ignores_dollar_placeholders(self):
        """Critical: in mustache mode, $variable is NOT substituted."""
        result = render_template(
            "Price: $100. Analysis: {{analysis}}",
            {"analysis": "OK"}
        )
        self.assertEqual(result, "Price: $100. Analysis: OK")


class TestErrorHandling(unittest.TestCase):
    """Tests for error cases."""

    def test_missing_mustache_placeholder_raises(self):
        """Missing key in mustache mode raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            render_template("{{missing_key}}", {})
        self.assertIn("missing_key", str(ctx.exception))

    def test_missing_legacy_placeholder_raises(self):
        """Missing key in legacy mode raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            render_template("$missing_key", {})
        self.assertIn("missing_key", str(ctx.exception))

    def test_empty_result_raises(self):
        """Template that renders to whitespace-only raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            render_template("{{x}}", {"x": "   "})
        self.assertIn("empty", str(ctx.exception).lower())

    def test_partial_missing_key_mustache(self):
        """One valid key, one missing — should raise for the missing one."""
        with self.assertRaises(ValueError) as ctx:
            render_template("{{a}} {{b}}", {"a": "present"})
        self.assertIn("b", str(ctx.exception))


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_adjacent_mustache_placeholders(self):
        result = render_template("{{a}}{{b}}", {"a": "hello", "b": "world"})
        self.assertEqual(result, "helloworld")

    def test_placeholder_in_multiline_template(self):
        template = "Line 1: {{a}}\nLine 2: {{b}}\nLine 3: no placeholder"
        result = render_template(template, {"a": "A", "b": "B"})
        self.assertEqual(result, "Line 1: A\nLine 2: B\nLine 3: no placeholder")

    def test_empty_string_value(self):
        """Empty string is a valid value (but template must not be all-whitespace after)."""
        result = render_template("prefix{{x}}suffix", {"x": ""})
        self.assertEqual(result, "prefixsuffix")

    def test_multiline_value(self):
        """Placeholder value can contain newlines."""
        result = render_template("Code:\n{{code}}\nEnd", {"code": "line1\nline2\nline3"})
        self.assertEqual(result, "Code:\nline1\nline2\nline3\nEnd")

    def test_value_with_braces(self):
        """Value containing {{ or }} should be inserted literally."""
        result = render_template("Result: {{x}}", {"x": "{{not_a_var}}"})
        # After substitution, the result contains {{not_a_var}} literally.
        # The regex won't re-process it because sub() does a single pass.
        self.assertEqual(result, "Result: {{not_a_var}}")

    def test_large_value_substitution(self):
        """Large values (file contents) substitute correctly."""
        large_content = "x" * 100_000
        result = render_template("File: {{content}}", {"content": large_content})
        self.assertEqual(result, f"File: {large_content}")

    def test_extra_keys_ignored(self):
        """Extra keys in input_data that don't appear in template are silently ignored."""
        result = render_template("{{a}}", {"a": "used", "b": "unused", "c": "also unused"})
        self.assertEqual(result, "used")

    def test_no_placeholders_at_all(self):
        """Template with no placeholders of either kind — legacy path, no substitution."""
        result = render_template("Just plain text with no placeholders", {})
        self.assertEqual(result, "Just plain text with no placeholders")


class TestKeyOrderingBehavior(unittest.TestCase):
    """Tests that pop-before-build pattern works correctly.

    The bug: functions like gemini_prompt_from_file() built input_data from
    ALL kwargs before popping reserved keys (template, template_file). This
    meant reserved keys leaked into input_data as placeholder values.

    The fix: pop reserved keys FIRST, then build input_data from remaining kwargs.

    We test the behavior through render_template directly since importing
    functions.py requires the full package tree (llm.ollama etc.).
    """

    def test_reserved_key_not_in_input_data(self):
        """Simulates the fixed behavior: template key is NOT in input_data.

        Before fix: input_data = {"template_file": "/path/to/file", "code": "..."}
        After fix:  input_data = {"code": "..."}
        """
        # Simulate the FIXED gemini_prompt_from_file behavior:
        # 1. Pop template_file from kwargs
        # 2. Build input_data from remaining kwargs only
        kwargs = {"template_file": "prompts/test.md", "code": "fn main() {}"}
        kwargs.pop("template_file")  # Step 1: pop reserved key
        input_data = {k: v for k, v in kwargs.items()}  # Step 2: build from remainder

        # template_file should NOT be in input_data
        self.assertNotIn("template_file", input_data)
        self.assertIn("code", input_data)

        # Template using {{code}} should work
        result = render_template("Review: {{code}}", input_data)
        self.assertEqual(result, "Review: fn main() {}")

    def test_reserved_key_in_template_raises(self):
        """If template uses {{template_file}} and that key was correctly popped,
        rendering should fail with a missing placeholder error."""
        kwargs = {"template_file": "prompts/test.md", "code": "fn main() {}"}
        kwargs.pop("template_file")
        input_data = {k: v for k, v in kwargs.items()}

        with self.assertRaises(ValueError) as ctx:
            render_template("File: {{template_file}}", input_data)
        self.assertIn("template_file", str(ctx.exception))

    def test_buggy_behavior_would_leak_key(self):
        """Demonstrates what the bug looked like: building input_data BEFORE popping.

        This test documents the bug so we never regress.
        """
        kwargs = {"template_file": "prompts/test.md", "code": "fn main() {}"}
        # BUG: build input_data from ALL kwargs (before popping)
        buggy_input_data = {k: v for k, v in kwargs.items()}
        # Then pop (too late — already copied into input_data)
        kwargs.pop("template_file")

        # template_file LEAKED into input_data — this is the bug
        self.assertIn("template_file", buggy_input_data)

        # With the buggy behavior, {{template_file}} would resolve (WRONG)
        buggy_result = render_template("File: {{template_file}}", buggy_input_data)
        self.assertEqual(buggy_result, "File: prompts/test.md")  # Bug: should have failed


if __name__ == "__main__":
    unittest.main()
