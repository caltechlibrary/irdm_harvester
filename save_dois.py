import sys, json

result = json.loads(sys.argv[1])

dois = result['doi']

print(dois)

for doi in dois.keys():
    print(doi)
    print(dois[doi])
    if dois[doi] != 'null':
        with open("harvested_dois.txt", "a") as f:
            f.write(doi + "\n")
