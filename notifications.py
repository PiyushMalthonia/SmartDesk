import os
import smtplib
from email.message import EmailMessage


def notify_ticket_created(ticket, user):
    email = user["email"] if "email" in user.keys() else user["user_email"]
    subject = f"SmartDesk AI ticket #{ticket['id']} created"
    body = (
        f"Your ticket has been created.\n\n"
        f"Title: {ticket['title']}\n"
        f"Category: {ticket['category']} ({ticket['category_confidence']}%)\n"
        f"Priority: {ticket['priority']} ({ticket['priority_confidence']}%)\n"
        f"Assigned To: {ticket['assigned_to']}\n"
        f"SLA Due: {ticket['sla_due_at']}\n"
    )
    send_email(email, subject, body)


def notify_ticket_updated(ticket, user):
    email = user["email"] if "email" in user.keys() else user["user_email"]
    subject = f"SmartDesk AI ticket #{ticket['id']} updated"
    body = (
        f"Your ticket has been updated.\n\n"
        f"Title: {ticket['title']}\n"
        f"Status: {ticket['status']}\n"
        f"Assigned To: {ticket['assigned_to']}\n"
        f"Admin Notes: {ticket['admin_notes'] or 'None'}\n"
    )
    send_email(email, subject, body)


def send_email(to_email, subject, body):
    host = os.getenv("SMARTDESK_SMTP_HOST")
    port = int(os.getenv("SMARTDESK_SMTP_PORT", "587"))
    username = os.getenv("SMARTDESK_SMTP_USER")
    password = os.getenv("SMARTDESK_SMTP_PASSWORD")
    sender = os.getenv("SMARTDESK_EMAIL_FROM", username or "smartdesk@example.com")

    if not host or not username or not password:
        print(f"[email not configured] To: {to_email} | {subject}")
        return False

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(message)
        return True
    except Exception as exc:
        print(f"[email failed] {exc}")
        return False
