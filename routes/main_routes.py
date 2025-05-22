from flask import Blueprint, render_template

main = Blueprint('main', __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/teams/join")
def join_team():
    return "Página de inscrição em time"
