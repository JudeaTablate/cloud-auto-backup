import os
import datetime
import shutil
from rclone_python import rclone

REMOTE_NAME = "gdrive" 
DESTINATION_FOLDER = "Backups"
SOURCE_PATH = "."

def run_backup():
    # 1. Generate a filename with a timestamp (e.g., backup_2026-02-25.zip)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')
    backup_filename = f"repo_backup_{timestamp}"
    
    print(f"📦 Starting backup process for: {backup_filename}...")

    try:
        # 2. Create the ZIP file
        zip_path = shutil.make_archive(backup_filename, 'zip', SOURCE_PATH)
        print(f"✅ Created archive: {zip_path}")

        # 3. Upload to Google Drive
        print(f"🚀 Uploading to {REMOTE_NAME}...")
        rclone.copy(zip_path, f"{REMOTE_NAME}:{DESTINATION_FOLDER}")
        
        print(f"🎉 Success! Backup uploaded to Google Drive.")

        # 4. Cleanup (Delete the zip file from the GitHub server to keep it clean)
        os.remove(zip_path)
        print(f"🧹 Local cleanup complete.")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        exit(1)

if __name__ == "__main__":
    run_backup()