import csv, json
import requests

# Open the file with the list of DOIs
with open("wos_report.csv", "r") as doi_list:
    reader = csv.reader(doi_list)
    # Create a list of DOIs
    doi_list = [row[0] for row in reader]
with open("full_wos_report_2024_08_27.csv", "w") as full_report:
    writer = csv.writer(full_report)
    writer.writerow(["DOI", "Type", "Publisher", "Title", "Journal", "Year"])
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
            if result["type"] == "journal-article":
                writer.writerow([doi, result["type"], publisher, title, journal, year])
            else:
                print(result["type"])
        except:
            print(doi)
            print(result)
