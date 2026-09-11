# hfmail ✉️🤖

`hfmail` is a CLI-only email workspace and SMTP receiver custom-built for people who hate email and want to interact with Hugging Face notifications strictly through a powerful, beautiful, and automated terminal interface.

By running a local SMTP daemon (`hfmaild`), it bypasses commercial email providers. Incoming emails are received directly, stored in a local SQLite database, classified using Hugging Face-tailored heuristics, and optionally auto-unsubscribed.

---

## 🛠️ Architecture

- **Daemon (`hfmaild`)**: Listening on a local port (default `1025`). It accepts SMTP connections, parses MIME payloads, runs spam/mention heuristics, auto-unsubscribes promotions, and persists records.
- **Database (`mail.db`)**: Located at `~/runs/hfmail/mail.db`. Contains the emails and custom classification filters.
- **Config (`config.json`)**: Located at `~/runs/hfmail/config.json`. Configures the SMTP receiver and outgoing SMTP credentials.
- **CLI (`hfmail`)**: Rich terminal user interface using colors and layout panels.

---

## 🚀 Getting Started

### 1. Installation

`hfmail` is managed using `uv` and resides in `~/code/dev/hfmail/`. It exposes commands via symlinks in `~/.local/bin/`.

```bash
# Clone/Nav to project
cd ~/code/dev/hfmail

# Install in editable mode
uv pip install -e .
```

### 2. Setting Up Incoming Email

`hfmail` supports two ways of receiving emails:

#### Option A: IMAP Fetcher (Safer, Recommended)
You can fetch emails from a standard, custom-registered mailbox on a secure provider:
1. Configure your credentials:
   ```bash
   hfmail config set incoming_imap.host imap.example.com
   hfmail config set incoming_imap.username user@example.com
   hfmail config set incoming_imap.password secretpassword
   ```
2. Sync new mail using the CLI command:
   ```bash
   hfmail sync
   ```
*(You can schedule `hfmail sync` in a local cron job to run periodically).*

#### Option B: SMTP Daemon (Local Receiver)
Start the background SMTP receiver daemon:
```bash
hfmail daemon start
```
Check status and see logs:
```bash
hfmail daemon status
```
Stop the daemon:
```bash
hfmail daemon stop
```

---

## 💻 CLI Commands

### Viewing and Reading Email
- **`hfmail sync`**: Connects to the configured IMAP server, downloads new unseen emails, processes classifications, and triggers auto-unsubscribe.
- **`hfmail inbox`**: Shows all unread **important** emails (e.g. direct mentions, PRs, security alerts) in a clean, color-coded table.
- **`hfmail inbox --all`**: Shows all emails (read/unread) across all categories.
- **`hfmail inbox --category promotion`**: Show only emails classified as promotions/newsletters.
- **`hfmail inbox --category spam`**: Show spam emails.
- **`hfmail inbox --category unsubscribed`**: Show messages from unsubscribed lists.
- **`hfmail read <id>`**: Renders metadata in a panel, formats the body as markdown, and marks the email as read.
- **`hfmail delete <id>`**: Removes the email from the database.

### Actions & Automation
- **`hfmail unsubscribe <id>`**: Attempts to perform an HTTP request on the unsubscribe URL and sends an SMTP email to the `List-Unsubscribe` mailto address. It also automatically registers a block filter for this sender.
- **`hfmail spam <id>`**: Changes category to `spam` and adds a permanent filter to automatically classify future emails from this sender as spam.
- **`hfmail important <id>`**: Marks email as important and adds a whitelisting filter.

### Filters Management
- **`hfmail filters list`**: Lists all active pattern-matching rules.
- **`hfmail filters add sender <email_or_domain> <action>`**: E.g. `hfmail filters add sender badguy@spammer.org spam`.
- **`hfmail filters remove <id>`**: Deletes a filter pattern.

### Config Management
- **`hfmail config show`**: Displays the active configuration in JSON.
- **`hfmail config set <key> <value>`**: E.g. `hfmail config set outgoing_smtp.host smtp.gmail.com`.

---

## 🧪 Injecting Test Emails

You can test the system locally using the `test-receive` command while the daemon is running:

```bash
# Inject a mention (goes to important inbox)
hfmail test-receive --type mention

# Inject a weekly newsletter (auto-unsubscribes and gets filed as unsubscribed)
hfmail test-receive --type newsletter

# Inject spam (gets filed as spam)
hfmail test-receive --type spam

# Inject custom details
hfmail test-receive --type other --sender somebody@huggingface.co --subject "Custom subject" --body "Hello body"
```

---

## 📬 Routing Production Email to hfmail

Because the SMTP server runs on your local workstation, you need to route public mail to it. Here are the three standard approaches:

1. **Direct Public MX Routing**:
   - Run the daemon on a VPS with a public IP.
   - Point your domain's MX record to your VPS IP address.
   - Map port 25 to `1025` using `iptables` or systemd socket activation.
   - Connect from your local CLI to the VPS database (or copy/sync it).
2. **Reverse Proxy Tunnel (Ngrok / Cloudflare Tunnel)**:
   - Expose port `1025` on your machine using a tunnel.
   - Point your MX server/domain to the tunnel end-point.
3. **Mail Fetcher / Relay Daemon**:
   - Fetch mails from a minimal external IMAP address using a lightweight script, and pipe them to your local port `1025` using SMTP injection.

---

## ✉️ Outgoing SMTP Configuration

Configure your settings in `~/runs/hfmail/config.json` (or use `hfmail config set`):

```json
{
    "incoming_smtp": {
        "host": "127.0.0.1",
        "port": 1025
    },
    "incoming_imap": {
        "host": "imap.example.com",
        "port": 993,
        "username": "user@example.com",
        "password": "secretpassword",
        "use_ssl": true,
        "folder": "INBOX"
    },
    "outgoing_smtp": {
        "host": "smtp.example.com",
        "port": 587,
        "username": "your-user@example.com",
        "password": "your-password",
        "use_tls": true,
        "from_address": "your-user@example.com"
    },
    "auto_unsubscribe": true,
    "only_huggingface": true
}
```
*Note*: As requested, this email client is hardcoded to never send or reply with any message other than automated unsubscribe letters.
