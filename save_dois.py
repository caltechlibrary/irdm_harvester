import sys, json

result = json.loads(sys.argv[1])

dois = result['doi']

for doi in dois.keys:
    with open("harvested_dois.txt", "a") as f:
        f.write(doi + "\n")
