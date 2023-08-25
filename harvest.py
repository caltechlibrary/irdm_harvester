import os, csv, json
import argparse
import datetime
import subprocess
import requests
from idutils import normalize_doi
from check_doi import check_doi
from caltechdata_api import caltechdata_write


def cleanup_metadata(metadata):
    licenses = {}
    with open("licenses.csv") as infile:
        reader = csv.DictReader(infile, delimiter=";")
        for row in reader:
            licenses[row["props__url"]] = row["id"]
    rights = []
    if 'rights' in 'metadata':
        for f in metadata["metadata"]["rights"]:
            link = f["link"]
            if link in licenses:
                f["id"] = licenses[link]
            else:
                f["title"]["en"] = "Unknown"
            if f["description"]["en"] == "vor":
                rights.append(f)
    metadata["metadata"]["rights"] = rights
    return metadata


def get_orcid_works(orcid):
    orcid_link = "https://orcid.org/"
    headers = {"Accept": "application/json"}
    result = requests.get(orcid_link + orcid, headers=headers).json()
    raw_works = result["activities-summary"]["works"]["group"]
    dois = []
    for work in raw_works:
        idvs = work["work-summary"][0]["external-ids"]["external-id"]
        for idv in idvs:
            if idv["external-id-type"] == "doi":
                dois.append(idv["external-id-value"])
    return dois


def get_crossref_ror():
    # Get defaults from environment variables if available
    ror = os.getenv("ROR")
    if ror is None:
        ror = "05dxps055"
    email = os.getenv("EMAIL")
    if email is None:
        email = "library@caltech.edu"

    # Get when the harvest was last run
    with open("last_run.txt") as infile:
        last_run = infile.read().strip("\n")

    crossref_path = f"http://api.crossref.org/works?filter=ror-id:{ror},from-index-date:{last_run}&mailto={email}&rows=1000"

    excluded = ["peer-review", "grant"]

    # Get the list of DOIs from Crossref
    response = requests.get(crossref_path)
    data = response.json()
    dois = []
    if "items" in data["message"]:
        for result in data["message"]["items"]:
            if result["type"] not in excluded:
                dois.append(result["DOI"])

    date = datetime.date.today().isoformat()
    with open("last_run.txt", "w") as outfile:
        outfile.write(date)

    return dois


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Harvest DOIs from Crossref or ORCID and add to CaltechAUTHORS"
    )
    parser.add_argument("harvest_type", help="crossref or orcid")
    parser.add_argument("-orcid", help="ORCID ID to harvest from")
    parser.add_argument("-doi", help="DOI to harvest")
    parser.add_argument("-actor", help="Name of actor to use for review message")
    args = parser.parse_args()

    harvest_type = args.harvest_type

    token = os.getenv("RDMTOK")

    # Get DOIs that have already been harvested
    with open("harvested_dois.txt") as infile:
        harvested_dois = infile.read().splitlines()

    community = "aedd135f-227e-4fdf-9476-5b3fd011bac6"

    if harvest_type == "crossref":
        dois = get_crossref_ror()
        review_message = (
            "Automatically added from Crossref based on Caltech ROR affiliation"
        )
    elif harvest_type == "orcid":
        dois = get_orcid_works(args.orcid)
        review_message = (
            f"Automatically added from ORCID from record {args.orcid} by {args.actor}"
        )
    elif harvest_type == "doi":
        dois = args.doi.split(' ')
        review_message = f"Automatically added by {args.actor} as part of import from DOI list: {args.doi}"
    else:
        print("Invalid harvest type")
        sys.exit(1)

    for doi in dois:
        doi = normalize_doi(doi)
        if not check_doi(doi, production=True):
            if doi not in harvested_dois:
                print(f"Harvesting {doi}")
                try:
                    transformed = subprocess.check_output(["doi2rdm", doi])
                    data = transformed.decode("utf-8")
                    data = json.loads(data)
                    data = cleanup_metadata(data)
                    response = caltechdata_write(
                        data,
                        token,
                        production=True,
                        authors=True,
                        community=community,
                        review_message=review_message,
                    )
                    print(response)
                    with open("harvested_dois.txt", "a") as f:
                        f.write(doi + "\n")
                except subprocess.CalledProcessError:
                    print("Error with doi2rdm")
            else:
                print(f"DOI {doi} has already been harvested, skipping")
        else:
            print(f"DOI {doi} is already in CaltechAUTHORS, skipping")
