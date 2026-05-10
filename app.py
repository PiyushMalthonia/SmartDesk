import os
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from ai_predictor import CATEGORIES, PRIORITIES, predict_ticket, suggest_chat_reply
from database import BASE_DIR, get_connection, init_db
from notifications import notify_ticket_created, notify_ticket_updated

STATUSES = ["Open", "In Progress", "Resolved", "Closed"]
CATEGORY_OPTIONS = [*CATEGORIES.keys(), "Other"]
TEAMS = ["IT Team", "Network Team", "Security Team"]
UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "log"}
SLA_HOURS = {"Critical": 1, "High": 4, "Medium": 24, "Low": 72}


def create_app():
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "smartdesk-ai-dev-secret")
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.permanent_session_lifetime = timedelta(days=30)
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    init_db()

    @app.before_request
    def load_user():
        g.user = None
        user_id = session.get("user_id")
        if user_id:
            with get_connection() as conn:
                g.user = conn.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()

    @app.route("/")
    def landing():
        if g.user and request.args.get("app") == "1":
            return redirect(url_for("index"))
        return render_template("landing.html")

    @app.route("/app")
    def index():
        if g.user and g.user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        if g.user:
            return redirect(url_for("user_dashboard"))
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not name or not email or len(password) < 6:
                flash("Enter a name, valid email, and password of at least 6 characters.", "danger")
                return render_template("register.html")

            try:
                with get_connection() as conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO users (name, email, password_hash, role)
                        VALUES (?, ?, ?, 'user')
                        """,
                        (name, email, generate_password_hash(password)),
                    )
                    user_id = cursor.lastrowid
                session.clear()
                session.permanent = True
                session["user_id"] = user_id
                flash("Account created. You are signed in and will stay logged in.", "success")
                return redirect(url_for("index"))
            except Exception:
                flash("That email is already registered.", "danger")

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            with get_connection() as conn:
                user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session.permanent = True
                session["user_id"] = user["id"]
                flash(f"Welcome back, {user['name']}.", "success")
                return redirect(url_for("index"))

            flash("Invalid email or password.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Signed out successfully.", "success")
        return redirect(url_for("landing"))

    @app.route("/dashboard")
    @login_required
    def user_dashboard():
        with get_connection() as conn:
            tickets = conn.execute(
                """
                SELECT * FROM tickets
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (g.user["id"],),
            ).fetchall()
        return render_template("user_dashboard.html", tickets=tickets, metrics=build_metrics(user_id=g.user["id"]))

    @app.route("/tickets/new", methods=["GET", "POST"])
    @login_required
    def create_ticket():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()

            if not title or not description:
                flash("Title and description are required.", "danger")
                return render_template("create_ticket.html")

            prediction = predict_ticket(title, description)
            attachment_path = save_attachment(request.files.get("attachment"))
            sla_due_at = calculate_sla_due(prediction["priority"])
            assigned_to = default_team(prediction["category"])

            with get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO tickets (
                        user_id, title, description, category, priority,
                        category_confidence, priority_confidence, confidence,
                        assigned_to, sla_due_at, attachment_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        g.user["id"],
                        title,
                        description,
                        prediction["category"],
                        prediction["priority"],
                        prediction["category_confidence"],
                        prediction["priority_confidence"],
                        prediction["confidence"],
                        assigned_to,
                        sla_due_at,
                        attachment_path,
                    ),
                )
                ticket_id = cursor.lastrowid
                add_log(conn, ticket_id, "Ticket Created")
                add_log(conn, ticket_id, f"AI routed to {assigned_to}")
                ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            notify_ticket_created(ticket, g.user)
            flash("Ticket created with AI-powered support prediction.", "success")
            return redirect(url_for("ticket_detail", ticket_id=ticket["id"]))

        return render_template("create_ticket.html")

    @app.route("/tickets/<int:ticket_id>")
    @login_required
    def ticket_detail(ticket_id):
        ticket = fetch_ticket(ticket_id)
        if not ticket:
            abort(404)
        if g.user["role"] != "admin" and ticket["user_id"] != g.user["id"]:
            abort(403)
        logs = fetch_logs(ticket_id)
        return render_template("ticket_detail.html", ticket=ticket, logs=logs, sla=sla_state(ticket))

    @app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
    @login_required
    def delete_ticket(ticket_id):
        ticket = fetch_ticket(ticket_id)
        if not ticket:
            abort(404)
        if g.user["role"] == "admin" or ticket["user_id"] != g.user["id"]:
            abort(403)

        attachment_path = ticket["attachment_path"]
        with get_connection() as conn:
            conn.execute("DELETE FROM ticket_logs WHERE ticket_id = ?", (ticket_id,))
            conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))

        if attachment_path:
            attachment_file = UPLOAD_FOLDER / attachment_path
            if attachment_file.is_file():
                attachment_file.unlink()

        flash("Ticket removed successfully.", "success")
        return redirect(url_for("user_dashboard"))

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        status = request.args.get("status", "")
        category = request.args.get("category", "")
        search = request.args.get("search", "").strip()
        tickets = query_admin_tickets(status, category, search)
        charts = build_chart_data()
        return render_template(
            "admin_dashboard.html",
            tickets=tickets,
            statuses=STATUSES,
            categories=CATEGORY_OPTIONS,
            charts=charts,
            metrics=build_metrics(),
            activity=latest_activity(),
            filters={"status": status, "category": category, "search": search},
        )

    @app.route("/admin/tickets/<int:ticket_id>", methods=["GET", "POST"])
    @admin_required
    def admin_ticket(ticket_id):
        ticket = fetch_ticket(ticket_id)
        if not ticket:
            abort(404)

        if request.method == "POST":
            status = request.form.get("status", "Open")
            category = request.form.get("category", "Other")
            priority = request.form.get("priority", "Low")
            assigned_to = request.form.get("assigned_to", "IT Team")
            admin_notes = request.form.get("admin_notes", "").strip()

            if (
                status not in STATUSES
                or category not in CATEGORY_OPTIONS
                or priority not in PRIORITIES
                or assigned_to not in TEAMS
            ):
                flash("Invalid ticket update values.", "danger")
                return redirect(url_for("admin_ticket", ticket_id=ticket_id))

            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE tickets
                    SET status = ?, category = ?, priority = ?, assigned_to = ?, admin_notes = ?
                    WHERE id = ?
                    """,
                    (status, category, priority, assigned_to, admin_notes, ticket_id),
                )
                if status != ticket["status"]:
                    add_log(conn, ticket_id, f"Admin changed status to {status}")
                if assigned_to != ticket["assigned_to"]:
                    add_log(conn, ticket_id, f"Assigned to {assigned_to}")
                if admin_notes and admin_notes != ticket["admin_notes"]:
                    add_log(conn, ticket_id, "Admin added notes")
            updated = fetch_ticket(ticket_id)
            notify_ticket_updated(updated, updated)
            flash("Ticket updated.", "success")
            return redirect(url_for("admin_ticket", ticket_id=ticket_id))

        return render_template(
            "admin_ticket.html",
            ticket=ticket,
            logs=fetch_logs(ticket_id),
            sla=sla_state(ticket),
            statuses=STATUSES,
            categories=CATEGORY_OPTIONS,
            priorities=PRIORITIES,
            teams=TEAMS,
        )

    @app.route("/analytics")
    @admin_required
    def analytics():
        return render_template("analytics.html", charts=build_chart_data(), metrics=build_metrics())

    @app.route("/api/search")
    @login_required
    def search_suggestions():
        term = request.args.get("q", "").strip()
        if len(term) < 2:
            return jsonify([])

        params = [f"%{term}%", f"%{term}%"]
        role_clause = ""
        if g.user["role"] != "admin":
            role_clause = "AND user_id = ?"
            params.append(g.user["id"])

        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, title, status, priority
                FROM tickets
                WHERE (title LIKE ? OR description LIKE ?) {role_clause}
                ORDER BY updated_at DESC
                LIMIT 8
                """,
                params,
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route("/api/chat", methods=["POST"])
    @login_required
    def chat_assistant():
        message = request.json.get("message", "") if request.is_json else request.form.get("message", "")
        return jsonify({"reply": suggest_chat_reply(message)})

    return app


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Sign in to continue.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_attachment(file):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        flash("Attachment type not allowed. Use images, PDF, TXT, or LOG files.", "warning")
        return None
    safe_name = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{timestamp}_{safe_name}"
    file.save(UPLOAD_FOLDER / stored_name)
    return stored_name


def calculate_sla_due(priority):
    return (datetime.now() + timedelta(hours=SLA_HOURS.get(priority, 24))).strftime("%Y-%m-%d %H:%M:%S")


def default_team(category):
    if category == "Network":
        return "Network Team"
    if category == "Security":
        return "Security Team"
    return "IT Team"


def add_log(conn, ticket_id, action):
    conn.execute("INSERT INTO ticket_logs (ticket_id, action) VALUES (?, ?)", (ticket_id, action))


def fetch_logs(ticket_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM ticket_logs
            WHERE ticket_id = ?
            ORDER BY timestamp ASC
            """,
            (ticket_id,),
        ).fetchall()


def fetch_ticket(ticket_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT tickets.*, users.name AS user_name, users.email AS user_email
            FROM tickets
            JOIN users ON users.id = tickets.user_id
            WHERE tickets.id = ?
            """,
            (ticket_id,),
        ).fetchone()


def query_admin_tickets(status, category, search):
    clauses = []
    params = []
    if status:
        clauses.append("tickets.status = ?")
        params.append(status)
    if category:
        clauses.append("tickets.category = ?")
        params.append(category)
    if search:
        clauses.append("(tickets.title LIKE ? OR tickets.description LIKE ? OR users.email LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT tickets.*, users.name AS user_name, users.email AS user_email
            FROM tickets
            JOIN users ON users.id = tickets.user_id
            {where}
            ORDER BY tickets.created_at DESC
            """,
            params,
        ).fetchall()


def build_metrics(user_id=None):
    user_clause = "WHERE user_id = ?" if user_id else ""
    params = [user_id] if user_id else []
    with get_connection() as conn:
        rows = conn.execute(f"SELECT status, priority, sla_due_at FROM tickets {user_clause}", params).fetchall()

    now = datetime.now()
    breaches = 0
    for row in rows:
        if row["status"] not in ("Resolved", "Closed") and row["sla_due_at"]:
            breaches += datetime.strptime(row["sla_due_at"], "%Y-%m-%d %H:%M:%S") < now

    return {
        "open": sum(1 for row in rows if row["status"] == "Open"),
        "resolved": sum(1 for row in rows if row["status"] == "Resolved"),
        "critical": sum(1 for row in rows if row["priority"] == "Critical"),
        "sla_breaches": breaches,
    }


def build_chart_data():
    with get_connection() as conn:
        status_rows = conn.execute(
            "SELECT status AS label, COUNT(*) AS value FROM tickets GROUP BY status"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT category AS label, COUNT(*) AS value FROM tickets GROUP BY category"
        ).fetchall()
        priority_rows = conn.execute(
            "SELECT priority AS label, COUNT(*) AS value FROM tickets GROUP BY priority"
        ).fetchall()
        team_rows = conn.execute(
            "SELECT assigned_to AS label, COUNT(*) AS value FROM tickets GROUP BY assigned_to"
        ).fetchall()
        recent_rows = conn.execute(
            """
            SELECT DATE(created_at) AS label, COUNT(*) AS value
            FROM tickets
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at) DESC
            LIMIT 10
            """
        ).fetchall()

    return {
        "status": normalize_counts(status_rows, STATUSES),
        "category": normalize_counts(category_rows, CATEGORY_OPTIONS),
        "priority": normalize_counts(priority_rows, PRIORITIES),
        "team": normalize_counts(team_rows, TEAMS),
        "recent": list(reversed([dict(row) for row in recent_rows])),
    }


def latest_activity():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT ticket_logs.*, tickets.title
            FROM ticket_logs
            JOIN tickets ON tickets.id = ticket_logs.ticket_id
            ORDER BY ticket_logs.timestamp DESC
            LIMIT 8
            """
        ).fetchall()


def normalize_counts(rows, labels):
    row_map = {row["label"]: row["value"] for row in rows}
    return [{"label": label, "value": row_map.get(label, 0)} for label in labels]


def sla_state(ticket):
    if not ticket["sla_due_at"]:
        return {"label": "No SLA", "seconds": 0, "breached": False}
    due = datetime.strptime(ticket["sla_due_at"], "%Y-%m-%d %H:%M:%S")
    remaining = int((due - datetime.now()).total_seconds())
    return {
        "label": due.strftime("%d %b %Y, %I:%M %p"),
        "seconds": remaining,
        "breached": remaining < 0 and ticket["status"] not in ("Resolved", "Closed"),
    }


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
