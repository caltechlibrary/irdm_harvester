import requests
import os, urllib


def extract_dois(records, dois):
    for rec in records:
        rec = rec["dynamic_data"]
        if "cluster_related" in rec:
            if "identifiers" in rec["cluster_related"]:
                try:
                    identifiers = rec["cluster_related"]["identifiers"]["identifier"]
                    for idv in identifiers:
                        try:
                            if idv["type"] == "doi":
                                doi = idv["value"]
                                if "arXiv" in doi:
                                    doi = "10.48550/arXiv." + doi.split("arXiv:")[1]
                                dois.append(doi)
                        except:
                            print(idv)
                except:
                    print(rec["cluster_related"]["identifiers"])


def get_wos_dois(harvest_period):
    """Get all DOIs from Web of Science for the harvest period (5D or 2M or 1Y etc...)"""

    token = os.environ["WOSTOK"]
    headers = {"X-ApiKey": token, "Content-type": "application/json"}

    base_url = "https://api.clarivate.com/api/wos/?databaseId=WOK"

    base_url = base_url + "&loadTimeSpan=" + str(harvest_period)

    query = """AD=(((91125 OR "California Institute of Technology" OR "Caltech" OR "Thirty-meter Telescope") not (91109 or (jet and prop and lab))) OR (91125 AND 91109))"""

    query = urllib.parse.quote_plus(query)
    url = base_url + "&usrQuery=" + query + "&count=100&firstRecord=1"

    response = requests.get(url, headers=headers)
    response = response.json()
    record_count = response["QueryResult"]["RecordsFound"]
    print(record_count, " Records from WOS")
    query_id = response["QueryResult"]["QueryID"]
    try:
        records = response["Data"]["Records"]["records"]["REC"]
    except:
        print(response)
    dois = []
    extract_dois(records, dois)
    # We have saved the first 100 records
    record_start = 101
    record_count = record_count - 100

    query_url = "https://api.clarivate.com/api/wos/query/"

    while record_count > 0:
        print(record_count)
        print(len(records), "records")
        if record_count > 100:
            url = (
                query_url
                + str(query_id)
                + "?count=100&firstRecord="
                + str(record_start)
            )
            response = requests.get(url, headers=headers)
            response = response.json()
            try:
                records = response["Records"]["records"]["REC"]
            except:
                print(response)

            extract_dois(records, dois)
            record_start = record_start + 100
            record_count = record_count - 100
        else:
            url = (
                query_url
                + str(query_id)
                + "?count="
                + str(record_count)
                + "&firstRecord="
                + str(record_start)
            )
            response = requests.get(url, headers=headers)
            response = response.json()
            records = response["Records"]["records"]["REC"]
            extract_dois(records, dois)
            record_count = 0

    return dois
