import os, csv, json
import argparse
import datetime
import subprocess
import requests
import dimcli
from idutils import normalize_doi
from check_doi import check_doi
from caltechdata_api import caltechdata_write
from wos import get_wos_dois
from traceback import format_exc


def grid_to_ror(grid):
    if grid == "grid.451078.f":
        ror = "00hm6j694"
    elif grid == "grid.5805.8":
        ror = "02en5vm52"
    elif grid == "grid.465477.3":
        ror = "00em52312"
    else:
        url = f"https://api.ror.org/organizations?query.advanced=external_ids.GRID.all:{grid}"
        results = requests.get(url).json()
        if len(results["items"]) == 0:
            print(url + "doesn't have a valid ROR")
            exit()
        ror = results["items"][0]["id"]
        ror = ror.split("ror.org/")[1]
    return ror


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


def add_dimensions_metadata(metadata, doi, review_message):
    dimkey = os.getenv("DIMKEY")
    endpoint = "https://cris-api.dimensions.ai/v3"
    dimcli.login(key=dimkey, endpoint=endpoint, verbose=False)
    dsl = dimcli.Dsl()
    res = dsl.query_iterative(
        f"""
        search publications
        where doi = "{doi}"
        return publications[basics+extras] """,
        verbose=False,
    )
    publication = res.json["publications"][0]
    dimensions_authors = publication["authors"]
    existing_authors = metadata["metadata"]["creators"]
    if len(dimensions_authors) == len(existing_authors):
        for position in range(len(dimensions_authors)):
            author = existing_authors[position]["person_or_org"]
            dimensions_author = dimensions_authors[position]
            if "identifiers" not in author:
                if dimensions_author["orcid"] not in [[], None]:
                    review_message = (
                        review_message
                        + f"\n ORCID added from Dimensions: {dimensions_author['orcid'][0]}"
                    )
                    author["identifiers"] = [
                        {"scheme": "orcid", "identifier": dimensions_author["orcid"][0]}
                    ]
            if "affiliations" not in author:
                affiliations = []
                if dimensions_author["affiliations"] not in [[], None]:
                    for affiliation in dimensions_author["affiliations"]:
                        review_message = (
                            review_message
                            + f"\n Affiliation added from Dimensions based on raw data: {affiliation['raw_affiliation']}"
                        )
                        affil = {}
                        if "id" in affiliation:
                            affil["id"] = grid_to_ror(affiliation["id"])
                        if "raw_affiliation" in affiliation:
                            affil["name"] = affiliation["raw_affiliation"]
                        affiliations.append(affil)
                    existing_authors[position]["affiliations"] = affiliations
    return metadata, review_message


def cleanup_metadata(metadata):
    # Read in groups list
    groups_list = {}
    with open("group_tagging.csv") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            if row["ORCID"] not in groups_list:
                groups_list[row["ORCID"]] = [row["Tag"]]
            else:
                groups_list[row["ORCID"]].append(row["Tag"])
    # Match creators by ORCID
    groups = set()
    for creator in metadata["metadata"]["creators"]:
        person = creator["person_or_org"]
        if "identifiers" in person:
            for identifier in person["identifiers"]:
                if identifier["scheme"] == "orcid":
                    orcid = identifier["identifier"]
                    match_orcid(creator, orcid)
                    if orcid in groups_list:
                        groups.update(groups_list[orcid])
    if "custom_fields" not in metadata:
        metadata["custom_fields"] = {}
    if groups:
        g_list = []
        for group in groups:
            g_list.append({"id": group})
        metadata["custom_fields"]["caltech:groups"] = g_list
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
            if "link" in f:
                link = f["link"]
                if link in licenses:
                    rights.append({"id": licenses[link]})
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
    if rights == []:
        rights.append({"id": "default"})
    metadata["metadata"]["rights"] = rights
    # Detailed dates aren't currently desired
    if "dates" in metadata["metadata"]:
        metadata["metadata"].pop("dates")
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


def get_dimensions():
    key = os.getenv("DIMKEY")

    date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    dois = []

    endpoint = "https://cris-api.dimensions.ai/v3"
    dimcli.login(key=key, endpoint=endpoint, verbose=False)
    dsl = dimcli.Dsl()

    res = dsl.query_iterative(
        f"""
        search publications
        where research_orgs.id = "grid.20861.3d"
        and date >= "{date}"
        return publications[basics+extras] """,
        verbose=False,
    )

    publications = res.json["publications"]
    for publication in publications:
        caltech = False
        for author in publication["authors"]:
            for affiliation in author["affiliations"]:
                if affiliation["id"] == "grid.20861.3d":
                    caltech_ind = True
                    if "91109" in affiliation["raw_affiliation"]:
                        caltech_ind = False
                    if "Jet Propulsion Laboratory" in affiliation["raw_affiliation"]:
                        caltech_ind = False
                else:
                    caltech_ind = False
            if caltech_ind:
                caltech = True
        if caltech:
            if "doi" in publication:
                dois.append(publication["doi"])

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


def check_record(data, review_message):
    title = data["metadata"]["title"]
    result = requests.get(
        f'https://authors.library.caltech.edu/api/records?q=metadata.title:"{title}"'
    ).json()
    if result["hits"]["total"] > 0:
        link = result["hits"]["hits"][0]["links"]["self_html"]
        review_message += f"\n  *** Duplicate title found: {link}"
    return review_message


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Harvest DOIs from Crossref or ORCID and add to CaltechAUTHORS"
    )
    parser.add_argument("harvest_type", help="crossref, orcid, doi, wos, dimensions")
    parser.add_argument("-orcid", help="ORCID ID to harvest from")
    parser.add_argument("-doi", help="DOI to harvest")
    parser.add_argument("-actor", help="Name of actor to use for review message")
    parser.add_argument("-message", help="Message to use in submission comment")
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
        if args.message:
            review_message = args.message
        else:
            review_message = (
                "Automatically added from Crossref based on Caltech ROR affiliation"
            )
        if args.print:
            ostring = "dois="
            for doi in dois:
                ostring += f" {doi}"
            print(ostring)
            print(f"message= {review_message}")
            dois = []
    elif harvest_type == "dimensions":
        dois = get_dimensions()
        if args.message:
            review_message = args.message
        else:
            review_message = "Automatically added from Crossref based on Caltech affiliation in Dimensions"
        if args.print:
            ostring = "dois="
            for doi in dois:
                ostring += f" {doi}"
            print(ostring)
            print(f"message= {review_message}")
            dois = []
    elif harvest_type == "orcid":
        dois = get_orcid_works(args.orcid)
        if args.message:
            review_message = args.message
        else:
            review_message = f"Automatically added from ORCID from record {args.orcid} by {args.actor}"
        if args.print:
            ostring = "dois= "
            for doi in dois:
                ostring += f" {doi}"
            print(ostring)
            print(f"message= {review_message}")
            dois = []
    elif harvest_type == "doi":
        dois = args.doi.split(" ")
        if args.message:
            review_message = args.message
        else:
            review_message = f"""Automatically added by {args.actor} as part of
            import from DOI list: {args.doi}"""
    elif harvest_type == "wos":
        dois = get_wos_dois("2M")
        new_dois = []
        existing_dois = []
        arxiv_dois = []
        dois, new_dois, existing_dois, arxiv_dois = read_outputs()
        count = 1
        while dois:
            doi = dois.pop()
            print(doi, len(dois))
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
        print(count)
        write_outputs(dois, new_dois, existing_dois, arxiv_dois)
    else:
        print("error: system error invalid harvest type")

    for doi in dois:
        doi = normalize_doi(doi)
        if not check_doi(doi, production=True, token=token):
            if doi not in harvested_dois:
                try:
                    transformed = subprocess.check_output(
                        ["doi2rdm", "options.yaml", doi]
                    )
                    data = transformed.decode("utf-8")
                    data = json.loads(data)
                except Exception as e:
                    cleaned = (
                        format_exc()
                        .replace("\n", "-")
                        .replace(":", "-")
                        .replace("'", "-")
                        .replace('"', "-")
                        .replace("=", "-")
                        .replace("(", "-")
                        .replace(")", "-")
                    )
                    print(f"error= system error with doi2rdm {cleaned}")
                try:
                    data, review_message = add_dimensions_metadata(
                        data, doi, review_message
                    )
                    data, files = cleanup_metadata(data)
                    review_message = check_record(data, review_message)
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
                except Exception as e:
                    cleaned = (
                        format_exc()
                        .replace("\n", "-")
                        .replace(":", "-")
                        .replace("'", "-")
                        .replace('"', "-")
                        .replace("=", "-")
                        .replace("(", "-")
                        .replace(")", "-")
                    )
                    print(
                        f"error= system error with writing metadata to CaltechAUTHORS {cleaned}"
                    )
            else:
                print(f"error=DOI {doi} has already been harvested, skipping")
        else:
            print(f"error=DOI {doi} is already in CaltechAUTHORS, skipping")
