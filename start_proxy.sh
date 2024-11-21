#!/bin/bash

# Log file for proxy setup
PROXY_LOG="/var/log/proxy_setup.log"
mkdir -p $(dirname "$PROXY_LOG")  # Ensure the log directory exists

# Ensure we have a valid port as an argument
if [ -z "$1" ]; then
  echo "[ERROR] No port specified for proxy setup!" | tee -a "$PROXY_LOG"
  echo "[EXIT] Exiting due to missing port argument." | tee -a "$PROXY_LOG"
  exit 1
fi

PROXY_PORT=$1
echo "[INFO] Starting proxy setup on port $PROXY_PORT..." | tee -a "$PROXY_LOG"

# Fetch the public IP of the container
echo "[INFO] Fetching public IP address..." | tee -a "$PROXY_LOG"
PUBLIC_IP=$(curl -s ifconfig.me)
if [ -z "$PUBLIC_IP" ]; then
  echo "[ERROR] Failed to retrieve public IP address!" | tee -a "$PROXY_LOG"
  exit 1
fi
echo "[INFO] Public IP address of container: $PUBLIC_IP" | tee -a "$PROXY_LOG"

# Function to debug network interfaces and routing table
debug_network_info() {
  echo "[DEBUG] Checking network interfaces inside the container..." | tee -a "$PROXY_LOG"
  ip addr | tee -a "$PROXY_LOG"

  echo "[DEBUG] Checking routing table inside the container..." | tee -a "$PROXY_LOG"
  ip route | tee -a "$PROXY_LOG"

  echo "[DEBUG] Checking DNS configuration (resolv.conf)..." | tee -a "$PROXY_LOG"
  cat /etc/resolv.conf | tee -a "$PROXY_LOG"
}

# Run initial network debugging information
debug_network_info

# Bind the proxy on all interfaces (0.0.0.0) for SOCKS5, instead of localhost
echo "[INFO] Attempting to bind SOCKS proxy on 0.0.0.0:$PROXY_PORT..." | tee -a "$PROXY_LOG"

# Start socat to listen for SOCKS5 proxy connections and capture both stdout and stderr
socat TCP4-LISTEN:$PROXY_PORT,fork SOCKS5-LISTEN:0.0.0.0:$PROXY_PORT,socksport=$PROXY_PORT 2>&1 | tee -a "$PROXY_LOG" &

PROXY_PID=$!
sleep 2  # Wait a little for socat to initialize

# Tail the log to dynamically capture the output and ensure real-time feedback
tail -f "$PROXY_LOG" &
TAIL_PID=$!

# Debugging: Check if the socat process is running
if ! kill -0 $PROXY_PID > /dev/null 2>&1; then
  echo "[ERROR] Failed to start the proxy! socat process is not running." | tee -a "$PROXY_LOG"
  
  # Add additional lsof debugging if needed
  echo "[DEBUG] Attempting to debug using lsof output for port $PROXY_PORT..." | tee -a "$PROXY_LOG"
  lsof -i :$PROXY_PORT | tee -a "$PROXY_LOG"
  
  echo "Proxy Info: Proxy setup failed" | tee -a "$PROXY_LOG"
  echo "[EXIT] Exiting with failure due to socat not running." | tee -a "$PROXY_LOG"
  kill $TAIL_PID  # Stop tailing the log
  exit 1  # Failure
fi

# Check if the port is in use and confirm the proxy is bound
if lsof -i :$PROXY_PORT > /dev/null; then
  echo "[INFO] Proxy is running on 0.0.0.0:$PROXY_PORT with PID: $PROXY_PID" | tee -a "$PROXY_LOG"
  echo "[INFO] Public IP Address: $PUBLIC_IP" | tee -a "$PROXY_LOG"  # Log the public IP
  echo "Proxy Info: 0.0.0.0:$PROXY_PORT" | tee -a "$PROXY_LOG"
  echo "[EXIT] Exiting successfully." | tee -a "$PROXY_LOG"
  kill $TAIL_PID  # Stop tailing the log
  exit 0  # Success
else
  echo "[ERROR] Proxy is not running or the port is not bound!" | tee -a "$PROXY_LOG"
  
  # Add final debugging output for troubleshooting
  echo "[DEBUG] Verifying active connections and bound ports using netstat..." | tee -a "$PROXY_LOG"
  netstat -tuln | grep $PROXY_PORT | tee -a "$PROXY_LOG"
  
  echo "Proxy Info: Proxy setup failed" | tee -a "$PROXY_LOG"
  echo "[EXIT] Exiting with failure due to port binding issue." | tee -a "$PROXY_LOG"
  kill $TAIL_PID  # Stop tailing the log
  exit 1  # Failure
fi

