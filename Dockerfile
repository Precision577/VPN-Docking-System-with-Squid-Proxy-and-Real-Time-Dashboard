# Stage 1: Base setup for Squid and VPN
FROM ubuntu:22.04 AS build

# Install wget, tar, and dependencies for building Squid
RUN apt-get update && \
    apt-get install -y wget tar git build-essential libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Squid and required libraries
RUN apt-get update && \
    apt-get install -y squid libecap3 libxml2 libexpat1 libnetfilter-conntrack3 libltdl7 squid-common && \
    rm -rf /var/lib/apt/lists/*

# Copy Squid config file into the build stage temporarily
COPY squid.conf /tmp/squid.conf

# Stage 2: Final Image - install only required tools
FROM ubuntu:22.04

# Install necessary packages without parallelization
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    openssl \
    ca-certificates \
    sudo \
    gnupg \
    iproute2 \
    openvpn \
    lsof \
    net-tools \
    tar \
    wget \
    libecap3 \
    libxml2 \
    libexpat1 \
    libnetfilter-conntrack3 \
    libltdl7 \
    squid squid-common && \
    rm -rf /var/lib/apt/lists/*

# Copy Squid and its config file from the build stage
COPY --from=build /usr/sbin/squid /usr/sbin/squid
COPY --from=build /tmp/squid.conf /etc/squid/squid.conf

# Ensure certificates are updated within the container
RUN update-ca-certificates

# Copy VPN credentials and OVPN files
COPY vpn_creds.txt /etc/openvpn/vpn_creds.txt
COPY ovpn_files /etc/openvpn/ovpn_files/

# Ensure proper permissions for VPN credentials and OVPN files
RUN chmod 600 /etc/openvpn/vpn_creds.txt && \
    chmod 600 /etc/openvpn/ovpn_files/*
RUN chmod 644 /etc/squid/squid.conf

# Copy scripts to the container
COPY fix_openvpn.sh /usr/local/bin/fix_openvpn.sh
COPY start_vpn.sh /usr/local/bin/start_vpn.sh
COPY start_proxy.sh /usr/local/bin/start_proxy.sh

# Set executable permissions on the scripts
RUN chmod +x /usr/local/bin/fix_openvpn.sh /usr/local/bin/start_vpn.sh /usr/local/bin/start_proxy.sh

# Create a normal user with a home directory
RUN useradd -ms /bin/bash normaluser

# Create a directory for OpenVPN logs and Squid logs
RUN mkdir -p /var/log/openvpn /var/log/squid

# Set the entry point to the VPN startup script
ENTRYPOINT ["/usr/local/bin/start_vpn.sh"]

