"""DataManager: Business-Logik & DB-Zugriffe für MoviWeb."""

from __future__ import annotations

import os
from typing import Iterable, Optional

import requests
from werkzeug.security import check_password_hash, generate_password_hash

from models import db, User, Movie


# -------- App-spezifische Fehler -----------------

class AppError(Exception):
    status_code = 400

class ValidationError(AppError):
    status_code = 400

class AuthError(AppError):
    status_code = 401

class NotFoundError(AppError):
    status_code = 404


# -------- DataManager ----------------------------

class DataManager:
    """Kapselt CRUD-Operationen und OMDb-Fetch."""

    def __init__(self, session):
        self.session = session
        self.omdb_key = os.getenv("OMDB_API_KEY")

    # ---- Users ----

    def register_user(self, name: str, password: str) -> User:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Bitte einen Nutzernamen angeben.")
        if not password:
            raise ValidationError("Bitte ein Passwort angeben.")

        if User.query.filter_by(name=name).first():
            raise ValidationError("Nutzername bereits vergeben.")

        user = User(name=name, password_hash=generate_password_hash(password))
        self.session.add(user)
        self.session.commit()
        return user

    def authenticate(self, name: str, password: str) -> User:
        name = (name or "").strip()
        user = User.query.filter_by(name=name).first()
        if not user or not check_password_hash(user.password_hash, password):
            raise AuthError("Ungültiger Nutzername oder Passwort.")
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        return User.query.get(user_id)

    # ---- Movies ----

    def get_movies(self, user_id: int) -> Iterable[Movie]:
        return Movie.query.filter_by(user_id=user_id).order_by(Movie.id.desc()).all()

    def add_movie_by_title(self, user_id: int, title: str) -> Movie:
        """Holt Daten aus OMDb (falls Key vorhanden) und speichert Movie."""
        title = (title or "").strip()
        if not title:
            raise ValidationError("Filmtitel darf nicht leer sein.")

        data = self._fetch_from_omdb(title=title) if self.omdb_key else {}

        movie = Movie(
            user_id=user_id,
            name=data.get("Title") or title,
            year=self._parse_year(data.get("Year")),
            director=self._clean(data.get("Director")),
            poster_url=self._clean(data.get("Poster")),
            plot=self._clean(data.get("Plot")),
            writer=self._clean(data.get("Writer")),
            actors=self._clean(data.get("Actors")),
            genre=self._clean(data.get("Genre")),
            runtime=self._clean(data.get("Runtime")),
            released=self._clean(data.get("Released")),
            rated=self._clean(data.get("Rated")),
            language=self._clean(data.get("Language")),
            country=self._clean(data.get("Country")),
            awards=self._clean(data.get("Awards")),
            imdb_rating=self._clean(data.get("imdbRating")),
            imdb_id=self._clean(data.get("imdbID")),
        )

        self.session.add(movie)
        self.session.commit()
        return movie

    def refresh_movie_from_omdb(self, movie_id: int) -> Movie:
        """Aktualisiert Metadaten eines Films via OMDb (by imdbID oder Title)."""
        movie = Movie.query.get(movie_id)
        if not movie:
            raise NotFoundError("Film nicht gefunden.")
        if not self.omdb_key:
            raise ValidationError("OMDb API-Key fehlt (OMDB_API_KEY).")

        data = self._fetch_from_omdb(imdb_id=movie.imdb_id, title=movie.name)

        # Map zurück auf Felder (nur überschreiben, wenn OMDb was liefert)
        updates = {
            "name": data.get("Title"),
            "year": self._parse_year(data.get("Year")),
            "director": self._clean(data.get("Director")),
            "poster_url": self._clean(data.get("Poster")),
            "plot": self._clean(data.get("Plot")),
            "writer": self._clean(data.get("Writer")),
            "actors": self._clean(data.get("Actors")),
            "genre": self._clean(data.get("Genre")),
            "runtime": self._clean(data.get("Runtime")),
            "released": self._clean(data.get("Released")),
            "rated": self._clean(data.get("Rated")),
            "language": self._clean(data.get("Language")),
            "country": self._clean(data.get("Country")),
            "awards": self._clean(data.get("Awards")),
            "imdb_rating": self._clean(data.get("imdbRating")),
            "imdb_id": self._clean(data.get("imdbID")) or movie.imdb_id,
        }
        for k, v in updates.items():
            if v not in (None, "", "N/A"):
                setattr(movie, k, v)

        self.session.commit()
        return movie

    def update_movie(self, movie_id: int, **fields) -> Movie:
        movie = Movie.query.get(movie_id)
        if not movie:
            raise NotFoundError("Film nicht gefunden.")

        allowed = {
            "name", "director", "year", "poster_url",
            "plot", "writer", "actors", "genre", "runtime",
            "released", "rated", "language", "country",
            "awards", "imdb_rating"
        }
        clean = {k: v for k, v in fields.items() if k in allowed}
        if "year" in clean:
            clean["year"] = self._parse_year(clean["year"])

        for k, v in clean.items():
            if v not in (None, ""):
                setattr(movie, k, v)

        self.session.commit()
        return movie

    def remove_favorite(self, user_id: int, movie_id: int) -> None:
        movie = Movie.query.filter_by(id=movie_id, user_id=user_id).first()
        if not movie:
            raise NotFoundError("Film nicht gefunden.")
        self.session.delete(movie)
        self.session.commit()

    # ---- Helpers ----

    @staticmethod
    def _clean(v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip().upper() == "N/A":
            return None
        return str(v).strip()

    @staticmethod
    def _parse_year(y) -> Optional[int]:
        if y is None:
            return None
        s = str(y).strip()
        if not s:
            return None
        try:
            return int(s.split("–")[0].split("-")[0])
        except Exception:
            return None

    def _fetch_from_omdb(self, title: Optional[str] = None, imdb_id: Optional[str] = None) -> dict:
        """Fragt OMDb ab – by imdbID (präzise) oder Title (fallback)."""
        if not self.omdb_key:
            return {}
        params = {"apikey": self.omdb_key, "plot": "short"}
        if imdb_id:
            params["i"] = imdb_id
        elif title:
            params["t"] = title
        else:
            return {}

        try:
            r = requests.get("https://www.omdbapi.com/", params=params, timeout=8)
            r.raise_for_status()
            data = r.json() or {}
        except requests.RequestException as exc:
            raise AppError(f"OMDb nicht erreichbar: {exc}") from exc

        if data.get("Response") == "False":
            return {}
        return data