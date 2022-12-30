import os
import math
from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    cashrow = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = math.floor(cashrow[0]["cash"] * 100) / 100
    user_stocks = db.execute(
        "SELECT symbol, SUM(shares) AS shares, price, stock_name FROM user_stocks WHERE user_id = ? GROUP BY symbol", user_id)
    sum = cash
    rows = 0
    # Calculate the total sum of cash + shares bought
    for row in user_stocks:
        shares = int(user_stocks[rows]["shares"])
        price = float(user_stocks[rows]["price"])
        sum += round(shares * price)
        rows += 1
    return render_template("index.html", cash=cash, sum=sum, user_stocks=user_stocks)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Missing Symbol", 400)
        elif not request.form.get("shares"):
            return apology("Please enter an amount of shares", 400)
        else:
            stock = lookup(request.form.get("symbol"))
            if stock == None:
                return apology("Stock symbol doesn't exist", 400)
            else:
                # Check that shares field is a number
                shares = request.form.get("shares")
                if shares.isnumeric() == False:
                    return apology("invalid shares", 400)
                else:
                    shares = float(request.form.get("shares"))
                    cost = shares * stock["price"]
                    user_id = session["user_id"]
                    cashrow = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
                    cash = cashrow[0]["cash"]
                    # Check that shares field is not negative or a decimal
                    if not shares >= 1:
                        return apology("invalid shares", 400)
                    elif (shares).is_integer() == False:
                        return apology("invalid shares", 400)
                    elif cost > cash:
                        return apology("Not enough funds for this purchase", 400)
                    else:
                        dt = datetime.now()
                        db.execute("INSERT INTO user_stocks (user_id, symbol, stock_name, price, shares) VALUES (?, ?, ?, ?, ?)",
                                   user_id, stock["symbol"], stock["name"], stock["price"], shares)
                        currentcash = cash - cost
                        db.execute("UPDATE users SET cash = ? WHERE id = ?", currentcash, user_id)
                        db.execute("INSERT INTO transactions (user_id, symbol, price, shares, date_bought, date) VALUES (?, ?, ?, ?, ?, ?)",
                                   user_id, stock["symbol"], stock["price"], shares, dt, dt)
                        flash("Bought!")
                        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

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
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        # if symbol not in lookup()
        if not request.form.get("symbol"):
            return apology("Please enter a stock symbol", 400)
        elif stock == None:
            return apology("Stock symbol doesn't exist", 400)
        else:
            return render_template("quoted.html", price=stock["price"], symbol=stock["symbol"], name=stock["name"])
    else:
        # display form to request stock quote
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Check for errors
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) != 0:
            return apology("Username is already taken", 400)
        elif not request.form.get("username"):
            return apology("Please provide a username", 400)
        elif not request.form.get("password"):
            return apology("Please provide a password", 400)
        elif not request.form.get("confirmation") == request.form.get("password"):
            return apology("Passwords do not match", 400)
        else:
            username = request.form.get("username")
            # For security, save the password as a hash rather than the actual password
            hash = generate_password_hash(request.form.get("password"))
            # Add user to the list of users
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)
            return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        user_id = session["user_id"]
        chosensymbol = request.form.get("symbol")
        symbolshares = db.execute(
            "SELECT SUM(shares) AS shares FROM user_stocks WHERE user_id = ? AND symbol = ?", user_id, chosensymbol)
        sellshares = int(request.form.get("shares"))
        shares = int(symbolshares[0]["shares"])
        # Check for errors
        if not request.form.get("symbol"):
            return apology("Please enter a stock symbol", 400)
        elif shares < 1:
            return apology("You do not own any share of this stock", 400)
        elif shares < sellshares:
            return apology("Too many shares", 400)
        elif sellshares < 1:
            return apology("Shares must be positive", 400)
        else:
            # Update users transaction and stock table to reflect sale
            dt = datetime.now()
            updatedshares = shares - sellshares
            db.execute("UPDATE user_stocks SET shares = ? WHERE user_id = ? AND symbol = ?", updatedshares, user_id, chosensymbol)
            cashrow = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
            cash = cashrow[0]["cash"]
            pricerow = db.execute("SELECT price FROM user_stocks WHERE user_id = ? AND symbol = ?", user_id, chosensymbol)
            price = float(pricerow[0]["price"])
            updatedcash = cash + (price * sellshares)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", updatedcash, user_id)
            db.execute("INSERT INTO transactions (user_id, symbol, price, shares, date_sold, date) VALUES (?, ?, ?, ?, ?, ?)",
                       user_id, chosensymbol, price, shares, dt, dt)
            return redirect("/")

    else:
        user_id = session["user_id"]
        user_stocks = db.execute("SELECT symbol FROM user_stocks WHERE user_id = ? GROUP BY symbol", user_id)
        return render_template("sell.html", user_stocks=user_stocks)


@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    if request.method == "POST":
        user_id = session["user_id"]
        addedcash = float(request.form.get("addcash"))
        cashrow = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = int(cashrow[0]["cash"])
        updatedcash = addedcash + cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updatedcash, user_id)
        return redirect("/")

    else:
        user_id = session["user_id"]
        cashrow = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = float(cashrow[0]["cash"])
        return render_template("addcash.html", cash=cash)