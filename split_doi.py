import json, os

data = os.environ["DOI"]

data = data.split()

os.environ["DOI"] = json.dumps(data)