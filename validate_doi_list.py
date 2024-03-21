import csv, json
import requests
from check_doi import check_doi

deduped = []

with open("full_wos_report.csv", "r") as full_report:
    reader = csv.reader(full_report)
    header = next(reader)
    for row in reader:
        doi = row[0]
        if check_doi(doi) == False:
            deduped.append(row)

with open("full_wos_report_cleaned_2024-03-21.csv", "w") as full_report:
    writer = csv.writer(full_report)
    writer.writerow(["DOI", "Type", "Publisher", "Title", "Journal", "Year"])
    for row in deduped:
        writer.writerow(row)
