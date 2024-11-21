#!/home/idontloveyou/miniconda/bin/python3.11
import csv
import os
from pathlib import Path
import sys
import traceback

from datetime import datetime, timedelta

# CSV file path
csv_file = Path("./vpn_nodes_info.csv")





def create_csv_with_headers(headers):
    """
    Create a new CSV file with the provided headers.
    """
    print(f"[DEBUG] CSV file '{csv_file}' does not exist. Creating with headers.")
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(headers)

def read_csv():
    """
    Read the CSV file and return the rows.
    """
    try:
        with open(csv_file, mode='r', newline='') as file:
            reader = csv.reader(file)
            rows = list(reader)
        return rows
    except Exception as e:
        print(f"[ERROR] Failed to read CSV file: {e}")
        traceback.print_exc()
        return []

def validate_headers(rows, expected_headers):
    """
    Validate the headers of the CSV file. If headers are missing or incorrect, return the updated rows.
    """
    # If the file is empty or the first row does not match the expected headers
    if not rows or rows[0] != expected_headers:
        print(f"[WARNING] CSV headers are missing or incorrect. Adding headers.")
        
        # Check if there is any data present in the file and preserve it
        if rows and rows[0] != expected_headers:
            # Insert headers and preserve the existing rows
            return [expected_headers] + rows
        else:
            # No data, just add headers
            return [expected_headers]

    # If headers match but the 'Last Updated' column is missing, append it.
    if len(rows[0]) != len(expected_headers):
        print(f"[WARNING] CSV headers are missing the 'Last Updated' column. Adding it.")
        # Add 'Last Updated' column and update rows accordingly
        for i in range(len(rows)):
            if len(rows[i]) == len(expected_headers) - 1: 
                rows[i].append('N/A' if i != 0 else expected_headers[-1])  # Add placeholder or column name

    return rows


def write_csv(rows):
    """
    Write the provided rows back to the CSV file.
    """
    print(f"[DEBUG] Writing data back to CSV file.")
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(rows)


def ensure_csv_with_headers():
    """
    Ensure the CSV file exists with the correct headers and data integrity,
    including the new 'Personal IP' column and 'Raw Timestamp'.
    """
    expected_headers = ['Node Name', 'Personal IP', 'VPN File', 'Public IP', 'VPN_TYPE', 'Status', 
                        'Connectivity', 'Container ID', 'Open Port', 'Proxy Info', 
                        'SOCKS5 Port', 'Last Updated', 'Raw Timestamp']  # Added Raw Timestamp

    if not csv_file.exists():
        create_csv_with_headers(expected_headers)
        return  # Headers created, no need for further action.

    # Read the CSV and validate headers
    rows = read_csv()
    updated_rows = validate_headers(rows, expected_headers)

    if updated_rows != rows:
        write_csv(updated_rows)
    else:
        print(f"[DEBUG] Headers are already present and correct.")







def ensure_correct_row_length(row):
    """
    Ensure each row has the correct number of columns, including the 'Personal IP' column.
    Dynamically assign 'Personal IP' based on the node number in the 'Node Name'.
    """
    # Ensure the row has the required number of columns
    while len(row) < 12:  
        row.append('N/A')

    # Extract the node number from the node name (e.g., vpn_node_1 -> 1)
    node_name = row[0]
    if node_name.startswith("vpn_node_"):
        try:
            node_number = int(node_name.split('_')[-1])  # Extract the node number
            row[1] = f"127.0.0.{node_number}"  # Dynamically assign Personal IP based on the node number
        except (ValueError, IndexError):
            print(f"[ERROR] Invalid node name format: {node_name}")
            row[1] = "127.0.0.0"  # Default IP in case of error
    else:
        row[1] = "127.0.0.0"  # Default IP if the node name doesn't match the expected format

    return row





def ensure_all_nodes_present(rows):
    """
    Ensure that all nodes are ordered as vpn_node_1, vpn_node_2, vpn_node_3, vpn_node_4.
    This function prioritizes sorting by node number and ensures the Public IP remains with the node.
    """
    # Extract header and body
    header = rows[0]
    body = rows[1:]  # Skip the header

    # Sort the body based on node number (assuming the format is 'vpn_node_X')
    sorted_body = sorted(body, key=lambda row: int(row[0].split('_')[-1]) if row[0].startswith('vpn_node_') else float('inf'))

    # Return the updated rows with the header and sorted body
    return [header] + sorted_body


def group_nodes_by_vpn_file(rows):
    """
    Group VPN nodes based on their VPN file, ensuring UDP and TCP pairs are listed together,
    and prioritize vpn_node_1, vpn_node_2, vpn_node_3, vpn_node_4, etc. Ensure Public IP stays with the correct node.
    """
    vpn_file_map = {}
    header = rows[0]

    # Map each row based on its VPN file (normalize the VPN file name by removing '-tcp' and '-udp')
    for row in rows[1:]:
        vpn_file_base = row[2].replace('-tcp', '').replace('-udp', '')  # VPN file is in column 3 (index 2)
        if vpn_file_base not in vpn_file_map:
            vpn_file_map[vpn_file_base] = []
        vpn_file_map[vpn_file_base].append(row)

    # Sort nodes within each VPN file group by node number to ensure correct order and Public IP alignment
    grouped_rows = []
    for vpn_file_base, node_group in vpn_file_map.items():
        sorted_group = sorted(node_group, key=lambda row: int(row[0].split('_')[-1]))
        grouped_rows.extend(sorted_group)

    # Return rows with the header and the grouped, sorted body
    return [header] + grouped_rows





def remove_inactive_exited_nodes(rows):
    """
    Removes nodes with "Exited" status if they've been inactive for more than 2 minutes.
    """
    updated_rows = []
    current_time = datetime.now()

    for row in rows[1:]:  # Skip the header row
        if row[5] == "Exited":  # Check the 'Status' column
            last_updated_time = datetime.strptime(row[11], '%Y-%m-%d %H:%M:%S')
            if current_time - last_updated_time > timedelta(minutes=2):
                print(f"[DEBUG] Node {row[0]} has been inactive for more than 2 minutes. Removing it.")
                continue  # Skip this row to effectively delete it
        updated_rows.append(row)

    return [rows[0]] + updated_rows  # Return rows with the header


def format_time_difference(last_updated):
    """
    Given a timestamp for 'Last Updated', return a human-readable string like:
    - 'x seconds ago' if less than 60 seconds,
    - 'x minutes ago' if less than 60 minutes,
    - 'x hours ago' if less than 24 hours,
    - 'x days ago' if more than 24 hours.
    """
    current_time = datetime.now()
    last_updated_time = datetime.strptime(last_updated, '%Y-%m-%d %H:%M:%S')
    time_diff = current_time - last_updated_time
    seconds = time_diff.total_seconds()

    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)} minutes ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)} hours ago"
    else:
        return f"{int(seconds // 86400)} days ago"


def update_csv(node_name, vpn_file, public_ip, vpn_type, status, connectivity, container_id, open_port, proxy_info, socks5_port):
    updated = False

    # Ensure headers are present in the CSV
    ensure_csv_with_headers()
    rows = read_csv()

    print(f"[DEBUG] Values passed in:")
    print(f"Node Name: {node_name}, VPN File: {vpn_file}, Public IP: {public_ip}, VPN_TYPE: {vpn_type}, Status: {status}, Connectivity: {connectivity}, Container ID: {container_id}, Open Port: {open_port}, Proxy Info: {proxy_info}, SOCKS5 Port: {socks5_port}")

    # Sanitize inputs
    vpn_file = vpn_file.strip().replace('\n', ' ') if vpn_file else "N/A"
    public_ip = public_ip.strip().replace('\n', ' ') if public_ip else "N/A"
    vpn_type = vpn_type.strip().replace('\n', ' ') if vpn_type else "N/A"
    proxy_info = proxy_info.strip().replace('\n', ' ') if proxy_info else "Disconnected"

    # Initialize port values (first node starts at these values)
    last_open_port = 8080
    last_socks5_port = 9090

    # Check the last used port in the CSV file
    for row in rows[1:]:  # Skip header
        if row[8].isdigit() and row[10].isdigit():  # Open Port and SOCKS5 Port should be digits
            last_open_port = max(last_open_port, int(row[8]))
            last_socks5_port = max(last_socks5_port, int(row[10]))

    # Assign default ports for vpn_node_1 or increment ports for other nodes
    if node_name == "vpn_node_1":
        open_port = str(open_port if open_port and open_port != 'NaN' else last_open_port)
        socks5_port = str(socks5_port if socks5_port and socks5_port != 'NaN' else last_socks5_port)
        personal_ip = "127.0.0.1"
    else:
        last_open_port += 1  # Increment for the next node
        last_socks5_port += 1
        open_port = str(open_port if open_port and open_port != 'NaN' else last_open_port)
        socks5_port = str(socks5_port if socks5_port and socks5_port != 'NaN' else last_socks5_port)
        personal_ip = f"127.0.0.{len(rows)}"  # Increment Personal IP for subsequent nodes

    # Convert ports to integers to ensure they don't have decimals
    open_port = str(int(open_port))
    socks5_port = str(int(socks5_port))

    status = status.capitalize()
    current_time = datetime.now()

    # Search for the node in the existing rows
    for index, row in enumerate(rows):
        if row[0] == node_name:
            print(f"[DEBUG] Found existing row for node {node_name}. Updating row.")
            row = ensure_correct_row_length(row)  # Ensure the row length and assign the correct 'Personal IP'

            # Update the rest of the row with new values
            row[2] = vpn_file  
            row[3] = public_ip  
            row[4] = vpn_type  
            row[5] = status
            row[6] = connectivity
            row[7] = container_id if container_id else row[7]
            row[8] = open_port  # Ensure port is an integer and no decimals
            row[9] = proxy_info  
            row[10] = socks5_port  # Ensure port is an integer and no decimals
            row[11] = format_time_difference(current_time.strftime('%Y-%m-%d %H:%M:%S'))  # Human-readable time diff
            row[12] = current_time.strftime('%Y-%m-%d %H:%M:%S')  # Raw timestamp for future calculations
            updated = True
            break


    # If no matching node was found, append a new row
    if not updated:
        print(f"[DEBUG] No existing row found for node {node_name}. Adding new row.")
        new_row = [node_name, f"127.0.0.{int(node_name.split('_')[-1])}", vpn_file, public_ip, vpn_type, status, 
                   connectivity, container_id, open_port, proxy_info, socks5_port, 
                   format_time_difference(current_time.strftime('%Y-%m-%d %H:%M:%S')),  # Human-readable time diff
                   current_time.strftime('%Y-%m-%d %H:%M:%S')]  # Raw timestamp
        rows.append(new_row)


    # Ensure nodes are grouped and ordered correctly
    rows = ensure_all_nodes_present(rows)
    rows = group_nodes_by_vpn_file(rows)

    # Write the updated rows back to the CSV
    write_csv(rows)
    print(f"[DEBUG] Successfully updated CSV file.")








if __name__ == "__main__":
    try:
        # Parse command-line arguments
        if len(sys.argv) != 11:  # Adjusted to 11 arguments to include VPN_TYPE
            print(f"[ERROR] Incorrect number of arguments: {len(sys.argv)}")
            print("Usage: update_vpn_info.py <Node Name> <VPN File> <Public IP> <VPN_TYPE> <Status> <Connectivity> <Container ID> <Open Port> <Proxy Info> <SOCKS5 Port>")
            sys.exit(1)

        node_name = sys.argv[1]
        vpn_file = sys.argv[2]
        public_ip = sys.argv[3]
        vpn_type = sys.argv[4]  # New VPN_TYPE argument
        status = sys.argv[5]
        connectivity = sys.argv[6]
        container_id = sys.argv[7]
        open_port = sys.argv[8]
        proxy_info = sys.argv[9]
        socks5_port = sys.argv[10]

        # Update the CSV file
        print(f"[DEBUG] Updating CSV with node {node_name}.")
        update_csv(node_name, vpn_file, public_ip, vpn_type, status, connectivity, container_id, open_port, proxy_info, socks5_port)

    except Exception as e:
        print(f"[ERROR] Exception occurred in main execution: {e}")
        traceback.print_exc()

