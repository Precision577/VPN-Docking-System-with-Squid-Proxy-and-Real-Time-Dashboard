#!/home/idontloveyou/miniconda/bin/python3.11

import streamlit as st
import pandas as pd
import os
import time
import traceback
import asyncio
import websocket
import threading
from io import StringIO
from pathlib import Path
from streamlit_autorefresh import st_autorefresh

# Set Streamlit to wide mode by default
st.set_page_config(layout="wide")

# Global variable to hold logs for developer mode
log_stream = StringIO()

# Global flag for WebSocket update trigger
ws_update_triggered = False
ws_update_event = threading.Event()



# Function to log messages to both console and the log stream
def log_message(message):
    print(message)
    log_stream.write(f"{message}\n")

# Global event to signal updates from WebSocket
ws_update_event = threading.Event()

def on_message(ws, message):
    log_message(f"[INFO] WebSocket message received: {message}")
    
    # Check if the message indicates a CSV update
    try:
        data = json.loads(message)
        if data.get("update") == "CSV Updated":
            log_message("[INFO] CSV update detected. Triggering rerun.")
            ws_update_event.set()  # Signal that an update is needed
            st.experimental_rerun()  # Trigger rerun when update is detected
        else:
            log_message("[INFO] Message received, but no CSV update detected.")
    except json.JSONDecodeError:
        log_message("[ERROR] Failed to parse WebSocket message as JSON.")




def on_error(ws, error):
    log_message(f"[ERROR] WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    log_message(f"[INFO] WebSocket connection closed: {close_msg}")

def on_open(ws):
    log_message("[INFO] WebSocket connection opened")






# Function to scan for CSV file in the current working directory (CWD)
def find_csv_file():
    for file in os.listdir(os.getcwd()):
        if file.endswith(".csv"):
            return Path(file)
    return None

# Load CSV file data into a pandas DataFrame
def load_csv_data(csv_file):
    try:
        # Log the attempt to load the file
        log_message(f"[INFO] Attempting to load CSV file: {csv_file}")
        
        # Use pandas for loading and processing the CSV file
        df = pd.read_csv(csv_file, na_values=["N/A", "n/a", "NA", "n/a"])

        log_message(f"[INFO] CSV loaded successfully. Columns: {df.columns.tolist()}")

        # Ensure numeric columns are treated as numbers
        numeric_columns = ['Open Port']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')  # Safely handle errors for numeric columns

        # Convert all non-numeric columns to Python strings to avoid pyarrow issues with NumPy types
        df = df.map(lambda x: str(x) if isinstance(x, (str, type(None))) else x)

        log_message("[INFO] Data processed and types converted successfully.")
        
        return df

    except Exception as e:
        error_message = f"[ERROR] Failed to load the CSV file: {str(e)}"
        log_message(error_message)
        log_message(traceback.format_exc())  # Log the full stack trace
        st.error(error_message)
        return None

# Detect if the CSV file has been updated based on its last modification time
def check_csv_update(csv_file_path):
    try:
        current_mod_time = os.path.getmtime(csv_file_path)
        if 'last_mod_time' not in st.session_state or st.session_state.last_mod_time != current_mod_time:
            st.session_state.last_mod_time = current_mod_time
            log_message(f"[INFO] Detected changes in CSV file: {csv_file_path}")
            return True
    except FileNotFoundError:
        log_message(f"[ERROR] CSV file not found: {csv_file_path}")
        st.error(f"CSV file not found: {csv_file_path}")
    except Exception as e:
        log_message(f"[ERROR] Failed to check CSV file update: {str(e)}")
        log_message(traceback.format_exc())
        st.error(f"Failed to check CSV file update: {str(e)}")
    
    return False




# Auto-refresh handler for real-time data updates
def check_auto_refresh():
    current_time = time.time()
    if st.session_state.auto_refresh and (current_time - st.session_state.last_refresh_time) >= st.session_state.refresh_interval:
        st.session_state.last_refresh_time = current_time
        log_message("[DEBUG] Auto-refresh triggered")
        # Trigger the page refresh at the specified interval
        st_autorefresh(interval=st.session_state.refresh_interval * 1000, key="auto_refresh")

def create_dashboard(data):
    if data is None:
        st.error("No valid data found to display")
        return

    # Set the title once
    st.title("VPN Nodes Information - Real-Time Dashboard")

    # Set dark mode styling
    st.markdown(
        """
        <style>
        body {
            background-color: #1E1E1E;
            color: white;
        }
        .css-1v0mbdj {
            background-color: #1E1E1E;
            color: white;
        }
        .css-1gkz2wo {
            color: white;
        }
        .css-18ni7ap {
            background-color: #1E1E1E;
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Count the number of running/online nodes
    running_statuses = ["running", "online", "active"]
    running_nodes = data[data['Status'].str.lower().isin(running_statuses)].shape[0]

    # Display the total count of running/online nodes
    st.markdown(f"### Total Running/Online VPN Nodes: {running_nodes}")

    # Quick Summary Metrics with Status Lights
    st.markdown("### Node Status Overview")

    # Create three columns to display the nodes in a grid
    col1, col2, col3 = st.columns(3)

    # Loop through the data and dynamically handle any number of nodes and statuses
    for index, row in data.iterrows():
        if 'Status' in row and pd.notna(row['Status']):
            node_status = str(row['Status']).lower()  # Convert to string and then lower to handle NaN or floats
            if any(word in node_status for word in running_statuses):
                status_icon = "🟢"  # Green light for active/running nodes
            else:
                status_icon = "🔴"  # Red light for inactive/offline nodes
            
            # Distribute the nodes across the three columns
            if index % 3 == 0:
                col1.markdown(f"{status_icon} **{row.get('Node Name', 'Unknown Node')}** - {row['Status']}")
            elif index % 3 == 1:
                col2.markdown(f"{status_icon} **{row.get('Node Name', 'Unknown Node')}** - {row['Status']}")
            else:
                col3.markdown(f"{status_icon} **{row.get('Node Name', 'Unknown Node')}** - {row['Status']}")
        else:
            col1.markdown(f"🔴 **{row.get('Node Name', 'Unknown Node')}** - No Status Found")

    # Render the dynamic table using HTML
    st.markdown("### Node Data Table")
    table_html = data.to_html(index=False)
    st.markdown(f'<div>{table_html}</div>', unsafe_allow_html=True)




# Automatically hide the sidebar on load
def hide_sidebar_on_load():
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] {
                display: none;
            }
            [data-testid="stSidebarButton"] {
                display: block;
                background-color: #333;
                color: white;
            }
        </style>
        <script>
            document.querySelector('[data-testid="stSidebarButton"]').click();
        </script>
        """, 
        unsafe_allow_html=True
    )

def add_websocket_reconnect():
    """Inject JavaScript to handle WebSocket reconnection and update query parameters."""
    st.markdown(
        """
        <script>
            let ws;

            function startWebSocket() {
                ws = new WebSocket("ws://localhost:4021/ws");

                ws.onopen = function() {
                    console.log("[INFO] WebSocket connection opened");
                };

                ws.onmessage = function(event) {
                    console.log("[INFO] WebSocket message received: ", event.data);
                    // Update query parameters to trigger a rerun
                    const url = new URL(window.location);
                    url.searchParams.set('update', Date.now());
                    window.history.replaceState({}, '', url);
                };

                ws.onerror = function(event) {
                    console.error("[ERROR] WebSocket encountered an error: ", event);
                };

                ws.onclose = function(event) {
                    console.warn("[WARN] WebSocket connection closed, attempting to reconnect in 5 seconds...");
                    setTimeout(function() {
                        startWebSocket(); // Try to reconnect every 5 seconds
                    }, 5000);
                };
            }

            // Start the WebSocket connection initially
            startWebSocket();
        </script>
        """, 
        unsafe_allow_html=True
    )


def main():
    hide_sidebar_on_load()

    # Inject WebSocket reconnection logic via JavaScript
    add_websocket_reconnect()

    # Initialize session state variables
    if 'last_query_params' not in st.session_state:
        st.session_state.last_query_params = {}
    if 'csv_data' not in st.session_state:
        st.session_state.csv_data = None  # Store CSV data in session state
    if 'last_refresh_time' not in st.session_state:
        st.session_state.last_refresh_time = time.time()  # Track when the last refresh happened
    if 'last_mod_time' not in st.session_state:
        st.session_state.last_mod_time = None  # For checking CSV file updates
    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = True  # Enable auto-refresh by default
    if "refresh_interval" not in st.session_state:
        st.session_state.refresh_interval = 10  # Default refresh interval

    # Use st_autorefresh to refresh the app periodically
    st_autorefresh(interval=1000, key="data_refresh")  # Refresh every 1 second
    
    # Check if the update_event is set
    if ws_update_event.is_set():
        ws_update_event.clear()  # Reset the event flag
        log_message("[DEBUG] WebSocket event detected, reloading data.")
        st.experimental_rerun()  # Trigger a rerun from the main thread

    # Sidebar settings with unique keys for the slider
    st.sidebar.title("Dashboard Settings")
    st.sidebar.markdown("Adjust the refresh rate and apply filters to the data.")
    st.session_state.refresh_interval = st.sidebar.slider(
        "Refresh Interval (Seconds)", 1, 60, st.session_state.refresh_interval, key="refresh_interval_slider"
    )
    st.session_state.auto_refresh = st.sidebar.checkbox(
        "Enable Auto-Refresh", value=st.session_state.auto_refresh, key="auto_refresh_checkbox"
    )
    dev_mode = st.sidebar.checkbox("Developer Mode", key="developer_mode_checkbox")

    # Get current query parameters
    query_params = st.query_params

    data_reloaded = False

    # Ensure the CSV file is found
    csv_file = find_csv_file()
    if csv_file is None:
        st.error("No CSV file found in the current working directory.")
        log_message("[ERROR] No CSV file found.")
        return

    # Check if 'update' parameter has changed
    if query_params.get('update') != st.session_state.last_query_params.get('update'):
        st.session_state.last_query_params = query_params
        log_message("[DEBUG] Detected query parameter change, reloading data.")

        # Reload CSV data and store in session state
        data = load_csv_data(csv_file)
        if data is not None and not data.empty:
            st.session_state.csv_data = data  # Store the data for later use
            data_reloaded = True
        else:
            st.warning("The CSV file is empty or invalid.")
            log_message("[WARNING] The CSV file is empty or invalid.")
            return

    # Check if CSV file has changed (modification time)
    elif check_csv_update(csv_file):
        log_message("[DEBUG] CSV file change detected, reloading data.")

        # Reload CSV data and store in session state
        data = load_csv_data(csv_file)
        if data is not None and not data.empty:
            st.session_state.csv_data = data  # Store the data for later use
            data_reloaded = True
        else:
            st.warning("The CSV file is empty or invalid.")
            log_message("[WARNING] The CSV file is empty or invalid.")
            return
    else:
        # No update detected; use existing data
        data = st.session_state.csv_data

    # If data was reloaded or is already available, display it
    if data_reloaded or (data is not None and not data.empty):
        create_dashboard(data)
    else:
        st.warning("No valid data available to display.")
        log_message("[WARNING] No valid data available.")

    # Auto-refresh mechanism using session state
    check_auto_refresh()

    # If Developer Mode is enabled, show logs
    if dev_mode:
        st.sidebar.markdown("## Developer Logs")
        st.sidebar.text_area("Logs", log_stream.getvalue(), height=300)



# Run the Streamlit app
if __name__ == "__main__":
    main()



