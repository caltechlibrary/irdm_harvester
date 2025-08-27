import os, csv, json
import argparse
import datetime
import subprocess
import requests
import dimcli
from idutils import normalize_doi, normalize_orcid
from check_doi import check_doi
from caltechdata_api import caltechdata_write, caltechdata_edit
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
        url = f"https://api.ror.org/organizations?query.advanced=external_ids.all:{grid}"
        results = requests.get(url).json()
        if len(results["items"]) == 0:
            ror = None
        else:
            ror = results["items"][0]["id"]
            ror = ror.split("ror.org/")[1]
    return ror


def match_orcid(creator, orcid, production=True):
    person = creator["person_or_org"]
    if production == False:
        base_url = "https://authors.caltechlibrary.dev/"
    else:
        base_url = "https://authors.library.caltech.edu/"
    url = f"{base_url}api/names?q=identifiers.identifier:{orcid}"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json()["hits"]["hits"]
        if len(results) == 1:
            result = results[0]
            if "affiliations" not in creator:
                creator["affiliations"] = result["affiliations"]
            if creator["affiliations"] == []:
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
        return publications[basics+extras+abstract] """,
        verbose=False,
    )
    publication = res.json["publications"]
    if len(publication) == 0:
        # Not yet in dimensions
        return metadata, review_message
    else:
        publication = publication[0]
    if "description" not in metadata["metadata"]:
        metadata["metadata"]["description"] = publication.get("abstract")
    if "pmcid" in publication:
        if "identifiers" not in metadata["metadata"]:
            metadata["metadata"]["identifiers"] = []
        metadata["metadata"]["identifiers"].append(
            {"scheme": "pmcid", "identifier": publication["pmcid"]}
        )
    if "pmid" in publication:
        if "identifiers" not in metadata["metadata"]:
            metadata["metadata"]["identifiers"] = []
        metadata["metadata"]["identifiers"].append(
            {"scheme": "pmid", "identifier": publication["pmid"]}
        )
    dimensions_authors = publication["authors"]
    existing_authors = metadata["metadata"]["creators"]
    add_affil = True
    # if len(dimensions_authors) > 500:
    # Skip affiliation if too many authors to avoid bashing ROR API
    # Can go away once Dimensions has ROR
    #    add_affil = False
    author_mismatch_is_ok = False
    position_in_crossref = 0
    if len(dimensions_authors) < len(existing_authors):
        review_message = (
            review_message
            + """ ⚠️⚠️⚠️  The Dimensions and CrossRef author count is off.
            This is probably due to a collaboration name, but please 
            manually confirm the author affiliations are correct."""
        )
        author_mismatch_is_ok = True
        # We want to check for the case where the first author is a
        # collaboration. This isn't perfect, but it is a start.
        dimensions_first_author = dimensions_authors[0].get("last_name")
        existing_first_author = existing_authors[1]["person_or_org"].get("family_name")
        if dimensions_first_author == existing_first_author:
            position_in_crossref = 1
    if len(dimensions_authors) == len(existing_authors) or author_mismatch_is_ok:
        for position in range(len(dimensions_authors)):
            author = existing_authors[position_in_crossref]["person_or_org"]
            dimensions_author = dimensions_authors[position]
            if "identifiers" not in author:
                if dimensions_author["orcid"] not in [[], None]:
                    review_message = (
                        review_message
                        + f"\n\n ORCID added from Dimensions: {dimensions_author['orcid'][0]}"
                    )
                    author["identifiers"] = [
                        {"scheme": "orcid", "identifier": dimensions_author["orcid"][0]}
                    ]
            if "affiliations" not in existing_authors[position_in_crossref]:
                affiliations = []
                if dimensions_author["affiliations"] not in [[], None]:
                    for affiliation in dimensions_author["affiliations"]:
                        review_message = (
                            review_message
                            + f"\n\n Affiliation added from Dimensions based on raw data: {affiliation['raw_affiliation']}"
                        )
                        affil = {}
                        if "id" in affiliation:
                            if affiliation["id"] is not None:
                                if affiliation["id"] == "grid.20861.3d":
                                    affil["id"] = "05dxps055"
                                elif add_affil:
                                    ror = grid_to_ror(affiliation["id"])
                                    if ror is not None:
                                        affil["id"] = ror
                        if "raw_affiliation" in affiliation:
                            raw = affiliation["raw_affiliation"]
                            affil["name"] = raw
                            if "91109" in raw:
                                affil["id"] = "027k65916"
                            if "Jet Propulsion Laboratory" in raw:
                                affil["id"] = "027k65916"
                            if "JPL" in raw:
                                affil["id"] = "027k65916"
                        if affil not in affiliations:
                            affiliations.append(affil)
                    existing_authors[position_in_crossref][
                        "affiliations"
                    ] = affiliations
            position_in_crossref += 1
    return metadata, review_message


def cleanup_metadata(metadata, production=True):
    # Read in supported identitifiers - this will go away once we upgrade
    # authors
    with open("ror.txt") as infile:
        lines = infile.readlines()
        ror = [e.strip() for e in lines]

    # Read in groups list
    groups_list = {}
    clpid_list = {}
    # Read in group list
    group_url = "https://feeds.library.caltech.edu/rpt/group_people_crosswalk.csv"
    with requests.get(group_url, stream=True) as r:
        lines = (line.decode("utf-8") for line in r.iter_lines())
        for row in csv.DictReader(lines):
            clpid_list[row["orcid"]] = row["clpid"]
            if row["orcid"] not in groups_list:
                groups_list[row["orcid"]] = [row["tag"]]
            else:
                groups_list[row["orcid"]].append(row["tag"])
    # Read in people list
    orcid_mapping = {}
    people_url = "https://feeds.library.caltech.edu/people/people.csv"
    with requests.get(people_url, stream=True) as r:
        lines = (line.decode("utf-8") for line in r.iter_lines())
        for row in csv.DictReader(lines):
            if row["orcid"] != "":
                orcid_mapping[row["orcid"]] = {
                    "cl_people_id": row["cl_people_id"],
                    "caltech": row["caltech"],
                    "jpl": row["jpl"],
                }
    # Match creators by ORCID
    groups = set()
    for creator in metadata["metadata"]["creators"]:
        person = creator["person_or_org"]
        clpid_needed = True
        clpid = None
        if "identifiers" in person:
            for identifier in person["identifiers"]:
                if identifier["scheme"] == "clpid":
                    clpid_needed = False
                if identifier["scheme"] == "orcid":
                    orcid = normalize_orcid(identifier["identifier"])
                    cold_data = orcid_mapping.get(orcid)
                    if cold_data is not None:
                        clpid = cold_data.get("cl_people_id")
                        caltech = cold_data.get("caltech")
                        jpl = cold_data.get("jpl")
                        if orcid in groups_list:
                            groups.update(groups_list[orcid])
        # Add clpid only if needed
        if clpid_needed:
            if clpid is not None:
                if "identifiers" not in person:
                    person["identifiers"] = []
                person["identifiers"].append({"scheme": "clpid", "identifier": clpid})
        # We need to check affiliation identifiers until we can update authors
        if "affiliations" in creator:
            clean_affiliations = []
            affil_ids = []
            #  We also need to check for duplicates, until supported in RDM
            for affiliation in creator["affiliations"]:
                if "id" in affiliation:
                    idv = affiliation["id"]
                    if idv not in affil_ids:
                        if idv in ror:
                            clean_affiliations.append(affiliation)
                            affil_ids.append(idv)
                else:
                    clean_affiliations.append(affiliation)
            creator["affiliations"] = clean_affiliations
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
    # The extra ISSN isn't needed
    if "identifiers" in metadata["metadata"]:
        identifiers = []
        for identifier in metadata["metadata"]["identifiers"]:
            if identifier["scheme"] != "issn":
                identifiers.append(identifier)
        metadata["metadata"]["identifiers"] = identifiers
    # Detailed dates aren't currently desired
    if "dates" in metadata["metadata"]:
        metadata["metadata"].pop("dates")
    # Set some defaults
    metadata["custom_fields"]["caltech:publication_status"] = [{"id": "published"}]
    metadata["metadata"]["version"] = "Published"

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
                    if "JPL" in affiliation["raw_affiliation"]:
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


def check_record(data, review_message, token, production=True):
    title = data["metadata"]["title"]
    if production == False:
        base_url = "https://authors.caltechlibrary.dev/"
    else:
        base_url = "https://authors.library.caltech.edu/"
    result = requests.get(f'{base_url}api/records?q=metadata.title:"{title}"')
    if result.status_code == 200:
        result = result.json()
        if result["hits"]["total"] > 0:
            possible_match = result["hits"]["hits"][0]
            if possible_match["metadata"]["title"] == title:
                link = possible_match["links"]["self_html"]
                review_message += f"\n\n  ❗❗❗ Duplicate title found: {link}"
    headers = {"Authorization": f"Bearer {token}"}
    result = requests.get(
        headers=headers,
        url=f'{base_url}api/requests/?q=title:"{title}"%20AND%20is_open:true',
    )
    if result.status_code == 200:
        result = result.json()
        if result["hits"]["total"] > 0:
            possible_match = result["hits"]["hits"][0]
            if possible_match["title"] == title:
                link_id = possible_match["id"]
                # Needed because https://github.com/inveniosoftware/invenio-communities/issues/1228
                link = f"{base_url}communities/caltechauthors/requests/{link_id}"
                review_message += f"\n\n  ❗❗❗ Duplicate title found in queue: {link}"
    return review_message


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Harvest DOIs from Crossref or ORCID and add to CaltechAUTHORS"
    )
    parser.add_argument(
        "harvest_type", help="crossref, orcid, doi, wos, dimensions, authors"
    )
    parser.add_argument("-orcid", help="ORCID ID to harvest from")
    parser.add_argument("-doi", help="DOI to harvest")
    parser.add_argument("-authors-source", help="Source record from authors")
    parser.add_argument("-authors-destination", help="Destination record from authors")
    parser.add_argument("-actor", help="Name of actor to use for review message")
    parser.add_argument("-message", help="Message to use in submission comment")
    parser.add_argument("-tag", help="Tag to use in submission comment")
    parser.add_argument("-report", help="Generate a report only", action="store_true")
    parser.add_argument("-test", help="Test mode", action="store_true")
    parser.add_argument(
        "-print", help="Print out DOIs (no harvesting)", action="store_true"
    )
    parser.add_argument(
        "-publish",
        help="Immediately publish records (does not go to requew queue)",
        action="store_true",
    )
    args = parser.parse_args()

    if args.test:
        production = False
    else:
        production = True

    harvest_type = args.harvest_type

    token = os.getenv("RDMTOK")

    # Get DOIs that have already been harvested
    with open("harvested_dois.txt") as infile:
        harvested_dois = infile.read().splitlines()

    if production:
        community = "aedd135f-227e-4fdf-9476-5b3fd011bac6"
    else:
        community = "ab23cb28-94b9-42db-80e6-c6ed80faafd0"

    if args.tag:
        if args.tag != "":
            if args.tag[0] != "@":
                tag = f"@{args.tag}"
            else:
                tag = args.tag
        else:
            tag = ""
    else:
        tag = ""

    if harvest_type == "crossref":
        dois = get_crossref_ror()
        if args.message:
            review_message = args.message
        else:
            review_message = f"Automatically added from Crossref based on Caltech ROR affiliation. {tag}"
        if args.print:
            ostring = "dois="
            for doi in dois:
                ostring += f" {doi}"
            print(ostring)
            print(f"message= {review_message}")
            dois = []
    elif harvest_type == "authors":
        dois = []
        if production == False:
            base_url = "https://authors.caltechlibrary.dev/"
        else:
            base_url = "https://authors.library.caltech.edu"
        if args.authors_source and args.authors_destination:
            source = args.authors_source
            destination = args.authors_destination
            response = requests.get(f"{base_url}api/records/{source}")
            if response.status_code == 200:
                source_record = response.json()
            else:
                print(f"error=source record {source} not found")
                exit()
            response = requests.get(f"{base_url}api/records/{destination}")
            if response.status_code == 200:
                destination_record = response.json()
            else:
                print(f"error=destination record {destination} not found")
                exit()
            try:
                response = caltechdata_edit(
                    destination,
                    source_record,
                    token,
                    production=production,
                    authors=True,
                    new_version=True,
                )
            except Exception as e:
                cleaned = format_error(format_exc())
                print(
                    f"error= system error with writing metadata to CaltechAUTHORS {cleaned}"
                )
        else:
            print(f"error=source and destination records must be provided")
            exit()
    elif harvest_type == "dimensions":
        dois = get_dimensions()
        if args.message:
            review_message = args.message
        else:
            review_message = "Automatically added from Dimensions Caltech affiliation harvest with metadata from Crossref. {tag}"
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
            review_message = f"Automatically added from ORCID from record {args.orcid} by {args.actor}. {tag}"
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
            import from DOI list: {args.doi}. {tag}"""
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
        if not check_doi(doi, production=production, token=token):
            if doi not in harvested_dois:
                try:
                    transformed = subprocess.check_output(
                        ["doi2rdm", "options.yaml", doi]
                    )
                    data = transformed.decode("utf-8")
                    data = json.loads(data)
                except subprocess.CalledProcessError as e:
                    if e.returncode == 2:
                        print(f"error=DOI {doi} not found in Crossref or DataCite")
                    else:
                        cleaned = format_error(format_exc())
                        print(f"error= system error with doi2rdm {cleaned}")
                    break
                try:
                    review_message = check_record(
                        data, review_message, token, production=production
                    )
                except Exception as e:
                    cleaned = format_error(format_exc())
                    print(f"error= system error with record checking {cleaned}")
                    break
                try:
                    data, review_message = add_dimensions_metadata(
                        data, doi, review_message
                    )
                except Exception as e:
                    cleaned = format_error(format_exc())
                    print(f"error= system error with Dimensions metadata {cleaned}")
                    break
                try:
                    data, files = cleanup_metadata(data)
                except Exception as e:
                    cleaned = format_error(format_exc())
                    print(f"error= system error with metadata cleanup {cleaned}")
                    break
                try:
                    if args.publish:
                        publish = True
                    else:
                        publish = False
                    response = caltechdata_write(
                        data,
                        token,
                        production=production,
                        authors=True,
                        community=community,
                        review_message=review_message,
                        files=files,
                        publish=publish,
                    )
                    print("doi=", doi)
                except Exception as e:
                    cleaned = format_error(format_exc())
                    print(
                        f"error= system error with writing metadata to CaltechAUTHORS {cleaned}"
                    )
            else:
                print(f"error=DOI {doi} has already been harvested, skipping")
        else:
            print(f"error=DOI {doi} is already in CaltechAUTHORS, skipping")
