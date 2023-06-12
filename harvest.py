import os, csv, json
import datetime
import subprocess
import requests
from check_doi import check_doi
from caltechdata_api import caltechdata_write


def cleanup_metadata(metadata):
    licenses = {}
    with open("licenses.csv") as infile:
        reader = csv.DictReader(infile, delimiter=";")
        for row in reader:
            licenses[row["props__url"]] = row["id"]
    rights = []
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


# Get defaults from environment variables if available
ror = os.getenv("ROR")
if ror is None:
    ror = "05dxps055"
email = os.getenv("EMAIL")
if email is None:
    email = "library@caltech.edu"
token = os.getenv("RDMTOK")

# Get when the harvest was last run
with open("last_run.txt") as infile:
    last_run = infile.read().strip("\n")

# Get DOIs that have already been harvested
with open("harvested_dois.txt") as infile:
    harvested_dois = infile.read().splitlines()

crossref_path = f"http://api.crossref.org/works?filter=ror-id:{ror},from-index-date:{last_run}&mailto={email}&rows=1000"

community = "9b22c27e-e7f6-4699-adf2-4593dce9cc48"

excluded = ["peer-review", "grant"]

# Get the list of DOIs from Crossref
response = requests.get(crossref_path)
data = response.json()
if "items" in data["message"]:
    for result in data["message"]["items"]:
        if result["type"] not in excluded:
            DOI = result["DOI"]
            if not check_doi(DOI, production=False):
                if DOI not in harvested_dois:
                    print(DOI)
                    try:
                        transformed = subprocess.check_output(["doi2rdm", DOI])
                        data = transformed.decode("utf-8")
                        data = json.loads(data)
                        data = cleanup_metadata(data)
                        response = caltechdata_write(
                            data,
                            token,
                            production=False,
                            authors=True,
                            community=community,
                            review_message="Automatically added from CrossRef based on Caltech ROR affiliation",
                        )
                        print(response)
                        with open("harvested_dois.txt", "a") as f:
                            f.write(DOI + "\n")
                    except subprocess.CalledProcessError:
                        print("Error with doi2rdm")
    date = datetime.date.today().isoformat()
    with open("last_run.txt", "w") as outfile:
        outfile.write(date)
