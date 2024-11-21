#!/bin/bash

# Create the /dev/net directory and the /dev/net/tun device node
echo "[INFO] Setting up /dev/net/tun device..."
mkdir -p /dev/net
mknod /dev/net/tun c 10 200
chmod 600 /dev/net/tun


