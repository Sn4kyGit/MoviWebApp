"""SQLAlchemy models for MoviWeb."""

from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    movies = db.relationship("Movie", backref="user", cascade="all, delete-orphan")

    def get_id(self) -> str:  # Flask-Login expects str
        return str(self.id)


class Movie(db.Model):
    __tablename__ = "movies"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # Core
    name = db.Column(db.String(200), nullable=False)  # OMDb: Title
    year = db.Column(db.Integer)                      # Year
    director = db.Column(db.String(200))              # Director
    poster_url = db.Column(db.String(500))            # Poster

    # OMDb extras (String/Short text – N/A tolerant)
    plot = db.Column(db.Text)                         # Plot
    writer = db.Column(db.String(400))                # Writer
    actors = db.Column(db.String(400))                # Actors
    genre = db.Column(db.String(200))                 # Genre
    runtime = db.Column(db.String(50))                # Runtime (e.g. "127 min")
    released = db.Column(db.String(50))               # Released (e.g. "11 Jun 1993")
    rated = db.Column(db.String(20))                  # Rated (e.g. "PG-13")
    language = db.Column(db.String(200))              # Language
    country = db.Column(db.String(200))               # Country
    awards = db.Column(db.String(300))                # Awards
    imdb_rating = db.Column(db.String(10))            # imdbRating as string to keep "N/A"
    imdb_id = db.Column(db.String(20))                # imdbID (for precise refresh)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "year": self.year,
            "director": self.director,
            "poster_url": self.poster_url,
            "plot": self.plot,
            "writer": self.writer,
            "actors": self.actors,
            "genre": self.genre,
            "runtime": self.runtime,
            "released": self.released,
            "rated": self.rated,
            "language": self.language,
            "country": self.country,
            "awards": self.awards,
            "imdb_rating": self.imdb_rating,
            "imdb_id": self.imdb_id,
        }