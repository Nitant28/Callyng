import requests

resp = requests.get("http://localhost:8000/api/calls/6f54be7d-2fff-42c1-b66a-e5d8e5833fab", headers={"Authorization": "Bearer fake_token_doesnt_matter"})
print(resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    print("Transcript type:", type(data.get('transcript')))
    if isinstance(data.get('transcript'), str):
        print("Snippet:", data['transcript'][:50])
    elif isinstance(data.get('transcript'), list):
        print("Snippet:", data['transcript'][:2])
else:
    print(resp.text)
