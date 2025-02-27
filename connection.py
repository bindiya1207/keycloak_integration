from pymilvus import connections

try:
    connections.connect(host = 'localhost', port = '19530')
    print("Connected to Milvus!")

except Exception as e:
    print(e)
