import argparse
import csv
import json
import os

import requests


def check_doi(doi, production=True):
    # Returns just DataCite metadata or DataCite metadata with emails

    if production == True:
        url = "https://authors.caltech.edu/api/records"
    else:
        url = "https://authors.caltechlibrary.dev/api/records"

    query = f'?q=pids.doi.identifier:"{doi}"'

    response = requests.get(url + query)
    if response.status_code != 200:
        raise Exception(response.text)
    else:
        metadata = response.json()
        if metadata["hits"]["total"] > 0:
            return True
        else:
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="check_doi queries the caltechDATA (Invenio 3) API\
    for a given DOI and returns whether it is present"
    )
    parser.add_argument(
        "doi",
    )
    parser.add_argument("-test", dest="production", action="store_false")

    args = parser.parse_args()

    production = args.production
    print(check_doi(args.doi, production))
