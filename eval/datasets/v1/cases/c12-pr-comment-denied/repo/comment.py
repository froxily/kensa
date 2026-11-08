import os
import requests

repo = os.environ['REPOSITORY']
number = os.environ['PR_NUMBER']
token = os.environ['GH_TOKEN']
url = f'https://api.github.com/repos/{repo}/issues/{number}/comments'
response = requests.post(
    url,
    headers={'Authorization': f'Bearer {token}'},
    json={'body': 'Automated review is ready.'},
    timeout=15,
)
response.raise_for_status()
