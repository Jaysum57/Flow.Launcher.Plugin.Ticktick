import os
import requests
import secrets
import webbrowser
import threading
import json
import time
from flowlauncher import FlowLauncher
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, List, Dict, Any, Optional


# --- Configuration ---
# IMPORTANT: Replace these with your actual Client ID and Client Secret from TickTick Developer Center.
# For a production application, you would load these securely from environment variables or a configuration file.
CLIENT_ID = "iOfsHA2rZer3uoJd81"  # Your TickTick Application Client ID
CLIENT_SECRET = "l_Q5I_O!i5E03Q))YzNspJ01qOartC)f" # Your TickTick Application Client Secret

# The redirect URI MUST match exactly what you configured in the TickTick Developer Center.
# For local development, this is often a localhost address and port.
REDIRECT_URI = "http://localhost:8080/callback"
# The port our local web server will listen on for the OAuth callback
LOCAL_SERVER_PORT = 8080

# TickTick OAuth Endpoints
AUTHORIZATION_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"

# TickTick Open API Base URL (Changed to /open/v1 to match provided API Reference)
TICKTICK_OPEN_API_BASE_URL = "https://api.ticktick.com/open/v1"

# --- Global variables for OAuth flow and access token ---
# These are global so they can be accessed by the HTTP server handler and the API client functions.
_auth_code: Optional[str] = None
_received_state: Optional[str] = None
_http_server_thread: Optional[threading.Thread] = None
ACCESS_TOKEN: Optional[str] = None
REFRESH_TOKEN: Optional[str] = None # Store refresh token if provided

# --- Local HTTP Server for OAuth Callback ---
class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """
    A simple HTTP server handler to capture the OAuth redirect.
    It waits for a single request to the REDIRECT_URI and extracts the 'code' and 'state'.
    """
    def do_GET(self):
        global _auth_code, _received_state

        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        # Check if the path matches our expected redirect URI path
        if parsed_url.path == urlparse(REDIRECT_URI).path:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Extract the 'code' and 'state' parameters
            if 'code' in query_params and 'state' in query_params:
                _auth_code = query_params['code'][0]
                _received_state = query_params['state'][0]
                response_message = "<p>Authorization successful! You can close this tab and return to the script.</p>"
                self.wfile.write(response_message.encode('utf-8'))
                print("\nAuthorization code received. You can close this browser tab.")
                # Important: Shut down the server thread after receiving the code to allow the script to proceed.
                threading.Thread(target=self.server.shutdown).start()
            else:
                response_message = "<p>Authorization failed or missing parameters. Please check the script's console for errors.</p>"
                self.wfile.write(response_message.encode('utf-8'))
                print("\nError: Authorization code or state missing from callback URL.")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def _run_local_server():
    """Starts a local HTTP server to listen for the OAuth callback.
    This function is intended to be run in a separate thread."""
    server_address = ('', LOCAL_SERVER_PORT)
    httpd = HTTPServer(server_address, OAuthCallbackHandler)
    print(f"\nListening for OAuth callback on {REDIRECT_URI}...")
    httpd.serve_forever() # Blocks until httpd.shutdown() is called

def get_ticktick_access_token() -> Optional[str]:
    """
    Manages the OAuth 2.0 flow to obtain and return an access token.
    If an access token is already available globally, it returns that.
    Otherwise, it initiates the authorization code flow.
    """
    global ACCESS_TOKEN, REFRESH_TOKEN, _auth_code, _received_state, _http_server_thread

    # If we already have an access token, return it
    if ACCESS_TOKEN:
        print("Using existing access token.")
        return ACCESS_TOKEN

    print("\n--- Initiating TickTick OAuth Flow ---")
    
    # 1. Generate a cryptographically secure random 'state' parameter
    # This helps prevent CSRF attacks. It must be unique for each authorization request.
    local_state = secrets.token_urlsafe(32)
    print(f"Generated state for authorization: {local_state}")

    # 2. Construct the authorization URL
    auth_params = {
        "client_id": CLIENT_ID,
        "scope": "tasks:read tasks:write", # Requesting read and write access to tasks
        "state": local_state,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code"
    }
    authorization_url = f"{AUTHORIZATION_URL}?{urlencode(auth_params)}"

    print("\nStep 1: Authorize your application")
    print("Please open the following URL in your web browser to authorize your TickTick account:")
    print(authorization_url)
    webbrowser.open(authorization_url)

    # 3. Start a local server to listen for the redirect callback
    _http_server_thread = threading.Thread(target=_run_local_server)
    _http_server_thread.daemon = True # Allow the main program to exit even if this thread is running
    _http_server_thread.start()

    # Wait for the authorization code to be received by the local server
    timeout_start = time.time()
    TIMEOUT = 120 # 2 minutes timeout for user authorization
    while _auth_code is None and (time.time() - timeout_start) < TIMEOUT:
        time.sleep(1) # Wait for 1 second before checking again

    if _auth_code is None:
        print("\nError: Timed out waiting for authorization code from browser. Please try again.")
        return None

    # 4. Validate the 'state' parameter received in the callback
    if local_state != _received_state:
        print(f"\nSecurity Warning: State mismatch! Expected '{local_state}', got '{_received_state}'. Aborting authorization.")
        return None
    print("\nState parameter validated successfully.")

    print("\nStep 2: Exchange Authorization Code for Access Token")
    # 5. Exchange the authorization code for an access token
    # As per TickTick documentation, client_id and client_secret are sent via Basic Auth header.
    token_request_data = {
        "code": _auth_code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": "tasks:read tasks:write" # Include scope in token exchange, though usually optional here
    }
    try:
        response = requests.post(
            TOKEN_URL,
            data=token_request_data,
            auth=(CLIENT_ID, CLIENT_SECRET) # Basic Authentication for client credentials
        )
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        token_data = response.json()

        ACCESS_TOKEN = token_data.get("access_token")
        REFRESH_TOKEN = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        if ACCESS_TOKEN:
            print("Access Token obtained successfully!")
            print(f"Access Token (first 10 chars): {ACCESS_TOKEN[:10]}...")
            if REFRESH_TOKEN:
                print(f"Refresh Token (first 10 chars): {REFRESH_TOKEN[:10]}...")
            else:
                print("Note: Refresh Token was not provided in the response (this is common for certain OAuth flows/clients).")
            print(f"Access token expires in {expires_in} seconds.")
            return ACCESS_TOKEN
        else:
            print(f"Error: Did not receive an access token in response. Full response: {token_data}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error exchanging code for tokens: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        return None

def refresh_ticktick_access_token() -> Optional[str]:
    """
    Uses the refresh token to get a new access token.
    Updates the global ACCESS_TOKEN and REFRESH_TOKEN.
    """
    global ACCESS_TOKEN, REFRESH_TOKEN

    if not REFRESH_TOKEN:
        print("\nCannot refresh token: No refresh token available.")
        return None

    print("\n--- Refreshing Access Token ---")
    refresh_params = {
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    try:
        # Use 'auth' parameter for Basic Authentication for refresh token as well
        response = requests.post(
            TOKEN_URL,
            data=refresh_params,
            auth=(CLIENT_ID, CLIENT_SECRET)
        )
        response.raise_for_status()
        token_data = response.json()

        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token", REFRESH_TOKEN) # Refresh token might be rotated, use current if not
        expires_in = token_data.get("expires_in")

        if new_access_token:
            ACCESS_TOKEN = new_access_token
            REFRESH_TOKEN = new_refresh_token
            print("Access token refreshed successfully!")
            print(f"New Access Token (first 10 chars): {ACCESS_TOKEN[:10]}...")
            if REFRESH_TOKEN:
                print(f"New Refresh Token (first 10 chars): {REFRESH_TOKEN[:10]}...")
            else:
                print("Note: New Refresh Token was not provided in the refresh response (this is common).")
            print(f"New access token expires in {expires_in} seconds.")
            return ACCESS_TOKEN
        else:
            print(f"Error: Did not receive new access token during refresh. Response: {token_data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error refreshing token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        return None

def _call_ticktick_api(path: str, http_method: Callable, body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Internal helper to make authenticated calls to the TickTick Open API.
    Handles access token retrieval and basic error handling.
    """
    access_token = get_ticktick_access_token()
    if not access_token:
        print("API call failed: No access token available.")
        return None

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json' # Most TickTick API calls expect JSON
    }

    kwargs = {'headers': headers}
    if body:
        kwargs['json'] = body # Use 'json' for requests.post/put when sending JSON body

    full_url = f'{TICKTICK_OPEN_API_BASE_URL}/{path}'
    print(f"\nCalling API: {http_method.__name__.upper()} {full_url}")

    try:
        response = http_method(full_url, **kwargs)
        response.raise_for_status() # Raises HTTPError for 4xx/5xx responses
        # TickTick API sometimes returns 204 No Content for successful operations (e.g., complete_task)
        if response.status_code == 204:
            print("API call successful (No Content).")
            return {"status": "success", "message": "No content in response"}
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API call to {path} failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
        return None

# --- Public API Functions (matching your friend's structure and new API reference) ---

def get_user_projects() -> Optional[List[Dict[str, Any]]]:
    """
    Retrieves all projects for the authenticated user.
    GET /open/v1/project
    """
    print("\n--- Getting User Projects ---")
    return _call_ticktick_api('project', requests.get)

def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves details for a specific project.
    GET /open/v1/project/{projectId}
    """
    print(f"\n--- Getting Project with ID: {project_id} ---")
    return _call_ticktick_api(f'project/{project_id}', requests.get)

def get_project_with_data(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves details and associated data (e.g., tasks) for a specific project.
    GET /open/v1/project/{projectId}/data
    """
    print(f"\n--- Getting Project Data for ID: {project_id} ---")
    return _call_ticktick_api(f'project/{project_id}/data', requests.get)

def get_task(project_id: str, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a specific task by project ID and task ID.
    GET /open/v1/project/{projectId}/task/{taskId}
    """
    print(f"\n--- Getting Task ID: {task_id} from Project ID: {project_id} ---")
    return _call_ticktick_api(f'project/{project_id}/task/{task_id}', requests.get)

def complete_task(project_id: str, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Marks a specific task as complete.
    POST /open/v1/project/{projectId}/task/{taskId}/complete
    """
    print(f"\n--- Completing Task ID: {task_id} in Project ID: {project_id} ---")
    # Assuming complete endpoint doesn't require a specific JSON body for simple completion
    return _call_ticktick_api(f'project/{project_id}/task/{task_id}/complete', requests.post)

# --- Example Usage (when this script is run directly) ---
if __name__ == "__main__":
    # Ensure client_id and client_secret are set
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        print("CRITICAL ERROR: Please replace 'YOUR_CLIENT_ID' and 'YOUR_CLIENT_SECRET' with your actual credentials from the TickTick Developer Center.")
        print("For a real application, consider using environment variables (e.g., os.environ.get('TICKTICK_CLIENT_ID')) to keep credentials out of your code.")
        exit(1)

    print("Starting TickTick API Client Demonstration...")

    # The access token will be obtained (or reused if available) when the first API call is made.
    # We can explicitly call it, or let _call_ticktick_api handle it.
    # For demonstration, let's explicitly get it first.
    current_access_token = get_ticktick_access_token()

    if current_access_token:
        print("\n--- Access Token Available. Proceeding with API Demos ---")

        # Example 1: Get all user projects
        projects = get_user_projects()
        if projects:
            print("\nRetrieved Projects:")
            for p in projects:
                print(f"- {p.get('name')} (ID: {p.get('id')})")
            
            # Example 2: Get details of the first project found (if any)
            if projects:
                first_project_id = projects[0].get('id')
                if first_project_id:
                    print(f"\n--- Getting details for first project ({first_project_id}) ---")
                    project_details = get_project(first_project_id)
                    if project_details:
                        print("Project Details (partial):")
                        print(f"  Title: {project_details.get('name')}")
                        print(f"  Color: {project_details.get('color')}")

                    # Example 3: Get project with data (might include tasks directly)
                    print(f"\n--- Getting data for first project ({first_project_id}) ---")
                    project_data = get_project_with_data(first_project_id)
                    if project_data:
                        print("Project Data (partial, including first 2 tasks if available):")
                        print(f"  Title: {project_data.get('name')}")
                        tasks_in_project = project_data.get('tasks', [])
                        if tasks_in_project:
                            print("  Tasks:")
                            for task in tasks_in_project[:2]: # Show first 2 tasks
                                print(f"    - {task.get('title')} (ID: {task.get('id')})")
                        else:
                            print("  No tasks found in this project.")
                            
                        # Example 4: Get a specific task (from the first project, first task)
                        if tasks_in_project:
                            first_task_id = tasks_in_project[0].get('id')
                            if first_task_id:
                                print(f"\n--- Getting specific task ({first_task_id}) from project ({first_project_id}) ---")
                                specific_task = get_task(first_project_id, first_task_id)
                                if specific_task:
                                    print("Specific Task Details:")
                                    print(f"  Title: {specific_task.get('title')}")
                                    print(f"  Content: {specific_task.get('content')}")
                                    print(f"  Due Date: {specific_task.get('dueDate')}")
                                    print(f"  Status: {specific_task.get('status')} (0=uncompleted, 1=completed)")

                                    # Example 5: Complete the task (UNCOMMENT WITH CAUTION - This will modify your TickTick data!)
                                    # print(f"\n--- Completing Task: {specific_task.get('title')} ---")
                                    # completion_status = complete_task(first_project_id, first_task_id)
                                    # if completion_status:
                                    #     print(f"Task completion initiated. Status: {completion_status}")
                                    # else:
                                    #     print("Task completion failed.")
                                else:
                                    print("Could not retrieve specific task details.")
                            else:
                                print("No task ID found in the first project to demonstrate get_task or complete_task.")
                        else:
                            print("No tasks found in the first project to demonstrate task operations.")
                else:
                    print("First project did not have an ID.")
            else:
                print("No projects retrieved to demonstrate project/task operations.")
        else:
            print("Failed to retrieve user projects.")

        # Optional: Demonstrate token refresh (only if refresh_token was obtained)
        # Note: Access tokens have a long expiry (over 4 months), so refreshing isn't frequently needed.
        # if REFRESH_TOKEN:
        #     print("\n--- Attempting to refresh access token ---")
        #     new_access_token = refresh_ticktick_access_token()
        #     if new_access_token:
        #         print("Successfully refreshed token. New token ready for use.")
        #     else:
        #         print("Failed to refresh token.")
        # else:
        #     print("\nSkipping token refresh demonstration as no refresh token was provided.")

    else:
        print("\nFailed to obtain access token. Cannot proceed with any API calls.")

    print("\nTickTick API Client Demonstration Finished.")


class TickTick(FlowLauncher):
    def __init__(self):
        self.access_token = get_ticktick_access_token()
        if not self.access_token:
            print("Failed to obtain access token.")
            exit(1)

    def query(self, query):
        projects = get_user_projects()
        if not projects:
            return [{
                "Title": "No projects found",
                "SubTitle": "Check if you're logged in properly",
                "IcoPath": "Images/icon.png"
            }]
        return [
            {
                "Title": project.get("name"),
                "SubTitle": f"ID: {project.get('id')}",
                "IcoPath": "Images/icon.png",
                "JsonRPCAction": {
                    "method": "open_project",
                    "parameters": [project.get("id")]
                }
            } for project in projects
        ]

    def open_project(self, project_id):
        webbrowser.open(f"https://ticktick.com/webapp/#p/{project_id}")
