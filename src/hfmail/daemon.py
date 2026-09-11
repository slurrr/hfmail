import asyncio
import logging
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from aiosmtpd.controller import Controller

from hfmail.config import load_config, DEFAULT_RUNS_DIR
from hfmail.db import init_db
from hfmail.processor import process_raw_email

PID_FILE = DEFAULT_RUNS_DIR / "daemon.pid"
LOG_FILE = DEFAULT_RUNS_DIR / "daemon.log"

# Setup logging
def setup_logging():
    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

class EmailHandler:
    async def handle_DATA(self, server, session, envelope):
        peer = session.peer
        mail_from = envelope.mail_from
        rcpt_tos = envelope.rcpt_tos
        content = envelope.content  # bytes
        
        logging.info(f"Incoming connection from {peer}, MAIL FROM: {mail_from}")
        
        try:
            email_data = process_raw_email(content)
            db_id = email_data["id"]
            category = email_data["category"]
            subject = email_data["subject"]
            logging.info(f"Saved email ID {db_id}. Subject: '{subject}'. Classified as: {category}")
            return "250 Message accepted for delivery"
        except Exception as e:
            logging.error(f"Error parsing incoming email: {str(e)}", exc_info=True)
            return "550 Internal error processing message"

def run_server():
    """Run SMTP server in foreground."""
    init_db()
    setup_logging()
    
    config = load_config()
    host = config["incoming_smtp"]["host"]
    port = config["incoming_smtp"]["port"]
    
    handler = EmailHandler()
    controller = Controller(handler, hostname=host, port=port)
    
    logging.info(f"Starting SMTP daemon on {host}:{port}")
    print(f"Starting hfmail SMTP daemon on {host}:{port}")
    
    controller.start()
    
    # Simple loop to keep daemon alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        logging.info("Stopping SMTP daemon")
        controller.stop()

# Daemon background management
def start_daemon():
    """Starts the daemon in background and writes PID."""
    if is_daemon_running():
        print("Daemon is already running.")
        return
        
    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Spawn background process using same interpreter
    # We call our package module 'hfmail.daemon'
    cmd = [sys.executable, "-m", "hfmail.daemon"]
    
    # Redirect outputs to log file
    log_file = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        preexec_fn=os.setpgrp, # run in new process group
        close_fds=True
    )
    
    # Write PID file
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
        
    print(f"hfmail daemon started in background (PID: {proc.pid})")
    print(f"Logs: {LOG_FILE}")

def stop_daemon():
    """Stops the background daemon."""
    if not PID_FILE.exists():
        print("Daemon is not running (no PID file).")
        return
        
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        print("Could not read PID file.")
        return
        
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to hfmail daemon (PID: {pid})")
        # Wait a bit for termination
        for _ in range(5):
            if not is_pid_alive(pid):
                break
            time.sleep(0.5)
        else:
            # Force kill
            os.kill(pid, signal.SIGKILL)
            print(f"Sent SIGKILL to hfmail daemon (PID: {pid})")
    except ProcessLookupError:
        print("Daemon process not found. Cleaning up PID file.")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()

def is_pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def is_daemon_running():
    if not PID_FILE.exists():
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        return is_pid_alive(pid)
    except Exception:
        return False

def daemon_status():
    running = is_daemon_running()
    if running:
        with open(PID_FILE, "r") as f:
            pid = f.read().strip()
        print(f"hfmail daemon is RUNNING (PID: {pid})")
    else:
        print("hfmail daemon is STOPPED")
    print(f"SMTP Config: {load_config()['incoming_smtp']['host']}:{load_config()['incoming_smtp']['port']}")
    print(f"Logs: {LOG_FILE}")
    if LOG_FILE.exists():
        print("\nLast 5 log lines:")
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            for line in lines[-5:]:
                print(f"  {line.strip()}")

if __name__ == "__main__":
    run_server()
