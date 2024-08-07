import csv, json
import requests

# Open the file with the list of DOIs
with open("wos_report.csv", "r") as doi_list:
    reader = csv.reader(doi_list)
    # Create a list of DOIs
    doi_list = [row[0] for row in reader]
with open("full_wos_report.csv", "w") as full_report:
    writer = csv.writer(full_report)
    writer.writerow(["DOI", "Type", "Publisher", "Title", "Journal", "Year"])
    with open("full_wos_report_cleaned_2024-07-04.csv", "r") as existing_doi_list:
        reader = csv.reader(existing_doi_list)
        reader.__next__()
        for row in reader:
            writer.writerow(row)
            if row[0] in doi_list:
                doi_list.remove(row[0])
    for doi in doi_list:
        url = "https://api.crossref.org/works/" + doi
        result = requests.get(url)
        try:
            result = result.json()["message"]
            # Write the results to a CSV file
            publisher = result["publisher"]
            title = result["title"][0]
            try:
                journal = result["container-title"][0]
            except:
                journal = ""
            year = result["issued"]["date-parts"][0][0]
            writer.writerow([doi, result["type"], publisher, title, journal, year])
        except:
            print(doi)
            print(result)
