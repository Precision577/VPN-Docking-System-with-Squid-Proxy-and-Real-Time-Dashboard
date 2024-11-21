import argparse
from pathlib import Path

def generate_vpn_node_config(node_number, udp_port, tcp_port, socks_port, ip_address, public_ips_dir):
    """
    Generates the configuration for a single VPN node, using the pre-built image for faster startup.
    Adds a health check for monitoring the container's health.
    """
    return f"""
  vpn_node_{node_number}:
    image: vpn_node_image  # Use the pre-built Docker image
    container_name: vpn_node_{node_number}
    environment:
      - VPN_FILE=${{VPN_FILE_{node_number}}}
      - VPN_TYPE=${{VPN_TYPE_{node_number}}}
    volumes:
      - ./vpn_creds.txt:/vpn_creds.txt
      - ./ovpn_files:/ovpn_files
      - {public_ips_dir}:/shared/public_ips
    ports:
      - "{udp_port}:8080/udp"
      - "{tcp_port}:22/tcp"
      - "{socks_port}:9090/tcp"
    networks:
      vpn_network:
        ipv4_address: {ip_address}
    stdin_open: true
    tty: true
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://{ip_address}:8080 || exit 1"]  # Check if the service is running on the dynamically generated IP and port
      interval: 1m
      timeout: 10s
      retries: 3
      start_period: 30s
    """


def generate_docker_compose(number_of_nodes, start_udp_port=8081, start_tcp_port=2221, start_socks_port=9091, start_ip="172.18.0.2"):
    """
    Generates the docker-compose.yml file for a given number of VPN nodes with correct formatting.
    Includes placeholders for environment variables and ensures proper indentation and line breaks.
    """
    services = []
    ip_segments = start_ip.split(".")

    # Resolve the dynamic public_ips folder based on CWD
    public_ips_dir = Path.cwd() / "public_ips"

    for i in range(1, number_of_nodes + 1):
        node_udp_port = start_udp_port + i - 1
        node_tcp_port = start_tcp_port + i - 1
        node_socks_port = start_socks_port + i - 1
        node_ip = f"{ip_segments[0]}.{ip_segments[1]}.{ip_segments[2]}.{int(ip_segments[3]) + i - 1}"

        # Generate the VPN node configuration
        vpn_node_config = generate_vpn_node_config(i, node_udp_port, node_tcp_port, node_socks_port, node_ip, public_ips_dir)

        # Add the VPN node configuration to the services list
        services.append(vpn_node_config)

    # Compose the final docker-compose configuration
    docker_compose_content = f"version: '3'\nservices:\n{''.join(services)}"

    # Add the networks section at the bottom
    docker_compose_content += """
networks:
  vpn_network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.18.0.0/16
"""

    # Write the configuration to docker-compose.yml in the current working directory
    output_file = Path.cwd() / "docker-compose.yml"
    with open(output_file, 'w') as yaml_file:
        yaml_file.write(docker_compose_content)

    print(f"docker-compose.yml has been generated and saved to {output_file}.")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Generate a docker-compose.yml file for VPN nodes.")
    parser.add_argument("--nodes", type=int, default=1, help="Number of VPN nodes to generate.")
    args = parser.parse_args()

    # Generate the docker-compose.yml file with the specified number of nodes
    generate_docker_compose(args.nodes)

