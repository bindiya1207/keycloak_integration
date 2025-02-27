from pymongo import MongoClient

def setup_mongodb_prompts():
    try:
        # Connect to MongoDB
        client = MongoClient('mongodb://localhost:27017/')  # Replace with your MongoDB connection string
        db = client['prompts']
        collection = db['known_prompts']
        
        # Initial prompt data
        prompt_data = [
            {
                "action": "INFORMATION_SEARCH",
                "text": "Looking for information ? Let me know!",
                "response": {
                    "text": "What information are you looking for? Please describe what you need.",
                    "incidentCreationMode": False,
                    "previewMode": True,
                    "prompts": []
                }
            },
            {
                "action": "IT_SUPPORT",
                "text": "Do you need IT support?",
                "response": {
                    "text": "Please describe the IT issue you're experiencing, and I'll help create a support ticket.",
                    "incidentCreationMode": True,
                    "previewMode": False,
                    "prompts": []
                }
            }
        ]
        
        # Clear existing prompts (optional - remove if you want to keep existing data)
        collection.delete_many({})
        
        # Insert the new prompts
        result = collection.insert_many(prompt_data)
        
        print(f"Successfully inserted {len(result.inserted_ids)} prompts")
        
        # Verify the data
        print("\nVerifying inserted data:")
        for prompt in collection.find():
            print(f"Action: {prompt['action']}")
            print(f"Text: {prompt['text']}")
            print("---")
            
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    setup_mongodb_prompts()