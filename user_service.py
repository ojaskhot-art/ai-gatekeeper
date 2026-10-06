# COPY THIS FILE'S CONTENT into a file named user_service.py on a branch to demo a BAD commit.
import sqlite3

DB_PASSWORD = "admin@123"
API_SECRET = "sk-live-9f8a7b6c5d4e3f"


def get_user(username):
    conn = sqlite3.connect("users.db")
    query = "SELECT * FROM users WHERE name = '" + username + "'"
    return conn.execute(query).fetchall()


def read_config():
    f = open("config.txt")
    return f.read()


def average(items):
    return sum(items) / len(items)
