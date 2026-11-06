import csv

# Path segments publishers append to an otherwise standard license url
LICENSE_URL_SUFFIXES = ("legalcode", "deed")


def format_error(e):
    return (
        e.replace("\n", "-")
        .replace(":", "-")
        .replace("'", "-")
        .replace('"', "-")
        .replace("=", "-")
        .replace("(", "-")
        .replace(")", "-")
    )


def normalize_license_url(url):
    # Publishers send the same license under a variety of urls, so we reduce a
    # url to a canonical form before comparing: http and https are the same
    # license, so are urls that differ only by case, a www. host, a trailing
    # slash, or a trailing legalcode/deed segment
    url = url.strip().lower()
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            url = url[len(scheme) :]
            break
    if url.startswith("www."):
        url = url[4:]
    url = url.rstrip("/")
    segments = url.split("/")
    # Only drop the suffix if a path is left behind - a host on its own doesn't
    # identify a license
    if len(segments) > 2 and segments[-1].split(".")[0] in LICENSE_URL_SUFFIXES:
        segments.pop()
    return "/".join(segments)


def read_licenses(path="licenses.csv"):
    # Returns the exact url lookup used to match a license, plus a lookup
    # keyed on the normalized url for the variants publishers send
    licenses = {}
    normalized = {}
    with open(path) as infile:
        reader = csv.DictReader(infile, delimiter=",")
        for row in reader:
            url = row["props__url"]
            if url == "":
                continue
            licenses[url] = row["id"]
            normalized.setdefault(normalize_license_url(url), row["id"])
    return licenses, normalized


def match_license(link, licenses, normalized):
    # We need to have a license known to RDM, so an exact match wins and the
    # normalized form is only a fallback. Returns None when we can't identify
    # the license and the caller should fall back to the default rights
    if link in licenses:
        return licenses[link]
    return normalized.get(normalize_license_url(link))
