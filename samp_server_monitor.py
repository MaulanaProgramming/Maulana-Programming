#!/usr/bin/env python3
"""
SA-MP Server Monitor with Discord Integration
Monitors SA-MP server status, player count, and sends alerts via Discord webhook
"""

import socket
import struct
import time
import logging
import json
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple
import requests
from requests.exceptions import RequestException
from abc import ABC


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('samp_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SAMPQueryException(Exception):
    """Custom exception for SAMP query errors"""
    pass


class SAMPServerQuery:
    """
    SA-MP Server Query Protocol Implementation
    Queries SA-MP servers for server information and player details
    """
    
    SAMP_QUERY_CONNECT = b'SAMP\x00\x00\x00\x00'
    SAMP_INFO_REQUEST = b'serverinfo'
    SAMP_PLAYERS_REQUEST = b'players'
    SAMP_PING_REQUEST = b'ping'
    
    def __init__(self, host: str, port: int, timeout: int = 5):
        """
        Initialize SAMP Query client
        
        Args:
            host: Server hostname or IP address
            port: Server port
            timeout: Query timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def _send_query(self, opcode: str) -> Optional[str]:
        """
        Send a query to the SAMP server
        
        Args:
            opcode: Query opcode (serverinfo, players, ping)
            
        Returns:
            Response string or None if failed
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # Build query packet
            query_packet = self.SAMP_QUERY_CONNECT + opcode.encode() + b'\x00'
            
            # Send query
            sock.sendto(query_packet, (self.host, self.port))
            
            # Receive response
            response, _ = sock.recvfrom(4096)
            sock.close()
            
            return response.decode('utf-8', errors='ignore')
        
        except socket.timeout:
            logger.warning(f"Query timeout for {self.host}:{self.port}")
            raise SAMPQueryException(f"Query timeout: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Query failed for {self.host}:{self.port}: {str(e)}")
            raise SAMPQueryException(f"Query failed: {str(e)}")
    
    def get_server_info(self) -> Optional[Dict]:
        """
        Get server information
        
        Returns:
            Dictionary with server info or None if failed
        """
        try:
            response = self._send_query('serverinfo')
            if not response:
                return None
            
            # Parse response (basic parsing - adjust based on actual protocol)
            info = {
                'host': self.host,
                'port': self.port,
                'timestamp': datetime.utcnow().isoformat(),
                'online': True
            }
            return info
        
        except SAMPQueryException:
            return None
    
    def get_player_count(self) -> Optional[int]:
        """
        Get current player count
        
        Returns:
            Player count or None if failed
        """
        try:
            response = self._send_query('players')
            if not response:
                return None
            
            # Extract player count from response
            # This is a basic implementation - adjust based on protocol
            return len(response.split('\n')) - 1
        
        except SAMPQueryException:
            return None
    
    def ping(self) -> Optional[int]:
        """
        Ping the server and get response time
        
        Returns:
            Ping time in milliseconds or None if failed
        """
        try:
            start = time.time()
            self._send_query('ping')
            ping = int((time.time() - start) * 1000)
            return ping
        
        except SAMPQueryException:
            return None


class DiscordNotifier:
    """
    Handles Discord webhook notifications for server alerts
    """
    
    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier
        
        Args:
            webhook_url: Discord webhook URL
        """
        self.webhook_url = webhook_url
    
    def send_alert(self, title: str, description: str, color: int = 0xFF0000,
                   fields: Optional[list] = None) -> bool:
        """
        Send an alert to Discord
        
        Args:
            title: Alert title
            description: Alert description
            color: Embed color (default: red)
            fields: List of field dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "footer": {
                    "text": "SA-MP Server Monitor"
                }
            }
            
            if fields:
                embed["fields"] = fields
            
            payload = {
                "embeds": [embed]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Discord alert sent: {title}")
                return True
            else:
                logger.error(f"Failed to send Discord alert: {response.status_code}")
                return False
        
        except RequestException as e:
            logger.error(f"Error sending Discord alert: {str(e)}")
            return False
    
    def send_status_update(self, server_name: str, status: str, player_count: int,
                          max_players: int, ping: Optional[int] = None) -> bool:
        """
        Send server status update to Discord
        
        Args:
            server_name: Server name
            status: Server status (Online/Offline)
            player_count: Current player count
            max_players: Maximum players
            ping: Server ping in ms
            
        Returns:
            True if successful, False otherwise
        """
        color = 0x00FF00 if status == "Online" else 0xFF0000
        
        fields = [
            {
                "name": "Status",
                "value": status,
                "inline": True
            },
            {
                "name": "Players",
                "value": f"{player_count}/{max_players}",
                "inline": True
            }
        ]
        
        if ping is not None:
            fields.append({
                "name": "Ping",
                "value": f"{ping}ms",
                "inline": True
            })
        
        return self.send_alert(
            title=f"SA-MP Server: {server_name}",
            description=f"Server Status Update",
            color=color,
            fields=fields
        )


class ServerMonitor:
    """
    Main server monitoring class
    Coordinates SA-MP server queries and Discord notifications
    """
    
    def __init__(self, config_file: str = 'monitor_config.json'):
        """
        Initialize server monitor
        
        Args:
            config_file: Path to configuration JSON file
        """
        self.config = self._load_config(config_file)
        self.notifier = DiscordNotifier(self.config['discord_webhook'])
        self.monitoring = False
        self.server_states = {}
    
    def _load_config(self, config_file: str) -> Dict:
        """
        Load configuration from JSON file
        
        Args:
            config_file: Path to config file
            
        Returns:
            Configuration dictionary
        """
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"Configuration loaded from {config_file}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_file}")
            return self._get_default_config()
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in config file: {config_file}")
            return self._get_default_config()
    
    @staticmethod
    def _get_default_config() -> Dict:
        """
        Get default configuration
        
        Returns:
            Default configuration dictionary
        """
        return {
            'discord_webhook': 'YOUR_WEBHOOK_URL_HERE',
            'check_interval': 60,  # seconds
            'servers': [
                {
                    'name': 'Main Server',
                    'host': '127.0.0.1',
                    'port': 7777,
                    'max_players': 500,
                    'alert_on_offline': True,
                    'alert_on_high_load': True,
                    'high_load_threshold': 0.8
                }
            ]
        }
    
    def check_server(self, server_config: Dict) -> Dict:
        """
        Check a single server's status
        
        Args:
            server_config: Server configuration dictionary
            
        Returns:
            Server status dictionary
        """
        host = server_config['host']
        port = server_config['port']
        name = server_config['name']
        
        try:
            query = SAMPServerQuery(host, port, timeout=5)
            
            ping = query.ping()
            player_count = query.get_player_count()
            info = query.get_server_info()
            
            status = {
                'name': name,
                'host': host,
                'port': port,
                'online': True,
                'ping': ping,
                'player_count': player_count or 0,
                'max_players': server_config.get('max_players', 100),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return status
        
        except SAMPQueryException as e:
            status = {
                'name': name,
                'host': host,
                'port': port,
                'online': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return status
    
    def handle_server_status_change(self, server_name: str, new_status: Dict,
                                   old_status: Optional[Dict] = None):
        """
        Handle changes in server status and send alerts
        
        Args:
            server_name: Server name
            new_status: New status dictionary
            old_status: Previous status dictionary (if any)
        """
        if old_status is None:
            return
        
        # Server went offline
        if old_status.get('online', True) and not new_status.get('online', False):
            logger.warning(f"Server {server_name} went offline!")
            self.notifier.send_alert(
                title=f"⚠️ Server Offline: {server_name}",
                description=f"{server_name} ({new_status['host']}:{new_status['port']}) is now OFFLINE",
                color=0xFF0000
            )
        
        # Server came back online
        elif not old_status.get('online', False) and new_status.get('online', True):
            logger.info(f"Server {server_name} came back online!")
            self.notifier.send_alert(
                title=f"✅ Server Online: {server_name}",
                description=f"{server_name} is now ONLINE",
                color=0x00FF00
            )
        
        # Check for player load threshold
        if new_status.get('online', False):
            max_players = new_status.get('max_players', 100)
            player_count = new_status.get('player_count', 0)
            load = player_count / max_players if max_players > 0 else 0
            
            threshold = 0.8
            old_load = old_status.get('player_count', 0) / old_status.get('max_players', 100) \
                if old_status.get('max_players', 100) > 0 else 0
            
            # High load alert
            if load >= threshold and old_load < threshold:
                logger.warning(f"Server {server_name} high load: {load:.0%}")
                self.notifier.send_alert(
                    title=f"⚠️ High Load: {server_name}",
                    description=f"Server load is above {threshold:.0%}",
                    color=0xFFA500,
                    fields=[
                        {
                            "name": "Player Count",
                            "value": f"{player_count}/{max_players}",
                            "inline": True
                        },
                        {
                            "name": "Load",
                            "value": f"{load:.1%}",
                            "inline": True
                        }
                    ]
                )
    
    def monitor_loop(self):
        """
        Main monitoring loop
        Continuously checks all servers and sends alerts
        """
        self.monitoring = True
        logger.info("Server monitoring started")
        
        while self.monitoring:
            try:
                for server_config in self.config.get('servers', []):
                    server_name = server_config['name']
                    
                    # Get current status
                    new_status = self.check_server(server_config)
                    
                    # Get previous status
                    old_status = self.server_states.get(server_name)
                    
                    # Handle status changes
                    self.handle_server_status_change(server_name, new_status, old_status)
                    
                    # Update stored status
                    self.server_states[server_name] = new_status
                    
                    # Log status
                    if new_status['online']:
                        logger.info(
                            f"{server_name}: ONLINE | Players: {new_status['player_count']} | "
                            f"Ping: {new_status['ping']}ms"
                        )
                    else:
                        logger.warning(f"{server_name}: OFFLINE | Error: {new_status.get('error')}")
                
                # Wait before next check
                check_interval = self.config.get('check_interval', 60)
                time.sleep(check_interval)
            
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                time.sleep(10)
    
    def start_monitoring(self, daemon: bool = True):
        """
        Start monitoring in a separate thread
        
        Args:
            daemon: Run as daemon thread
        """
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=daemon)
        monitor_thread.start()
        logger.info("Monitor thread started")
        return monitor_thread
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.monitoring = False
        logger.info("Server monitoring stopped")
    
    def get_status_report(self) -> Dict:
        """
        Get current status report for all servers
        
        Returns:
            Dictionary with all server statuses
        """
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'servers': self.server_states
        }
    
    def save_status_report(self, filename: str = 'status_report.json'):
        """
        Save status report to file
        
        Args:
            filename: Output filename
        """
        try:
            report = self.get_status_report()
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Status report saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save status report: {str(e)}")


def create_sample_config(filename: str = 'monitor_config.json'):
    """
    Create a sample configuration file
    
    Args:
        filename: Output filename
    """
    config = {
        "discord_webhook": "https://discordapp.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN",
        "check_interval": 60,
        "servers": [
            {
                "name": "Main SA-MP Server",
                "host": "127.0.0.1",
                "port": 7777,
                "max_players": 500,
                "alert_on_offline": True,
                "alert_on_high_load": True,
                "high_load_threshold": 0.8
            },
            {
                "name": "Dev SA-MP Server",
                "host": "127.0.0.1",
                "port": 7778,
                "max_players": 100,
                "alert_on_offline": True,
                "alert_on_high_load": True,
                "high_load_threshold": 0.8
            }
        ]
    }
    
    try:
        with open(filename, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Sample configuration created: {filename}")
    except Exception as e:
        logger.error(f"Failed to create sample config: {str(e)}")


def main():
    """
    Main entry point
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='SA-MP Server Monitor with Discord Integration'
    )
    parser.add_argument(
        '--config',
        default='monitor_config.json',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--create-config',
        action='store_true',
        help='Create a sample configuration file'
    )
    
    args = parser.parse_args()
    
    # Create sample config if requested
    if args.create_config:
        create_sample_config(args.config)
        return
    
    # Start monitoring
    try:
        monitor = ServerMonitor(config_file=args.config)
        monitor.start_monitoring(daemon=False)
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user")
        monitor.stop_monitoring()


if __name__ == '__main__':
    main()
