import sys
from pathlib import Path
import json
import os
import webbrowser # For opening URLs or the TickTick app

# --- Flow Launcher specific setup for Lib folder ---
plugindir = Path.absolute(Path(__file__).parent)
paths = (".", "Lib", "plugin") # 'plugin' is sometimes used for sub-modules, though 'Lib' is primary for external
sys.path = [str(plugindir / p) for p in paths] + sys.path
# --- End Flow Launcher setup ---

from flowlauncher import FlowLauncher # This will be imported from our Lib folder


# We will need a way to store TickTick API credentials and tokens.
# A simple JSON file within the plugin directory is a reasonable approach for
# non-sensitive user-specific data like tokens.
CONFIG_FILE = Path.absolute(Path(__file__).parent) / "config.json"

class TickTickPlugin(FlowLauncher):

    def __init__(self):
        super().__init__()
        self.client_id = os.environ.get("TICKTICK_CLIENT_ID")
        self.client_secret = os.environ.get("TICKTICK_CLIENT_SECRET")
        self.ticktick_api = None # This will hold our TickTickAPI client

        if not self.client_id or not self.client_secret:
            # We'll need a way to prompt the user to set these up in Flow Launcher
            # For now, we'll indicate missing credentials.
            pass # We'll handle this more gracefully later

        self._load_config()


    def _load_config(self):
        """Loads configuration from config.json."""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def _save_config(self):
        """Saves configuration to config.json."""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def query(self, query):
        """
        Main query method for Flow Launcher.
        Parses user input and returns results.
        """
        results = []
        lower_query = query.lower().strip()

        # Initial check for credentials
        if not self.client_id or not self.client_secret:
            results.append({
                "Title": "TickTick API Credentials Missing",
                "SubTitle": "Please set TICKTICK_CLIENT_ID and TICKTICK_CLIENT_SECRET environment variables.",
                "IcoPath": "Images/app.png",
                "JsonRPCAction": {
                    "method": "open_url",
                    "parameters": ["https://developer.ticktick.com/api#/openapi"] # Link to developer docs
                }
            })
            return results

        # Placeholder for authentication check
        # We will implement the actual TickTickAPI client and authentication
        # in a later step. For now, let's just make sure the flow works.
        if not self.config.get("access_token"):
             results.append({
                "Title": "TickTick Plugin Not Authenticated",
                "SubTitle": "Click to authenticate with TickTick.",
                "IcoPath": "Images/app.png",
                "JsonRPCAction": {
                    "method": "authenticate_ticktick",
                    "parameters": [] # This method will generate the auth URL
                }
            })
             return results

        # TODO: Implement parsing for 'tt add', 'tt today', 'tt upcoming'
        if lower_query.startswith("add "):
            results.append({
                "Title": f"Add Task: {query[4:]}",
                "SubTitle": "Add a new task to TickTick.",
                "IcoPath": "Images/app.png",
                "JsonRPCAction": {
                    "method": "add_task",
                    "parameters": [query[4:]] # Pass the task name
                }
            })
        elif lower_query == "today":
            results.append({
                "Title": "View Today's Tasks",
                "SubTitle": "Open TickTick to the 'Today' view.",
                "IcoPath": "Images/app.png",
                "JsonRPCAction": {
                    "method": "open_ticktick_view",
                    "parameters": ["today"]
                }
            })
        elif lower_query == "upcoming":
            results.append({
                "Title": "View Upcoming Tasks",
                "SubTitle": "Open TickTick to the 'Upcoming' view.",
                "IcoPath": "Images/app.png",
                "JsonRPCAction": {
                    "method": "open_ticktick_view",
                    "parameters": ["upcoming"]
                }
            })
        else:
            results.append({
                "Title": "TickTick Plugin",
                "SubTitle": "Type 'tt add <task>', 'tt today', or 'tt upcoming'",
                "IcoPath": "Images/app.png"
            })


        return results

    def authenticate_ticktick(self):
        """Initiates the OAuth2 authentication flow for TickTick."""
        # This will be replaced by the actual ticktick-py auth process
        auth_url = "https://developer.ticktick.com/api#/openapi" # Placeholder
        webbrowser.open(auth_url)
        # In a real scenario, we'd then listen for the redirect or instruct the user
        # to paste the code. This is a bit more complex for Flow Launcher,
        # so we'll simplify this or use ticktick-py's built-in auth helper.
        self.config["auth_pending"] = True
        self._save_config()
        self.flow_launcher_api.show_msg("Authentication Initiated", "Please complete authentication in your browser.")
        # For simplicity, we might ask the user to manually paste the auth code
        # back into Flow Launcher if the ticktick-py helper doesn't fit neatly.

    def add_task(self, task_details):
        """Adds a task to TickTick."""
        self.flow_launcher_api.show_msg("Adding Task", f"Attempting to add: {task_details}")
        # TODO: Implement actual API call using self.ticktick_api
        # For now, just a placeholder.
        print(f"DEBUG: Adding task: {task_details}") # For console debugging

    def open_ticktick_view(self, view_name):
        """Opens TickTick to a specific view."""
        self.flow_launcher_api.show_msg("Opening TickTick", f"Opening to {view_name} view.")
        # This will attempt to launch the TickTick application.
        # We'll refine this to open specific views if possible.
        try:
            # Common paths for TickTick desktop app, or just launch the executable name
            # For Windows: C:\Program Files\TickTick\TickTick.exe
            # This is a general approach, users might have it installed elsewhere.
            # A more robust solution might use os.startfile on Windows or specific platform tools.
            webbrowser.open("ticktick://") # Try URL scheme first if it exists for views
            # If the URL scheme doesn't work for specific views, we'll fall back to just launching the app:
            # os.startfile("TickTick.exe") # This requires TickTick.exe to be in PATH or full path.
        except Exception as e:
            self.flow_launcher_api.show_msg("Error", f"Could not open TickTick: {e}")
            print(f"DEBUG: Error opening TickTick: {e}")


if __name__ == "__main__":
    TickTickPlugin()