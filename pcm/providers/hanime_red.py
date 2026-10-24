"""Independent hanime post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class HanimeRedProvider(HtmlPostProvider):
    name = "hanime_red"
    display_name = "hanime"
    hosts = {"hanime.red"}
