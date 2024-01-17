import json, os

data = os.environ["DOI"]

data = data.split()
print('matrix=',json.dumps(data))

