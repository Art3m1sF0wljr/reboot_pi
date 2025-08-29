import os
import time
import subprocess
import paramiko
import schedule
from datetime import datetime
from dotenv import load_dotenv
import yt_dlp

# Load environment variables
load_dotenv()

class StreamMonitor:
    def __init__(self):
        self.consecutive_failures = 0
        self.max_failures = int(os.getenv('MAX_CONSECUTIVE_FAILURES', 3))
        self.channel_url = os.getenv('YOUTUBE_CHANNEL_URL')
        self.ssh_host = os.getenv('SSH_HOST')
        self.ssh_username = os.getenv('SSH_USERNAME')
        self.ssh_password = os.getenv('SSH_PASSWORD')
        
        if not all([self.channel_url, self.ssh_host, self.ssh_username, self.ssh_password]):
            raise ValueError("Missing required environment variables")
    
    def check_live_stream(self):
        """Check if there's a live stream using yt-dlp"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'force_json': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract channel livestreams
                info = ydl.extract_info(self.channel_url, download=False)
                
                # Check if any entry is a live stream
                live_streams = [
                    entry for entry in info.get('entries', [])
                    if entry.get('is_live') or 'live' in entry.get('title', '').lower()
                ]
                
                is_live = len(live_streams) > 0
                
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if is_live:
                    print(f"[{current_time}] ✅ Live stream detected")
                    self.consecutive_failures = 0
                else:
                    print(f"[{current_time}] ❌ No live stream detected")
                    self.consecutive_failures += 1
                
                return is_live
                
        except Exception as e:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] ⚠️ Error checking stream: {e}")
            self.consecutive_failures += 1
            return False
    
    def reboot_raspberry_pi(self):
        """Reboot the Raspberry Pi using sshpass and subprocess"""
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] 🔄 Attempting to reboot Raspberry Pi...")
            
            # Use sshpass to handle password authentication
            command = [
                'sshpass', '-p', self.ssh_password,
                'ssh', f'{self.ssh_username}@{self.ssh_host}',
                'sudo', 'reboot', 'now'
            ]
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"[{current_time}] ✅ Reboot command sent successfully")
                return True
            else:
                print(f"[{current_time}] ❌ Reboot failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"[{current_time}] ⏰ Reboot command timed out (may have succeeded)")
            return True
        except Exception as e:
            print(f"[{current_time}] ❌ Failed to reboot Raspberry Pi: {e}")
            return False
    
    def monitor_task(self):
        """Main monitoring task"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Checking for live streams...")
        
        is_live = self.check_live_stream()
        
        # Check if we need to reboot
        if self.consecutive_failures >= self.max_failures:
            print(f"🚨 {self.consecutive_failures} consecutive failures detected - rebooting Raspberry Pi")
            self.reboot_raspberry_pi()
            print(f"I WOULD HAVE REBOOTED NOW, CHECK IF OK")
            # Reset counter after reboot attempt
            self.consecutive_failures = 0
    
    def run(self):
        """Start the monitoring service"""
        check_interval = int(os.getenv('CHECK_INTERVAL', 10))
        
        print(f"🎥 Starting YouTube Stream Monitor")
        print(f"📺 Channel: {self.channel_url}")
        print(f"⏰ Check interval: {check_interval} minutes")
        print(f"🔁 Max failures before reboot: {self.max_failures}")
        print("=" * 50)
        
        # Run initial check
        self.monitor_task()
        
        # Schedule regular checks
        schedule.every(check_interval).minutes.do(self.monitor_task)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")

def main():
    try:
        monitor = StreamMonitor()
        monitor.run()
    except Exception as e:
        print(f"❌ Failed to start monitor: {e}")
        print("Please check your .env file configuration")

if __name__ == "__main__":
    main()
