import requests  
print(requests.post('http://localhost:5000/api/upload', files={'file': open('(提供)ケースマスタ.xlsx', 'rb')}).text)  
