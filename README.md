# Expense Tracker

A simple and beginner-friendly Expense Tracker built with Python Flask.

## Features

- Add an expense with amount and category
- Add an optional note and expense date
- View all expenses
- See total expenses
- Delete expenses
- Filter by category or search text
- Sort by newest, oldest, highest, lowest, or category
- Export visible expenses to CSV
- Clear all expenses
- View a simple pie chart using Chart.js
- Store data in a local JSON file

## Project Structure

```text
expense-tracker/
│
├── app.py
├── requirements.txt
├── expenses.json
├── templates/
│   └── index.html
├── static/
│   └── style.css
├── README.md
```

## Local Run

1. Make sure Python 3 is installed.
2. Install the dependency:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python app.py
```

4. Open your browser and visit:

```text
http://localhost:5000
```

## AWS EC2 Deployment Steps

Run these exact commands on your EC2 Ubuntu server:

```bash
sudo apt update
sudo apt install python3-pip python3-venv -y
git clone <repo>
cd expense-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The Flask app runs on:

```python
host='0.0.0.0'
port=5000
```

## Notes

- This project uses no database.
- This project uses no login system.
- This project is easy to deploy and update.
- Expense data is stored in `expenses.json`.
