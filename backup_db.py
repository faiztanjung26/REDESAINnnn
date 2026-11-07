import os
import subprocess
import gzip
import shutil
from datetime import datetime

# Try to import boto3, print clear instructions if not installed
try:
    import boto3
except ImportError:
    print("Error: 'boto3' library is not installed. Please install it using: pip install boto3")
    exit(1)

# Database Configuration
# Loaded from environment variable if available, else defaults to the production DB
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("DB_PORT", "3306")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "cmms_db")

# Biznet NEO Object Storage Configuration
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "cmms-db-backup")

def run_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cmms_backup_{timestamp}.sql"
    gz_filename = f"{filename}.gz"
    
    print(f"[{datetime.now()}] Starting database backup process...")
    
    # 1. Dump database via mysqldump
    print(f"[{datetime.now()}] Dumping database '{DB_NAME}' from {DB_HOST}:{DB_PORT}...")
    dump_cmd = [
        "mysqldump",
        f"-h{DB_HOST}",
        f"-P{DB_PORT}",
        f"-u{DB_USER}",
        f"-p{DB_PASS}",
        "--single-transaction",
        "--quick",
        "--lock-tables=false",
        DB_NAME
    ]
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True, check=True)
        print(f"[{datetime.now()}] Database dumped successfully to {filename}")
    except subprocess.CalledProcessError as e:
        print(f"Error running mysqldump: {e.stderr}")
        if os.path.exists(filename):
            os.remove(filename)
        return
    except FileNotFoundError:
        print("Error: 'mysqldump' utility not found. Please ensure MySQL client utilities are installed on this server.")
        return
        
    # 2. Compress the SQL file using gzip
    print(f"[{datetime.now()}] Compressing SQL dump...")
    try:
        with open(filename, "rb") as f_in:
            with gzip.open(gz_filename, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"[{datetime.now()}] Compressed successfully to {gz_filename}")
    except Exception as e:
        print(f"Error compressing file: {e}")
        if os.path.exists(filename): os.remove(filename)
        if os.path.exists(gz_filename): os.remove(gz_filename)
        return
    finally:
        # Delete uncompressed sql file
        if os.path.exists(filename):
            os.remove(filename)
            
    # 3. Upload the compressed backup to NEO Object Storage
    print(f"[{datetime.now()}] Uploading backup to Biznet NEO Object Storage...")
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name="idn"
        )
        
        s3_key = f"db_backups/{gz_filename}"
        s3.upload_file(
            Filename=gz_filename,
            Bucket=S3_BUCKET,
            Key=s3_key
        )
        print(f"[{datetime.now()}] Uploaded successfully to S3 bucket '{S3_BUCKET}' as '{s3_key}'")
    except Exception as e:
        print(f"Error uploading to S3: {e}")
    finally:
        # Delete local compressed file
        if os.path.exists(gz_filename):
            os.remove(gz_filename)
            
    print(f"[{datetime.now()}] Backup process completed.")

if __name__ == "__main__":
    run_backup()
