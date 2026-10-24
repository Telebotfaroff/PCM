"""Independent POR N4DAYS post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class Porn4DaysProvider(HtmlPostProvider):
    name = "porn4days"
    display_name = "PORN4DAYS"
    hosts = {"porn4days.pw"}
