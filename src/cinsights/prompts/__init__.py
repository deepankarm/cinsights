from cinsights.settings import Paths


def render(template_name: str, **kwargs: object) -> str:
    """Render a Jinja2 template from the templates directory."""
    return Paths.jinja_env.get_template(template_name).render(**kwargs)
