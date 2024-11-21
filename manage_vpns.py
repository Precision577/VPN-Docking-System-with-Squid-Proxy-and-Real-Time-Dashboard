#!/home/idontloveyou/miniconda/bin/python3.11
import os
import subprocess
import time
import docker
from pathlib import Path
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta


# Constants
DELETE_TEXT_FILES = False  # Toggle for deleting text files after processing
SHARED_DIR = Path.cwd() / 'public_ips'
PYTHON_SCRIPT = Path.cwd() / 'update_vpn_info.py'
# New Constants for UDP/TCP Nodes
DEFAULT_UDP_NODES = '1' # Set a default number of UDP nodes (can be adjusted)
DEFAULT_TCP_NODES = '1'  # Set a default number of TCP nodes (can be adjusted)

delete_csv_flag = False # Global flag to ensure CSV is deleted only once


MAX_ATTEMPTS = 10
SOCKS5_START_PORT = 9090
UDP_START_PORT = 8080


processed_files = {}  # Global dictionary to track processed public IP files
public_ip_cache = {}  # Global dictionary to cache public IP info

# Initialize Docker client
client = docker.from_env()

def cleanup_vpn_nodes():
    print("Cleaning up existing VPN node containers...")

    # Delete all text files in the shared directory
    for text_file in SHARED_DIR.glob("*.txt"):
        try:
            print(f"[DEBUG] Deleting {text_file} as part of initial cleanup...")
            text_file.unlink()
            print(f"[DEBUG] Successfully deleted {text_file}.")
        except Exception as e:
            print(f"[ERROR] Failed to delete {text_file}: {str(e)}")
            traceback.print_exc()

    # Stop and remove containers using subprocess
    try:
        # Get container IDs before stopping/removing them to update the CSV
        result = subprocess.run(
            "docker ps -aq --filter 'name=vpn_node_'",
            shell=True, capture_output=True, text=True, check=True
        )
        container_ids = result.stdout.strip().split('\n')
        container_ids = [container_id[:12] for container_id in container_ids if container_id]
        
        for container_id in container_ids:
            public_ip_file = SHARED_DIR / f"{container_id}-ip.txt"
            container_name = f"vpn_node_{container_id[:4]}"  # Use part of the container ID for the name
            print(f"[DEBUG] Updating CSV with 'Exited' status for {container_name} (ID: {container_id}) before cleanup.")

            # If the IP file exists, update the VPN info to mark as 'Exited'
            if public_ip_file.exists():
                node, vpn_file, vpn_type, public_ip, proxy_info = extract_info_from_file(public_ip_file)
                update_vpn_info(container_name, vpn_file or "N/A", vpn_type or "N/A", public_ip or "VPN failed to start", "Exited", "Not Connected", container_id, "N/A", proxy_info or "No Proxy", "N/A")

                if DELETE_TEXT_FILES:
                    delete_text_file(public_ip_file)
            else:
                print(f"[ERROR] No public IP file found for exited container {container_name} (ID: {container_id}).")

        # Stop and remove all containers with names starting with 'vpn_node_'
        subprocess.run(
            "docker ps -aq --filter 'name=vpn_node_' | xargs -r docker stop | xargs -r docker rm",
            shell=True, check=True
        )
        print("All VPN node containers stopped and removed.")

        # Prune Docker resources (volumes, networks, and unused containers)
        subprocess.run("docker system prune -f --volumes", shell=True, check=True)

        print("Docker system pruned successfully, including volumes and unused images.")

        # Check and clear any open ports after pruning
        for port in range(SOCKS5_START_PORT, SOCKS5_START_PORT + MAX_ATTEMPTS):
            if check_port_in_use(port):
                print(f"[DEBUG] Port {port} is still in use. Clearing it...")
                clear_port(port)

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to clean up VPN nodes: {e}")
        traceback.print_exc()


def build_vpn_nodes(udp_node_count, tcp_node_count):
    """
    Build and start VPN nodes with the specified UDP and TCP node counts.
    """
    print(f"Building and starting {udp_node_count} UDP nodes and {tcp_node_count} TCP nodes...")

    # Adjust the subprocess call to pass node counts and types
    retries = 0
    while retries < 5:
        result = subprocess.run(
            ["./build_vpn_nodes.py", str(udp_node_count), str(tcp_node_count)], 
            text=True  # This will ensure the output is printed directly
        )
        if result.returncode == 99:
            print("VPN public IP retrieval failed. Retrying...")
            time.sleep(2)
            retries += 1
        else:
            break
    if retries == 5:
        print("Failed to build VPN nodes after maximum retries.")
        return False
    return True




def get_container_ids():
    try:
        result = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "name=vpn_node_"],
            capture_output=True,
            text=True,
            check=True
        )
        container_ids = result.stdout.strip().split('\n')
        container_ids = [container_id[:12] for container_id in container_ids if container_id]
        for container_id in container_ids:
            print(f"Node: {container_id}")
        return container_ids
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving container IDs: {str(e)}")
        traceback.print_exc()
        return []


def determine_connectivity(public_ip, proxy_info, socks5_port):
    if public_ip == "Auth Failed":
        return "Auth Failed"
    elif not public_ip:
        return "Not Connected"
    elif "Proxy setup failed" in proxy_info or not socks5_port or socks5_port == "N/A":
        return "Disconnected"
    else:
        return "Connected"


def restart_container(container_id, container_name):
    """
    Restart the container with the given ID and update its status to 'Restarting'.
    After restart, update the status to 'Running' in the CSV file.
    """
    print(f"[DEBUG] Restarting container {container_name} (ID: {container_id})...")

    # Use the cached public IP info to update the node data
    if container_id in public_ip_cache:
        node_info = public_ip_cache[container_id]
        node, vpn_file, vpn_type, public_ip, open_port, socks5_port = (
            node_info['node'],
            node_info['vpn_file'],
            node_info['vpn_type'],
            node_info['public_ip'],
            node_info['open_port'],
            node_info['socks5_port']
        )

        # Determine connectivity (Connected/Disconnected)
        connectivity = determine_connectivity(public_ip, node_info.get('proxy_info', 'No Proxy'), socks5_port)
        proxy_info = "Connected" if connectivity == "Connected" else "Disconnected"

        # Log the restart with the cached port information
        update_vpn_info(container_name, vpn_file or "N/A", vpn_type or "N/A", public_ip or "VPN failed to start", 
                        "Restarting", "Not Connected", container_id, open_port, proxy_info, socks5_port)
    else:
        print(f"[ERROR] No cached public IP info found for {container_name} (ID: {container_id}). Using defaults.")
        return

    try:
        container = client.containers.get(container_id)
        container.restart()

        # Wait for the container to fully restart
        if wait_for_container(container_id, container_name):
            print(f"[DEBUG] Successfully restarted container {container_name} (ID: {container_id}).")
            
            # Check for the public IP file after restart and update the CSV
            public_ip_file = SHARED_DIR / f"{container_id}-ip.txt"
            if public_ip_file.exists():
                node, vpn_file, vpn_type, public_ip, proxy_info = extract_info_from_file(public_ip_file)
                update_vpn_info(container_name, vpn_file, vpn_type, public_ip, "running", "Connected", container_id, open_port, proxy_info, socks5_port)
            else:
                print(f"[DEBUG] No new public IP file found for {container_name}. Using cached data.")
        else:
            print(f"[ERROR] Failed to restart container {container_name} (ID: {container_id}).")
    except docker.errors.NotFound:
        print(f"[ERROR] Container {container_id} not found.")
    except Exception as e:
        print(f"[ERROR] Exception during restart of {container_name}: {str(e)}")






def wait_for_container(container_id, container_name):
    """
    Waits for the container to start, checks its health, and logs its status. 
    Restarts if necessary. Returns True if container is running successfully.
    """
    timeout = 45  # Set timeout to 30 seconds for container status check
    file_wait_timeout = 60  # Set additional timeout for the public IP file

    public_ip_file = SHARED_DIR / f"{container_id}-ip.txt"
    container = None

    print(f"[INFO] Waiting for container {container_name} (ID: {container_id}) to reach 'running' status...")

    # First, wait for the container to start or exit
    for _ in range(timeout):
        try:
            container = client.containers.get(container_id)
        except docker.errors.NotFound:
            print(f"[ERROR] Container {container_id} not found. Exiting wait.")
            return False

        status = container.status

        if status == "running":
            print(f"[INFO] Container {container_name} (ID: {container_id}) is now running.")
            
            # Update the CSV immediately with "running" status
            if public_ip_file.exists():
                node, vpn_file, vpn_type, public_ip, proxy_info = extract_info_from_file(public_ip_file)
                update_vpn_info(container_name, vpn_file, vpn_type, public_ip, "running", "Connected", 
                                container_id, "N/A", proxy_info, "N/A")
            else:
                # Fallback to cached data if public_ip_file doesn't exist
                if container_id in public_ip_cache:
                    cache_data = public_ip_cache[container_id]
                    update_vpn_info(container_name, cache_data['vpn_file'], cache_data['vpn_type'], 
                                    cache_data['public_ip'], "running", "Connected", 
                                    container_id, "N/A", cache_data['proxy_info'], "N/A")
            break
        elif status == "exited":
            print(f"[WARNING] Container {container_name} (ID: {container_id}) has exited.")
            restart_container(container_id, container_name)
            return False  # Restart initiated, exit this check
        time.sleep(1)
    else:
        print(f"[ERROR] Container {container_name} (ID: {container_id}) did not reach 'running' status within {timeout} seconds.")
        return False

    # Check for public IP file once the container is running
    print(f"[INFO] Waiting for public IP file for {container_name} (ID: {container_id})...")
    for _ in range(file_wait_timeout):
        if public_ip_file.exists():
            print(f"[INFO] Public IP file found for {container_name} (ID: {container_id}). Proceeding with further checks.")
            return True
        time.sleep(1)

    print(f"[ERROR] Public IP file not found for {container_name} (ID: {container_id}) within {file_wait_timeout} seconds. Using cached data if available.")
    return False








def collect_public_ips_and_ports():
    """
    Continuously monitors containers, handles public IP updates, restarts containers if they exit,
    and updates container IDs if the container changes after a restart.
    """
    check_counter = 1  # Initialize the check counter
    container_info = {}  # Dictionary to store container info, keyed by node name

    while True:  # Continuous monitoring
        print(f"[CHECK {check_counter}] Starting check {check_counter}...")

        container_ids = get_container_ids()  # Get current container IDs
        logged_files = set()  # A set to keep track of files that have already been logged

        # Update container info if it's the first time or after restarts
        update_container_info(container_ids, container_info)

        for i, (node_name, info) in enumerate(container_info.items(), start=1):
            container_id = info["container_id"]
            container_name = f"vpn_node_{i}"
            open_port = info["open_port"]
            socks5_port = info["socks5_port"]
            public_ip_file = SHARED_DIR / f"{container_id}-ip.txt"

            # Process container status even if the file has been processed
            if public_ip_file.exists() or container_id in public_ip_cache:
                process_container_status(container_id, container_name, open_port, socks5_port, public_ip_file, container_info)
            else:
                print(f"[ERROR] Neither public IP file nor cache available for {container_name}. Skipping.")
        
        print(f"[INFO] Completed check {check_counter}. All containers have been checked.")
        check_counter += 1
        time.sleep(120)  # Wait for 5 seconds before the next check to avoid overwhelming the system


def cache_public_ip(container_id, node, vpn_file, vpn_type, public_ip, connectivity, open_port, socks5_port):
    """
    Store the public IP info into the cache to avoid reliance on file-based access after processing.
    Save proxy_info based on the connectivity status.
    """
    proxy_info = "Connected" if connectivity == "Connected" else "Disconnected"  # Determine proxy_info
    public_ip_cache[container_id] = {
        "node": node,
        "vpn_file": vpn_file or "N/A",
        "vpn_type": vpn_type or "N/A",
        "public_ip": public_ip or "VPN failed to start",
        "connectivity": connectivity,  # Store connectivity status
        "proxy_info": proxy_info,  # Cache proxy_info based on connectivity
        "open_port": open_port if open_port != "N/A" else public_ip_cache.get(container_id, {}).get("open_port", "N/A"),
        "socks5_port": socks5_port if socks5_port != "N/A" else public_ip_cache.get(container_id, {}).get("socks5_port", "N/A")
    }
    print(f"[DEBUG] Cached public IP and connectivity data for container {container_id}.")





def update_container_info(container_ids, container_info):
    """
    Updates container information (such as container IDs, open ports, socks5 ports, etc.) 
    and ensures that new containers are properly tracked.
    """
    for i, container_id in enumerate(container_ids, start=1):
        node_name = f"vpn_node_{i}"
        open_port = UDP_START_PORT + (i - 1)  # Assign open port starting from 8080
        socks5_port = SOCKS5_START_PORT + (i - 1)  # Assign SOCKS5 port starting from 9090
        
        if node_name not in container_info:
            container_info[node_name] = {
                "container_id": container_id,
                "open_port": open_port,
                "socks5_port": socks5_port
            }
        else:
            # Check if the container ID has changed (in case of restarts)
            if container_info[node_name]["container_id"] != container_id:
                print(f"[INFO] Container ID for {node_name} changed from {container_info[node_name]['container_id']} to {container_id}. Updating...")
                container_info[node_name]["container_id"] = container_id
                container_info[node_name]["open_port"] = open_port  # Update the open port if container changes
                container_info[node_name]["socks5_port"] = socks5_port  # Update the SOCKS5 port if container changes





def process_container_status(container_id, container_name, open_port, socks5_port, public_ip_file, container_info):
    """
    Handles the status of a single container: checks if it exited, waits for the public IP file, and processes the file.
    Restarts the container and updates the container ID if necessary.
    """
    # Check the container status first
    container_status = wait_for_container(container_id, container_name)

    # Restart the container if it has exited
    if container_status == "exited":
        if public_ip_file.exists():
            print(f"[DEBUG] Updating exited container {container_name} (ID: {container_id}) with 'Exited' status.")
            node, vpn_file, vpn_type, public_ip, proxy_info = extract_info_from_file(public_ip_file)

            # Update CSV with the exited status
            update_vpn_info(container_name, vpn_file or "N/A", vpn_type or "N/A", 
                            public_ip or "VPN failed to start", "Exited", "Not Connected", 
                            container_id, open_port, proxy_info or "No Proxy", socks5_port)

            # Keep the old public IP file until the new container is fully ready
            print(f"[DEBUG] Retaining old public IP file for {container_name} (ID: {container_id}) until the new one is fully ready.")
            return  # Exit early, avoiding deletion of the old file until the new one is available

        else:
            print(f"[ERROR] No public IP file found for exited container {container_name} (ID: {container_id}). Relying on cached data.")
            # Fall back to cache if no public IP file is found
            if container_id in public_ip_cache:
                cache_data = public_ip_cache[container_id]
                update_vpn_info(container_name, cache_data['vpn_file'], cache_data['vpn_type'], 
                                cache_data['public_ip'], "Exited", "Not Connected", 
                                container_id, open_port, cache_data['proxy_info'], socks5_port)
        return

    # If the container is running, ensure the public IP file is processed
    if public_ip_file.exists():
        if public_ip_file in processed_files:
            print(f"[INFO] Public IP file for {container_name} (ID: {container_id}) has already been processed. Skipping reprocessing.")
        else:
            fully_formatted = False
            attempt = 0

            print(f"[DEBUG] Waiting for {public_ip_file} to be fully formatted...")

            while attempt < MAX_ATTEMPTS:
                node, vpn_file, vpn_type, public_ip, proxy_info = extract_info_from_file(public_ip_file)

                if node and vpn_file and public_ip and proxy_info:
                    fully_formatted = True
                    print(f"[DEBUG] {public_ip_file} is fully formatted. Proceeding with data extraction.")
                    break
                else:
                    print(f"[DEBUG] {public_ip_file} is not fully formatted yet. Waiting for it...")
                    time.sleep(2)
                    attempt += 1

            if fully_formatted:
                process_public_ip_file(container_name, container_id, public_ip_file, open_port, socks5_port)
                processed_files[public_ip_file] = "processed"  # Mark the file as processed

                # Now we can safely delete the old file
                if DELETE_TEXT_FILES:
                    print(f"[DEBUG] Deleting processed file {public_ip_file}...")
                    delete_text_file(public_ip_file)
            else:
                print(f"[ERROR] {public_ip_file} was not fully formatted after {MAX_ATTEMPTS} attempts. Skipping.")
    else:
        print(f"[ERROR] Public IP file {public_ip_file} does not exist for {container_name}. Using cache for data.")
        # Fall back to cached data if the public IP file does not exist
        if container_id in public_ip_cache:
            cache_data = public_ip_cache[container_id]
            update_vpn_info(container_name, cache_data['vpn_file'], cache_data['vpn_type'], 
                            cache_data['public_ip'], "running", "Connected", 
                            container_id, open_port, cache_data['proxy_info'], socks5_port)







def extract_info_from_file(public_ip_file):
    with open(public_ip_file) as f:
        lines = f.readlines()
    node = extract_value("Node", lines)
    vpn_file = extract_value("VPN File", lines)
    vpn_type = extract_value("VPN_TYPE", lines)  # Added to extract VPN_TYPE from the text file
    public_ip = extract_value("Public IP", lines)
    proxy_info = extract_value("Proxy Info", lines)
    return node, vpn_file, vpn_type, public_ip, proxy_info


def extract_value(label, lines):
    for line in lines:
        if line.startswith(f"{label}: "):
            return line.split(f"{label}: ")[1].strip()
    return None

def process_public_ip_file(container_name, container_id, public_ip_file, open_port, socks5_port):
    node, vpn_file, vpn_type, public_ip, proxy_info = extract_info_from_file(public_ip_file)

    if "Auth Failed" in public_ip:
        public_ip = "Auth Failed"
        print(f"[DEBUG] Auth Failed detected for container {container_name}.")
    
    # Determine connectivity based on proxy info and valid port
    connectivity = determine_connectivity(public_ip, proxy_info, socks5_port)
    proxy_info = "Connected" if connectivity == "Connected" else "Disconnected"

    if not open_port or open_port == "N/A":
        print(f"[DEBUG] Open port not set for {container_name} (ID: {container_id}). Skipping update.")
        return

    print(f"[DEBUG] Determined connectivity: {connectivity}, SOCKS5 Port: {socks5_port}, Open Port: {open_port}")

    # Cache the public IP info, including the valid ports and determined connectivity
    cache_public_ip(container_id, node, vpn_file, vpn_type, public_ip, connectivity, open_port, socks5_port)

    # Update VPN info with the corrected connectivity status and valid ports
    update_vpn_info(container_name, vpn_file or "N/A", vpn_type or "N/A", public_ip, "running", connectivity, container_id, open_port, proxy_info, socks5_port)

    if DELETE_TEXT_FILES:
        delete_text_file(public_ip_file)













def check_port_in_use(port):
    return subprocess.run(f"lsof -i :{port}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def update_vpn_info(container_name, vpn_file, vpn_type, public_ip, status, connectivity, container_id, open_port, proxy_info, socks5_port):
    # If either open_port or socks5_port is 'N/A', attempt to update with valid cached or determined values
    if open_port == 'N/A' or socks5_port == 'N/A':
        print(f"[DEBUG] Missing port information for {container_name} (ID: {container_id}). Attempting to update from cache.")
        
        # Attempt to pull from cache if available
        if container_id in public_ip_cache:
            cached_data = public_ip_cache[container_id]
            open_port = cached_data.get('open_port', 'N/A')
            socks5_port = cached_data.get('socks5_port', 'N/A')

        # Log if we still have 'N/A' ports after checking the cache
        if open_port == 'N/A' or socks5_port == 'N/A':
            print(f"[ERROR] Ports missing for {container_name} (ID: {container_id}). Cannot update CSV or cache without valid port info.")
            return

    # Convert ports to strings if they are integers
    open_port_str = str(open_port)
    socks5_port_str = str(socks5_port)

    # Pass the connectivity (Connected/Disconnected) instead of proxy_info
    args = [str(PYTHON_SCRIPT), container_name, vpn_file, public_ip, vpn_type, status, connectivity, container_id, open_port_str, connectivity, socks5_port_str]

    # Use subprocess to run the script and capture both stdout and stderr
    try:
        result = subprocess.run(["python3"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Output stdout and stderr to the console
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        
        # Handle non-zero exit codes
        if result.returncode != 0:
            print(f"[ERROR] Failed to update VPN info for {container_name} (ID: {container_id})")
        else:
            print(f"[DEBUG] Successfully updated VPN info for {container_name} (ID: {container_id})")
            
            # Cache the updated info, ensuring that connectivity is correctly stored
            cache_public_ip(container_id, container_name, vpn_file, vpn_type, public_ip, connectivity, open_port_str, socks5_port_str)
    except Exception as e:
        print(f"[ERROR] An exception occurred while updating VPN info: {str(e)}")
        traceback.print_exc()











def delete_text_file(public_ip_file):
    if public_ip_file.exists():
        try:
            print(f"[DEBUG] Deleting public IP file {public_ip_file}...")
            public_ip_file.unlink()
            print(f"[DEBUG] Successfully deleted public IP file {public_ip_file}.")
            processed_files[public_ip_file] = "processed"  # Ensure file is marked as processed
        except Exception as e:
            print(f"[ERROR] Failed to delete {public_ip_file}: {str(e)}")
            traceback.print_exc()
    else:
        print(f"[DEBUG] Public IP file {public_ip_file} does not exist, skipping deletion.")


def delete_csv_file():
    csv_file = Path.cwd() / "vpn_nodes_info.csv"  # Assuming the CSV file is named vpn_info.csv
    if csv_file.exists():
        try:
            print(f"[DEBUG] Deleting CSV file {csv_file}...")
            csv_file.unlink()  # Delete the file
            print(f"[DEBUG] Successfully deleted CSV file {csv_file}.")
        except Exception as e:
            print(f"[ERROR] Failed to delete CSV file {csv_file}: {str(e)}")
            traceback.print_exc()
    else:
        print(f"[DEBUG] CSV file {csv_file} does not exist, skipping deletion.")



def parse_udp_tcp_node_count(udp_input, tcp_input, available_udp_nodes, available_tcp_nodes):
    """
    Parse the input for both UDP and TCP node counts. If set to 'all', set the count to 55.
    Otherwise, return the number specified, capped by the available number of nodes.
    """
    def parse_node_count(node_input, available_nodes):
        # Ensure that 'node_input' is cast to string to handle both integers and 'all'
        node_input = str(node_input)
        if node_input.lower() == 'all':  # Lowercase to handle 'ALL' or 'all'
            return 55  # Set to 55 if 'all' is passed as input
        try:
            node_count = int(node_input)  # Ensure we are converting the value to an integer
            return min(node_count, available_nodes)
        except ValueError:
            print("[ERROR] Invalid node count input. Please specify a valid number or 'all'.")
            return 0

    udp_node_count = parse_node_count(udp_input, available_udp_nodes)
    tcp_node_count = parse_node_count(tcp_input, available_tcp_nodes)

    return udp_node_count, tcp_node_count



def generate_docker_compose_file(udp_node_count, tcp_node_count):
    total_nodes = udp_node_count + tcp_node_count
    print(f"[DEBUG] Calling generate_yml.py to create docker-compose.yml with {total_nodes} nodes.")

    try:
        # Run the generate_yml.py script with the correct argument format --nodes <number>
        result = subprocess.run(
            ["python3", "generateyml.py", "--nodes", str(total_nodes)],
            capture_output=True,
            text=True,
            check=True
        )
        if result.returncode == 0:
            print("[DEBUG] Successfully generated docker-compose.yml.")
        else:
            print(f"[ERROR] Failed to generate docker-compose.yml: {result.stderr.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Exception occurred during docker-compose.yml generation: {str(e)}")
        traceback.print_exc()



def main():
    global delete_csv_flag
    
    # Ensure cleanup before starting the process
    print("Ensuring cleanup of existing VPN nodes and Docker resources before starting...")
    cleanup_vpn_nodes()  # This will stop, remove, and prune any leftover nodes

    # Delete the CSV file only once, if it hasn't been deleted yet
    if not delete_csv_flag:
        delete_csv_file()  # Delete the CSV file from the current working directory
        delete_csv_flag = True  # Set the flag to avoid re-deleting the CSV file

    # Fetch available .ovpn files for both UDP and TCP
    cwd = Path.cwd()
    udp_ovpn_dir = cwd / 'ovpn_files' / 'udp'
    tcp_ovpn_dir = cwd / 'ovpn_files' / 'tcp'

    udp_ovpn_files = list(udp_ovpn_dir.glob("*.ovpn"))
    tcp_ovpn_files = list(tcp_ovpn_dir.glob("*.ovpn"))

    available_udp_nodes = len(udp_ovpn_files)
    available_tcp_nodes = len(tcp_ovpn_files)

    # Use constants for node count and adjust dynamically for both UDP and TCP nodes
    udp_node_count, tcp_node_count = parse_udp_tcp_node_count(DEFAULT_UDP_NODES, DEFAULT_TCP_NODES, available_udp_nodes, available_tcp_nodes)

    if udp_node_count == 0 and tcp_node_count == 0:
        print("No nodes to build. Exiting.")
        return

    # Generate the docker-compose.yml based on the total node count
    generate_docker_compose_file(udp_node_count, tcp_node_count)

    # Clean up VPN nodes before building new ones
    cleanup_vpn_nodes()  # Clean up before starting new nodes

    # Build the new VPN nodes
    if not build_vpn_nodes(udp_node_count, tcp_node_count):  # Pass the node counts here
        print("Failed to build VPN nodes. Exiting.")
        return

    # Retrieve container IDs after building nodes
    container_ids = get_container_ids()

    # Wait for each container to become ready and restart if exited
    for i, container_id in enumerate(container_ids, start=1):
        container_name = f"vpn_node_{i}"  # Generate the container name based on the index
        print(f"Checking container (ID: {container_id})...")
        wait_for_container(container_id, container_name)  # Pass both container_id and container_name

    # Continuous monitoring and updating of VPN nodes and ports
    while True:
        print("Checking VPN nodes and updating CSV file...")
        collect_public_ips_and_ports()
        time.sleep(10)

if __name__ == "__main__":
    main()

