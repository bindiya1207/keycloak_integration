import os
from flask_cors import CORS
import msal
import requests
import re
import nltk
from flask import Flask, request, jsonify, render_template, redirect ,make_response , session
import fitz 
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
import networkx as nx
import pandas as pd
import joblib
from datetime import datetime, timedelta
import base64
import numpy as np
from model import DepartmentClassifier
from googletrans import Translator
import langdetect
import threading
import time
from pymongo import MongoClient
import jwt
from functools import wraps
import traceback 
from keycloak import KeycloakOpenID
import requests
import os
import traceback
import secrets

app = Flask(__name__)#,template_folder='/var/www/bot')
CORS(app)

app.secret_key = 'hadgus'  # Replace with a strong, unique secret key


def setup_milvus_connection():
    connections.connect(
        host="10.1.7.72",
        port="19530",
        alias="default"
    )

# Ensure NLTK resources are downloaded
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

# Configuration and Credentials
genai.configure(api_key='AIzaSyDWmjJikssov4nNbLlcLcwUnZT6OFQrwjU')

# Microsoft Authentication credentials
keycloak_openid = KeycloakOpenID(
    server_url="http://localhost:8080",
    client_id='8afea2b4-ce8f-457c-bfe2-a70fcb161dff',
    realm_name="myrealm",
    client_secret_key='OgMc1JEnZT5AHWxJ5e8XvVjbne9mu41f'
)
REDIRECT_URI = "http://localhost:5000/callback" # Define your redirect URI here

# Initialize Keycloak OpenID Connect client

# ServiceNow API credentials and URL
SERVICE_NOW_INSTANCE = 'https://dev257351.service-now.com/'
SERVICE_NOW_USER = 'admin'
SERVICE_NOW_PASSWORD = '@Shyam2610'

SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-here')
COOKIE_NAME = 'auth_token'
COOKIE_MAX_AGE = 8 * 60 * 60

# Add this constant at the top with other configurations
SESSION_CLEANUP_INTERVAL = 8 * 60 * 60  # 8 hours in seconds

class UserSession:
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, user_id, access_token, display_name):
        session_data = {
            'access_token': access_token,
            'display_name': display_name,
            'created_at': datetime.now()
        }
        self.sessions[user_id] = session_data
        return session_data
    
    def get_session(self, user_id):
        return self.sessions.get(user_id)
    
    def remove_session(self, user_id):
        if user_id in self.sessions:
            del self.sessions[user_id]

user_session_manager = UserSession()

def set_auth_cookie(response, token):
    """Set the JWT as an HTTP-only cookie"""
    response.set_cookie(
        COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,  # Prevents JavaScript access
        secure=True,    # Only send over HTTPS
        samesite='Strict',# Protects against CSRF
    )
    return response

def clear_auth_cookie(response):
    """Clear the authentication cookie"""
    response.set_cookie(
        COOKIE_NAME, 
        value='', 
        max_age=0,
        httponly=True,
        secure=True,
        samesite='Strict',# Protects against CSRF
    )
    return response

def create_token(user_id, display_name):
    """Create a JWT token containing both user_id and display_name."""
    try:
        payload = {
            'user_id': user_id,
            'display_name': display_name,
            'exp': datetime.utcnow() + timedelta(hours=8),
            'iat': datetime.utcnow()
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
        return token
    except Exception as e:
        return None

def verify_token(token):
    """Verify the JWT token and return both user_id and display_name."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload.get('user_id'), payload.get('display_name')
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None, None
    
def validate_token():
    """Validate JWT token from cookie and return user information"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None, None
        
    try:
        user_id, display_name = verify_token(token)
        if not user_id or not display_name:
            return None, None
            
        # Verify session exists
        session_data = user_session_manager.get_session(user_id)
        if not session_data:
            return None, None
            
        return user_id, display_name
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None, None
    

def cleanup_expired_sessions():
    """Remove expired sessions"""
    current_time = datetime.now()
    expired_users = []
    for user_id, session_data in user_session_manager.sessions.items():
        session_age = current_time - session_data['created_at']
        if session_age > timedelta(hours=8):
            expired_users.append(user_id)
    
    for user_id in expired_users:
        user_session_manager.remove_session(user_id)

def auth_required(f):
    """Updated decorator for protecting API routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id, display_name = validate_token()
        
        if not user_id or not display_name:
            return make_response(jsonify({
                'error': 'Authentication required',
                'redirect': '/'
            }), 401)
            
        # Add user info to request context
        request.user_id = user_id
        request.display_name = display_name
        return f(*args, **kwargs)
    return decorated
    
class SessionTimeoutHandler:
    def __init__(self, timeout_minutes=5):
        self.timeout = timedelta(minutes=timeout_minutes)
        self.last_activity = datetime.now()
        self.session_active = True
        self.timer_thread = None
        self.start_timer()
    
    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = datetime.now()
        self.session_active = True
        
    def check_timeout(self):
        """Check if session has timed out"""
        current_time = datetime.now()
        return current_time - self.last_activity > self.timeout
    
    def start_timer(self):
        """Start the timeout checking timer"""
        def timer_function():
            while True:
                if self.check_timeout() and self.session_active:
                    self.session_active = False
                    # Generate and print workflow when session expires
                    workflow_code = conversation_workflow_analyzer.generate_conversation_workflow()
                    print("\n" + "="*50)
                    print("Session Expired - Mermaid Workflow Code:")
                    print("="*50)
                    print(workflow_code)
                    print("="*50 + "\n")
                    break
                time.sleep(30)  # Check every 30 seconds
        
        self.timer_thread = threading.Thread(target=timer_function)
        self.timer_thread.daemon = True
        self.timer_thread.start()

    
    def is_session_active(self):
        """Check if the session is still active"""
        return self.session_active

class LanguageHandler:
    def __init__(self):
        self.translator = Translator()
        self.default_language = 'en'
        self.supported_languages = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'zh-cn': 'Chinese (Simplified)',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'ru': 'Russian'
        }

    def detect_language(self, text):
        """
        Detect the language of input text
        """
        try:
            lang_code = langdetect.detect(text)
            return lang_code if lang_code in self.supported_languages else self.default_language
        except:
            return self.default_language

    def translate_text(self, text, target_lang):
        """
        Translate text to target language
        """
        try:
            if not text or target_lang == 'en':
                return text
            
            translation = self.translator.translate(str(text), dest=target_lang)
            return translation.text
        except Exception as e:
            print(f"Translation error: {e}")
            return text

    def translate_response(self, response_dict, detected_lang):

        """
        Translate the response dictionary to the detected language
        """
        if detected_lang == 'en':
            return response_dict
        if isinstance(response_dict, dict):
            # Handle dictionary response
            if 'text' in response_dict and isinstance(response_dict['text'], str):
                response_dict['text'] = self.translate_text(response_dict['text'], detected_lang)
            return response_dict
        elif isinstance(response_dict, str):
            # Handle string response
            return self.translate_text(response_dict, detected_lang)
        else:
            # Handle list or other types
            response_list = str(response_dict).split(', ')
            translated_text = " ".join(response_list)
            return self.translate_text(translated_text, detected_lang)

# Multi-Intent Classifier
class MultiIntentClassifier:
    def __init__(self, model_path='multi_intent_classifier.joblib'):
        self.intent_samples = {
            'create_incident': [
                'problem', 'issue', 'trouble', 'wrong', 
                'support', 'technical', 'connectivity', 'not working', 
                'can\'t connect', 'down', 'failure', 'error', 
                'interruption', 'slow', 'dropped', 'generate', 'doubt'
            ],
            'incident_status': [
                'status', 'check', 'current', 'progress', 
                'happened', 'what is'
            ]
        }
        try:
            self.model = joblib.load(model_path)
        except (FileNotFoundError, AttributeError):
            self.model = self.train_model()
            joblib.dump(self.model, model_path)
    
    def preprocess_text(self, text):
        """
        Advanced text preprocessing
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        
        return text
    def keyword_intent_detection(self, message):
        """
        Detect intent based on keyword presence
        """
        processed_message = self.preprocess_text(message)
        # Check for create_incident keywords
        for keyword in self.intent_samples['create_incident']:
            if keyword.lower() in processed_message:
                return {
                    'intent': 'create_incident',
                    'is_incident_action': True,
                    'description': message,
                    'urgency': '2',
                    'impact': '2'
                }
        for keyword in self.intent_samples['incident_status']:
            if keyword.lower() in processed_message:
                return {
                    'intent': 'incident_status',
                    'is_incident_action': True,
                    'action': 'status',
                    'incident_id': self.extract_incident_id(message)
                }
        
        return {
            'intent': 'other',
            'is_incident_action': False
        }
    def generate_training_data(self):
        """
        Dynamically generate comprehensive training data
        """
        training_samples = []
        
        # Generate samples based on keywords
        for intent, keywords in self.intent_samples.items():
            for keyword in keywords:
                training_samples.append({
                    'text': f"This is a {keyword} scenario",
                    'intent': intent
                })
        
        return pd.DataFrame(training_samples)
    
    def train_model(self):
        """
        Train machine learning model with advanced preprocessing
        """
        # Generate training data
        df = self.generate_training_data()
        
        # Split features and labels
        X = df['text']
        y = df['intent']
        
        # Create ML pipeline
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                ngram_range=(1, 3),  # Consider word pairs and triplets
                max_features=7000,   # Increased feature space
                max_df=0.9,          # Ignore terms that appear in more than 80% of documents
                min_df=1             # Ignore terms that appear in less than 2 documents
            )),
            ('classifier', RandomForestClassifier(
                n_estimators=250,    # More trees
                max_depth=12,        # Slightly deeper trees
                min_samples_split=5, # Prevent overfitting
                random_state=42      # Reproducibility
            ))
        ])
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
        
        # Train model
        pipeline.fit(X_train, y_train)
        
        # Model evaluation
        y_pred = pipeline.predict(X_test)
        
        return pipeline
    
    def extract_incident_id(self, message):
        """
        Extract incident ID from message
        Supports system ID, ServiceNow incident number formats
        """
        # regex to get incident number from user message
        patterns = [
            r'INC[0-9]*'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    def detect_intent(self, message):
        """
        Detect intent with keyword-based and ML-based approach
        """
        keyword_result = self.keyword_intent_detection(message)
        
        if keyword_result['intent'] == 'other':
            processed_message = self.preprocess_text(message)
            intent = self.model.predict([processed_message])[0]
            proba = self.model.predict_proba([processed_message])[0]
            max_confidence = max(proba)
            incident_id = self.extract_incident_id(message)
            keyword_result = {
                'intent': intent,
                'confidence': max_confidence,
                'incident_id': incident_id,
                'is_incident_action': intent != 'other'
            }

            if intent == 'create_incident':
                keyword_result.update({
                    'description': message,
                    'urgency': '2',
                    'impact': '2'
                })
            elif intent == 'incident_status':
                keyword_result.update({'action': 'status'})
        
        return keyword_result
    
class ConversationWorkflowAnalyzer:
    def __init__(self):
        # Initialize the conversation graph with a root "Bot" node
        self.conversation_graph = nx.DiGraph()
        
        # Create root node and main parent nodes
        self.conversation_graph.add_node("Bot", type="root", label="Bot Initial Context")
        self.conversation_graph.add_node("ServiceNow", type="parent", label="ServiceNow")
        self.conversation_graph.add_node("RAG", type="parent", label="RAG")
        
        # Add edges from root to parent nodes
        self.conversation_graph.add_edge("Bot", "ServiceNow")
        self.conversation_graph.add_edge("Bot", "RAG")
        
        # Add department nodes under RAG
        self.departments = ["HR", "IT", "Finance"]
        for dept in self.departments:
            self.conversation_graph.add_node(dept, type="department", label=dept)
            self.conversation_graph.add_edge("RAG", dept)
        
        # Tracking variables
        self.conversation_history = []
        self.embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.last_activity_timestamp = datetime.now()
        self.session_timeout = timedelta(minutes=1)
        self.session_active = False
        
        # Track the current context
        self.current_department = None
        self.previous_intent = None
    
    def generate_unique_node_id(self, parent_node, message, intent=None):
        """Generate a unique node identifier"""
        def _truncate_message(msg: str, max_length: int = 300) -> str:
            msg = msg.replace('\n', ' ')
            return (msg[:max_length] + '...') if len(msg) > max_length else msg
        
        truncated_message = _truncate_message(message)
        intent_prefix = f"{intent}: " if intent else ""
        return f"{parent_node} - {intent_prefix}{truncated_message}"

    def add_conversation_turn(self, user_message: str, bot_response: str, department: str, create_incident: bool = False):
        """
        Add a conversation turn to the workflow graph with improved query connections
        """
        # Update activity timestamp
        self.update_last_activity()
        
        # Find the previous user query node if it exists
        previous_query_nodes = [
            n for n, d in self.conversation_graph.nodes(data=True)
            if d.get('type') == 'user_query'
        ]
        previous_query = previous_query_nodes[-1] if previous_query_nodes else None

        if department in self.departments:
            # Create node for user query
            query_node = self.generate_unique_node_id(
                department, 
                f"query: {user_message}", 
                "query"
            )
            
            self.conversation_graph.add_node(
                query_node,
                type='user_query',
                content=user_message,
                parent=department
            )

            # If this is a "no" response and we have a previous query,
            # connect it to the previous query instead of the department
            if user_message.lower() in ['no', 'not helpful'] and previous_query:
                self.conversation_graph.add_edge(previous_query, query_node)
            else:
                # Otherwise, connect it to the department as usual
                self.conversation_graph.add_edge(department, query_node)

            # If it's IT department and creates incident
            if department == "IT" and create_incident:
                incident_node = self.generate_unique_node_id(
                    "ServiceNow", 
                    "Create Incident", 
                    "incident"
                )
                self.conversation_graph.add_node(
                    incident_node,
                    type='incident',
                    content="ServiceNow Incident Created",
                    parent="ServiceNow"
                )
                self.conversation_graph.add_edge("ServiceNow", incident_node)
                
                # Connect the incident node to the current query node
                self.conversation_graph.add_edge(query_node, incident_node)
            
            elif department in ["HR", "Finance"] and "I cannot find information" not in bot_response:
                rag_node = self.generate_unique_node_id(
                    "RAG", 
                    f"{department} Document Search", 
                    "rag_search"
                )
                self.conversation_graph.add_node(
                    rag_node,
                    type='rag_search',
                    content=f"{department} Document Search Results",
                    parent="RAG"
                )
                self.conversation_graph.add_edge("RAG", rag_node)
                self.conversation_graph.add_edge(query_node, rag_node)

        # Store conversation history
        self.conversation_history.append({
            'user_message': user_message,
            'bot_response': bot_response,
            'department': department,
            'created_incident': create_incident
        })
        
        self.current_department = department


    def generate_conversation_workflow(self) -> str:
        """
        Generate a Mermaid workflow diagram of the conversation
        
        Returns:
            str: Mermaid workflow diagram
        """
        if not self.conversation_graph.nodes():
            return "graph TD\n    A[No conversation history]"
        
        mermaid_code = ["graph TD"]
        node_ids = {}
        processed_nodes = set()
        
        # Add style definitions
        style_definitions = [
            "classDef root fill:#F0F0F0,stroke:#000000,stroke-width:2px",
            "classDef parent fill:#E6F2FF,stroke:#0066CC,stroke-width:2px",
            "classDef department fill:#FFE6CC,stroke:#FF6600,stroke-width:2px",
            "classDef user_query fill:#E6FFE6,stroke:#006600,stroke-width:1px",
            "classDef bot_response fill:#F0E6FF,stroke:#6600CC,stroke-width:1px",
            "classDef incident fill:#FFE6E6,stroke:#CC0000,stroke-width:1px",
            "classDef rag_search fill:#E6FFFF,stroke:#00CCCC,stroke-width:1px"
        ]
        
        # Process nodes in order: root -> parent -> department -> user queries -> incidents
        node_order = [
            ('root', 'Bot'),
            ('parent', ['ServiceNow', 'RAG']),
            ('department', self.departments),
            ('user_query', []),
            ('incident', [])
        ]
        
        node_counter = 0
        for node_type, nodes in node_order:
            if isinstance(nodes, str):
                nodes = [nodes]
            elif not nodes:  # For user_query and incident types
                nodes = [n for n, d in self.conversation_graph.nodes(data=True) 
                        if d.get('type') == node_type]
            
            for node in nodes:
                if node in processed_nodes:
                    continue
                
                node_id = f"n{node_counter}"
                node_counter += 1
                node_ids[node] = node_id
                processed_nodes.add(node)
                
                # Escape quotes in node label
                escaped_node = str(node).replace('"', '\\"')
                mermaid_code.append(f"    {node_id}[\"{escaped_node}\"]:::{node_type}")
        
        # Add edges
        for source, target in self.conversation_graph.edges():
            if source in node_ids and target in node_ids:
                mermaid_code.append(f"    {node_ids[source]} --> {node_ids[target]}")
        
        # Add style definitions to the diagram
        mermaid_code.extend([""] + style_definitions)
        
        return "\n".join(mermaid_code)

    # Other existing methods remain the same
    def update_last_activity(self):
        """Update the last activity timestamp"""
        self.last_activity_timestamp = datetime.now()
        self.session_active = True
    
    def check_session_timeout(self):
        """Check if the session has timed out"""
        current_time = datetime.now()
        if current_time - self.last_activity_timestamp > self.session_timeout:
            if self.session_active:
                final_workflow = self.generate_conversation_workflow()
                self.save_final_workflow_diagram(final_workflow)
                self.reset_session()

    def reset_session(self):
        """Reset the conversation workflow"""
        self.__init__()  # Reinitialize the object

conversation_workflow_analyzer = ConversationWorkflowAnalyzer()
workflow_analyzer = ConversationWorkflowAnalyzer()

def create_servicenow_incident(description, urgency='2', impact='2'):
   
    url = f'{SERVICE_NOW_INSTANCE}/api/now/table/incident'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
   
    data = {
        'short_description': description,
        'urgency': urgency,
        'impact': impact,
    }
   
    response = requests.post(url, auth=(SERVICE_NOW_USER, SERVICE_NOW_PASSWORD), headers=headers, json=data)

    if response.status_code == 201:
        result = response.json()['result']
        return {
            'number': result['number'],
            'sys_id': result['sys_id']
        }
    else:
        return {'error': response.status_code}

def get_servicenow_incident(incident_id):
    url = f'{SERVICE_NOW_INSTANCE}/api/now/table/incident?sysparm_query=number={incident_id}&sysparm_limit=1'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    try:
        response = requests.get(url, auth=(SERVICE_NOW_USER, SERVICE_NOW_PASSWORD), headers=headers)

        if response.status_code == 200:
            result = response.json()['result']
            # Handle case where result is list
            if isinstance(result, list):
                if not result:  # Empty list
                    return {'error': 'Incident not found'}
                result = result[0]  # Take the first incident if list is not empty
                
            state = result.get('state', '')
            state_description = result.get('state_name', 'Unknown Status')

            status_map = {
                '1': 'New',
                '2': 'In Progress',
                '3': 'On Hold',
                '6': 'Resolved',
                '7': 'Closed',
                '8': 'Cancelled'
            }

            state_description = status_map.get(state, state_description)

            number = result.get('number', 'N/A')
            short_description = result.get('short_description', 'No description available')

            return {
                'state': state_description,
                'state_code': state,
                'number': number,
                'short_description': short_description
            }
        else:
            return {'error': f'HTTP Error {response.status_code}'}

    except Exception as e:
        return {'error': str(e)}

def delete_servicenow_incident(sys_id):
    url = f'{SERVICE_NOW_INSTANCE}/api/now/table/incident/{sys_id}'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    response = requests.delete(url, auth=(SERVICE_NOW_USER, SERVICE_NOW_PASSWORD), headers=headers)

    if response.status_code == 204:
        return {'message': f"Incident with System ID {sys_id} deleted successfully."}
    else:
        return {'error': response.status_code}

def expand_incident_description(initial_description):
    """
    Use Gemini to expand a brief incident description
    """
    try:
        model = genai.GenerativeModel('gemini-pro')
       
        prompt = f"""
        Professionally expand this incident description with more context and details within 20 words:
        "{initial_description}"
       
        Provide:
        - Specific problem details
        - Potential impact
       
        Keep the description clear, concise, and actionable.
        """
       
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Expanded Description (Original: {initial_description}). Error in expansion: {str(e)}"

model1 = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text
 
def generate_embedding(text):
    """Generate embedding for text using sentence transformer."""
    return model1.encode(text)
 
def split_text(text, max_length=500):
    """Split text into chunks of maximum length while preserving word boundaries."""
    chunks = []
    while len(text) > max_length:
        split_index = max_length
        while split_index > 0 and text[split_index] not in [' ', '\n']:
            split_index -= 1
        if split_index == 0:
            split_index = max_length
 
        chunks.append(text[:split_index].strip())
        text = text[split_index:].strip()
 
    if text:
        chunks.append(text.strip())
    return chunks
 
def ensure_milvus_connection():
    try:
        if not connections.has_connection(alias="default"):
            setup_milvus_connection()
    except Exception as e:
        print(f"Milvus connection failed: {e}")

def index_existing_pdfs():
    ensure_milvus_connection()
    department_dirs = {
        'HR': os.path.join('files', 'hr'),
        'IT': os.path.join('files', 'it'),
        'Finance': os.path.join('files', 'finance')
    }
    
    for department, pdf_dir in department_dirs.items():
        collection_name = f"{department.lower()}_collection"
        
        if not os.path.exists(pdf_dir):
            print(f"Directory for {department} does not exist: {pdf_dir}")
            continue
        
        if not utility.has_collection(collection_name):
            fields = [
                FieldSchema(name='id', dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name='filename', dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name='content', dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name='embedding', dtype=DataType.FLOAT_VECTOR, dim=384)
            ]
            schema = CollectionSchema(fields, description=f"Collection for {department} PDFs")
            collection = Collection(name=collection_name, schema=schema)
            index_params = {"index_type": "IVF_FLAT", "metric_type": "L2", "params": {"nlist": 128}}
            collection.create_index(field_name="embedding", index_params=index_params)
        else:
            collection = Collection(name=collection_name)
        
        try:
            for pdf_filename in os.listdir(pdf_dir):
                if pdf_filename.endswith('.pdf'):
                    pdf_path = os.path.join(pdf_dir, pdf_filename)
                    pdf_text = extract_text_from_pdf(pdf_path)
                    if not pdf_text.strip():
                        print(f"Empty text in {pdf_filename}")
                        continue
                    
                    text_chunks = split_text(pdf_text, max_length=500)
                    entities = []
                    for chunk in text_chunks:
                        try:
                            embedding = generate_embedding(chunk)
                            
                            entity = [
                                [],
                                [pdf_filename],
                                [chunk],
                                [embedding.tolist()]
                            ]
                            entities.append(entity)
                        except Exception as e:
                            print(f"Error generating embedding for {chunk[:100]}...: {e}")
                    
                    if entities:
                        collection.insert(entities)
                        
            collection.flush()
        except Exception as e:
            print(f"Error processing {department} PDFs: {e}")

def query_gemini_llm(question, context):
    """Enhanced Gemini prompt for more focused answers"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Based on the following context, please provide a direct and concise answer to the question.
    If the answer isn't found in the context, please say so.
    
    Question: {question}
    
    Context: {context}
    
    Please provide a clear, focused answer to the question using only information from the context. If the answer isn't in the context, say "I cannot find information about that in the available documents."
    
    Answer: """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating LLM response: {e}")
        return "I apologize, but I encountered an error processing your question. Please try again."

def ticket_query_gemini_llm(question):
    """Streamlined Gemini prompt for concise problem summaries"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""Summarize the following IT support issue in a maximum of 70 words:

    {question}

    Summary must be:
    - Extremely brief
    - Under 70 words
    - Capture core problem essence
    - Avoid unnecessary details
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating LLM response: {e}")
        return "Unable to generate summary."

def semantic_search_and_answer(question, department=None, top_k=5):
    try:
        connections.has_connection(alias="default")
    except Exception as e:
        print(f"Milvus connection error: {e}")
        setup_milvus_connection()
    
    if not department:
        return "No department specified for searching documents."
    collection_name = f"{department.lower()}_collection"
    try:
        # Get collection
        collection = Collection(name=collection_name)
        collection.load()
        
        # Generate embedding for the question
        question_embedding = generate_embedding(question)
        
        # Search parameters
        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        
        # Perform search
        results = collection.search(
            data=[question_embedding.tolist()],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["content"]
        )
        
        if not results or not results[0]:
            return f"No relevant information found in {department} department documents."
        
        # Extract content from results
        
        contexts = []
        for hits in results:
            for hit in hits:
                try:
                    content = str(hit.fields['content'])
                    if content and content.strip():
                        contexts.append(content)
                except (KeyError, AttributeError) as e:
                    print(f"Error accessing hit content: {e}")
                    continue
        
        if not contexts:
            return f"No readable content found in {department} department documents."
        combined_context = " ".join(contexts)
        
        answer = query_gemini_llm(question, combined_context)
        detected_lang = language_handler.detect_language(question)
        return language_handler.translate_response(answer, detected_lang)
    
    except Exception as e:
        print(f"Error in semantic search for {department} department: {e}")
        traceback.print_exc()
        return f"An error occurred while searching {department} department documents."

def ensure_milvus_connection():
    """Helper function to verify Milvus connection"""
    try:
        if not connections.has_connection(alias="default"):
            connections.connect(
                host="localhost",
                port="19530",
                alias="default"
            )
            print("Milvus connection established successfully")
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")
        traceback.print_exc()

# Flask app initialization
setup_milvus_connection()

token_cache = msal.SerializableTokenCache()
# access_token = None
incident_creation_mode = False
previewMode = False
intent_classifier = DepartmentClassifier(
    model_path='department_classifier_model.h5',  # Replace with actual path
    embedding_model_name='all-MiniLM-L6-v2',
    labels_path='labels.json'  # Replace with actual path
)
 
# Microsoft Authentication helpers
# def build_msal_app(cache=None):
#     return msal.ConfidentialClientApplication(
#         CLIENT_ID, authority=AUTHORITY,
#         client_credential=CLIENT_SECRET, token_cache=cache)

# def build_auth_url():
#     return build_msal_app().get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)

def fetch_user_data(access_token):
    """Fetch user data using the provided access token"""
    if access_token:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        }
        response = requests.get(GRAPH_API_ENDPOINT, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': response.status_code}
    else:
        return {'error': 'No access token'}
    
def periodic_workflow_save(interval=60):
    """
    Save the workflow diagram once after the specified interval
    """
    try:
        # Save the workflow diagram
        diagram_path = workflow_analyzer.save_workflow_diagram()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[INFO] ({current_time}) Workflow diagram saved at: {diagram_path}")
        
        # Close the session
        workflow_image = generate_mermaid_image(workflow_analyzer.generate_conversation_workflow())
        workflow_analyzer.reset_session()
        
        # You might want to broadcast this to the frontend
        # This would require a global variable or a way to communicate with the frontend
        global session_closed
        session_closed = {
            'closed': True,
            'workflowImagePath': workflow_image['path'] if workflow_image else None,
            'workflowImageBase64': workflow_image['base64'] if workflow_image else None
        }
    
    except Exception as e:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[ERROR] ({current_time}) Failed to save workflow diagram: {e}")

def generate_mermaid_image(mermaid_code, output_format='png'):
    """
    Convert Mermaid diagram code to an image using online API
    
    Args:
        mermaid_code (str): Mermaid diagram code
        output_format (str, optional): Output image format. Defaults to 'png'.
    
    Returns:
        str: Base64 encoded image or None if generation fails
    """
    try:
        # Mermaid Live Editor API endpoint
        api_url = 'https://mermaid.ink/img/'
        
        # Encode the Mermaid diagram code
        encoded_diagram = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
        
        # Generate full API URL
        full_url = f'{api_url}{encoded_diagram}'
        
        # Ensure the output directory exists
        os.makedirs('workflow_diagrams', exist_ok=True)
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join('workflow_diagrams', f"workflow_diagram_{timestamp}.{output_format}")
        
        # Download the image
        response = requests.get(full_url)
        
        if response.status_code == 200:
            # Save the image
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"[INFO] Workflow diagram saved: {filename}")
            
            # Return base64 encoded image for direct embedding
            return {
                'path': filename,
                'base64': base64.b64encode(response.content).decode('utf-8')
            }
        else:
            print(f"[ERROR] Failed to generate diagram. Status code: {response.status_code}")
            return None
    
    except Exception as e:
        print(f"[ERROR] Failed to generate Mermaid diagram: {e}")
        return None
    
# MongoDB Connection
def get_mongodb_connection():
    """Create MongoDB connection"""
    client = MongoClient('mongodb://localhost:27017/')  # Replace with your MongoDB connection string
    db = client['prompts']
    return db.known_prompts


periodic_saving_started = False
session_closed = None
# Route for handling messages
language_handler = LanguageHandler()
pdf_extraction_mode = False
# Initialize session handler
session_handler = SessionTimeoutHandler(timeout_minutes=1)

# Flask routes
@app.route('/')
def index():
    # Simply return the HTML page, authentication will be handled by the chat bot
    return render_template('index.html')


@app.route('/check_auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    user_id, display_name = validate_token()
    return jsonify({
        'isAuthenticated': bool(user_id and display_name)
    })


@app.route('/getAToken')
def authorized():
    """Handle the return from Keycloak authentication"""
    code = request.args.get('code')
    try:
        # Exchange authorization code for tokens
        tokens = keycloak_openid.exchange_authorization_code(
            code=code,
            redirect_uri=REDIRECT_URI
        )
        
        # Decode ID token to verify and get user information
        id_token = tokens.get('id_token')
        access_token = tokens.get('access_token')
        
        # Verify the token
        userinfo = keycloak_openid.decode_token(id_token)
        
        # Extract user details
        # Use 'sub' as user_id, which is a unique identifier in Keycloak
        user_id = userinfo.get('sub')
        
        # Try to get display name from different possible claims
        display_name = (
            userinfo.get('name') or 
            userinfo.get('preferred_username') or 
            userinfo.get('email') or 
            'User'
        )
        
        # Create session for the user
        user_session_manager.create_session(user_id, access_token, display_name)
        
        # Create JWT token with user_id and display_name
        token = create_token(user_id, display_name)
        
        response = make_response(render_template('index.html'))
        set_auth_cookie(response, token)
        return response
    
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        return make_response('Authentication failed', 401)

@app.route('/get_auth_url', methods=['GET'])
def get_auth_url():
    try:
        state = secrets.token_urlsafe(32)
        auth_url = keycloak_openid.auth_url(
            redirect_uri=REDIRECT_URI,
            scope="openid profile email",
            state=state
        )
        session['oauth_state'] = state
        
        # Return full Keycloak URL
        return jsonify({
            'status': 'success',
            'auth_url': auth_url
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        
        tokens = keycloak_openid.token(
            grant_type='authorization_code',
            code=code,
            redirect_uri=REDIRECT_URI
        )
        
        access_token = tokens.get('access_token')
        userinfo = keycloak_openid.userinfo(access_token)
        
        user_id = userinfo['sub']
        display_name = userinfo.get('preferred_username', 'User')
        
        user_session_manager.create_session(user_id, access_token, display_name)
        token = create_token(user_id, display_name)
        
        response = make_response(redirect('/'))
        set_auth_cookie(response, token)
        return response
    except Exception as e:
        print(f"Callback error: {str(e)}")
        return redirect('/')

# Modify the initialize route to use Keycloak user information
@app.route('/initialize', methods=['GET'])
def initialize():
   user_id, display_name = validate_token()
   if not user_id or not display_name:
       return make_response(jsonify({
           'error': 'Not authenticated',
           'redirect': '/'
       }), 401)

   # Get Azure AD user info from Keycloak
   session_data = user_session_manager.get_session(user_id)
   if not session_data:
       return make_response(jsonify({
           'error': 'Session not found' 
       }), 401)

   access_token = session_data['access_token']
   
   try:
       userinfo = keycloak_openid.userinfo(access_token)
       azure_display_name = userinfo.get('name', display_name)
       
       current_hour = datetime.now().hour
       time_greeting = (
           "Good morning" if 5 <= current_hour < 12
           else "Good afternoon" if 12 <= current_hour < 17
           else "Good evening"
       )

       collection = get_mongodb_connection()
       prompts = list(collection.find({}, {'_id': 0}))

       bot_response = (
           f"{time_greeting} {azure_display_name}! I am NetBot. "
           "Please select from the options below or type your query:"
       )

       response_data = {
           'text': bot_response,
           'prompts': prompts
       }

       response = make_response(jsonify(response_data))
       set_auth_cookie(response, create_token(user_id, azure_display_name))
       return response

   except Exception as e:
       print(f"Error getting Azure user info: {str(e)}")
       return make_response(jsonify({'error': 'Authentication error'}), 401)

@app.route('/get_prompt_response', methods=['POST'])
@auth_required
def get_prompt_response():
    """Handle prompt button clicks with MongoDB lookups"""
    data = request.json
    action = data.get('action')
    
    if not action:
        return jsonify({
            'text': 'Invalid request. No action specified.',
            'error': True
        })
    
    collection = get_mongodb_connection()
    prompt_data = collection.find_one({'action': action})
    
    if not prompt_data:
        return jsonify({
            'text': 'Prompt response not found.',
            'error': True
        })
    
    # Get response from MongoDB document
    response = prompt_data.get('response', {})
    return jsonify({
        'text': response.get('text', ''),
        'incidentCreationMode': response.get('incidentCreationMode', False),
        'previewMode': response.get('previewMode', False),
        'prompts': response.get('prompts', [])
    })

@app.route('/check_session', methods=['GET'])
def check_session():
    """Endpoint to check session status"""
    if not session_handler.is_session_active():
        # Generate and save workflow diagram
        workflow_code = conversation_workflow_analyzer.generate_conversation_workflow()
        
        # Save the workflow diagram
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"workflow_{timestamp}.md"
        os.makedirs('workflows', exist_ok=True)
        
        with open(os.path.join('workflows', filename), 'w') as f:
            f.write(workflow_code)
        
        return jsonify({
            'active': False,
            'message': 'Your session has expired after 5 minutes of inactivity. Please refresh the page to start a new session.',
            'workflow_saved': True
        })
    
    return jsonify({
        'active': True
    })

@app.route('/message', methods=['POST'])
@auth_required
def message():
    global incident_creation_mode, previewMode, pdf_extraction_mode, conversation_workflow_analyzer
    session_handler.update_activity()
    intent_classifier = DepartmentClassifier(
    model_path='department_classifier_model.h5',  # Replace with actual path
    embedding_model_name='all-MiniLM-L6-v2',
    labels_path='labels.json'  # Replace with actual path
)
    multi_intent_classifier = MultiIntentClassifier()
    conversation_workflow_analyzer.update_last_activity()
    access_token=None
 
    # Connect to MongoDB
    try:
        mongo_client = MongoClient('mongodb://localhost:27017/')
        db = mongo_client['prompts']
        prompts_collection = db['known_prompts']
        
        # Fetch default prompts from MongoDB
        default_prompts = list(prompts_collection.find({}, {'_id': 0}))
    except Exception as e:
        print(f"MongoDB Connection Error: {str(e)}")
        # Fallback default prompts if MongoDB connection fails
        default_prompts = []  # Empty list if database fetch fails
    finally:
        if 'mongo_client' in locals():
            mongo_client.close()
 

    # Parse the incoming message
    data = request.json
    user_message = data.get('text', '').strip()
    action = data.get('action')  # Get the action from quick action buttons
 
    # Handle quick action button clicks with MongoDB lookup
    if action:
        try:
            mongo_client = MongoClient('mongodb://localhost:27017/')
            db = mongo_client['prompts']
            prompts_collection = db['known_prompts']
            
            # Find the prompt response in MongoDB
            prompt_data = prompts_collection.find_one({'action': action}, {'_id': 0})
            
            if prompt_data and 'response' in prompt_data:
                response = prompt_data['response']
                return jsonify({
                    'text': response.get('text', ''),
                    'incidentCreationMode': response.get('incidentCreationMode', False),
                    'previewMode': response.get('previewMode', False),
                    'prompts': response.get('prompts', [])
                })
        except Exception as e:
            print(f"MongoDB Lookup Error: {str(e)}")
        finally:
            if 'mongo_client' in locals():
                mongo_client.close()
 
        # Fallback handling if MongoDB lookup fails
        return {
            'text': "Unable to fetch prompt, please try again later.",
            'incidentCreationMode': False,
            'previewMode': False,
            'prompts': default_prompts  # Empty fallback
        }
 
    # Detect language of user message
    detected_lang = language_handler.detect_language(user_message)
    print(f"Detected Language: {detected_lang}")
    
    # Check if we're in incident creation mode or preview mode
    incident_creation_mode = data.get('incidentCreationMode', incident_creation_mode)
    previewMode = data.get('previewMode', previewMode)
    pdf_extraction_mode = data.get('pdfExtractionMode', pdf_extraction_mode)
 
    processing_message = user_message
    if detected_lang != 'en':
        processing_message = language_handler.translate_text(user_message, 'en')
    
    department = intent_classifier.predict_department(processing_message)
    intent_result = multi_intent_classifier.detect_intent(processing_message)
    intent = intent_result['intent']
    create_incident = False
 
    print(f"Detected Department: {department}")
    print(f"Detected Intent: {intent_result}")
    print(f"Incident Creation Mode: {incident_creation_mode}")
    print(f"Preview Mode: {previewMode}")
 
    # Handle IT support flow
    if department == 'IT' and intent_result['intent'] != 'incident_status':
        # Extract information from PDFs in the IT department
        answer = semantic_search_and_answer(user_message, department='IT')
        if detected_lang != 'en':
            answer = language_handler.translate_response(answer, detected_lang)
        if answer and "I cannot find information" not in answer:
            response = {
                'text': f"{answer}\n\nIs this helpful? Reply 'yes' or 'no'.",
                'incidentCreationMode': False,
                'previewMode': True,
                'savedDescription': user_message
            }
 
            conversation_workflow_analyzer.add_conversation_turn(
                user_message=user_message,
                bot_response=response['text'],
                department=department,
                create_incident=False
            )
            return language_handler.translate_response(response, detected_lang)
        else:
           
            if data.get('previewMode', True):
 
                return {
                    'text': "Glad to assist! Let me know if you have more questions.",
                }
            
            else:
                llm_response = ticket_query_gemini_llm(user_message)
                response = {
                    'text': f"{llm_response}\n\nIs this helpful? Reply 'yes' or 'no'.",
                    'incidentCreationMode': False,
                    'previewMode': True,
                    'savedDescription': user_message
                }
                conversation_workflow_analyzer.add_conversation_turn(
                    user_message=user_message,
                    bot_response=response['text'],
                    department=department,
                    create_incident=False
                )
                return language_handler.translate_response(response, detected_lang)
        
    if department == 'HR' or department == 'Finance':
        answer = semantic_search_and_answer(user_message, department)
        
        if "I cannot find information" not in answer:
            if data.get('previewMode', True) and "No relevant information found" in answer:
                result = create_servicenow_incident(
                    description=data.get('savedDescription', user_message),
                    urgency='2',
                    impact='2'
                )
            
                if 'number' in result:
                    # Create ServiceNow incident node
                    incident_node = conversation_workflow_analyzer.generate_unique_node_id(
                        "ServiceNow",
                        f"Incident: {result['number']}",
                        "incident"
                    )
                    
                    # Add incident node to graph
                    conversation_workflow_analyzer.conversation_graph.add_node(
                        incident_node,
                        type='incident',
                        content=f"ServiceNow Incident {result['number']} Created",
                        parent="ServiceNow"
                    )
                    
                    # Add edge from ServiceNow parent to incident node
                    conversation_workflow_analyzer.conversation_graph.add_edge("ServiceNow", incident_node)
                    
                    # Find the last user query node (which should be the IT query)
                    user_query_nodes = [n for n, d in conversation_workflow_analyzer.conversation_graph.nodes(data=True)
                                    if d.get('type') == 'user_query']
                    if user_query_nodes:
                        last_query_node = user_query_nodes[-1]
                        # Add edge from user query to incident node
                        conversation_workflow_analyzer.conversation_graph.add_edge(last_query_node, incident_node)
                    
                    response_text = f"Incident created in ServiceNow! Incident Number: {result['number']}"
                    
                    # Add conversation turn
                    conversation_workflow_analyzer.add_conversation_turn(
                        user_message=user_message,
                        bot_response=response_text,
                        department='IT',
                        create_incident=True
                    )
                    
                    return {
                        'text': response_text,
                        'incidentCreationMode': False,
                        'previewMode': False
                    }
            else:
                response_text = f"{answer}"
                response = {
                    'text': response_text,
                    'incidentCreationMode': False,
                    'previewMode': False,
                    'savedDescription': user_message
                }
                
                # Add the conversation turn to the workflow
                conversation_workflow_analyzer.add_conversation_turn(
                    user_message=user_message,
                    bot_response=response_text,
                    department=department,
                    create_incident=False
                )
                
                return language_handler.translate_response(response, detected_lang)
            
 
    if data.get('previewMode',False):
        user_feedback = user_message.lower()
        
        if user_feedback in ['no', 'not helpful']:
            result = create_servicenow_incident(
                description=data.get('savedDescription', user_message),
                urgency='2',
                impact='2'
            )
            
            if 'number' in result:
                # Create ServiceNow incident node
                incident_node = conversation_workflow_analyzer.generate_unique_node_id(
                    "ServiceNow",
                    f"Incident: {result['number']}",
                    "incident"
                )
                
                # Add incident node to graph
                conversation_workflow_analyzer.conversation_graph.add_node(
                    incident_node,
                    type='incident',
                    content=f"ServiceNow Incident {result['number']} Created",
                    parent="ServiceNow"
                )
                
                # Add edge from ServiceNow parent to incident node
                conversation_workflow_analyzer.conversation_graph.add_edge("ServiceNow", incident_node)
                
                # Find the last user query node (which should be the IT query)
                user_query_nodes = [n for n, d in conversation_workflow_analyzer.conversation_graph.nodes(data=True)
                                if d.get('type') == 'user_query']
                if user_query_nodes:
                    last_query_node = user_query_nodes[-1]
                    # Add edge from user query to incident node
                    conversation_workflow_analyzer.conversation_graph.add_edge(last_query_node, incident_node)
                
                response_text = f"Incident created in ServiceNow! Incident Number: {result['number']}"
                
                # Add conversation turn
                conversation_workflow_analyzer.add_conversation_turn(
                    user_message=user_message,
                    bot_response=response_text,
                    department='IT',
                    create_incident=True
                )
                
                return {
                    'text': response_text,
                    'incidentCreationMode': False,
                    'previewMode': False
                }
   
    
    if intent_result['intent'] == 'greeting':
        if access_token:
            user_data = fetch_user_data()
            if 'error' not in user_data:
                current_hour = datetime.now().hour
                
                if 5 <= current_hour < 12:
                    time_greeting = "Good morning"
                elif 12 <= current_hour < 17:
                    time_greeting = "Good afternoon"
                else:
                    time_greeting = "Good evening"
                
                response = {
                    'text': f"{time_greeting} {user_data['displayName']}! How can I assist you today?",
                    'incidentCreationMode': False,
                    'previewMode': False,
                    'retryMode': False
                }
                return language_handler.translate_response(response, detected_lang)
 
    intent_result = multi_intent_classifier.detect_intent(user_message)
    intent = intent_result.get('predicted_intent', '')
    
    if intent_result['intent'] == 'get_incident':
        if intent_result.get('incident_id'):
            result = get_servicenow_incident(intent_result['incident_id'])
            if 'error' in result:
                response = {
                    'text': f"Error retrieving incident: {result['error']}",
                    'incidentCreationMode': False,
                    'previewMode': False,
                    'retryMode': False
                }
                return language_handler.translate_response(response, detected_lang)
            response = {
                'text': f"Incident Number: {result['number']}\nDescription: {result['short_description']}",
                'incidentCreationMode': False,
                'previewMode': False,
                'retryMode': False
            }
            return language_handler.translate_response(response, detected_lang)
        else:
            response = {
                'text': 'Please provide a specific incident ID',
                'incidentCreationMode': False,
                'previewMode': False,
                'retryMode': False
            }
            return language_handler.translate_response(response, detected_lang)
    
    elif intent_result['intent'] == 'incident_status':
        if intent_result.get('incident_id'):
            result = get_servicenow_incident(intent_result['incident_id'])
            if 'error' in result:
                return {
                    'text': f"Error checking incident status: {result['error']}",
                    'incidentCreationMode': False,
                    'previewMode': False,
                    'retryMode': False
                }
            return {
                'text': f"Incident Status Details:\nIncident Number: {result['number']}\nStatus: {result['state']}",
                'incidentCreationMode': False,
                'previewMode': False,
                'retryMode': False
            }
        else:
            return {
                'text': "Please provide an incident number to check the status.",
                'incidentCreationMode': False,
                'previewMode': False,
                'retryMode': False
            }
 
    if not session_handler.is_session_active():
        return jsonify({
            'text': 'Session expired due to inactivity.',
            'session_expired': True
        })
    response = {
        'text': "I'm not sure how to help. Please try rephrasing your query.",
        'incidentCreationMode': False,
        'previewMode': False
    }
    return language_handler.translate_response(response, detected_lang)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return make_response(jsonify({'message': 'Token is missing'}), 401)
        
        # Verify the token
        user_id, display_name = verify_token(token)
        if not user_id or not display_name:
            response = make_response(jsonify({'message': 'Invalid token'}), 401)
            clear_auth_cookie(response)
            return response
        
        # Add both user_id and display_name to request context
        request.user_id = user_id
        request.display_name = display_name
        return f(*args, **kwargs)
    return decorated

@app.route('/protected')
@token_required
def protected():
    return make_response(jsonify({
        'message': f'Hello {request.display_name}, this is a protected route'
    }))

@app.route('/logout')
def logout():
    token = request.cookies.get(COOKIE_NAME)
    if token:
        # Unpack user_id from verify_token 
        # Note the use of * to handle multiple return values
        user_id, *_ = verify_token(token)
        
        if user_id:
            # Remove the user's session
            user_session_manager.remove_session(user_id)
            
            # Optional: Logout from Keycloak
            try:
                keycloak_openid.logout(token)
            except Exception as e:
                print(f"Keycloak logout error: {str(e)}")
    
    response = make_response(redirect('/'))
    clear_auth_cookie(response)
    return response

@app.errorhandler(401)
def unauthorized_error(error):
    response = make_response(jsonify({
        'error': 'Authentication required',
        'redirect': '/'
    }), 401)
    # Clear invalid token
    clear_auth_cookie(response)
    return response

@app.errorhandler(500)
def internal_error(error):
    return make_response(jsonify({
        'error': 'Internal server error',
        'message': str(error)
    }), 500)

if __name__ == '__main__':
    index_existing_pdfs()
    app.run(debug=True, port=5000)
