import requests

# Test the new single URL API
# r = requests.post("http://localhost:8000/scrape/async", json={"url": "https://www.tiktok.com/@simplehome/video/7309754078010051841"})
# print("Task started:")
# print(r.json())

# Get task ID from response to check status

status_r = requests.get(f"http://localhost:8000/task/14062cd9-8c36-4a6b-92db-5ee536dbe5e9")
print(status_r.json())