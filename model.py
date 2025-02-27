import json
import re
import numpy as np
import nltk
from nltk.corpus import stopwords
from tensorflow.keras.models import load_model
from sentence_transformers import SentenceTransformer
import torch
 
class DepartmentClassifier:
    def __init__(self, model_path, embedding_model_name, labels_path):
        # Load the trained model
        self.model = load_model(model_path)
 
        # Load the embedding model
        self.embedding_model = SentenceTransformer(embedding_model_name)
 
        # Load labels
        with open(labels_path, 'r') as f:
            self.labels = json.load(f)
        self.inverse_labels = {v: k for k, v in self.labels.items()}
 
        # Ensure NLTK stopwords are downloaded
        nltk.download('stopwords')
        self.stop_words = set(stopwords.words('english'))
 
    def preprocess_text(self, text):
        """Preprocess the input text by converting to lowercase, removing non-alphabetic characters, and stopwords."""
        text = text.lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)  # Remove non-alphabetic characters
        text = ' '.join(word for word in text.split() if word not in self.stop_words)  # Remove stopwords
        return text
 
    def predict_department(self, query):
        """Predict the department based on the input query."""
        # Preprocess the query
        query = self.preprocess_text(query)
 
        # Generate embedding
        query_embedding = self.embedding_model.encode(query)
        if isinstance(query_embedding, torch.Tensor):
            query_embedding = query_embedding.cpu().numpy()
 
        # Predict department
        prediction = self.model.predict(query_embedding.reshape(1, -1))
        predicted_label = np.argmax(prediction)
 
        # Map label back to department
        return self.inverse_labels[predicted_label]