import sys
from pathlib import Path
import json
import os
import webbrowser
import urllib.parse

# --- Flow Launcher specific setup for Lib folder ---
plugindir = Path.absolute(Path(__file__).parent)
paths = (".", "lib", "plugin") # not sure if Lib or lib
sys.path = [str(plugindir / p) for p in paths] + sys.path
# --- End Flow Launcher setup ---

from flowlauncher import FlowLauncher
from ticktick.oauth2 import TickTickOAuth
from ticktick.api import TickTickAPI

# Configuration file for storing dynamic tokens (not static settings)
CONFIG_FILE = Path.absolute(Path(__file__).parent) / "config.json"

class TickTickPlugin(FlowLauncher):

    def __init__(self):
        super().__init__()
        self._load_config() # Loads config.json (for tokens)

        # Get Client ID, Client Secret, and Redirect URI from Flow Launcher's settings
        # These are now defined in plugin.json and accessed via self.settings
        self.client_id = self.settings.get("client_id")
        self.client_secret = self.settings.get("client_secret")
        self.redirect_uri = self.settings.get("redirect_uri", "http://localhost:8080") # Provide a default if not set

        self.ticktick_api = None
        self.oauth_client = None

        if self.client_id and self.client_secret and self.redirect_uri:
            self.oauth_client = TickTickOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri
            )
            # Try to initialize TickTick API with stored tokens
            if self.config.get("access_token") and self.config.get("refresh_token"):
                try:
                    self.ticktick_api = TickTickAPI(
                        client_id=self.client_id,
                        client_secret=self.client_secret,
                        access_token=self.config["access_token"],
                        refresh_token=self.config["refresh_token"],
                        oauth_client=self.oauth_client
                    )
                except Exception as e:
                    self.flow_launcher_api.show_msg(
                        "TickTick Login Failed",
                        f"Stored tokens invalid. Please re-authenticate. Error: {e}",
                        "Images/logo.png"
                    )
                    print(f"DEBUG: Token initialization failed: {e}")
                    self.ticktick_api = None
                    self.config.pop("access_token", None)
                    self.config.pop("refresh_token", None)
                    self._save_config()
        else:
            # If settings are missing, prompt the user to configure them in Flow Launcher
            self.flow_launcher_api.show_msg(
                "TickTick Plugin Configuration Needed",
                "Please go to Flow Launcher settings -> Plugins -> TickTick to enter your credentials.",
                "Images/logo.png"
            )

    def _load_config(self):
        """Loads authentication tokens from config.json."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
            except json.JSONDecodeError:
                self.config = {} # Corrupted config, start fresh
                self.flow_launcher_api.show_msg("Config Error", "config.json was corrupted. Resetting.", "Images/logo.png")
        else:
            self.config = {}

    def _save_config(self):
        """Saves authentication tokens to config.json."""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def query(self, query):
        results = []
        lower_query = query.lower().strip()

        # Check if basic settings (Client ID, Secret, Redirect URI) are configured
        if not (self.client_id and self.client_secret and self.redirect_uri):
            results.append({
                "Title": "TickTick Plugin Not Configured",
                "SubTitle": "Go to Flow Launcher settings to enter Client ID and Secret.",
                "IcoPath": "Images/logo.png",
                "JsonRPCAction": {
                    "method": "open_settings_json", # A custom method to open plugin.json or guide user
                    "parameters": []
                }
            })
            return results

        # Check authentication status (for tokens)
        if not self.ticktick_api:
            if self.config.get("auth_pending_url"):
                results.append({
                    "Title": "Paste TickTick Redirect URL",
                    "SubTitle": "After authenticating in browser, copy the URL and type 'tt auth paste <URL>'",
                    "IcoPath": "Images/logo.png"
                })
            else:
                results.append({
                    "Title": "Authenticate TickTick Plugin",
                    "SubTitle": "Click to open TickTick login page in your browser.",
                    "IcoPath": "Images/logo.png",
                    "JsonRPCAction": {
                        "method": "authenticate_ticktick",
                        "parameters": []
                    }
                })
            # Handle the 'tt auth paste' command even if not fully authenticated yet
            if lower_query.startswith("auth paste "):
                pasted_url = query[len("auth paste "):].strip()
                if pasted_url:
                    results.append({
                        "Title": "Complete Authentication",
                        "SubTitle": f"Using URL: {pasted_url[:50]}...",
                        "IcoPath": "Images/logo.png",
                        "JsonRPCAction": {
                            "method": "complete_auth",
                            "parameters": [pasted_url]
                        }
                    })
            return results

        # --- If authenticated, proceed with main commands ---
        if lower_query.startswith("add "):
            task_details = query[4:].strip()
            if task_details:
                results.append({
                    "Title": f"Add Task: {task_details}",
                    "SubTitle": "Add a new task to TickTick. Use 'due <date> #<tag>' for details.",
                    "IcoPath": "Images/logo.png",
                    "JsonRPCAction": {
                        "method": "add_task",
                        "parameters": [task_details]
                    }
                })
            else:
                results.append({
                    "Title": "Add Task",
                    "SubTitle": "Type 'tt add <task name>'",
                    "IcoPath": "Images/logo.png"
                })
        elif lower_query == "today":
            results.append({
                "Title": "View Today's Tasks",
                "SubTitle": "Open TickTick to the 'Today' view.",
                "IcoPath": "Images/logo.png",
                "JsonRPCAction": {
                    "method": "open_ticktick_view",
                    "parameters": ["today"]
                }
            })
        elif lower_query == "upcoming":
            results.append({
                "Title": "View Upcoming Tasks",
                "SubTitle": "Open TickTick to the 'Upcoming' view.",
                "IcoPath": "Images/logo.png",
                "JsonRPCAction": {
                    "method": "open_ticktick_view",
                    "parameters": ["upcoming"]
                }
            })
        else:
            results.append({
                "Title": "TickTick Plugin",
                "SubTitle": "Type 'tt add <task>', 'tt today', or 'tt upcoming'",
                "IcoPath": "Images/logo.png"
            })

        return results

    # No longer needed as credentials are set via settings UI
    # def show_credential_setup_instructions(self):
    #     pass

    def authenticate_ticktick(self):
        if not self.oauth_client:
            self.flow_launcher_api.show_msg("Error", "Client ID or Secret not set up in plugin settings.", "Images/logo.png")
            return

        auth_url = self.oauth_client.get_auth_url(state="flow_launcher_ticktick")
        webbrowser.open(auth_url)
        self.config["auth_pending_url"] = auth_url
        self._save_config()
        self.flow_launcher_api.show_msg(
            "Authentication Initiated",
            f"Please complete authentication in your browser. After redirect, copy the URL and use 'tt auth paste <URL>'.",
            "Images/logo.png"
        )

    def complete_auth(self, redirect_url):
        if not self.oauth_client:
            self.flow_launcher_api.show_msg("Error", "Client ID or Secret not set up in plugin settings.", "Images/logo.png")
            return

        try:
            parsed_url = urllib.parse.urlparse(redirect_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            auth_code = query_params.get("code")

            if not auth_code:
                raise ValueError("No 'code' parameter found in the provided URL.")
            auth_code = auth_code[0] # auth_code is a list, get the first element

            self.flow_launcher_api.show_msg("Exchanging Code...", "Please wait.", "Images/logo.png")

            token_response = self.oauth_client.get_access_token(auth_code)

            self.config["access_token"] = token_response["access_token"]
            self.config["refresh_token"] = token_response["refresh_token"]

            self.config.pop("auth_pending_url", None) # Clean up pending flag
            self._save_config()

            # Re-initialize TickTickAPI with new tokens
            self.ticktick_api = TickTickAPI(
                client_id=self.client_id,
                client_secret=self.client_secret,
                access_token=self.config["access_token"],
                refresh_token=self.config["refresh_token"],
                oauth_client=self.oauth_client
            )
            self.flow_launcher_api.show_msg("TickTick Authentication Successful!", "You are now logged in.", "Images/logo.png")

        except Exception as e:
            self.flow_launcher_api.show_msg("Authentication Failed", f"Error: {e}. Please try again.", "Images/logo.png")
            print(f"DEBUG: Authentication failed: {e}")
            self.config.pop("access_token", None) # Clear invalid tokens
            self.config.pop("refresh_token", None)
            self.config.pop("auth_pending_url", None)
            self._save_config()

    def add_task(self, task_details_string):
        # ... (same as before)
        if not self.ticktick_api:
            self.flow_launcher_api.show_msg("Error", "Not authenticated with TickTick.", "Images/logo.png")
            return

        try:
            task_title = task_details_string
            due_date_str = None
            tag = None

            if '#' in task_title:
                parts = task_title.rsplit('#', 1)
                task_title = parts[0].strip()
                tag = parts[1].strip()

            if ' due ' in task_title.lower():
                parts = task_title.lower().split(' due ', 1)
                task_title = task_title[:len(parts[0])].strip()
                due_date_str = parts[1].strip()

            task_data = {"title": task_title}
            if due_date_str:
                task_data["dueDate"] = due_date_str

            if tag:
                # Add tag to content as a fallback or if we don't map to a specific list
                # For more robust tag support, you might need to query TickTick for existing projects/tags
                # and map them, or use a specific field if the API allows direct tag assignment.
                # As per ticktick-py docs, content can be used for extra info.
                task_data["content"] = (task_data.get("content", "") + f" #{tag}").strip()

            created_task = self.ticktick_api.create_task(task_data)

            if created_task:
                self.flow_launcher_api.show_msg("Task Added!", created_task.get("title", "Unknown Task"), "Images/logo.png")
            else:
                self.flow_launcher_api.show_msg("Failed to Add Task", "TickTick API did not return a created task.", "Images/logo.png")

        except Exception as e:
            self.flow_launcher_api.show_msg("Error Adding Task", f"Details: {e}", "Images/logo.png")
            print(f"DEBUG: Error adding task: {e}")


    def open_ticktick_view(self, view_name):
        # ... (same as before)
        target_url = "ticktick://"

        if view_name == "today":
            target_url = "ticktick://view/today"
        elif view_name == "upcoming":
            target_url = "ticktick://view/upcoming"

        try:
            webbrowser.open(target_url)
            self.flow_launcher_api.show_msg("Opening TickTick", f"Opening to {view_name} view.", "Images/logo.png")
        except Exception as e:
            self.flow_launcher_api.show_msg("Error", f"Could not open TickTick: {e}", "Images/logo.png")
            print(f"DEBUG: Error opening TickTick: {e}")

    # Helper method to guide the user to plugin settings
    def open_settings_json(self):
        # This isn't perfect, as it won't open Flow Launcher settings directly to your plugin.
        # It's more of a hint. Flow Launcher doesn't expose a direct method to open its settings UI to a specific plugin.
        self.flow_launcher_api.show_msg(
            "Go to Flow Launcher Settings",
            "Open Flow Launcher settings, navigate to 'Plugins', find 'TickTick', and enter your credentials.",
            "Images/logo.png"
        )
        # You could try to launch the main settings if you know the executable path,
        # but that's generally not recommended for plugin-specific settings.


if __name__ == "__main__":
    TickTickPlugin()