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
        """Check if there's a currently live stream using yt-dlp"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'force_json': True,
            'playlistend': 10,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.channel_url, download=False)
                
                current_live_streams = []
                for entry in info.get('entries', []):
                    is_currently_live = (
                        entry.get('live_status') == 'is_live' or
                        (entry.get('is_live') and not entry.get('was_live')) or
                        entry.get('live_status') == 'live'
                    )
                    
                    if is_currently_live:
                        duration = entry.get('duration', 0)
                        if duration is None or duration > 3600:
                            current_live_streams.append(entry)
                
                is_live = len(current_live_streams) > 0
                return is_live, current_live_streams
                
        except Exception as e:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] ⚠️ Error checking stream: {e}")
            return False, []
    
    def check_live_stream_alternative(self):
        """Alternative method using YouTube's live search filter"""
        try:
            if '/videos' in self.channel_url or '/streams' in self.channel_url:
                live_url = self.channel_url.replace('/videos', '/streams').replace('/featured', '/streams')
            else:
                live_url = self.channel_url.rstrip('/') + '/streams'
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'force_json': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(live_url, download=False)
                
                current_live = []
                for entry in info.get('entries', []):
                    if (entry.get('live_status') == 'is_live' or 
                        (entry.get('is_live') and 'live' in entry.get('title', '').lower())):
                        current_live.append(entry)
                
                is_live = len(current_live) > 0
                return is_live, current_live
                
        except Exception as e:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] ⚠️ Error checking stream (alternative): {e}")
            return False, []
    
    def reboot_raspberry_pi(self):
        """Reboot the Raspberry Pi using sshpass and subprocess"""
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] 🔄 Attempting to reboot Raspberry Pi...")
            
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
        """Main monitoring task - only increments failure counter once per check"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{current_time}] 🔍 Checking for live streams...")
        
        # Try both methods, but only count one failure if both fail
        is_live1, streams1 = self.check_live_stream()
        is_live2, streams2 = self.check_live_stream_alternative()
        
        # Consider it a live stream if either method detects one
        is_live = is_live1 or is_live2
        
        if is_live:
            stream_title = streams1[0].get('title', 'Unknown') if streams1 else streams2[0].get('title', 'Unknown') if streams2 else 'Unknown'
            print(f"[{current_time}] ✅ Live stream detected: {stream_title}")
            self.consecutive_failures = 0
        else:
            print(f"[{current_time}] ❌ No live stream detected")
            self.consecutive_failures += 1
            print(f"[{current_time}] 📊 Consecutive failures: {self.consecutive_failures}/{self.max_failures}")
        
        # Check if we need to reboot
        if self.consecutive_failures >= self.max_failures:
            print(f"🚨 {self.consecutive_failures} consecutive failures detected - rebooting Raspberry Pi")
            self.reboot_raspberry_pi()
            print("I WOULD HAVE REBOOTED NOW, CHECK IF OK")
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
