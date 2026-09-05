# utils/admin_utils.py
import os
from pathlib import Path
import re

SERVERS_FILE = Path(__file__).parent.parent / "configs" / "premium.conf"

def get_servers_from_file():
    if not SERVERS_FILE.exists():
        return []
    servers = []
    with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    server_id = 1
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            server_name = extract_server_name(line)
            servers.append({
                "id": server_id,
                "name": server_name,
                "full": line
            })
            server_id += 1
    return servers

def extract_server_name(line: str) -> str:
    if '#' in line:
        parts = line.split('#')
        if len(parts) > 1:
            return parts[-1].strip()
    return line[:50] + "..." if len(line) > 50 else line

def get_full_config_content():
    servers = get_servers_from_file()
    content = []
    for server in servers:
        content.append(server["full"])
    return "\n".join(content)

def add_server_to_file(server_link: str):
    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SERVERS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{server_link}\n")

def remove_server_from_file(server_id: int):
    if not SERVERS_FILE.exists():
        return
    with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    config_lines = []
    for line in lines:
        line_stripped = line.strip()
        if line_stripped and not line_stripped.startswith('#'):
            config_lines.append(line)
    
    if 1 <= server_id <= len(config_lines):
        config_lines.pop(server_id - 1)
    
    with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
        for line in config_lines:
            f.write(line)

def clear_servers_file():
    if SERVERS_FILE.exists():
        SERVERS_FILE.unlink()
        SERVERS_FILE.touch()