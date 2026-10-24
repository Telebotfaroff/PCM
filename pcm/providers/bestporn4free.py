"""Independent BestPorn4Free post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class BestPorn4FreeProvider(HtmlPostProvider):
    name = "bestporn4free"
    display_name = "BestPorn4Free"
    hosts = {"bestporn4free.com"}
