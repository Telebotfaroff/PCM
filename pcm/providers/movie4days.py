"""Independent Movie4days post-page provider."""
from pcm.providers.html_post import HtmlPostProvider


class Movie4DaysProvider(HtmlPostProvider):
    name = "movie4days"
    display_name = "Movie4days"
    hosts = {"movie4days.com"}
