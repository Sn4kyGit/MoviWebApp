"""MoviWeb Flask application."""

from __future__ import annotations

import os
from typing import Optional

from flask import Flask, abort, flash, redirect, render_template, request, url_for, jsonify
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.exceptions import HTTPException

from models import db, User
from data_manager import DataManager, AppError, AuthError, NotFoundError, ValidationError

try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

class Config:
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASEDIR, "data")

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(DATA_DIR, 'movies.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    TEMPLATES_AUTO_RELOAD = True


class DevelopmentConfig(Config):
    SEND_FILE_MAX_AGE_DEFAULT = 0
    DEBUG = True
    ENV = "development"


class ProductionConfig(Config):
    DEBUG = False
    ENV = "production"


def create_app(config: Optional[type[Config]] = None) -> Flask:
    app = Flask(__name__)
    cfg_class = config or (DevelopmentConfig if os.getenv("FLASK_ENV") == "development" else ProductionConfig)
    os.makedirs(cfg_class.DATA_DIR, exist_ok=True)
    app.config.from_object(cfg_class)

    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = "auth"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> Optional[User]:
        try:
            with app.app_context():
                dm = DataManager(db.session)
                return dm.get_user(int(user_id))
        except AppError:
            return None

    with app.app_context():
        db.create_all()

    app.data_manager = DataManager(db.session)  # type: ignore[attr-defined]

    @app.route("/", methods=["GET"])
    def root():
        return redirect(url_for("my_movies") if current_user.is_authenticated else url_for("auth"))

    @app.route("/auth", methods=["GET"])
    def auth():
        if current_user.is_authenticated:
            return redirect(url_for("my_movies"))
        return render_template("auth.html")

    @app.route("/register", methods=["POST"])
    def register():
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        try:
            user = dm.register_user(username, password)
            login_user(user)
            flash("Registrierung erfolgreich. Willkommen!", "success")
            return redirect(url_for("my_movies"))
        except AppError as err:
            flash(str(err), "error")
            return redirect(url_for("auth")), err.status_code

    @app.route("/login", methods=["POST"])
    def login():
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        try:
            user = dm.authenticate(username, password)
            login_user(user)
            flash("Login erfolgreich.", "success")
            return redirect(url_for("my_movies"))
        except AppError as err:
            flash(str(err), "error")
            return redirect(url_for("auth")), err.status_code

    @app.route("/logout", methods=["GET"])
    @login_required
    def logout():
        logout_user()
        flash("Abgemeldet.", "success")
        return redirect(url_for("auth"))

    @app.route("/me/movies", methods=["GET"])
    @login_required
    def my_movies():
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        movies = dm.get_movies(current_user.id)  # type: ignore[arg-type]
        return render_template("user_movies.html", user=current_user, movies=movies)

    @app.route("/me/movies", methods=["POST"])
    @login_required
    def my_movies_add():
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Bitte einen Filmtitel eingeben.", "error")
            return redirect(url_for("my_movies")), 400
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        try:
            dm.add_movie_by_title(current_user.id, title)  # type: ignore[arg-type]
            flash("Film hinzugefügt.", "success")
            return redirect(url_for("my_movies"))
        except AppError as err:
            flash(str(err), "error")
            return redirect(url_for("my_movies")), err.status_code

    @app.route("/me/movies/<int:movie_id>/update", methods=["POST"])
    @login_required
    def my_movies_update(movie_id: int):
        fields = {
            "name": request.form.get("name"),
            "director": request.form.get("director"),
            "poster_url": request.form.get("poster_url"),
            "plot": request.form.get("plot"),
            "writer": request.form.get("writer"),
            "actors": request.form.get("actors"),
            "genre": request.form.get("genre"),
            "runtime": request.form.get("runtime"),
            "released": request.form.get("released"),
            "rated": request.form.get("rated"),
            "language": request.form.get("language"),
            "country": request.form.get("country"),
            "awards": request.form.get("awards"),
            "imdb_rating": request.form.get("imdb_rating"),
            "year": request.form.get("year"),
        }
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        try:
            dm.update_movie(movie_id, **fields)
            flash("Film aktualisiert.", "success")
            return redirect(url_for("my_movies"))
        except AppError as err:
            flash(str(err), "error")
            return redirect(url_for("my_movies")), err.status_code

    @app.route("/me/movies/<int:movie_id>/refresh", methods=["POST"])
    @login_required
    def my_movies_refresh(movie_id: int):
        """Metadaten via OMDb aktualisieren."""
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        try:
            dm.refresh_movie_from_omdb(movie_id)
            flash("Metadaten aktualisiert.", "success")
            return redirect(url_for("my_movies"))
        except AppError as err:
            flash(str(err), "error")
            return redirect(url_for("my_movies")), err.status_code

    @app.route("/me/movies/<int:movie_id>/delete", methods=["POST"])
    @login_required
    def my_movies_delete(movie_id: int):
        dm: DataManager = app.data_manager  # type: ignore[attr-defined]
        try:
            dm.remove_favorite(current_user.id, movie_id)  # type: ignore[arg-type]
            flash("Film entfernt.", "success")
            return redirect(url_for("my_movies"))
        except AppError as err:
            flash(str(err), "error")
            return redirect(url_for("my_movies")), err.status_code

    @app.errorhandler(404)
    def not_found(err: HTTPException):  # type: ignore[override]
        return render_template("404.html", message=getattr(err, "description", None)), 404

    @app.errorhandler(500)
    def internal_error(err: Exception):  # type: ignore[override]
        app.logger.exception("Server Error: %s", err)
        return render_template("500.html"), 500

    return app


if __name__ == "__main__":
    app_ = create_app()
    print("Running on http://127.0.0.1:4999 …")
    app_.run(host="127.0.0.1", port=4999, debug=app_.debug)