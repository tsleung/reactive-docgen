from string import Template
from typing import Dict

def render_template(template_str, input_data):
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