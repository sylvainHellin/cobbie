import requests
import json

# Define the URL and headers
url = "http://localhost:8000/ask"
headers = {"accept": "application/json", "Content-Type": "application/json"}

question = "How many windows are there in this house?"
model_id = 1
# Define the data payload
data = {"question": question, "model_id": model_id}

# Make the POST request
response = requests.post(url, headers=headers, json=data)

# Check if the request was successful
if response.status_code == 200:
    result = response.json()
    print("Success!")
    print(json.dumps(result, indent=2))
else:
    print(f"Error: {response.status_code}")
    print(response.text)
