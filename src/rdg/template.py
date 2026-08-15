import re
from string import Template

# Mustache-style pattern: matches {{variable_name}}
# Whitespace inside the braces is tolerated: {{name}} and {{ name }} are the same placeholder.
# The strict form silently DID NOT MATCH a spaced placeholder, so {{ src }} rendered as its own
# literal text — a template that looked one character-class away from correct produced a wrong
# artifact that verified clean. An LLM authoring loop failed to converge on that difference across
# four passes; a human squints at it too. Postel's law, scoped to whitespace only.
_MUSTACHE_RE = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}')

def render_template(template_str, input_data):
    """Render template by replacing placeholders with input_data values.

    Supports two syntaxes:
    - {{variable}} (mustache-style, preferred — no collision with $ in financial content)
    - $variable (legacy Python string.Template style, for backward compatibility)

    If the template contains any {{...}} placeholders, mustache-style is used.
    Otherwise, falls back to legacy $variable substitution.
    """
    if _MUSTACHE_RE.search(template_str):
        return _render_mustache(template_str, input_data)
    else:
        return _render_legacy(template_str, input_data)

def _render_mustache(template_str, input_data):
    """Render using {{variable}} placeholders."""
    def replacer(match):
        key = match.group(1)
        if key not in input_data:
            raise ValueError(f"Template placeholder not found: '{key}'")
        return input_data[key]

    try:
        rendered = _MUSTACHE_RE.sub(replacer, template_str)
        if not rendered.strip():
            raise ValueError("Rendered template is empty or contains only whitespace.")
        return rendered
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Template rendering failed: {e}")

def _render_legacy(template_str, input_data):
    """Render using $variable placeholders (backward compatibility)."""
    try:
        template = Template(template_str)
        rendered = template.substitute(input_data)
        if not rendered.strip():
            raise ValueError("Rendered template is empty or contains only whitespace.")
        return rendered
    except KeyError as e:
        raise ValueError(f"Template placeholder not found: {e}")
    except Exception as e:
        raise RuntimeError(f"Template rendering failed: {e}")
