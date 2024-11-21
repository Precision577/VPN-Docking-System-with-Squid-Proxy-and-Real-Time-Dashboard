#!/bin/bash

# VPN credentials in the current working directory (CWD)
VPN_CREDS="/etc/openvpn/vpn_creds.txt"

# Log file
LOG_FILE="/var/log/openvpn.log"
mkdir -p $(dirname "$LOG_FILE")  # Ensure the log directory exists

AUTH_FAILED_DETECTED=false
CLEANUP_FLAG=false


log_message() {
  local message="$1"
  echo "$message" | tee -a "$LOG_FILE"
}

# Function to determine and log the correct OVPN file
find_vpn_file() {
  echo "[INFO] Checking VPN_TYPE and determining the correct OVPN file directory..." | tee -a "$LOG_FILE"

  # Check the VPN_TYPE environment variable (either 'tcp' or 'udp')
  VPN_TYPE=${VPN_TYPE:-"udp"}  # Default to 'udp' if not set

  # Set the OVPN file directory based on VPN_TYPE
  if [ "$VPN_TYPE" = "tcp" ]; then
    OVPN_DIR="/etc/openvpn/ovpn_files/tcp"
    echo "[INFO] VPN_TYPE is set to 'tcp'. Looking for OVPN files in $OVPN_DIR" | tee -a "$LOG_FILE"
  elif [ "$VPN_TYPE" = "udp" ]; then
    OVPN_DIR="/etc/openvpn/ovpn_files/udp"
    echo "[INFO] VPN_TYPE is set to 'udp'. Looking for OVPN files in $OVPN_DIR" | tee -a "$LOG_FILE"
  else
    echo "[ERROR] Invalid VPN_TYPE value. Must be 'tcp' or 'udp'." | tee -a "$LOG_FILE"
    exit 1
  fi

  # Ensure VPN_FILE is set
  if [ -z "$VPN_FILE" ]; then
    echo "[ERROR] VPN_FILE environment variable not set!" | tee -a "$LOG_FILE"
    exit 1
  fi

  # Combine OVPN directory and VPN file name
  OVPN_FILE="$OVPN_DIR/$VPN_FILE"
  echo "[INFO] Checking if OVPN file exists at $OVPN_FILE" | tee -a "$LOG_FILE"

  # Check if the OVPN file exists
  if [ ! -f "$OVPN_FILE" ]; then
    echo "[ERROR] OVPN file $OVPN_FILE not found!" | tee -a "$LOG_FILE"
    exit 1
  else
    echo "[INFO] OVPN file $OVPN_FILE found." | tee -a "$LOG_FILE"
  fi
}

# Trap SIGINT and SIGTERM to ensure cleanup happens
trap 'cleanup; exit 1' SIGINT SIGTERM EXIT


cleanup() {
  echo "[INFO] Cleanup initiated..." | tee -a "$LOG_FILE"
  
  # Set the cleanup flag to true to prevent any new actions
  CLEANUP_FLAG=true

  # Kill OpenVPN process if running
  if [ -n "$OPENVPN_PID" ]; then
    if kill -0 $OPENVPN_PID 2>/dev/null; then
      echo "[INFO] Killing OpenVPN process with PID: $OPENVPN_PID" | tee -a "$LOG_FILE"
      kill $OPENVPN_PID
    fi
  fi

  # Kill Proxy process if running
  if [ -n "$PROXY_PID" ]; then
    if kill -0 $PROXY_PID 2>/dev/null; then
      echo "[INFO] Killing Proxy process with PID: $PROXY_PID" | tee -a "$LOG_FILE"
      kill $PROXY_PID
    fi
  fi

  # Ensure all tail processes are stopped
  pkill -P $$ tail

  # Additional cleanup steps if necessary
  echo "[INFO] Cleanup complete. Exiting now." | tee -a "$LOG_FILE"
}

# Call the function to find and verify the OVPN file
find_vpn_file


save_public_ip_file() {
  local node="$1"
  local vpn_file_name="$2"
  local public_ip="$3"
  local proxy_info="$4"
  local output_file="$SHARED_DIR/$node-ip.txt"

  # Prevent multiple writes to the file
  if [ -f "$output_file" ]; then
    echo "[INFO] File $output_file already exists. Skipping file write." | tee -a "$LOG_FILE"
    return 0
  fi

  # Extract just the port from the proxy_info (assumes format "Proxy running on 0.0.0.0:PORT")
  local proxy_port=$(echo "$proxy_info" | grep -oP ':\K[0-9]+')

  # Convert VPN_TYPE to uppercase
  local vpn_type_upper=$(echo "$VPN_TYPE" | tr '[:lower:]' '[:upper:]')

  # Save the file only when both VPN and Proxy setup succeeded
  if [ "$AUTH_FAILED_DETECTED" = false ] && [ "$PROXY_STARTED" = true ]; then
    # Append VPN_TYPE (uppercase) and proxy port information to the file content
    echo -e "Node: $node\nVPN File: $vpn_file_name\nVPN_TYPE: $vpn_type_upper\nPublic IP: $public_ip\nProxy Info: $proxy_port" > "$output_file"
    echo "[INFO] Public IP, VPN_TYPE, and Proxy Port written to $output_file successfully." | tee -a "$LOG_FILE"
  else
    echo -e "Node: $node\nVPN File: $vpn_file_name\nVPN_TYPE: $vpn_type_upper\nPublic IP: $public_ip\nProxy Info: $proxy_port" > "$output_file"
    echo "[INFO] Public IP, VPN_TYPE, and Proxy Port written to $output_file with failure status." | tee -a "$LOG_FILE"
  fi

  # Force sync to ensure the file is written to disk and visible on the host system
  sync
  sleep 1  # A small delay to ensure the sync completes
}






# Print start time and basic info
echo "[INFO] Script started at $(date)" | tee -a "$LOG_FILE"

# Check if the OVPN file exists
if [ ! -f "$OVPN_FILE" ]; then
  echo "[ERROR] OVPN file $OVPN_FILE not found!" | tee -a "$LOG_FILE"
  exit 1
else
  echo "[INFO] OVPN file $VPN_FILE exists." | tee -a "$LOG_FILE"
fi

# Create a temporary credentials file with restricted permissions
TEMP_CREDS=$(mktemp)
chmod 600 "$TEMP_CREDS"
cp "$VPN_CREDS" "$TEMP_CREDS"

# Read and echo the username and password for debugging purposes
USERNAME=$(sed -n '1p' "$TEMP_CREDS")
PASSWORD=$(sed -n '2p' "$TEMP_CREDS")

echo "[DEBUG] Using VPN credentials:"
echo "Username: $USERNAME"
echo "Password: $PASSWORD"

# Print container's network interface info for debugging
echo "[DEBUG] Checking network interfaces inside the container..." | tee -a "$LOG_FILE"
ip addr | tee -a "$LOG_FILE"
# Print routing table for debugging
echo "[DEBUG] Checking routing table inside the container..." | tee -a "$LOG_FILE"
ip route | tee -a "$LOG_FILE"

# Check DNS resolution (verify resolv.conf)
echo "[DEBUG] Checking DNS configuration (resolv.conf)..." | tee -a "$LOG_FILE"
cat /etc/resolv.conf | tee -a "$LOG_FILE"

# Function to check the public IP of the current container
check_public_ip() {
  if [ "$AUTH_FAILED_DETECTED" = true ]; then
    echo "[DEBUG] Skipping public IP check due to AUTH_FAILED." | tee -a "$LOG_FILE"
    return 1  # Skip further steps if AUTH_FAILED is detected
  fi

  echo "[INFO] Checking public IP..." | tee -a "$LOG_FILE"
  
  ip_services=(
    "https://api64.ipify.org"
    "https://checkip.amazonaws.com"
    "https://ifconfig.me"
    "https://ipinfo.io/ip"
  )

  for service in "${ip_services[@]}"; do
    echo "[DEBUG] Attempting to fetch public IP from: $service" | tee -a "$LOG_FILE"
    IP=$(curl -s $service)

    if [ -n "$IP" ]; then
      echo "[INFO] Successfully fetched public IP: $IP from $service" | tee -a "$LOG_FILE"
      return 0  # Success
    else
      echo "[ERROR] Failed to fetch public IP from $service" | tee -a "$LOG_FILE"
    fi
  done

  echo "[ERROR] Could not fetch public IP from any service." | tee -a "$LOG_FILE"
  return 1  # Failure to fetch public IP
}

# Check if the public IP of the current container matches the expected public IP
if check_public_ip; then
  echo "[INFO] Public IP matches VPN. Proceeding with OpenVPN setup." | tee -a "$LOG_FILE"
else
  echo "[ERROR] Unable to fetch public IP. Exiting." | tee -a "$LOG_FILE"
  exit 1
fi

# Set the absolute path for the shared directory on the host machine
SHARED_DIR="/home/idontloveyou/Desktop/LinuxServer1/freedomdata/storage/docker/public_ips"
PUBLIC_IP_FILE="$SHARED_DIR/$HOSTNAME-ip.txt"
VPN_FILE_NAME=$(basename "$OVPN_FILE")




start_openvpn() {
  echo "[INFO] Starting OpenVPN with $OVPN_FILE..." | tee -a "$LOG_FILE"

  # Start OpenVPN with logging and verbosity
  openvpn --config "$OVPN_FILE" --auth-user-pass "$TEMP_CREDS" --auth-nocache --verb 4 2>&1 | tee -a "$LOG_FILE" &

  # Capture the OpenVPN process ID
  OPENVPN_PID=$!

  # Tail the OpenVPN log to monitor connection and AUTH_FAILED
  tail_openvpn_log

  # If AUTH_FAILED is detected, ensure we do not continue
  if [ "$AUTH_FAILED_DETECTED" = true ]; then
    echo "[ERROR] AUTH_FAILED detected. Aborting further execution." | tee -a "$LOG_FILE"
    cleanup  # Ensure cleanup happens if OpenVPN fails
    kill -9 $$  # Forcefully terminate the script and all subprocesses
  fi
}

tail_openvpn_log() {
  log_message "[INFO] Monitoring OpenVPN log for exact 'AUTH_FAILED' detection or successful connection..."

  # Tailing the OpenVPN log and printing it in real-time
  tail -n +0 -f "$LOG_FILE" | while read -r line; do
    echo "$line" | tee -a "$LOG_FILE"  # Print each log line to the console and log file

    # Exact string matching for 'AUTH_FAILED'
    if echo "$line" | grep -q "^AUTH_FAILED$"; then
      log_message "[ERROR] Exact 'AUTH_FAILED' detected in OpenVPN log."

      # Log the specific line where AUTH_FAILED is detected for confirmation
      log_message "[DEBUG] Detected AUTH_FAILED line: $line"
      
      # Set AUTH_FAILED flag to true
      AUTH_FAILED_DETECTED=true

      # Save public IP as "Auth Failed" and exit immediately
      save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "Auth Failed" "Proxy setup failed"

      # Kill OpenVPN process if running
      if kill -0 $OPENVPN_PID 2>/dev/null; then
        log_message "[INFO] Killing OpenVPN process with PID: $OPENVPN_PID"
        kill $OPENVPN_PID
      fi

      # Cleanup and force exit
      log_message "[INFO] Exiting script due to AUTH_FAILED."
      cleanup  # Ensure cleanup happens immediately
      pkill -P $$ tail  # Kill tail processes
      kill -9 $$  # Forcefully terminate the current script and all its subprocesses
      break  # Stop tailing
    elif echo "$line" | grep -q "Initialization Sequence Completed"; then
      log_message "[INFO] OpenVPN connection established successfully."
      pkill -P $$ tail  # Stop tailing immediately after success
      break  # Stop tailing
    fi
  done
}



handle_vpn_failure() {
  if [ "$AUTH_FAILED_DETECTED" = true ]; then
    echo "[ERROR] OpenVPN failed due to AUTH_FAILED. Skipping further steps." | tee -a "$LOG_FILE"
    # Save public IP as "Auth Failed" when saving to the file
    save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "Auth Failed" "Proxy setup failed"
    cleanup  # Trigger cleanup immediately to stop further processes
    exit 1  # Exit after handling failure
  else
    echo "[ERROR] OpenVPN failed to start. Check the log file for details." | tee -a "$LOG_FILE"
    save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "VPN failed to start" "Proxy setup failed"
    sync
    cleanup
    exit 1
  fi
}



# Ensure the shared directory exists
mkdir -p "$SHARED_DIR"

# Start OpenVPN and monitor the logs
start_openvpn

PROXY_STARTED=false


start_proxy() {
  if [ "$PROXY_STARTED" = true ]; then
    echo "[ERROR] Proxy setup already initiated. Skipping duplicate setup." | tee -a "$LOG_FILE"
    return 1
  fi

  # Check if SOCKS_PORT environment variable is set
  if [ -z "$SOCKS_PORT" ]; then
    echo "[ERROR] SOCKS_PORT environment variable not set. Exiting." | tee -a "$LOG_FILE"
    cleanup
    exit 1
  fi

  PROXY_PORT=$SOCKS_PORT  
  echo "[INFO] Starting Squid proxy setup on port $PROXY_PORT..." | tee -a "$LOG_FILE"

  # Check if the port is already in use
  if lsof -i :$PROXY_PORT > /dev/null; then
    echo "[ERROR] Port $PROXY_PORT is already in use." | tee -a "$LOG_FILE"
    cleanup
    exit 1
  else
    echo "[INFO] Port $PROXY_PORT is available." | tee -a "$LOG_FILE"
  fi

  # Replace the port in the Squid configuration file before starting Squid
  sed -i "s/^http_port .*/http_port $PROXY_PORT/" /etc/squid/squid.conf

  # Print the configuration being used for verification
  echo "[INFO] Using Squid configuration file:" | tee -a "$LOG_FILE"
  cat /etc/squid/squid.conf | tee -a "$LOG_FILE"

  # Start Squid using the configuration file
  squid -f /etc/squid/squid.conf -NYCd1 2>&1 | tee -a "$LOG_FILE" &

  PROXY_PID=$!
  sleep 2

  # Ensure the proxy started successfully by checking if Squid is running
  if kill -0 $PROXY_PID > /dev/null 2>&1; then
    echo "[INFO] Squid proxy is running on 0.0.0.0:$PROXY_PORT with PID: $PROXY_PID" | tee -a "$LOG_FILE"
    PROXY_STARTED=true
    save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "$IP" "Squid proxy running on 0.0.0.0:$PROXY_PORT"
  else
    echo "[ERROR] Failed to start the Squid proxy!" | tee -a "$LOG_FILE"
    cleanup
    exit 1
  fi
}















# Ensure OpenVPN and proxy setup run only once, and save the correct information after success
if [ "$AUTH_FAILED_DETECTED" = false ]; then
  echo "[INFO] OpenVPN setup completed. Proceeding with public IP check and proxy setup." | tee -a "$LOG_FILE"

  # Check public IP after OpenVPN initialization
  echo "[INFO] Checking public IP after OpenVPN initialization..." | tee -a "$LOG_FILE"
  if check_public_ip; then
    echo "[INFO] Public IP matches VPN. Proceeding with proxy setup." | tee -a "$LOG_FILE"
    
    # Start the proxy setup only if it has not been started yet
    if [ "$PROXY_STARTED" = false ]; then
      start_proxy
    fi

    # Check if the proxy setup was successful
    if [ "$PROXY_STARTED" = true ]; then
      echo "[INFO] Proxy setup successful." | tee -a "$LOG_FILE"
      save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "$IP" "Proxy running on 0.0.0.0:$PROXY_PORT"
    else
      echo "[ERROR] Proxy setup failed. Saving file with failure info." | tee -a "$LOG_FILE"
      save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "$IP" "Proxy setup failed"
      cleanup
      exit 1
    fi

  else
    echo "[ERROR] Failed to retrieve public IP after VPN setup. Saving failure info." | tee -a "$LOG_FILE"
    save_public_ip_file "$HOSTNAME" "$VPN_FILE_NAME" "Public IP fetch failed" "Proxy setup failed"
    cleanup
    exit 1
  fi
else
  echo "[ERROR] OpenVPN failed. Skipping proxy setup." | tee -a "$LOG_FILE"
  cleanup  # Ensure cleanup happens immediately if AUTH_FAILED
  exit 1
fi

# Wait for OpenVPN process to exit
wait $OPENVPN_PID
cleanup

echo "[INFO] OpenVPN process has terminated. Exiting container." | tee -a "$LOG_FILE"


