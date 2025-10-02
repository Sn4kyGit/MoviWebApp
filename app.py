# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from werkzeug.exceptions import HTTPException
from models import db
from data_manager import DataManager, AppError, NotFoundError, ValidationError, ExternalAPIError, DatabaseError

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.path.join(basedir, "data")
os.makedirs(data_dir, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(data_dir, 'movies.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

db.init_app(app)
with app.app_context():
    db.create_all()

dm = DataManager(db.session)

# --------------------------
# Hilfsfunktion: JSON gewünscht?
# --------------------------
def wants_json() -> bool:
    # sehr einfache Heuristik: API-Pfad oder Accept-Header
    if request.path.startswith("/api/"):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept.lower()

# --------------------------
# Routen
# --------------------------
@app.route("/")
def home():
    users = dm.get_users()
    return render_template("index.html", users=users)

@app.route("/users", methods=["POST"])
def create_user():
    try:
        name = request.form.get("name", "")
        dm.create_user(name)
        flash(f"User '{name.strip()}' wurde angelegt.", "success")
        return redirect(url_for("home"))
    except AppError as e:
        flash(str(e), "error")
        return redirect(url_for("home")), e.status_code

@app.route("/users/<int:user_id>/movies", methods=["GET"])
def list_user_movies(user_id: int):
    try:
        user = dm.get_user(user_id)
        movies = dm.get_movies(user_id)
        return render_template("user_movies.html", user=user, movies=movies)
    except NotFoundError as e:
        abort(404, description=str(e))

@app.route("/users/<int:user_id>/movies", methods=["POST"])
def add_user_movie(user_id: int):
    try:
        title = request.form.get("title", "")
        movie = dm.add_movie_by_title(user_id, title)
        flash(f"'{movie.name}' hinzugefügt.", "success")
        return redirect(url_for("list_user_movies", user_id=user_id))
    except AppError as e:
        flash(str(e), "error")
        return redirect(url_for("list_user_movies", user_id=user_id)), e.status_code

@app.route("/users/<int:user_id>/movies/<int:movie_id>/update", methods=["POST"])
def update_user_movie(user_id: int, movie_id: int):
    try:
        # Nur erlaubte Felder
        fields = {
            "name": (request.form.get("name") or None),
            "director": (request.form.get("director") or None),
            "poster_url": (request.form.get("poster_url") or None),
        }
        year_raw = request.form.get("year")
        if year_raw:
            try:
                fields["year"] = int(year_raw)
            except ValueError:
                raise ValidationError("Ungültiges Jahr.")
        dm.update_movie(movie_id, **fields)
        flash("Film gespeichert.", "success")
        return redirect(url_for("list_user_movies", user_id=user_id))
    except AppError as e:
        flash(str(e), "error")
        return redirect(url_for("list_user_movies", user_id=user_id)), e.status_code

@app.route("/users/<int:user_id>/movies/<int:movie_id>/delete", methods=["POST"])
def delete_user_movie(user_id: int, movie_id: int):
    try:
        dm.remove_favorite(user_id, movie_id)
        flash("Film entfernt.", "success")
        return redirect(url_for("list_user_movies", user_id=user_id))
    except AppError as e:
        flash(str(e), "error")
        return redirect(url_for("list_user_movies", user_id=user_id)), e.status_code

# --- kleine API zum Testen ---
@app.route("/api/users")
def api_users():
    try:
        users = [u.to_dict() for u in dm.get_users()]
        return jsonify(users), 200
    except AppError as e:
        return jsonify({"error": str(e)}), e.status_code

# --------------------------
# Error Handler (HTTP + Custom)
# --------------------------
@app.errorhandler(404)
def page_not_found(e):
    # e.description bei abort()/NotFound
    if wants_json():
        return jsonify({"error": getattr(e, "description", "Not Found")}), 404
    return render_template("404.html", message=getattr(e, "description", None)), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.exception("Server Error: %s", e)
    if wants_json():
        return jsonify({"error": "Internal Server Error"}), 500
    return render_template("500.html"), 500

@app.errorhandler(AppError)
def handle_app_error(e: AppError):
    # falls jemand AppError außerhalb von Routes wirft
    if wants_json():
        return jsonify({"error": str(e)}), e.status_code
    flash(str(e), "error")
    return redirect(url_for("home")), e.status_code

@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    # Einheitliches Fallback für andere HTTP-Fehler
    if wants_json():
        return jsonify({"error": e.description}), e.code
    if e.code == 404:
        return render_template("404.html", message=e.description), 404
    if e.code >= 500:
        app.logger.exception("HTTPException %s: %s", e.code, e)
        return render_template("500.html"), e.code
    return render_template("404.html", message=e.description), e.code

if __name__ == "__main__":
    print("Running on http://127.0.0.1:5000 …")
    app.run(host="127.0.0.1", port=5000, debug=True)