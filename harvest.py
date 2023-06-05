import os,csv,json
import subprocess
import requests
from check_doi import check_doi
from caltechdata_api import caltechdata_write

# Get defaults from environment variables if available
ror = os.getenv("ROR")
if ror is None:
    ror = "05dxps055"
email = os.getenv("EMAIL")
if email is None:
    email = "library@caltech.edu"
token = os.getenv("RDMTOK")

# Get when the harvest was last run
with open("last_run.txt") as infile:
    last_run = infile.read().strip('\n')

crossref_path = f"http://api.crossref.org/works?filter=ror-id:{ror},from-index-date:{last_run}&mailto={email}"

community = '70768bd5-918b-441b-bd45-12a3f296447c'

excluded = ['peer-review','grant']

# Get the list of DOIs from Crossref
response = requests.get(crossref_path)
data = response.json()
if 'items' in data['message']:
    for result in data['message']['items']:
        if result['type'] not in excluded:
            DOI = result['DOI']
            print(DOI)
            if not check_doi(DOI,production=False):
                try:
                    transformed = subprocess.check_output(['doi2rdm', DOI])
                    data = transformed.decode('utf-8')
                    print(data)
                    data = json.loads(data)
                    response = caltechdata_write(data,token,production=False,authors=True,community=community)
                    print(response)
                    exit()
                except subprocess.CalledProcessError:
                    print("Error with doi2rdm")
                
