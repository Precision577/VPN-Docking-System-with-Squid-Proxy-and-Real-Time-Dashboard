# VPN Docking System with Squid Proxy and Real-Time Dashboard

## Project Overview
This project is a powerful, modular, and scalable VPN docking system designed to manage multiple VPN connections simultaneously. It achieves the following:

- **110 Unique Proxies:** Establishes 55 Private Internet Access (PIA) OpenVPN connections for both UDP and TCP (one per PIA server location).
- **Dynamic Proxy Management:** Combines these connections with Squid proxy to expose them as SOCKS5 proxies.
- **Real-Time Monitoring:** Includes a Streamlit-based dashboard for live updates and detailed status monitoring of all nodes.

### Use Cases
This system is ideal for:
- **Web scraping** across diverse IPs.
- **Bypassing geolocation restrictions.**
- **Load balancing** with unique proxy setups.

---

## Features
- **110 Proxies:** 55 for UDP and 55 for TCP, each with unique public IPs.
- **Dynamic Configuration:** Nodes can be scaled by modifying configuration files.
- **Resilient Design:** Automatic retries for failed nodes, real-time updates via WebSockets, and robust error handling.
- **Interactive Dashboard:** A visually appealing dashboard to track node statuses, public IPs, and proxy information.

---

## Technologies and Frameworks Used

### Programming Languages
- **Python 3.11:** Core logic for node management, monitoring, and communication.
- **Bash:** Auxiliary scripts for container setup and Squid proxy configuration.

### Frameworks and Libraries

#### Node Management
- **Docker SDK:**
  - Handles creation, management, and cleanup of containers.
  - Dynamically maps ports for VPN and proxy services.
- **OpenVPN:** Establishes secure and reliable VPN connections.

#### Proxy Management
- **Squid Proxy:**
  - Dynamically configured for SOCKS5 proxies on unique ports for each node.

#### Real-Time Monitoring
- **Streamlit:** 
  - Builds the live dashboard with real-time updates.
  - Provides user-friendly visualization for node statuses.
- **FastAPI:** Manages WebSocket communication for instant updates.
- **Watchdog:** Monitors CSV file changes and triggers dashboard updates dynamically.

#### Concurrency
- **Concurrent Futures:** Enables multi-threaded execution for efficient container management.
- **ThreadPoolExecutor:** Parallelizes node creation and monitoring for high performance.

#### Data Processing
- **Pandas:** Parses and processes CSV data for dashboard insights.
- **Hashlib:** Ensures file integrity through checksum generation.

#### Other Libraries
- **Pathlib:** Simplifies cross-platform file path handling.
- **Streamlit Autorefresh:** Ensures the dashboard stays up-to-date without manual refresh.

---

## System Architecture

### 1. Node Management
**File:** `manage_vpns.py`  
**Functionality:**
- Initializes and manages Docker containers running OpenVPN and Squid proxy.
- Dynamically assigns unique ports to each container.
- Periodically cleans up inactive or failed containers.

### 2. Node Setup
**File:** `build_vpn_nodes.py`  
**Functionality:**
- Pairs UDP and TCP `.ovpn` files by server location.
- Configures and launches Docker containers with proper VPN and Squid settings.

### 3. Real-Time Dashboard
**File:** `csv_dashboard.py`  
**Functionality:**
- Displays node statuses, proxy ports, and public IPs in an interactive dashboard.
- Provides real-time metrics like the number of active nodes and their statuses.

### 4. WebSocket Communication
**File:** `websocket_server.py`  
**Functionality:**
- Sends updates to the dashboard whenever the node status CSV file changes.

---

## Setup Instructions

### 1. Prerequisites
#### Install Docker and Docker Compose:
```bash
sudo apt-get install docker docker-compose -y
```

#### Install Python 3.11 and Pip:
```bash
sudo apt-get install python3.11 python3-pip -y
```

#### Install required Python libraries:
```bash
pip install -r requirements.txt
```

---

### 2. Setting Up Credentials
Create a file named `vpn_creds.txt` in the project root directory with the following format:
```text
username (replace with actual username)
password (replace with actual password)
```
Replace `username` and `password` with your actual PIA credentials.

---

### 3. Running the System

#### Step 1: Start the WebSocket Server
```bash
python3 websocket_server.py
```
This launches the WebSocket server, enabling real-time updates to the dashboard.

#### Step 2: Launch the Real-Time Dashboard
```bash
streamlit run csv_dashboard.py
```
This opens the Streamlit-based dashboard in your default browser for monitoring node statuses.

#### Step 3: Start Managing VPN Nodes
```bash
python3 manage_vpns.py
```
This script initializes the system, creates Docker containers, and starts managing VPN nodes.

---

### 4. Optional Configuration

#### Adjust Node Counts:
Modify the `DEFAULT_UDP_NODES` and `DEFAULT_TCP_NODES` constants in `manage_vpns.py` to set the number of nodes for each type.

#### Custom Ports:
Update `SOCKS5_START_PORT` and `UDP_START_PORT` in `manage_vpns.py` to change the starting ports for proxies.

---

## Key Functionalities

### 1. Container Management
- **Automatic Cleanup:** Removes inactive or failed containers.
- **Dynamic Initialization:** Creates containers with unique UDP/TCP ports and SOCKS5 proxies.

### 2. Proxy Integration
- **Squid Configuration:** Dynamically assigns ports for each proxy.
- **SOCKS5 Integration:** Configures Squid to expose proxies as SOCKS5 connections.

### 3. Real-Time Updates
- **WebSocket Communication:** Provides instant updates to the dashboard when node statuses change.
- **Auto-Refresh:** Automatically refreshes the dashboard to display the latest data.

### 4. Dashboard Insights
- **Node Status:** Displays statuses such as "Running," "Disconnected," or "Failed."
- **Proxy Details:** Shows public IPs and proxy ports for each node.

---

## Example Use Case
1. Configure PIA `.ovpn` files for 55 server locations.
2. Run all three scripts in order:
   - WebSocket server for updates.
   - Dashboard for monitoring.
   - VPN manager to initialize nodes.
3. Access 110 unique proxies for web scraping tasks.

---

## Conclusion
This project showcases expertise in:
- **Network Automation:** Using Docker, OpenVPN, and Squid to create scalable proxy setups.
- **Real-Time Monitoring:** Implementing WebSocket-based updates and dynamic dashboards.
- **Concurrency and Parallelism:** Leveraging Python's threading and async features for efficient execution.

This VPN docking system is complete, robust, and ready for deployment in real-world scenarios.
