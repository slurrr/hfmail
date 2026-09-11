import imaplib
import logging
from hfmail.config import load_config
from hfmail.processor import process_raw_email

def fetch_imap_emails():
    """
    Connects to the configured IMAP server, downloads new (UNSEEN) emails,
    processes them via process_raw_email, and marks them as SEEN.
    
    Returns:
        dict: Statistics about the fetch run.
    """
    config = load_config()
    imap_cfg = config.get("incoming_imap", {})
    
    host = imap_cfg.get("host")
    port = imap_cfg.get("port", 993)
    user = imap_cfg.get("username")
    pwd = imap_cfg.get("password")
    use_ssl = imap_cfg.get("use_ssl", True)
    folder = imap_cfg.get("folder", "INBOX")
    
    if not host or not user or not pwd:
        raise ValueError("IMAP connection details not configured in config.json")
        
    stats = {
        "fetched": 0,
        "important": 0,
        "promotion": 0,
        "spam": 0,
        "unsubscribed": 0,
        "errors": 0
    }
    
    # Establish connection
    if use_ssl:
        mail = imaplib.IMAP4_SSL(host, port)
    else:
        mail = imaplib.IMAP4(host, port)
        
    try:
        mail.login(user, pwd)
        mail.select(folder)
        
        # Search for unseen emails
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            logging.warning("Could not perform search for UNSEEN messages on IMAP server")
            return stats
            
        msg_ids = messages[0].split()
        logging.info(f"IMAP Fetcher: Found {len(msg_ids)} new emails to process")
        
        for msg_id in msg_ids:
            try:
                # Fetch RFC822 full email body
                status, data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    stats["errors"] += 1
                    continue
                    
                raw_content = data[0][1]
                
                # Process the raw content
                email_data = process_raw_email(raw_content)
                
                # Update statistics
                stats["fetched"] += 1
                cat = email_data.get("category", "important")
                if cat in stats:
                    stats[cat] += 1
                else:
                    stats["important"] += 1
                    
                # Delete from server or mark as seen
                if imap_cfg.get("delete_from_server", True):
                    mail.store(msg_id, '+FLAGS', '\\Deleted')
                else:
                    mail.store(msg_id, '+FLAGS', '\\Seen')
                
            except Exception as e:
                logging.error(f"Error fetching/processing IMAP message ID {msg_id}: {str(e)}", exc_info=True)
                stats["errors"] += 1
                
        # Expunge deleted emails and close connection
        if imap_cfg.get("delete_from_server", True):
            mail.expunge()
        mail.close()
        mail.logout()
        
    except Exception as e:
        logging.error(f"IMAP Connection or Login failed: {str(e)}", exc_info=True)
        raise e
        
    return stats
