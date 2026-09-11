import logging
import uuid
import re
from datetime import datetime
from email.parser import BytesParser
from email.policy import default

from hfmail.config import load_config
from hfmail.db import save_email
from hfmail.classifier import classify_email

def process_raw_email(content: bytes) -> dict:
    """
    Parses raw email bytes, extracts metadata and content, runs classification,
    saves it to the database, and triggers auto-unsubscribe if applicable.
    
    Returns:
        dict: Processed email metadata including category and DB ID.
    """
    # Parse email MIME structure
    message = BytesParser(policy=default).parsebytes(content)
    
    # Extract basic fields
    subject = message.get("Subject", "")
    sender = message.get("From", "")
    recipient = message.get("To", "")
    message_id = message.get("Message-ID") or f"{uuid.uuid4()}@local"
    
    # Extract plain text & HTML bodies
    body_text = ""
    body_html = ""
    
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if "attachment" in content_disposition:
                continue
                
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body_text = payload.decode(charset, errors="replace")
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body_html = payload.decode(charset, errors="replace")
    else:
        content_type = message.get_content_type()
        payload = message.get_payload(decode=True)
        charset = message.get_content_charset() or "utf-8"
        if content_type == "text/plain":
            body_text = payload.decode(charset, errors="replace")
        elif content_type == "text/html":
            body_html = payload.decode(charset, errors="replace")
    
    # Extract list-unsubscribe headers
    list_unsubscribe = message.get("List-Unsubscribe", "")
    list_unsubscribe_mailto = ""
    list_unsubscribe_url = ""
    if list_unsubscribe:
        links = re.findall(r"<([^>]+)>", list_unsubscribe)
        for link in links:
            if link.lower().startswith("mailto:"):
                list_unsubscribe_mailto = link
            elif link.lower().startswith("http"):
                list_unsubscribe_url = link
    
    # Parse Received Date
    received_at = datetime.now().isoformat()
    from email.utils import parsedate_to_datetime
    date_header = message.get("Date")
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header).isoformat()
        except Exception:
            pass
    
    email_data = {
        "message_id": message_id,
        "sender": sender,
        "recipient": recipient,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "list_unsubscribe_mailto": list_unsubscribe_mailto,
        "list_unsubscribe_url": list_unsubscribe_url,
        "received_at": received_at,
        "is_read": 0
    }
    
    # Classify
    category = classify_email(email_data)
    email_data["category"] = category
    
    # Save to Database
    db_id = save_email(email_data)
    email_data["id"] = db_id
    
    # Check for Auto-Unsubscribe
    config = load_config()
    if category in ("unsubscribed", "promotion") and config.get("auto_unsubscribe", True):
        from hfmail.unsubscriber import unsubscribe_email
        logging.info(f"Triggering auto-unsubscribe for email ID {db_id}")
        success, desc = unsubscribe_email(email_data)
        logging.info(f"Auto-unsubscribe status: {success} - {desc}")
        email_data["unsubscribe_success"] = success
        email_data["unsubscribe_details"] = desc
        
    return email_data
