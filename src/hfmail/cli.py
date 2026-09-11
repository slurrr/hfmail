import click
import json
import smtplib
import sys
import uuid
from email.message import EmailMessage
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

from hfmail.config import load_config, save_config, CONFIG_PATH
from hfmail.db import (
    get_emails, get_email, mark_as_read, delete_email, 
    update_category, get_filters, add_filter, remove_filter
)
from hfmail.daemon import start_daemon, stop_daemon, daemon_status, run_server
from hfmail.unsubscriber import unsubscribe_email
from hfmail.imap_fetcher import fetch_imap_emails

console = Console()

@click.group()
def cli():
    """hfmail: A CLI-only email client and SMTP receiver custom-built for Hugging Face."""
    pass

@cli.command("inbox")
@click.option("--all", "-a", is_flag=True, help="Show all emails (read and unread).")
@click.option("--category", "-c", type=click.Choice(["important", "promotion", "spam", "unsubscribed"]), help="Filter by category.")
@click.option("--search", "-s", help="Search text in sender, subject, or body.")
@click.option("--limit", "-l", default=20, help="Max number of emails to show.")
def list_emails(all, category, search, limit):
    """List emails in a beautiful formatted table."""
    unread_only = not all
    
    # Default to 'important' category if none specified and not showing all
    if category is None and not all:
        category = "important"
        
    # If a specific category or search is requested, default to showing all matching (not just unread)
    if (category and category != "important") or search:
        unread_only = False
        
    emails = get_emails(category=category, unread_only=unread_only, search_query=search, limit=limit)
    
    if not emails:
        console.print("[yellow]No emails found matching criteria.[/yellow]")
        return
        
    table = Table(title="[bold green]hfmail Inbox[/bold green]")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Category", width=12)
    table.add_column("Sender", width=25)
    table.add_column("Subject", style="bold", width=45)
    table.add_column("Received", width=18)
    table.add_column("Read", width=6)
    
    category_colors = {
        "important": "bold green",
        "promotion": "yellow",
        "spam": "red",
        "unsubscribed": "dim blue"
    }
    
    for email in emails:
        cat = email["category"]
        cat_color = category_colors.get(cat, "white")
        cat_text = Text(cat.upper(), style=cat_color)
        
        is_read = email["is_read"]
        read_text = "[green]Yes[/green]" if is_read else "[bold red]No[/bold red]"
        
        # Style rows: unread messages are bold/bright
        row_style = "bold white" if not is_read else "dim white"
        
        # Format sender
        sender = email["sender"]
        if "<" in sender:
            # Extract name if present
            sender = sender.split("<")[0].strip()
            
        subject = email["subject"]
        if len(subject) > 42:
            subject = subject[:40] + "..."
            
        # Parse date representation
        received = email["received_at"]
        if "T" in received:
            # clean up ISO string slightly for terminal
            received = received.replace("T", " ").split(".")[0]
            
        table.add_row(
            str(email["id"]),
            cat_text,
            Text(sender, style=row_style),
            Text(subject, style=row_style),
            Text(received, style="cyan"),
            read_text
        )
        
    console.print(table)
    console.print(f"[dim]Showing {len(emails)} emails. Run with --all to see read messages.[/dim]")

@cli.command("read")
@click.argument("email_id", type=int)
@click.option("--raw", is_flag=True, help="Print raw unformatted body text.")
def read_email(email_id, raw):
    """Read an email by its ID."""
    email = get_email(email_id)
    if not email:
        console.print(f"[red]Error: Email with ID {email_id} not found.[/red]")
        sys.exit(1)
        
    # Mark as read
    mark_as_read(email_id, 1)
    
    category_colors = {
        "important": "green",
        "promotion": "yellow",
        "spam": "red",
        "unsubscribed": "blue"
    }
    cat_color = category_colors.get(email["category"], "white")
    
    # Format header metadata panel
    header_content = (
        f"[bold]From:[/bold] {email['sender']}\n"
        f"[bold]To:[/bold] {email['recipient']}\n"
        f"[bold]Date:[/bold] {email['received_at']}\n"
        f"[bold]Category:[/bold] [{cat_color}]{email['category'].upper()}[/{cat_color}]\n"
    )
    
    unsubscribe_methods = []
    if email["list_unsubscribe_url"]:
        unsubscribe_methods.append("URL")
    if email["list_unsubscribe_mailto"]:
        unsubscribe_methods.append("Mailto")
        
    if unsubscribe_methods:
        header_content += f"[bold]Unsubscribe Headers:[/bold] {', '.join(unsubscribe_methods)}\n"
    if email["unsubscribed_at"]:
        header_content += f"[bold]Unsubscribed At:[/bold] {email['unsubscribed_at']}\n"
        
    console.print(Panel(header_content, title=f"[bold cyan]{email['subject']}[/bold cyan]", border_style="cyan"))
    
    body = email["body_text"] or "[dim](No plain text content. HTML only)[/dim]"
    
    console.print("\n[bold underline]Message Body:[/bold underline]")
    if raw:
        console.print(body)
    else:
        # Detect if body looks like markdown or has HTML tags
        # Clean email text commonly has markdown elements.
        try:
            markdown = Markdown(body)
            console.print(markdown)
        except Exception:
            console.print(body)
            
    console.print("\n" + "-" * 40)
    console.print(f"[dim]Actions: hfmail delete {email_id} | hfmail unsubscribe {email_id} | hfmail spam {email_id}[/dim]")

@cli.command("delete")
@click.argument("email_id", type=int)
def delete(email_id):
    """Delete an email."""
    email = get_email(email_id)
    if not email:
        console.print(f"[red]Error: Email with ID {email_id} not found.[/red]")
        sys.exit(1)
    delete_email(email_id)
    console.print(f"[green]Email {email_id} deleted.[/green]")

@cli.command("unsubscribe")
@click.argument("email_id", type=int)
def unsubscribe(email_id):
    """Auto-unsubscribe from the mailing list of this email and block future sends."""
    email = get_email(email_id)
    if not email:
        console.print(f"[red]Error: Email with ID {email_id} not found.[/red]")
        sys.exit(1)
        
    console.print(f"Triggering unsubscribe for: [cyan]'{email['subject']}'[/cyan]")
    success, desc = unsubscribe_email(email)
    
    if success:
        console.print(f"[green]Successfully unsubscribed![/green]")
        console.print(f"[dim]{desc}[/dim]")
    else:
        console.print(f"[yellow]Unsubscribe action partially completed or failed:[/yellow]")
        console.print(f"[red]{desc}[/red]")
        console.print(f"[dim]Sender is still added to the unsubscribed block filter.[/dim]")

@cli.command("spam")
@click.argument("email_id", type=int)
def mark_spam(email_id):
    """Mark email as spam and block future emails from this sender."""
    email = get_email(email_id)
    if not email:
        console.print(f"[red]Error: Email with ID {email_id} not found.[/red]")
        sys.exit(1)
        
    update_category(email_id, "spam")
    
    # Extract email domain/sender pattern
    sender = email["sender"].lower()
    import re
    match = re.search(r"[\w.-]+@[\w.-]+", sender)
    sender_clean = match.group(0) if match else sender
    
    add_filter("sender", sender_clean, "spam")
    console.print(f"[green]Email {email_id} marked as SPAM.[/green]")
    console.print(f"[dim]Added filter: sender '{sender_clean}' -> auto-spam[/dim]")

@cli.command("important")
@click.argument("email_id", type=int)
def mark_important(email_id):
    """Mark email as important and whitelist future emails from this sender."""
    email = get_email(email_id)
    if not email:
        console.print(f"[red]Error: Email with ID {email_id} not found.[/red]")
        sys.exit(1)
        
    update_category(email_id, "important")
    
    sender = email["sender"].lower()
    import re
    match = re.search(r"[\w.-]+@[\w.-]+", sender)
    sender_clean = match.group(0) if match else sender
    
    add_filter("sender", sender_clean, "important")
    console.print(f"[green]Email {email_id} marked as IMPORTANT.[/green]")
    console.print(f"[dim]Added filter: sender '{sender_clean}' -> auto-important[/dim]")

# Daemon commands
@cli.group("daemon")
def daemon_group():
    """Manage the background SMTP server daemon."""
    pass

@daemon_group.command("start")
def d_start():
    """Start the SMTP receiver daemon in the background."""
    start_daemon()

@daemon_group.command("stop")
def d_stop():
    """Stop the background SMTP receiver daemon."""
    stop_daemon()

@daemon_group.command("status")
def d_status():
    """Show status and logs of the SMTP receiver daemon."""
    daemon_status()

@daemon_group.command("run")
def d_run():
    """Run the SMTP receiver daemon in the foreground (blocking)."""
    try:
        run_server()
    except KeyboardInterrupt:
        console.print("\n[yellow]Foreground SMTP daemon stopped.[/yellow]")

# Filter commands
@cli.group("filters")
def filters_group():
    """Manage custom rules for email classification."""
    pass

@filters_group.command("list")
def filt_list():
    """List all active filters."""
    filters = get_filters()
    if not filters:
        console.print("[yellow]No custom filters defined.[/yellow]")
        return
        
    table = Table(title="[bold yellow]Active Filters[/bold yellow]")
    table.add_column("ID", width=6)
    table.add_column("Type", width=12)
    table.add_column("Pattern", width=40)
    table.add_column("Action", width=15)
    
    action_colors = {
        "important": "green",
        "spam": "red",
        "unsubscribed": "blue",
        "promotion": "yellow"
    }
    
    for f in filters:
        action_style = action_colors.get(f["action"], "white")
        table.add_row(
            str(f["id"]),
            f["pattern_type"],
            f["pattern"],
            Text(f["action"].upper(), style=f"bold {action_style}")
        )
    console.print(table)

@filters_group.command("add")
@click.argument("pattern_type", type=click.Choice(["sender", "subject"]))
@click.argument("pattern")
@click.argument("action", type=click.Choice(["important", "promotion", "spam", "unsubscribed"]))
def filt_add(pattern_type, pattern, action):
    """Add a new classification filter rule."""
    filter_id = add_filter(pattern_type, pattern, action)
    console.print(f"[green]Added filter rule {filter_id}: {pattern_type} '{pattern}' -> {action.upper()}[/green]")

@filters_group.command("remove")
@click.argument("filter_id", type=int)
def filt_remove(filter_id):
    """Remove a classification filter rule."""
    remove_filter(filter_id)
    console.print(f"[green]Filter rule {filter_id} removed.[/green]")

# Config commands
@cli.group("config")
def config_group():
    """Manage configuration settings."""
    pass

@config_group.command("show")
def cfg_show():
    """Show the current configuration file."""
    config = load_config()
    console.print(Panel(json.dumps(config, indent=4), title="[bold]hfmail Config[/bold]", border_style="yellow"))
    console.print(f"[dim]Config file path: {CONFIG_PATH}[/dim]")

@config_group.command("set")
@click.argument("section_key")
@click.argument("value")
def cfg_set(section_key, value):
    """
    Set a configuration option.
    Format: section.key value (e.g. outgoing_smtp.host smtp.gmail.com)
    or just: key value (e.g. auto_unsubscribe false)
    """
    config = load_config()
    
    # Parse section.key or key
    if "." in section_key:
        sec, key = section_key.split(".", 1)
        if sec not in config:
            console.print(f"[red]Error: Section '{sec}' does not exist.[/red]")
            return
        # Cast types if appropriate
        old_val = config[sec].get(key)
        if isinstance(old_val, bool):
            val_parsed = value.lower() in ("true", "1", "yes")
        elif isinstance(old_val, int):
            val_parsed = int(value)
        else:
            val_parsed = value
            
        config[sec][key] = val_parsed
    else:
        key = section_key
        if key not in config:
            console.print(f"[red]Error: Key '{key}' does not exist.[/red]")
            return
        old_val = config.get(key)
        if isinstance(old_val, bool):
            val_parsed = value.lower() in ("true", "1", "yes")
        elif isinstance(old_val, int):
            val_parsed = int(value)
        else:
            val_parsed = value
            
        config[key] = val_parsed
        
    save_config(config)
    console.print(f"[green]Config updated: {section_key} = {val_parsed}[/green]")

# Test receive command
@cli.command("test-receive")
@click.option("--sender", "-f", default="noreply@huggingface.co", help="Sender email address.")
@click.option("--subject", "-s", default="[Hugging Face] Discussion in transformers", help="Subject line.")
@click.option("--body", "-b", help="Email body content.")
@click.option("--type", "-t", type=click.Choice(["mention", "newsletter", "spam", "other"]), default="mention", help="Preset templates.")
def test_receive(sender, subject, body, type):
    """Simulate receiving an email by sending it via SMTP to the local running daemon."""
    config = load_config()
    host = config["incoming_smtp"]["host"]
    port = config["incoming_smtp"]["port"]
    
    # Set default templates based on type
    if type == "mention":
        sender = "website@huggingface.co"
        subject = "[Hugging Face] @poop mentioned you in discussion 'transformers/v5-release'"
        if not body:
            body = (
                "Hi poop,\n\n"
                "@nielsrogge mentioned you in a discussion:\n\n"
                "> Let's ask @poop to take a look at this PR since they are the main maintainer.\n\n"
                "View the discussion here: https://huggingface.co/transformers/discussions/123\n\n"
                "Cheers,\nThe Hugging Face Team"
            )
    elif type == "newsletter":
        sender = "newsletters@huggingface.co"
        subject = "[Hugging Face] Weekly Digest: Trending Models and Spaces"
        if not body:
            body = (
                "Hello Hugging Face user!\n\n"
                "Here are this week's top trending models:\n"
                "1. meta-llama/Llama-3-70b\n"
                "2. gradientai/Llama-3-8B-Instruct-Gradient-1048k\n\n"
                "Check out these spaces:\n"
                "- https://huggingface.co/spaces/coqui/xtts\n\n"
                "If you wish to stop receiving these digests, unsubscribe by clicking the link below:\n"
                "Unsubscribe: https://huggingface.co/unsubscribe?token=weekly-digest-token-xyz\n\n"
                "Thanks,\nHugging Face newsletters"
            )
    elif type == "spam":
        sender = "spammer@getrichquick.info"
        subject = "Earn $5000/day working from home!"
        if not body:
            body = "Hey there, buy bitcoin or viagra now! Visit http://casinogiant.com"
            
    if not body:
        body = "This is a generic mock email body."
        
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "poop@localhost"
    msg["Message-ID"] = f"<test-{uuid.uuid4()}@localhost>"
    msg.set_content(body)
    
    # Add List-Unsubscribe if it's a newsletter
    if type == "newsletter":
        msg["List-Unsubscribe"] = "<mailto:unsubscribe-weekly@huggingface.co?subject=unsubscribe-weekly>, <https://huggingface.co/unsubscribe?token=weekly-digest-token-xyz>"
        
    try:
        console.print(f"Connecting to SMTP daemon at {host}:{port}...")
        with smtplib.SMTP(host, port, timeout=5) as s:
            s.send_message(msg)
        console.print("[green]Mock email successfully sent via SMTP![/green]")
        console.print("[dim]Check 'hfmail inbox' to see the processed and classified email.[/dim]")
    except Exception as e:
        console.print(f"[red]Error sending email: {str(e)}[/red]")
        console.print("[yellow]Ensure the daemon is running with 'hfmail daemon start' before injecting test mails.[/yellow]")

@cli.command("sync")
def sync_emails():
    """Sync/fetch emails from the configured IMAP server."""
    console.print("[yellow]Connecting to IMAP server and checking for new messages...[/yellow]")
    try:
        stats = fetch_imap_emails()
        
        # Format output
        table = Table(title="[bold green]Sync completed successfully[/bold green]")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="bold green")
        
        table.add_row("Total Fetched", str(stats["fetched"]))
        table.add_row("Important Mentions", str(stats["important"]))
        table.add_row("Promotions/Newsletters", str(stats["promotion"]))
        table.add_row("Auto-Unsubscribed", str(stats["unsubscribed"]))
        table.add_row("Spam Filtered", str(stats["spam"]))
        table.add_row("Errors encountered", str(stats["errors"]))
        
        console.print(table)
        if stats["fetched"] > 0:
            console.print("[dim]Use 'hfmail inbox' to view new important messages.[/dim]")
    except ValueError as ve:
        console.print(f"[red]Configuration Error:[/red] {str(ve)}")
        console.print("[yellow]Hint: Configure your IMAP settings in config.json or use:[/yellow]")
        console.print("  hfmail config set incoming_imap.host imap.example.com")
        console.print("  hfmail config set incoming_imap.username user@example.com")
        console.print("  hfmail config set incoming_imap.password password")
    except Exception as e:
        console.print(f"[red]Error connecting/syncing IMAP server:[/red] {str(e)}")

if __name__ == "__main__":
    cli()
