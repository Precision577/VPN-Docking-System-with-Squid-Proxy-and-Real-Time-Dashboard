#!/home/idontloveyou/miniconda/bin/python3.11

import os
import time
import json
import uvicorn
import signal
from fastapi import FastAPI, WebSocket
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Thread, Event
import asyncio
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import streamlit as st


app = FastAPI()

# Store active WebSocket connections
clients = []

# Create a global stop event for managing shutdown
stop_event = Event()
global_event_loop = None
# Hidden text input to act as a signal
update_signal = st.text_input("Update Signal", key="update_signal")


def start_event_loop():
    """Start an asyncio event loop in a separate thread."""
    global global_event_loop
    loop = asyncio.new_event_loop()
    global_event_loop = loop  # Set the global event loop
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Create and start the event loop thread at the start of the program
event_loop_thread = Thread(target=start_event_loop)
event_loop_thread.daemon = True  # Ensure it closes when the main program exits
event_loop_thread.start()


def find_csv_file():
    current_dir = Path.cwd()
    for file in current_dir.iterdir():
        if file.suffix == ".csv":
            return file
    return None



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    print(f"[INFO] New WebSocket connection established. Total clients: {len(clients)}")
    
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive by waiting for messages
    except Exception as e:
        print(f"[ERROR] WebSocket connection error: {e}")
    finally:
        clients.remove(websocket)
        print(f"[INFO] WebSocket connection closed. Total clients: {len(clients)}")

class CSVHandler(FileSystemEventHandler):
    def __init__(self, filepath):
        self.filepath = filepath
        self.last_mod_time = os.path.getmtime(filepath)
        self.last_file_size = os.path.getsize(filepath)
        self.last_checksum = self.get_file_checksum(filepath)
        self.last_file_content = self.get_file_content(filepath)
        self.executor = ThreadPoolExecutor(max_workers=16)  # Use 16 workers for concurrency
        print(f"[DEBUG] Monitoring started on {filepath}. Initial mod time: {self.last_mod_time}, size: {self.last_file_size}, checksum: {self.last_checksum}")

    def get_file_checksum(self, filepath):
        """Generate a checksum (MD5) for the file content to detect changes with retries."""
        retries = 3
        while retries:
            try:
                md5 = hashlib.md5()
                with open(filepath, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        md5.update(chunk)
                return md5.hexdigest()
            except Exception as e:
                print(f"[ERROR] Failed to calculate file checksum, retrying... Error: {e}")
                retries -= 1
                time.sleep(0.1)
        return ""

    def get_file_content(self, filepath):
        """Read the entire file content to detect changes."""
        retries = 3
        while retries:
            try:
                with open(filepath, 'r') as f:
                    return f.read()
            except Exception as e:
                print(f"[ERROR] Failed to read file content, retrying... Error: {e}")
                retries -= 1
                time.sleep(0.1)
        return ""

    def on_modified(self, event):
        # Process every detected modification, regardless of content size or checksum
        if event.src_path == str(self.filepath):
            self.executor.submit(self.process_file_event)

    def process_file_event(self):
        try:
            # Introduce a short delay to ensure the file has finished writing
            time.sleep(0.1)

            # Load new content and metadata
            new_mod_time = os.path.getmtime(self.filepath)
            new_file_size = os.path.getsize(self.filepath)
            new_checksum = self.get_file_checksum(self.filepath)
            new_file_content = self.get_file_content(self.filepath)

            print(f"[DEBUG] Detected event on {self.filepath}. New mod time: {new_mod_time}, size: {new_file_size}, checksum: {new_checksum}")

            # Treat all events as significant changes to ensure every modification is handled
            self.last_mod_time = new_mod_time
            self.last_file_size = new_file_size
            self.last_checksum = new_checksum
            self.last_file_content = new_file_content

            print("[INFO] All changes are treated as significant. Reloading the file and notifying clients...")

            # Use the global event loop (the one running in the separate thread)
            asyncio.run_coroutine_threadsafe(notify_clients(), global_event_loop)

        except Exception as e:
            print(f"[ERROR] Error during CSV file modification handling: {e}")








# Function to notify WebSocket clients when the CSV file changes
async def notify_clients():
    data = {"update": "CSV Updated"}
    message = json.dumps(data)
    print(f"[DEBUG] Notifying {len(clients)} clients about the update.")
    
    tasks = []
    for client in clients[:]:  # Copy to avoid issues when modifying the list
        try:
            tasks.append(send_to_client(client, message))
        except Exception as e:
            print(f"[ERROR] Error preparing async task for client notification: {e}")
            clients.remove(client)
    
    if tasks:
        await asyncio.gather(*tasks)  # Await all tasks to ensure they're handled concurrently



# Async function to send messages to clients
async def send_to_client(client, message):
    try:
        print(f"[DEBUG] Sending message to client: {message}")
        await client.send_text(message)  # Use await to properly handle asynchronous calls
    except Exception as e:
        print(f"[ERROR] Failed to send message to client. Removing client. Error: {e}")
        clients.remove(client)


def start_watching_csv():
    csv_file = find_csv_file()
    if csv_file is None:
        print("[ERROR] No CSV file found in the current directory. Please add a CSV file.")
        return

    print(f"[INFO] Monitoring CSV file: {csv_file}")
    event_handler = CSVHandler(csv_file)
    observer = Observer()
    observer.schedule(event_handler, path=csv_file.parent, recursive=False)
    observer.start()

    try:
        while not stop_event.is_set():  # Continue monitoring until stopped
            time.sleep(1)  # Ensure that the observer keeps running
    except KeyboardInterrupt:
        print("[INFO] Stopping CSV monitoring...")
        observer.stop()
    observer.join()


# Signal manager to handle cleanup on termination (Ctrl+C)
class SignalManager:
    def __init__(self):
        self.cleanup_done = False

    def handle_signal(self, signum, frame):
        print(f"\n[INFO] Received signal {signum}. Initiating graceful shutdown...")
        self.cleanup()

    def cleanup(self):
        if not self.cleanup_done:
            print("[INFO] Cleaning up resources...")
            stop_event.set()  # Signal to stop threads
            # Stop the asyncio event loop in the separate thread
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(loop.stop)
            print("[INFO] WebSocket server and CSV watcher stopping.")
            self.cleanup_done = True


# Function to start the WebSocket server and CSV watcher in separate threads
def run_server_and_watcher():
    # Initialize and start the signal manager
    signal_manager = SignalManager()
    signal.signal(signal.SIGINT, signal_manager.handle_signal)
    signal.signal(signal.SIGTERM, signal_manager.handle_signal)

    # Start the event loop in a separate thread
    event_loop_thread = Thread(target=start_event_loop)
    event_loop_thread.daemon = True
    event_loop_thread.start()

    # Start monitoring the CSV file in a separate thread
    watcher_thread = Thread(target=start_watching_csv)
    watcher_thread.daemon = True  # Ensure the thread terminates when the main thread ends
    watcher_thread.start()

    # Run the WebSocket server in the main thread
    print("[INFO] Starting WebSocket server on port 4021")
    uvicorn.run(app, host="0.0.0.0", port=4021)


# Main execution
if __name__ == "__main__":
    run_server_and_watcher()

