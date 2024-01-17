import json, os

data = os.environ["DOI"]

data = data.split()
print(data)

os.environ["DOI"] = json.dumps(data)
