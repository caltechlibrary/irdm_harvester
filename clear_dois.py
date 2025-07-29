import csv

infile = "to_close.csv"

with open(infile, "r") as f:
    reader = csv.reader(f)
    dois = [row[3] for row in reader if row]

with open("harvested_dois.txt") as infile:
    harvested_dois = infile.read().splitlines()

for doi in dois:
    if doi in harvested_dois:
        harvested_dois.remove(doi)

with open("harvested_dois.txt", "w") as outfile:
    outfile.write("\n".join(harvested_dois))
