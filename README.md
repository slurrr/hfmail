# hfmail

A terminal email client and local SMTP receiver that triages Hugging Face
notifications into `important`, `promotion`, `spam` and `unsubscribed`. It
receives mail over IMAP or a local SMTP listener, stores it in SQLite, applies
sender/subject filters and Hugging Face-specific heuristics, and presents the
result in a fast `rich` CLI. It never sends or replies with anything except
automated `List-Unsubscribe` messages.

## Requirements

- Python 3.14 or newer (see `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- One way to receive mail: an IMAP mailbox, or a local SMTP path to the
  included daemon
- Outgoing SMTP credentials only if you want automatic unsubscribe emails

## Install

From a checkout of this repository:

```bash
uv sync
uv run hfmail --help
```

`uv sync` installs the `hfmail` CLI and the `hfmaild` SMTP server into the
project environment. `uv run <command>` runs them from that environment.

## Runtime state

On first use hfmail creates `~/runs/hfmail/` and keeps all local state there:

| Path | Purpose |
| --- | --- |
| `config.json` | IMAP, SMTP and classification settings |
| `mail.db` | SQLite email store and custom filters |
| `daemon.pid` | PID of the background SMTP daemon |
| `daemon.log` | Daemon log |

Delete that directory to reset the application. Nothing is stored in the
repository.

## Receiving mail

### Option A: IMAP (recommended)

```bash
uv run hfmail config set incoming_imap.host imap.example.com
uv run hfmail config set incoming_imap.username user@example.com
uv run hfmail config set incoming_imap.password secret
uv run hfmail sync
```

`sync` fetches unseen messages, classifies them and optionally triggers
unsubscribe actions. Schedule it with cron or a systemd timer if you want
periodic delivery.

### Option B: local SMTP daemon

```bash
uv run hfmail daemon start
uv run hfmail daemon status
uv run hfmail daemon stop
```

The daemon listens on `127.0.0.1:1025` by default. Change the address with:

```bash
uv run hfmail config set incoming_smtp.host 127.0.0.1
uv run hfmail config set incoming_smtp.port 1025
```

To run the receiver in the foreground, use `uv run hfmail daemon run` or
`uv run hfmaild`. The SMTP listener has no authentication or TLS; keep it on
loopback or a private network.

## Example

With the daemon running, inject a sample notification and list it:

```bash
uv run hfmail test-receive --type mention
uv run hfmail inbox
```

```text
┌─────┬───────────┬──────────────────────────┬───────────────────────────────────────┬─────────────────────┬──────┐
│ ID  │ Category  │ Sender                   │ Subject                               │ Received            │ Read │
├─────┼───────────┼──────────────────────────┼───────────────────────────────────────┼─────────────────────┼──────┤
│ 1   │ IMPORTANT │ website@huggingface.co   │ [Hugging Face] @you mentioned you ... │ 2026-01-01 12:00:00 │ No   │
└─────┴───────────┴──────────────────────────┴───────────────────────────────────────┴─────────────────────┴──────┘
Showing 1 emails. Run with --all to see read messages.
```

Other presets are `--type newsletter`, `--type spam` and `--type other`, or pass
`--sender`, `--subject` and `--body` explicitly. Read a message with
`uv run hfmail read 1`.

## Commands

| Command | Purpose |
| --- | --- |
| `hfmail sync` | Fetch new mail from IMAP |
| `hfmail inbox [--all] [--category C] [--search TEXT] [--limit N]` | List messages |
| `hfmail read <id> [--raw]` | Render a message and mark it read |
| `hfmail delete <id>` | Delete a message from the local store |
| `hfmail unsubscribe <id>` | Send the list's unsubscribe request and block the sender |
| `hfmail spam <id>` | Move to spam and block the sender |
| `hfmail important <id>` | Move to important and whitelist the sender |
| `hfmail filters list` | List classification filters |
| `hfmail filters add <sender\|subject> <pattern> <action>` | Add a filter |
| `hfmail filters remove <id>` | Remove a filter |
| `hfmail config show` | Print the merged configuration |
| `hfmail config set <key> <value>` | Update a setting |
| `hfmail daemon start\|stop\|status\|run` | Manage the SMTP daemon |
| `hfmail test-receive` | Inject a sample message through SMTP |

## Classification

Messages are classified in this order:

1. Custom filter rules from the database.
2. `only_huggingface` (default `true`): non-Hugging Face senders become spam.
3. Obvious spam keywords.
4. Security and direct-mention subjects become important.
5. Newsletter, digest and announcement subjects become promotion.
6. Remaining messages with a `List-Unsubscribe` header become promotion.
7. Everything else becomes important.

## Outgoing SMTP

Outgoing SMTP is used only to send unsubscribe requests found in a message's
`List-Unsubscribe` header. Configure it with `hfmail config set` or edit
`~/runs/hfmail/config.json`:

```json
{
  "outgoing_smtp": {
    "host": "smtp.example.com",
    "port": 587,
    "username": "you@example.com",
    "password": "your-password",
    "use_tls": true,
    "from_address": "you@example.com"
  }
}
```

## Verify

There is no automated test suite yet. This round trip exercises SMTP receipt,
MIME parsing, storage, classification and the CLI, and keeps all state in a
temporary home directory:

```bash
export HOME="$(mktemp -d)"
.venv/bin/hfmail config set incoming_smtp.port 1125
.venv/bin/hfmail daemon start
sleep 1
.venv/bin/hfmail test-receive --type mention
.venv/bin/hfmail inbox
.venv/bin/hfmail daemon stop
```

Expected: `test-receive` prints `Mock email successfully sent via SMTP!`, and
`inbox` shows one `IMPORTANT` row with subject
`[Hugging Face] @you mentioned you in discussion ...`.

## License

MIT. See [LICENSE](LICENSE).
