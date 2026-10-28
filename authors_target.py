"""Which CaltechAUTHORS the harvester talks to.

There are four targets:

  production         no flag
  the dev host       harvest.py -test        (authors.caltechlibrary.dev)
  a local instance   harvest.py -local       (https://127.0.0.1:5000, TLS not
                     verified; reach a Multipass VM there with local_forward.py)
  any other instance harvest.py -url URL     (for example an AWS test instance)

-local and -url need the community id of that instance in AUTHORS_COMMUNITY.
The community ids of production and the dev host are fixed below.

A CaltechAUTHORS built from production's configuration advertises its links
on production's hostname, and caltechdata_api follows those links. So when the
target is not production or the dev host, install_host_guard sends any request
meant for those two hosts to the target instead; without it a test run would
reach production.
"""

import os
from urllib.parse import urlsplit, urlunsplit

PRODUCTION_URL = "https://authors.library.caltech.edu/"
DEV_URL = "https://authors.caltechlibrary.dev/"
LOCAL_URL = "https://127.0.0.1:5000/"
COMMUNITY_ENV = "AUTHORS_COMMUNITY"
PRODUCTION_COMMUNITY = "aedd135f-227e-4fdf-9476-5b3fd011bac6"
DEV_COMMUNITY = "fb980d43-af44-48bc-bdd6-f785653038b8"

PRODUCTION_HOST = "authors.library.caltech.edu"
# hosts whose requests the guard sends to the target
GUARDED_HOSTS = (PRODUCTION_HOST, "authors.caltechlibrary.dev")


def base_url(production=True, local=False, url=None):
    """Return the base URL, with one trailing slash.

    url (a -url value) wins over local, and local over production.
    """
    if url and url.strip():
        return url.strip().rstrip("/") + "/"
    if local:
        return LOCAL_URL
    return PRODUCTION_URL if production else DEV_URL


def tls_verify(local=False):
    """Return the value for requests' verify: off only for a local instance."""
    return not local


def community_id(production=True, local=False, url=None):
    """Return the community id for the target, or raise ValueError.

    A local or -url target has no fixed id: it must be named in the
    environment, so such a run can never write into the dev or production
    community.
    """
    if local or (url and url.strip()):
        found = os.environ.get(COMMUNITY_ENV, "").strip()
        if not found:
            raise ValueError(
                f"-local and -url need {COMMUNITY_ENV} set to the community "
                "id on that instance"
            )
        return found
    return PRODUCTION_COMMUNITY if production else DEV_COMMUNITY


def install_host_guard(target):
    """Send every request meant for a guarded host to target; return an undo.

    It wraps requests' Session.request, which every requests call goes
    through, rewriting only the scheme and host of a URL on production's or
    the dev authors host (path, query and arguments are kept). Other hosts
    (Crossref, ROR, feeds) are left alone. target must be an http(s) URL and
    must not be production. Installing again replaces the guard rather than
    stacking. Call the returned function to remove it; it is safe to call twice.
    """
    parts = urlsplit(target or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"the target must be an http(s) URL, got {target!r}")
    if parts.hostname.lower() == PRODUCTION_HOST:
        raise ValueError("production cannot be a test target; leave -url and -local off")

    import requests.sessions

    session = requests.sessions.Session
    original = getattr(session.request, "_guard_original", session.request)

    def request(self, method, url, *args, **kwargs):
        got = urlsplit(url)
        if (got.hostname or "").lower() in GUARDED_HOSTS:
            url = urlunsplit(
                (parts.scheme, parts.netloc, got.path, got.query, got.fragment)
            )
        return original(self, method, url, *args, **kwargs)

    request._guard_original = original
    session.request = request

    def undo():
        if session.request is request:
            session.request = original

    return undo
