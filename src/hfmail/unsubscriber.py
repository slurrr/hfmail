import re
import urllib.parse
import smtplib
from email.mime.text import MIMEText
import httpx
from hfmail.config import load_config
from hfmail.db import mark_unsubscribed, add_filter, get_email

def parse_mailto(mailto_str):
    """
    Parses a mailto link into (to_address, subject, body).
    Example: mailto:unsubscribe-123@huggingface.co?subject=unsubscribe
    """
    if mailto_str.lower().startswith("mailto:"):
        mailto_str = mailto_str[7:]
    
    parts = mailto_str.split("?", 1)
    to_address = parts[0]
    subject = "unsubscribe"
    body = "unsubscribe"
    
    if len(parts) > 1:
        query = urllib.parse.parse_qs(parts[1])
        if "subject" in query:
            subject = query["subject"][0]
        if "body" in query:
            body = query["body"][0]
            
    return to_address, subject, body

def send_unsubscribe_email(to_address, subject, body):
    """
    Sends an unsubscribe email via the configured outgoing SMTP relay.
    """
    config = load_config()
    out = config.get("outgoing_smtp", {})
    
    host = out.get("host")
    port = out.get("port", 587)
    user = out.get("username")
    pwd = out.get("password")
    from_addr = out.get("from_address") or user
    
    if not host or not user or not pwd:
        raise ValueError("Outgoing SMTP relay credentials not configured in config.json")
        
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address
    
    # Secure connection logic
    use_tls = out.get("use_tls", True)
    
    server = smtplib.SMTP(host, port)
    server.ehlo()
    if use_tls:
        server.starttls()
        server.ehlo()
    
    server.login(user, pwd)
    server.sendmail(from_addr, [to_address], msg.as_string())
    server.quit()

def unsubscribe_email(email_id_or_data):
    """
    Attempts to unsubscribe using the URL and/or Mailto headers from an email.
    Saves filter rule to prevent future emails from being shown.
    """
    if isinstance(email_id_or_data, (int, str)):
        email_data = get_email(int(email_id_or_data))
    else:
        email_data = email_id_or_data
        
    if not email_data:
        return False, "Email not found"
        
    email_id = email_data.get("id")
    sender = email_data.get("sender")
    mailto_link = email_data.get("list_unsubscribe_mailto")
    url_link = email_data.get("list_unsubscribe_url")
    
    success = False
    details = []
    
    # 1. Try URL unsubscribe
    if url_link:
        try:
            # Clean url_link (strip brackets if any)
            url_link = url_link.strip("<>")
            # Perform HTTP GET request (some list-unsubscribe targets are POST, but GET is standard starting point)
            r = httpx.get(url_link, follow_redirects=True, timeout=10.0)
            if r.status_code < 400:
                success = True
                details.append(f"HTTP GET to {url_link} succeeded ({r.status_code})")
            else:
                details.append(f"HTTP GET to {url_link} failed with status {r.status_code}")
        except Exception as e:
            details.append(f"HTTP GET to {url_link} error: {str(e)}")
            
    # 2. Try Mailto unsubscribe
    if mailto_link:
        try:
            mailto_link = mailto_link.strip("<>")
            to_address, subject, body = parse_mailto(mailto_link)
            send_unsubscribe_email(to_address, subject, body)
            success = True
            details.append(f"Sent SMTP unsubscribe mail to {to_address}")
        except Exception as e:
            details.append(f"SMTP unsubscribe to {mailto_link} failed: {str(e)}")
            
    # If unsubscribe links were not found, we can't click them, but we still mark it as unsubscribed in our filters!
    if not mailto_link and not url_link:
        details.append("No List-Unsubscribe headers found in this email")
        # We still count this as a success in terms of filter block
        success = True
        
    # 3. Create automatic filter rule to drop future emails from this sender/subject pattern
    # Clean the sender address to extract just the email or domain
    sender_clean = sender.lower()
    match = re.search(r"[\w.-]+@[\w.-]+", sender_clean)
    if match:
        sender_clean = match.group(0)
        
    # Add a block filter in DB
    add_filter("sender", sender_clean, "unsubscribed")
    details.append(f"Added filter: sender '{sender_clean}' -> auto-unsubscribe")
    
    # Mark in database
    if email_id:
        mark_unsubscribed(email_id)
        
    return success, "; ".join(details)
