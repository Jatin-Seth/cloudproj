import csv
import json
import os
import time
from datetime import datetime
from io import StringIO
from urllib.parse import urlparse

from flask import Flask, flash, make_response, redirect, render_template, request, url_for

app = Flask(__name__)

# Flash messages need a secret key. This default keeps setup easy for beginners.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "expense-tracker-secret-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "expenses.json")
DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Shopping",
    "Health",
    "Travel",
    "Entertainment",
    "Other",
]


@app.template_filter("currency")
def currency_filter(value):
    """Show numbers like $1,234.50 inside templates."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0
    return f"${amount:,.2f}"


@app.template_filter("pretty_datetime")
def pretty_datetime_filter(value):
    """Turn a saved timestamp into a friendlier format."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return parsed.strftime("%d %b %Y, %I:%M %p")
    except (TypeError, ValueError):
        return value


def today_string():
    """Return today's date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")


def is_valid_date(date_text):
    """Check that a date matches the HTML date input format."""
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def normalize_whitespace(text):
    """Collapse repeated spaces and trim text."""
    return " ".join(str(text).split()).strip()


def normalize_category_name(category):
    """Keep category names clean and consistent for filters and charts."""
    cleaned = normalize_whitespace(category)
    if not cleaned:
        return "Uncategorized"
    return cleaned.title()


def generate_expense_id():
    """Generate a simple unique integer ID without a database."""
    return time.time_ns()


def expense_date_key(expense):
    """Convert an expense date string into a sortable datetime object."""
    return datetime.strptime(expense["expense_date"], "%Y-%m-%d")


def normalize_expense(expense):
    """Keep saved expense data consistent, even for older entries."""
    if not isinstance(expense, dict):
        return None

    try:
        amount = round(float(expense.get("amount", 0)), 2)
    except (TypeError, ValueError):
        return None

    if amount <= 0:
        return None

    category = normalize_category_name(expense.get("category", "Uncategorized"))
    note = normalize_whitespace(expense.get("note", ""))

    expense_date = str(expense.get("expense_date", "")).strip()
    if not is_valid_date(expense_date):
        created_at_text = str(expense.get("created_at", "")).strip()
        candidate = created_at_text[:10]
        expense_date = candidate if is_valid_date(candidate) else today_string()

    created_at = str(expense.get("created_at", "")).strip()
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    expense_id = expense.get("id")
    if not isinstance(expense_id, int):
        try:
            expense_id = int(expense_id)
        except (TypeError, ValueError):
            expense_id = generate_expense_id()

    return {
        "id": expense_id,
        "amount": amount,
        "category": category,
        "note": note,
        "expense_date": expense_date,
        "created_at": created_at,
    }


def load_expenses():
    """Load expenses from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            raw_data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(raw_data, list):
        return []

    expenses = []
    for raw_expense in raw_data:
        normalized = normalize_expense(raw_expense)
        if normalized:
            expenses.append(normalized)

    return expenses


def save_expenses(expenses):
    """Save expenses to the JSON file."""
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(expenses, file, indent=2)


def get_total(expenses):
    """Calculate the total of all expense amounts."""
    return round(sum(expense["amount"] for expense in expenses), 2)


def get_category_totals(expenses):
    """Group expenses by category for the chart and summary cards."""
    totals = {}
    for expense in expenses:
        category = normalize_category_name(expense["category"])
        totals[category] = totals.get(category, 0) + expense["amount"]

    sorted_totals = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return {category: round(total, 2) for category, total in sorted_totals}


def get_category_breakdown(expenses):
    """Create category rows with percentages for the UI."""
    total = get_total(expenses)
    breakdown = []

    for category, amount in get_category_totals(expenses).items():
        percentage = round((amount / total) * 100, 1) if total else 0
        breakdown.append(
            {
                "category": category,
                "amount": amount,
                "percentage": percentage,
            }
        )

    return breakdown


def filter_expenses(expenses, selected_category, search_text):
    """Filter expenses by category and free-text search."""
    filtered = expenses

    if selected_category and str(selected_category).lower() != "all":
        normalized_category = normalize_category_name(selected_category)
        filtered = [expense for expense in filtered if expense["category"] == normalized_category]

    if search_text:
        needle = search_text.lower()
        filtered = [
            expense
            for expense in filtered
            if needle in expense["category"].lower()
            or needle in expense["note"].lower()
            or needle in expense["expense_date"]
            or needle in f"{expense['amount']:.2f}"
        ]

    return filtered


def sort_expenses(expenses, sort_by):
    """Sort expenses for list display."""
    if sort_by == "oldest":
        return sorted(expenses, key=lambda expense: (expense_date_key(expense), expense["id"]))
    if sort_by == "highest":
        return sorted(expenses, key=lambda expense: (-expense["amount"], -expense["id"]))
    if sort_by == "lowest":
        return sorted(expenses, key=lambda expense: (expense["amount"], -expense["id"]))
    if sort_by == "category":
        return sorted(expenses, key=lambda expense: (expense["category"].lower(), -expense["amount"]))

    return sorted(expenses, key=lambda expense: (expense_date_key(expense), expense["id"]), reverse=True)


def get_dashboard_stats(all_expenses, visible_expenses):
    """Build simple stats for the dashboard cards."""
    visible_total = get_total(visible_expenses)
    overall_total = get_total(all_expenses)
    visible_count = len(visible_expenses)
    overall_count = len(all_expenses)
    average_expense = round(visible_total / visible_count, 2) if visible_count else 0

    current_month = datetime.now().strftime("%Y-%m")
    monthly_total = round(
        sum(expense["amount"] for expense in visible_expenses if expense["expense_date"].startswith(current_month)),
        2,
    )

    category_totals = get_category_totals(visible_expenses)
    top_category_name = next(iter(category_totals), "No Category Yet")
    top_category_amount = category_totals.get(top_category_name, 0)
    largest_expense = max(visible_expenses, key=lambda expense: expense["amount"], default=None)

    return {
        "visible_total": visible_total,
        "overall_total": overall_total,
        "visible_count": visible_count,
        "overall_count": overall_count,
        "average_expense": average_expense,
        "monthly_total": monthly_total,
        "top_category_name": top_category_name,
        "top_category_amount": top_category_amount,
        "largest_expense": largest_expense,
    }


def get_active_filters(selected_category, search_query, sort_by):
    """Create simple active-filter labels for the UI."""
    filters = []

    if selected_category != "all":
        filters.append(f"Category: {normalize_category_name(selected_category)}")
    if search_query:
        filters.append(f"Search: {search_query}")
    if sort_by != "newest":
        sort_labels = {
            "oldest": "Oldest first",
            "highest": "Highest amount",
            "lowest": "Lowest amount",
            "category": "Category name",
        }
        filters.append(f"Sort: {sort_labels.get(sort_by, 'Newest first')}")

    return filters


def get_recent_categories(expenses, limit=6):
    """Return the most-used categories for quick form buttons."""
    counts = {}
    for expense in expenses:
        category = expense["category"]
        counts[category] = counts.get(category, 0) + 1

    ranked_categories = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    recent_categories = [category for category, _ in ranked_categories[:limit]]

    for category in DEFAULT_CATEGORIES:
        if category not in recent_categories and len(recent_categories) < limit:
            recent_categories.append(category)

    return recent_categories


def sanitize_next_url(next_url):
    """Allow redirects only back to pages inside this app."""
    if not next_url:
        return None

    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path.startswith("/"):
        return None

    cleaned = parsed.path
    if parsed.query:
        cleaned = f"{cleaned}?{parsed.query}"
    return cleaned


def get_redirect_target(default_endpoint="index"):
    """Send the user back to the page they came from when it is safe."""
    next_url = sanitize_next_url(request.form.get("next_url", "").strip())
    if next_url:
        return next_url

    referrer = request.referrer or ""
    safe_referrer = sanitize_next_url(urlparse(referrer).path + (f"?{urlparse(referrer).query}" if urlparse(referrer).query else ""))
    if safe_referrer:
        return safe_referrer

    return url_for(default_endpoint)


@app.route("/", methods=["GET"])
def index():
    all_expenses = sort_expenses(load_expenses(), "newest")
    raw_category = request.args.get("category", "all").strip()
    selected_category = "all" if raw_category.lower() in ("", "all") else normalize_category_name(raw_category)
    search_query = normalize_whitespace(request.args.get("search", ""))
    sort_by = request.args.get("sort", "newest")

    filtered_expenses = filter_expenses(all_expenses, selected_category, search_query)
    visible_expenses = sort_expenses(filtered_expenses, sort_by)
    category_totals = get_category_totals(visible_expenses)
    category_breakdown = get_category_breakdown(visible_expenses)
    stats = get_dashboard_stats(all_expenses, visible_expenses)
    categories = sorted({expense["category"] for expense in all_expenses})
    suggested_categories = sorted(set(DEFAULT_CATEGORIES + categories))
    quick_categories = get_recent_categories(all_expenses)
    current_url = request.full_path[:-1] if request.full_path.endswith("?") else request.full_path
    has_filters = selected_category != "all" or bool(search_query) or sort_by != "newest"
    active_filters = get_active_filters(selected_category, search_query, sort_by)

    return render_template(
        "index.html",
        expenses=visible_expenses,
        category_totals=category_totals,
        category_breakdown=category_breakdown,
        categories=categories,
        suggested_categories=suggested_categories,
        quick_categories=quick_categories,
        selected_category=selected_category,
        search_query=search_query,
        sort_by=sort_by,
        stats=stats,
        has_filters=has_filters,
        active_filters=active_filters,
        today=today_string(),
        current_url=current_url or url_for("index"),
    )


@app.route("/add", methods=["POST"])
def add_expense():
    """Add a new expense from the form."""
    amount_text = request.form.get("amount", "").strip()
    category = normalize_category_name(request.form.get("category", ""))
    note = normalize_whitespace(request.form.get("note", ""))
    expense_date = request.form.get("expense_date", "").strip() or today_string()

    if not amount_text or not category or not expense_date:
        flash("Please fill in amount, category, and date.", "error")
        return redirect(get_redirect_target())

    try:
        amount = float(amount_text)
    except ValueError:
        flash("Amount must be a valid number.", "error")
        return redirect(get_redirect_target())

    if amount <= 0:
        flash("Amount must be greater than zero.", "error")
        return redirect(get_redirect_target())

    if not is_valid_date(expense_date):
        flash("Please select a valid expense date.", "error")
        return redirect(get_redirect_target())

    expenses = load_expenses()
    expenses.append(
        {
            "id": generate_expense_id(),
            "amount": round(amount, 2),
            "category": category,
            "note": note,
            "expense_date": expense_date,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    save_expenses(sort_expenses(expenses, "newest"))
    flash("Expense added successfully.", "success")

    # After a successful add, return to the main list so the new item is visible.
    return redirect(url_for("index"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    """Delete one expense by its ID."""
    expenses = load_expenses()
    updated_expenses = [expense for expense in expenses if expense["id"] != expense_id]

    if len(updated_expenses) == len(expenses):
        flash("Expense not found.", "error")
    else:
        save_expenses(updated_expenses)
        flash("Expense deleted.", "success")

    return redirect(get_redirect_target())


@app.route("/clear", methods=["POST"])
def clear_expenses():
    """Remove all saved expenses."""
    expenses = load_expenses()

    if not expenses:
        flash("There are no expenses to clear.", "error")
    else:
        save_expenses([])
        flash("All expenses were cleared.", "success")

    return redirect(url_for("index"))


@app.route("/export", methods=["GET"])
def export_csv():
    """Export the current filtered list as a CSV file."""
    all_expenses = load_expenses()
    selected_category = request.args.get("category", "all")
    search_query = normalize_whitespace(request.args.get("search", ""))
    sort_by = request.args.get("sort", "newest")

    filtered_expenses = filter_expenses(all_expenses, selected_category, search_query)
    visible_expenses = sort_expenses(filtered_expenses, sort_by)

    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["Amount", "Category", "Note", "Expense Date", "Created At"])

    for expense in visible_expenses:
        writer.writerow(
            [
                f"{expense['amount']:.2f}",
                expense["category"],
                expense["note"],
                expense["expense_date"],
                expense["created_at"],
            ]
        )

    response = make_response(csv_buffer.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=expenses.csv"
    return response


if __name__ == "__main__":
    # Run on all network interfaces for easy EC2 deployment.
    app.run(host="0.0.0.0", port=5000)
