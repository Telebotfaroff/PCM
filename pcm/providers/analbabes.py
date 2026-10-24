"""Independent AnalBabes post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class AnalBabesProvider(HtmlPostProvider):
    name = "analbabes"
    display_name = "AnalBabes"
    hosts = {"analbabes.porn"}
