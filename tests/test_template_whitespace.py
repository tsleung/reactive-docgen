"""{{ name }} and {{name}} are the same placeholder.

The strict pattern silently skipped spaced placeholders, so a template one whitespace away from
correct rendered its own literal text as the artifact — and verified clean. Hermetic.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.rdg.template import render_template


class WhitespaceTolerantMustache(unittest.TestCase):
    def test_spaced_and_tight_are_the_same_placeholder(self):
        self.assertEqual(render_template("{{name}}", {"name": "X"}), "X")
        self.assertEqual(render_template("{{ name }}", {"name": "X"}), "X")
        self.assertEqual(render_template("{{  name  }}", {"name": "X"}), "X")

    def test_unknown_spaced_placeholder_raises_like_tight(self):
        with self.assertRaises(ValueError):
            render_template("{{ missing }}", {"name": "X"})

    def test_replacement_text_is_not_rescanned(self):
        # A substituted value containing a placeholder-shaped string stays literal.
        self.assertEqual(render_template("{{a}}", {"a": "{{ b }}"}), "{{ b }}")


if __name__ == "__main__":
    unittest.main()
