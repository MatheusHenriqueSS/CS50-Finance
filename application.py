import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Verify whether the share input is valid


def check_shares(shares):
    try:
        float(shares)
        if float(shares) == int(float(shares)):
            shares = int(float(shares))
            if shares <= 0:
                return -1
            return shares
        return -1
    except ValueError:
        return -1


@app.route("/")
@login_required
def index():
    rows = db.execute("SELECT * FROM wallet WHERE id LIKE ?", session["user_id"])
    table_rows = []
    total = 0
    cash = db.execute("SELECT * FROM users WHERE id LIKE ?", session["user_id"])[0]["cash"]
    for row in rows:
        # For each stock in portfolio
        stock = lookup(row["symbol"])
        data = dict()

        data["symbol"] = row["symbol"]
        data["name"] = stock["name"]
        data["shares"] = row["shares"]
        data["price"] = stock["price"]
        data["total"] = row["shares"] * stock["price"]
        total += row["shares"] * stock["price"]
        table_rows.append(data)
    total += cash
    return render_template("portfolio.html", rows=table_rows, total=total, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol") or lookup(request.form.get("symbol")) == None:
            return apology("invalid stock", 400)
        if not request.form.get("shares"):
            return apology("invalid shares", 400)

        shares = check_shares(request.form.get("shares"))
        if shares == -1:
            return apology("invalid shares", 400)

        rows = db.execute("SELECT cash FROM users WHERE id LIKE ?", session["user_id"])
        balance = rows[0]["cash"]
        stock = lookup(request.form.get("symbol"))

        if balance < int(shares) * stock["price"]:
            return apology("insufficient balance", 400)
        balance -= int(shares) * stock["price"]
        # Update balance in users
        db.execute("UPDATE users SET cash = ? WHERE id LIKE ?", balance, session["user_id"])
        # Record transaction in history table
        time = db.execute(f"SELECT datetime(\"now\")")[0]["datetime(\"now\")"]
        db.execute("INSERT INTO statement(id, symbol, price, shares, time) VALUES( ?, ?, ?, ?, ?)",
                   session["user_id"], stock["symbol"], stock["price"], shares, time)

        e_name = stock["name"]
        e_price = stock["price"]
        e_symbol = stock["symbol"]

        have = db.execute("SELECT * FROM wallet WHERE id LIKE ? AND symbol LIKE ?", session["user_id"], stock["symbol"])
        if len(have) == 0:
            # If user didn't had any shares from this enterprise, add it to wallet
            db.execute("INSERT INTO wallet(id, symbol, shares) VALUES( ?, ?, ?)", session["user_id"], stock["symbol"], shares)
        else:
            db.execute("UPDATE wallet SET shares = ? WHERE id LIKE ? AND symbol LIKE ?",
                       have[0]["shares"] + shares, session["user_id"], stock["symbol"])

        flash("Bought!")
        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    table_rows = []
    rows = db.execute("SELECT * FROM statement WHERE id LIKE ? ORDER BY time DESC", session["user_id"])

    for row in rows:
        if row["shares"] < 0:
            row["shares"] *= -1
            row["operation"] = "sell"
        else:
            row["operation"] = "buy"
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if stock == None:
            return apology("invalid symbol", 400)
        return render_template("/quoted.html", stock=stock)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        rows = db.execute("SELECT * FROM users WHERE username LIKE ?", request.form.get("username"))
        if len(rows) != 0:
            return apology("username not available", 400)

        if not request.form.get("password"):
            return apology("must provide password", 400)
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 400)

        password_hash = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users(username, hash) VALUES (?, ?)", request.form.get("username"), password_hash)

        return redirect("/login")

    return render_template("register.html")


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        rows = db.execute("SELECT * FROM users WHERE id LIKE ?", session["user_id"])

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("c_password")):
            return apology("wrong password", 400)

        if request.form.get("n_password") != request.form.get("confirmation"):
            return apology("different passwords", 400)

        password_hash = generate_password_hash(request.form.get("n_password"))
        db.execute("UPDATE users SET hash = ? WHERE id LIKE ?", password_hash, session["user_id"])

        return redirect("/login")
    return render_template("password.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":
        if not request.form.get("symbol") or lookup(request.form.get("symbol")) == None:
            return apology("invalid stocke", 400)
        stock = lookup(request.form.get("symbol"))
        rows = db.execute("SELECT * FROM wallet WHERE id LIKE ? AND symbol LIKE ?", session["user_id"], stock["symbol"])

        if len(rows) == 0:
            # The user doesn't have the stock
            return apology("invalid stock", 400)
        # Shares is how many shares the user has in its wallet
        shares = rows[0]["shares"]

        if int(request.form.get("shares")) > shares:
            return apology("invalide number of shares", 400)

        shares -= int(request.form.get("shares"))

        # Update users wallet
        db.execute("UPDATE wallet SET shares = ? WHERE id LIKE ? AND symbol LIKE ?", shares, session["user_id"], stock["symbol"])
        time = db.execute(f"SELECT datetime(\"now\")")[0]["datetime(\"now\")"]
        # Update users statement
        db.execute("INSERT INTO statement(id, symbol, price, shares, time) VALUES( ?, ?, ?, ?, ?)",
                   session["user_id"], stock["symbol"], stock["price"], -1 * int(request.form.get("shares")), time)
        # Update users cash
        cash = db.execute("SELECT * FROM users WHERE id LIKE ?", session["user_id"])[0]["cash"]
        db.execute("UPDATE users SET cash = ? WHERE id LIKE ?", cash +
                   stock["price"] * int(request.form.get("shares")), session["user_id"])
        flash("Sold!")
        return redirect("/")
    symbols = db.execute("SELECT * FROM wallet WHERE id LIKE ?", session["user_id"])
    array = []
    for sy in symbols:
        array.append(sy["symbol"])
    return render_template("sell.html", stocks=array)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

# pk_a42ed19a650d4836bdaf08d94807386c