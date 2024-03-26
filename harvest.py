import os, csv, json
import argparse
import datetime
import subprocess
import requests
from idutils import normalize_doi
from check_doi import check_doi
from caltechdata_api import caltechdata_write
from wos import get_wos_dois


def match_orcid(creator, orcid):
    person = creator["person_or_org"]
    url = f"https://authors.library.caltech.edu/api/names?q=identifiers.identifier:{orcid}"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json()["hits"]["hits"]
        if len(results) == 1:
            result = results[0]
            creator["affiliations"] = result["affiliations"]
            person["identifiers"] = result["identifiers"]


def cleanup_metadata(metadata):
    # Match creators by ORCID
    for creator in metadata["metadata"]["creators"]:
        person = creator["person_or_org"]
        if "identifiers" in person:
            for identifier in person["identifiers"]:
                if identifier["scheme"] == "orcid":
                    orcid = identifier["identifier"]
                    match_orcid(creator, orcid)
    # Clean up licenses
    licenses = {}
    with open("licenses.csv") as infile:
        reader = csv.DictReader(infile, delimiter=";")
        for row in reader:
            licenses[row["props__url"]] = row["id"]
    rights = []
    files = None
    if "rights" in metadata["metadata"]:
        for f in metadata["metadata"]["rights"]:
            link = f["link"]
            if link in licenses:
                f["id"] = licenses[link]
            else:
                f["title"]["en"] = "Unknown"
            # Not supporting file download till v12
            # if f["description"]["en"] == "vor":
            #    rights.append(f)
            #    if f["id"] == 'cc-by-4.0':
            #        doi = metadata["pids"]["doi"]["identifier"]
            #        response = requests.get('https://api.crossref.org/works/' + doi)
            #        if response.status_code == 200:
            #            data = response.json()
            #            try:
            #                links = data["message"]["link"]
            #                for link in links:
            #                    if link["content-type"] == "application/pdf":
            #                        link = link["URL"]
            #                        requests.get(link)
            #                        fname = f"{doi.replace('/','_')}.pdf"
            #                        with open(fname, "wb") as f:
            #                            f.write(response.content)
            #                        files = fname
            #            except:
            #                pass
    metadata["metadata"]["rights"] = rights
    return metadata, files


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

    excluded = ["peer-review", "grant", "dataset"]

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


def write_outputs(dois, new_dois, existing_dois, arxiv_dois):
    outfile = open("wos_dois.csv", "w")
    writer = csv.writer(outfile)
    for doi in dois:
        writer.writerow([doi])
    outfile.close()
    outfile = open("wos_report.csv", "w")
    writer = csv.writer(outfile)
    print(f"New: {len(new_dois)}")
    for doi in new_dois:
        writer.writerow([doi])
    outfile.close()
    outfile = open("wos_report_existing.csv", "w")
    writer = csv.writer(outfile)
    print(f"Existing: {len(existing_dois)}")
    for doi in existing_dois:
        writer.writerow([doi])
    outfile.close()
    outfile = open("wos_report_arxiv.csv", "w")
    writer = csv.writer(outfile)
    print(f"arXiv: {len(arxiv_dois)}")
    for doi in arxiv_dois:
        writer.writerow([doi])
    outfile.close()


def read_outputs():
    infile = open("wos_dois.csv", "r")
    reader = csv.reader(infile)
    dois = []
    for row in reader:
        dois.append(row[0])
    infile.close()
    infile = open("wos_report.csv", "r")
    reader = csv.reader(infile)
    new_dois = []
    for row in reader:
        new_dois.append(row[0])
    infile.close()
    infile = open("wos_report_existing.csv", "r")
    reader = csv.reader(infile)
    existing_dois = []
    for row in reader:
        existing_dois.append(row[0])
    infile.close()
    infile = open("wos_report_arxiv.csv", "r")
    reader = csv.reader(infile)
    arxiv_dois = []
    for row in reader:
        arxiv_dois.append(row[0])
    infile.close()
    return dois, new_dois, existing_dois, arxiv_dois


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Harvest DOIs from Crossref or ORCID and add to CaltechAUTHORS"
    )
    parser.add_argument("harvest_type", help="crossref, orcid, doi, ror")
    parser.add_argument("-orcid", help="ORCID ID to harvest from")
    parser.add_argument("-doi", help="DOI to harvest")
    parser.add_argument("-actor", help="Name of actor to use for review message")
    parser.add_argument("-report", help="Generate a report only", action="store_true")
    parser.add_argument(
        "-print", help="Print out DOIs (no harvesting)", action="store_true"
    )
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
        if args.print:
            ostring = "dois="
            for doi in dois:
                ostring += f" {doi}"
            print(ostring)
            dois = []
    elif harvest_type == "orcid":
        dois = get_orcid_works(args.orcid)
        review_message = (
            f"Automatically added from ORCID from record {args.orcid} by {args.actor}"
        )
        if args.print:
            ostring = "dois= "
            for doi in dois:
                ostring += f" {doi}"
            print(ostring)
            dois = []
    elif harvest_type == "doi":
        dois = args.doi.split(" ")
        review_message = f"Automatically added by {args.actor} as part of import from DOI list: {args.doi}"
    elif harvest_type == "wos":
        # dois = get_wos_dois("1Y")
        dois, new_dois, existing_dois, arxiv_dois = read_outputs()
        count = 1
        while dois:
            doi = dois.pop()
            try:
                if not check_doi(doi, production=True, token=token):
                    if "arXiv" in doi:
                        arxiv_dois.append(doi)
                    else:
                        new_dois.append(doi)
                else:
                    existing_dois.append(doi)
            except Exception as e:
                print(e)
                if args.report:
                    print(count)
                    write_outputs(dois, new_dois, existing_dois, arxiv_dois)
                exit()
            count += 1
        if args.report:
            print(count)
            write_outputs(dois, new_dois, existing_dois, arxiv_dois)
        exit()
    else:
        print("error: system error invalid harvest type")

    for doi in dois:
        doi = normalize_doi(doi)
        if not check_doi(doi, production=True, token=token):
            if doi not in harvested_dois:
                try:
                    transformed = subprocess.check_output(["doi2rdm", "crossref", doi])
                    data = transformed.decode("utf-8")
                    data = json.loads(data)
                    data, files = cleanup_metadata(data)
                    response = caltechdata_write(
                        data,
                        token,
                        production=True,
                        authors=True,
                        community=community,
                        review_message=review_message,
                        files=files,
                    )
                    print("doi=", doi)
                    # with open("harvested_dois.txt", "a") as f:
                    #    f.write(doi + "\n")
                except Exception as e:
                    cleaned = str(e).replace("'","/")
                    print(f"error= system error with doi2rdm {cleaned}")
            else:
                print(f"error=DOI {doi} has already been harvested, skipping")
        else:
            print(f"error=DOI {doi} is already in CaltechAUTHORS, skipping")
