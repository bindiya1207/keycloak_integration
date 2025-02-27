KEYCLOAK_SERVER_URL = "http://localhost:8080/auth/"
KEYCLOAK_REALM_NAME = "myrealm"
KEYCLOAK_CLIENT_ID = "client123"
KEYCLOAK_CLIENT_SECRET = "AoCHYunOp7V3D0uVgZHlaIxfcLDItTnZ"
REDIRECT_URI = "http://localhost:5000/callback"


# Initialize Keycloak OpenID Connect client
keycloak_openid = KeycloakOpenID(
    server_url=KEYCLOAK_SERVER_URL,
    client_id=KEYCLOAK_CLIENT_ID,
    realm_name=KEYCLOAK_REALM_NAME,
    client_secret_key=KEYCLOAK_CLIENT_SECRET
)



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
    """
    Generate Keycloak authentication URL
    """
    try:
        # Generate Keycloak authorization URL
        auth_url = keycloak_openid.auth_url(
            redirect_uri=REDIRECT_URI,
            scope="openid profile email"
        )
        return jsonify({
            'status': 'success',
            'auth_url': auth_url
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to generate authentication URL: {str(e)}'
        }), 500
@app.route('/callback')
def callback():
    """
    Handle Keycloak callback and token exchange
    """
    try:
        # Get authorization code from request
        code = request.args.get('code')
        
        # Exchange code for tokens
        tokens = keycloak_openid.exchange_authorization_code(
            code=code,
            redirect_uri=REDIRECT_URI
        )
        
        # Decode ID token to get user information
        id_token = tokens.get('id_token')
        access_token = tokens.get('access_token')
        
        # Verify the token
        keycloak_openid.decode_token(id_token)
        
        # Fetch user information from Keycloak
        userinfo = keycloak_openid.userinfo(access_token)
        
        # Extract user details
        user_id = userinfo.get('sub')  # Unique user identifier
        display_name = userinfo.get('name', userinfo.get('preferred_username', 'User'))
        
        # Create session for the user
        user_session_manager.create_session(user_id, access_token, display_name)
        
        # Create JWT token with user_id and display_name
        token = create_token(user_id, display_name)
        
        # Prepare response
        response = make_response(render_template('index.html'))
        set_auth_cookie(response, token)
        return response
    
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        return make_response('Authentication failed', 401)

# Modify the initialize route to use Keycloak user information
@app.route('/initialize', methods=['GET'])
def initialize():
    """Initialize chat for authenticated users"""
    user_id, display_name = validate_token()
    
    if not user_id or not display_name:
        return make_response(jsonify({
            'error': 'Not authenticated',
            'redirect': '/'
        }), 401)
    
    session_data = user_session_manager.get_session(user_id)
    if not session_data:
        return make_response(jsonify({
            'error': 'Session not found'
        }), 401)
    
    # Use display name from session
    user_name = session_data['display_name']
    token = create_token(user_id, user_name)
    
    # Time-based greeting logic (keeping existing code)
    current_hour = datetime.now().hour
    time_greeting = (
        "Good morning" if 5 <= current_hour < 12
        else "Good afternoon" if 12 <= current_hour < 17
        else "Good evening"
    )
    
    collection = get_mongodb_connection()
    prompts = list(collection.find({}, {'_id': 0}))
    
    bot_response = (
        f"{time_greeting} {user_name}! I am NetBot. "
        "Please select from the options below or type your query:"
    )
    
    response_data = {
        'text': bot_response,
        'prompts': prompts
    }
    
    response = make_response(jsonify(response_data))
    set_auth_cookie(response, token)
    return response


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
