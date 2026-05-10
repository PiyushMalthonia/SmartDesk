"""Local AI-lite prediction helpers for SmartDesk AI tickets."""

CATEGORIES = {
    "Hardware": [
        "laptop",
        "desktop",
        "monitor",
        "keyboard",
        "mouse",
        "printer",
        "scanner",
        "battery",
        "screen",
        "hard drive",
        "ram",
        "device",
    ],
    "Software": [
        "software",
        "app",
        "application",
        "install",
        "update",
        "crash",
        "license",
        "bug",
        "error",
        "windows",
        "excel",
    ],
    "Network": [
        "network",
        "wifi",
        "wi-fi",
        "internet",
        "vpn",
        "router",
        "dns",
        "connection",
        "lan",
        "slow",
    ],
    "Account/Login": [
        "password",
        "login",
        "log in",
        "account",
        "locked",
        "access",
        "mfa",
        "otp",
        "credential",
    ],
    "Email": [
        "email",
        "mail",
        "outlook",
        "inbox",
        "smtp",
        "attachment",
        "calendar",
    ],
    "Security": [
        "virus",
        "malware",
        "phishing",
        "ransomware",
        "breach",
        "suspicious",
        "hacked",
        "security",
        "data leak",
    ],
}

PRIORITY_KEYWORDS = {
    "Critical": [
        "critical",
        "urgent",
        "emergency",
        "outage",
        "down",
        "breach",
        "ransomware",
        "cannot work",
        "entire team",
        "all users",
        "production",
    ],
    "High": [
        "blocked",
        "deadline",
        "failed",
        "not working",
        "unable",
        "multiple users",
        "client",
        "payment",
    ],
    "Medium": [
        "slow",
        "intermittent",
        "issue",
        "problem",
        "error",
        "warning",
        "delay",
    ],
}

PRIORITIES = ["Low", "Medium", "High", "Critical"]


def predict_category(title, description):
    text = f"{title} {description}".lower()
    scores = {}

    for category, keywords in CATEGORIES.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score:
            scores[category] = score

    if not scores:
        return "Other", 58

    category, score = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
    confidence = min(96, 68 + (score * 8))
    return category, confidence


def predict_priority(title, description, category=None):
    text = f"{title} {description}".lower()
    score = 0

    for priority, keywords in PRIORITY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if priority == "Critical":
            score += hits * 4
        elif priority == "High":
            score += hits * 3
        else:
            score += hits * 2

    if category == "Security":
        score += 3
    if "?" in text:
        score -= 1
    if len(description) < 40:
        score -= 1

    if score >= 7:
        return "Critical", min(97, 82 + score)
    if score >= 4:
        return "High", min(94, 78 + score)
    if score >= 1:
        return "Medium", min(90, 70 + score)
    return "Low", 62


def suggest_chat_reply(message):
    text = message.lower()
    if any(word in text for word in ["vpn", "network", "wifi", "internet"]):
        return "Try reconnecting to the company VPN, restarting Wi-Fi, and checking whether other sites load. If the issue continues, create a Network ticket with the error message."
    if any(word in text for word in ["password", "login", "account", "locked"]):
        return "Use the password reset flow first. If your account is locked or MFA is failing, create an Account/Login ticket so IT can verify your identity and unlock access."
    if any(word in text for word in ["phishing", "virus", "malware", "hacked"]):
        return "Disconnect from the network if possible, do not click more links, and create a Security ticket immediately. Mark it Critical if company data may be exposed."
    if any(word in text for word in ["printer", "monitor", "keyboard", "laptop"]):
        return "Check cables, power, and restart the device. Attach a screenshot or photo when creating a Hardware ticket so the IT team can diagnose faster."
    if any(word in text for word in ["email", "outlook", "mail"]):
        return "Restart Outlook or webmail, confirm your internet connection, and include any bounce/error message in an Email ticket."
    return "I can help triage this. Describe the affected app/device, who is impacted, and the exact error message, then create a ticket so SmartDesk AI can route it."


def predict_ticket(title, description):
    category, category_confidence = predict_category(title, description)
    priority, priority_confidence = predict_priority(title, description, category)
    return {
        "category": category,
        "priority": priority,
        "confidence": round((category_confidence + priority_confidence) / 2),
        "category_confidence": category_confidence,
        "priority_confidence": priority_confidence,
    }
