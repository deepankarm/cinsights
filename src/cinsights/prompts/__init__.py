from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), keep_trailing_newline=True)


def render(template_name: str, **kwargs: object) -> str:
    """Render a Jinja2 template from the templates directory."""
    return _env.get_template(template_name).render(**kwargs)
