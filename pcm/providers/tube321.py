"""Independent 321tube post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class Tube321Provider(HtmlPostProvider):
    name = "tube321"
    display_name = "321tube"
    hosts = {"321tube.com"}
