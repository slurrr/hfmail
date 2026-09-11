import re
from hfmail.db import get_filters
from hfmail.config import load_config

def get_email_domain(sender):
    if not sender:
        return ""
    # Extract domain from something like "Hugging Face <noreply@huggingface.co>" or "noreply@huggingface.co"
    match = re.search(r"@([\w.-]+)", sender)
    if match:
        return match.group(1).lower()
    return ""

def classify_email(email_data):
    """
    Classifies an email dictionary.
    Returns: 'important', 'promotion', 'spam', 'unsubscribed'
    """
    sender = email_data.get("sender", "").lower()
    subject = email_data.get("subject", "").lower()
    body = email_data.get("body_text", "").lower()
    headers = email_data.get("headers", {})
    
    config = load_config()
    
    # 1. Check user-defined database filters
    filters = get_filters()
    for f in filters:
        pattern = f["pattern"].lower()
        if f["pattern_type"] == "sender":
            if pattern in sender:
                return f["action"]
        elif f["pattern_type"] == "subject":
            if pattern in subject:
                return f["action"]
    
    # 2. Check if only_huggingface is enabled
    domain = get_email_domain(sender)
    is_hf = "huggingface.co" in domain or "huggingface.cloud" in domain
    
    if config.get("only_huggingface", True) and not is_hf:
        return "spam"
        
    # 3. Check for obvious spam keywords
    spam_keywords = ["lottery", "crypto", "bitcoin", "viagra", "casino", "free money", "winner"]
    for kw in spam_keywords:
        if kw in subject or (kw in body and not is_hf):
            return "spam"
            
    # 4. Check for List-Unsubscribe presence indicating a list/bulk email
    # (Note: we store unsubscribe headers as fields in email_data)
    has_list_unsubscribe = bool(email_data.get("list_unsubscribe_mailto") or email_data.get("list_unsubscribe_url"))
    
    # 5. Look for Security / Direct transactional triggers (Always IMPORTANT)
    security_triggers = [
        "security", "alert", "password", "reset", "login", "ssh key", 
        "token", "authorize", "verification", "verify", "two-factor", "2fa"
    ]
    for trig in security_triggers:
        if trig in subject:
            return "important"
            
    # Collaboration and Direct Mentions (Always IMPORTANT)
    important_triggers = [
        "mentioned you", "invited you", "invite", "organization", "org",
        "discussion in", "pr in", "pull request", "collaborator", "support ticket",
        "reply", "replied", "direct message", "dm"
    ]
    for trig in important_triggers:
        if trig in subject or f"@{config.get('huggingface_username', '').lower()}" in subject:
            return "important"
            
    # 6. Look for Promotion / Newsletter / Digest triggers
    promotion_triggers = [
        "digest", "newsletter", "weekly", "monthly", "trending", 
        "top models", "announcing", "announcement", "hubs", "spaces of the week",
        "what's new", "check out", "join our discord", "introducing"
    ]
    for trig in promotion_triggers:
        if trig in subject:
            return "promotion"
            
    # 7. Default classification based on whether it is a mailing list
    if has_list_unsubscribe:
        # If it has unsubscribe links but wasn't flagged as important, it's likely a promotion
        return "promotion"
        
    # Default fallback
    return "important"
