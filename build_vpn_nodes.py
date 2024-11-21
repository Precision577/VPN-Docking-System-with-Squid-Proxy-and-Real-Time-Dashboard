#!/home/idontloveyou/miniconda/bin/python3.11
#this is build vpn nodes it is ran by manage_vpns.py
import argparse
import docker
import multiprocessing
import time
from pathlib import Path
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
# Initialize Docker client
client = docker.from_env()

import traceback

def build_and_run_container(tag, ovpn_file, udp_port, socks_port=9090, vpn_type="udp"):
    """
    Build and run a Docker container for a VPN node, mapping the correct UDP or TCP port.
    Set up SSH to run inside the container and expose the correct SOCKS proxy.
    Ensure the base image is used locally.
    """
    try:
        # Cleanup old containers
        cleanup_container(tag)
        
        # Get absolute paths for the credentials and ovpn files using pathlib, converted to strings
        vpn_creds_path = str(Path("./vpn_creds.txt").resolve())
        ovpn_files_path = str(Path("./ovpn_files").resolve())
        public_ips_path = str(Path("/home/idontloveyou/Desktop/LinuxServer1/freedomdata/storage/docker/public_ips").resolve())
        ovpn_file_str = str(Path(ovpn_file).name)  # Get only the filename (not the full path)

        # Get the absolute path for SSL certificates directory
        ssl_certs_path = str(Path("/etc/ssl/certs").resolve())

        # Check if the base image is available locally
        try:
            client.images.get("ubuntu:22.04")
            print("Base image 'ubuntu:22.04' is already available locally.")
        except docker.errors.ImageNotFound:
            print("Base image 'ubuntu:22.04' not found locally. Pulling from Docker Hub...")
            client.images.pull("ubuntu:22.04")

        # Log port information
        print(f"Attempting to build container {tag} with VPN file {ovpn_file_str} on {vpn_type.upper()} port {udp_port} and SOCKS5 proxy on port {socks_port} (TCP)...")

        # Build the Docker image with the tag
        image, build_logs = client.images.build(path=".", tag=tag, buildargs={"OVPN_FILE": ovpn_file_str})
        print(f"Container image {tag} built successfully.")

        # Run the Docker container using the tagged image
        container = client.containers.run(
            image.id,  # Use the image ID instead of the tag directly
            detach=True,
            name=tag,
            environment={
                "VPN_FILE": ovpn_file_str,
                "VPN_TYPE": vpn_type,  # Pass the VPN type as an environment variable
                "SOCKS_PORT": str(socks_port)  # Pass the SOCKS5 port as an environment variable
            },
            volumes={
                vpn_creds_path: {"bind": "/etc/openvpn/vpn_creds.txt", "mode": "ro"},  # Bind the VPN credentials
                ovpn_files_path: {"bind": "/etc/openvpn/ovpn_files", "mode": "ro"},  # Bind the OVPN files directory
                public_ips_path: {"bind": "/home/idontloveyou/Desktop/LinuxServer1/freedomdata/storage/docker/public_ips", "mode": "rw"},
                ssl_certs_path: {"bind": "/etc/ssl/certs", "mode": "ro"}  # Mount SSL certificates directory
            },
            ports={f'{udp_port}/udp': udp_port, f'{socks_port}/tcp': socks_port},  # Expose both UDP and SOCKS5 ports
            cap_add=["NET_ADMIN"],  # Allow NET_ADMIN capability
            devices=["/dev/net/tun"],  # Enable access to /dev/net/tun device
            privileged=True  # Ensure the container can modify network settings
        )
        print(f"Container {tag} is running on {vpn_type.upper()} port {udp_port} and SOCKS5 proxy on TCP port {socks_port}.")

    except docker.errors.BuildError as e:
        print(f"Failed to build container {tag}: {e}")
        traceback.print_exc()  # Print full stack trace for better debugging
    except Exception as e:
        print(f"Error while building/running container {tag}: {e}")
        traceback.print_exc()  # Print full stack trace for better debugging



def map_nodes(pairs):
    """
    Ensure that Node 1 is UDP and Node 2 is TCP, then Node 3 is UDP and Node 4 is TCP, and so on.
    """
    node_map = []
    
    # For each pair, assign the first node to UDP and the second to TCP
    for i, (udp_file, tcp_file) in enumerate(pairs):
        udp_node = i * 2 + 1  # Node 1, Node 3, etc. (Odd-numbered nodes for UDP)
        tcp_node = i * 2 + 2  # Node 2, Node 4, etc. (Even-numbered nodes for TCP)
        
        # Append the nodes with correct pairing: UDP first, then TCP
        node_map.append((udp_node, "udp", udp_file))  # UDP is always odd-numbered
        node_map.append((tcp_node, "tcp", tcp_file))  # TCP is always even-numbered
    
    return node_map





def sequential_build_and_run_with_map(node_map):
    """
    Build and run VPN nodes sequentially using the node map.
    Ensures each container is fully built before moving to the next.
    """
    def run_container(node_name, vpn_type, ovpn_file, port, socks_port):
        build_and_run_container(node_name, ovpn_file, port, socks_port, vpn_type)

    # Define port ranges: UDP on odd nodes, TCP on even nodes
    udp_ports = range(8080, 8080 + len(node_map), 2)  # UDP ports start from 8080, assigned to odd nodes
    tcp_ports = range(8081, 8081 + len(node_map), 2)  # TCP ports start from 8081, assigned to even nodes
    socks_ports = range(9090, 9090 + len(node_map))  # SOCKS5 proxy ports (9090, 9091, ...)

    udp_port_index = 0  # UDP port index
    tcp_port_index = 0  # TCP port index

    for node_num, vpn_type, ovpn_file in node_map:
        node_name = f"vpn_node_{node_num}"

        # Assign ports based on whether it's UDP or TCP, use the node number for SOCKS5 port assignment
        if vpn_type == "udp":
            port = udp_ports[udp_port_index]
            socks_port = socks_ports[node_num - 1]  # SOCKS5 port is based on node_num
            print(f"Building and running UDP container {node_name} on port {port} and SOCKS5 {socks_port}...")
            run_container(node_name, vpn_type, ovpn_file, port, socks_port)
            udp_port_index += 1
        else:
            port = tcp_ports[tcp_port_index]
            socks_port = socks_ports[node_num - 1]  # SOCKS5 port is based on node_num
            print(f"Building and running TCP container {node_name} on port {port} and SOCKS5 {socks_port}...")
            run_container(node_name, vpn_type, ovpn_file, port, socks_port)
            tcp_port_index += 1

        # Ensure container is fully built and running before proceeding
        print(f"Container {node_name} started successfully.")






def setup_proxy_in_container(container_id, socks_port=9090):
    """
    Set up a SOCKS proxy inside the running container using SSH.
    """
    try:
        # Use Docker exec to run the SOCKS proxy setup inside the container on the specified SOCKS5 port
        command = f"ssh -D 0.0.0.0:{socks_port} -q -C -N root@localhost"
        print(f"Setting up SOCKS proxy in container {container_id} on port {socks_port} with command: {command}")
        subprocess.run(["docker", "exec", container_id, "/bin/bash", "-c", command], check=True)
        print(f"Proxy successfully set up on port {socks_port} for container {container_id}")

    except subprocess.CalledProcessError as e:
        print(f"Failed to set up proxy in container {container_id}: {e}")




def cleanup_container(tag):
    """
    Stop and remove a Docker container if it exists.
    """
    try:
        print(f"Cleaning up container {tag}...")
        container = client.containers.get(tag)
        container.stop()
        container.remove()
        print(f"Container {tag} cleaned up.")
    except docker.errors.NotFound:
        print(f"Container {tag} not found. Skipping cleanup.")
    except Exception as e:
        print(f"Error during cleanup of {tag}: {e}")


def cleanup_existing_containers():
    """
    Stop and remove all existing VPN containers before starting the new setup.
    """
    try:
        # Get a list of all running containers with the prefix 'vpn_node'
        containers = client.containers.list(all=True, filters={"name": "vpn_node"})

        if containers:
            print("Cleaning up existing VPN node containers...")
            for container in containers:
                try:
                    print(f"Cleaning up container {container.name} (ID: {container.id})...")
                    container.stop()
                    container.remove()
                    print(f"Container {container.name} (ID: {container.id}) stopped and removed.")
                except Exception as e:
                    print(f"[ERROR] Error cleaning up container {container.name} (ID: {container.id}): {e}")
        else:
            print("No existing VPN containers found.")
        
        # Optionally prune system to remove any unused images, containers, volumes
        print("Docker system prune to remove unused images and volumes...")
        client.containers.prune()
        client.images.prune()

    except Exception as e:
        print(f"[ERROR] Error during container cleanup: {e}")




def get_matching_ovpn_files(udp_directory, tcp_directory, udp_node_count, tcp_node_count):
    """
    Get a specified number of UDP .ovpn files and find matching TCP files from both directories.
    Ensure that UDP and TCP files from the same server are paired and assigned sequentially.
    """
    udp_ovpn_files = list(Path(udp_directory).glob("*.ovpn"))
    tcp_ovpn_files = list(Path(tcp_directory).glob("*.ovpn"))

    # Create a mapping of server names to their respective TCP and UDP files
    udp_files_dict = {udp_file.stem.replace('-udp', ''): udp_file for udp_file in udp_ovpn_files}
    tcp_files_dict = {tcp_file.stem.replace('-tcp', ''): tcp_file for tcp_file in tcp_ovpn_files}

    selected_pairs = []

    # Match UDP and TCP by location
    for server_name, udp_file in udp_files_dict.items():
        if server_name in tcp_files_dict:
            tcp_file = tcp_files_dict[server_name]
            selected_pairs.append((udp_file, tcp_file))  # Pair UDP and TCP files in sequence

        # Stop when we've reached the requested number of UDP and TCP pairs
        if len(selected_pairs) >= min(udp_node_count, tcp_node_count):
            break

    # Ensure we have enough pairs of matching files
    if len(selected_pairs) < udp_node_count:
        raise ValueError(f"Not enough matching UDP and TCP .ovpn files found. Found {len(selected_pairs)}.")

    print(f"Selected {len(selected_pairs)} UDP and TCP pairs in sequence.")
    
    return selected_pairs


def main():
    parser = argparse.ArgumentParser(description="VPN Node Manager")
    parser.add_argument("udp_node_count", type=int, help="Number of UDP nodes to create")
    parser.add_argument("tcp_node_count", type=int, help="Number of TCP nodes to create")
    args = parser.parse_args()

    udp_node_count = args.udp_node_count
    tcp_node_count = args.tcp_node_count

    udp_directory = './ovpn_files/udp'
    tcp_directory = './ovpn_files/tcp'

    # Step 1: Cleanup existing containers
    cleanup_existing_containers()

    # Step 2: Get matching pairs of UDP and TCP .ovpn files
    pairs = get_matching_ovpn_files(udp_directory, tcp_directory, udp_node_count, tcp_node_count)

    # Step 3: Create a map of nodes where the first is UDP, second is TCP, etc.
    node_map = map_nodes(pairs)

    # Step 4: Build containers sequentially to avoid race conditions
    start_time = time.time()
    sequential_build_and_run_with_map(node_map)
    end_time = time.time()

    print(f"Completed {udp_node_count + tcp_node_count} VPN nodes setup in {end_time - start_time} seconds.")

if __name__ == "__main__":
    main()

