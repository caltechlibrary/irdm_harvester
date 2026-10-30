"""Which CaltechAUTHORS the harvester talks to.

There are three targets:

  production         no flag
  the dev host       harvest.py -test        (authors.caltechlibrary.dev)
  a local instance   harvest.py -local       (https://127.0.0.1:5000, TLS not
                     verified; forward port 5000 to a Multipass VM yourself)

-local needs the community id of that instance in AUTHORS_COMMUNITY.
The community ids of production and the dev host are fixed below.

A test instance must advertise its own address. caltechdata_api follows the
links the server returns (links["review"], links["files"], ...), and an
instance built from production's configuration returns production's hostname
in them. For -local set SITE_UI_URL to https://127.0.0.1:5000 and SITE_API_URL
to https://127.0.0.1:5000/api in the instance's invenio.cfg. Nothing in the
harvester checks this: a -local run against an instance that still advertises
production's hostname follows those links and writes to production, so a
-local run first asks the instance which host it advertises
(check_local_links) and stops if that is not its own.
"""

import os
from urllib.parse import urlsplit

PRODUCTION_URL = "https://authors.library.caltech.edu/"
DEV_URL = "https://authors.caltechlibrary.dev/"
LOCAL_URL = "https://127.0.0.1:5000/"
COMMUNITY_ENV = "AUTHORS_COMMUNITY"
PRODUCTION_COMMUNITY = "aedd135f-227e-4fdf-9476-5b3fd011bac6"
DEV_COMMUNITY = "fb980d43-af44-48bc-bdd6-f785653038b8"


def base_url(production=True, local=False):
    """Return the base URL, with one trailing slash.

    local wins over production.
    """
    if local:
        return LOCAL_URL
    return PRODUCTION_URL if production else DEV_URL


def tls_verify(local=False):
    """Return the value for requests' verify: off only for a local instance."""
    return not local


def community_id(production=True, local=False):
    """Return the community id for the target, or raise ValueError.

    A local target has no fixed id: it must be named in the
    environment, so such a run can never write into the dev or production
    community.
    """
    if local:
        found = os.environ.get(COMMUNITY_ENV, "").strip()
        if not found:
            raise ValueError(
                f"-local needs {COMMUNITY_ENV} set to the community "
                "id on that instance"
            )
        return found
    return PRODUCTION_COMMUNITY if production else DEV_COMMUNITY


def check_local_links(get):
    """Raise ValueError unless the local instance advertises its own address.

    caltechdata_api follows the links the server returns, so an instance still
    configured with production's SITE_UI_URL and SITE_API_URL would send a
    -local write to production.

    @param get {callable} requests.get, or a stand-in with its signature
    @returns {None} nothing when links.self is on the local host
    @example
        check_local_links(requests.get)
    """
    local_host = urlsplit(LOCAL_URL).netloc
    fix = (
        f"set SITE_UI_URL to https://{local_host} and SITE_API_URL to "
        f"https://{local_host}/api in the instance's invenio.cfg"
    )
    try:
        response = get(LOCAL_URL + "api/records?size=1", verify=False)
    except Exception as e:
        raise ValueError(f"cannot reach the -local instance at {local_host}: {e}")
    if response.status_code != 200:
        raise ValueError(
            f"the -local instance at {local_host} answered "
            f"{response.status_code}, so its links cannot be checked"
        )
    try:
        advertised = urlsplit(response.json()["links"]["self"]).netloc
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            f"the -local instance at {local_host} returned no links.self, "
            "so its links cannot be checked"
        )
    if advertised != local_host:
        raise ValueError(
            f"the -local instance advertises {advertised or 'no host'} in its "
            f"links, not {local_host}; {fix}"
        )
