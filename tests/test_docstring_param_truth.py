"""A formula's docstring is its published interface: downstream doc surfaces render docstrings,
and authors (human or LLM) copy parameter names from them. A docstring naming a parameter the
function does not accept sends every author into a runtime error the docs told them was correct
(observed live: DIRECTORYTOMARKDOWN documented `directory_path` while raising "The parameter
'directory' is required" — one downstream agent pass burned per consumer).

This test closes the class, not the instance: for every registered formula whose source raises
"The parameter 'X' is required", the docstring must mention X.
"""

import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.rdg.functions import FUNCTION_REGISTRY

REQUIRED_RE = re.compile(r"[Tt]he (?:parameter )?'?(\w+)'? (?:parameter )?is required")


def test_every_required_param_appears_in_its_docstring():
    failures = []
    for name, func in FUNCTION_REGISTRY.items():
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError):
            continue
        doc = inspect.getdoc(func) or ""
        for match in REQUIRED_RE.finditer(source):
            param = match.group(1)
            if not re.search(rf"\b{re.escape(param)}\b", doc):
                failures.append(f"{name}: raises for required param '{param}' but its docstring never mentions it")
    assert failures == [], "\n".join(failures)


def test_directorytomarkdown_docstring_names_the_real_param():
    # The observed instance, pinned directly: the docs said directory_path, the code wants directory.
    doc = inspect.getdoc(FUNCTION_REGISTRY["DIRECTORYTOMARKDOWN"]) or ""
    assert "directory (str)" in doc
    assert "directory_path" not in doc
