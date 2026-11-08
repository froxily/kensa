import requests

response = requests.get('https://127.0.0.1:19200/_cluster/health', timeout=5)
response.raise_for_status()
print(response.json()['status'])
