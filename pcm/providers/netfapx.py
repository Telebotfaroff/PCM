"""Independent Netfapx post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class NetfapxProvider(HtmlPostProvider):
    name = "netfapx"
    display_name = "Netfapx"
    hosts = {"netfapx.com"}
