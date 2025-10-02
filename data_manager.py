# data_manager.py
import os
from typing import Optional, List
from models import db, User, Movie
import requests

# --- Custom Exceptions ---
class AppError(Exception):
    """Base class for app-specific errors."""
    status_code = 400
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code

class ValidationError(AppError):
    status_code = 400

class NotFoundError(AppError):
    status_code = 404

class ExternalAPIError(AppError):
    status_code = 502  # Bad gateway / upstream error

class DatabaseError(AppError):
    status_code = 500


class DataManager:
    """
    Kapselt alle DB-Operationen (CRUD) + OMDb-Fetch.
    Wirf aussagekräftige Exceptions, die von Flask-Handlern sauber gemappt werden.
    """

    def __init__(self, session, omdb_api_key: Optional[str] = None):
        self.session = session
        self.omdb_api_key = omdb_api_key or os.getenv("OMDB_API_KEY")

    # --- intern: sicher committen ---
    def _commit(self):
        try:
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise DatabaseError(f"Datenbankfehler: {e}") from e

    # ---------- USERS ----------
    def create_user(self, name: str) -> User:
        if not name or not name.strip():
            raise ValidationError("Name darf nicht leer sein.")
        user = User(name=name.strip())
        self.session.add(user)
        self._commit()
        return user

    def get_users(self) -> List[User]:
        return User.query.order_by(User.name.asc()).all()

    def get_user(self, user_id: int) -> User:
        user = User.query.get(user_id)
        if not user:
            raise NotFoundError(f"User {user_id} nicht gefunden.")
        return user

    # ---------- MOVIES / FAVORITES ----------
    def get_movies(self, user_id: int) -> List[Movie]:
        user = self.get_user(user_id)  # wirft NotFoundError bei Bedarf
        return user.favorites.order_by(Movie.name.asc()).all()

    def ensure_movie(self, name: str, year: Optional[int] = None) -> Movie:
        if not name or not name.strip():
            raise ValidationError("Filmtitel darf nicht leer sein.")
        q = Movie.query.filter(Movie.name == name.strip())
        if year:
            q = q.filter(Movie.year == year)
        existing = q.first()
        if existing:
            return existing
        m = Movie(name=name.strip(), year=year)
        self.session.add(m)
        self._commit()
        return m

    def add_movie(self, user_id: int, movie: Movie) -> None:
        user = self.get_user(user_id)  # NotFoundError möglich
        if movie.id is None:
            self.session.add(movie)
            self._commit()
        if not user.favorites.filter_by(id=movie.id).first():
            user.favorites.append(movie)
            self._commit()

    def add_movie_by_title(self, user_id: int, title: str) -> Movie:
        movie = self.ensure_movie_from_omdb(title)
        self.add_movie(user_id, movie)
        return movie

    def remove_favorite(self, user_id: int, movie_id: int) -> None:
        user = self.get_user(user_id)  # NotFoundError möglich
        movie = Movie.query.get(movie_id)
        if not movie:
            raise NotFoundError(f"Film {movie_id} nicht gefunden.")
        if user.favorites.filter_by(id=movie_id).first():
            user.favorites.remove(movie)
            self._commit()

    def update_movie(self, movie_id: int, **fields) -> Movie:
        movie = Movie.query.get(movie_id)
        if not movie:
            raise NotFoundError(f"Film {movie_id} nicht gefunden.")
        for k, v in fields.items():
            if v is not None and hasattr(movie, k):
                setattr(movie, k, v)
        self._commit()
        return movie

    def delete_movie_global(self, movie_id: int) -> None:
        movie = Movie.query.get(movie_id)
        if not movie:
            raise NotFoundError(f"Film {movie_id} nicht gefunden.")
        self.session.delete(movie)
        self._commit()

    # ---------- OMDb ----------
    def _fetch_from_omdb(self, title: str) -> Optional[dict]:
        if not self.omdb_api_key:
            # Kein harter Fehler – wir erlauben Offline-Eintrag
            return None
        params = {"t": title, "apikey": self.omdb_api_key}
        try:
            r = requests.get("https://www.omdbapi.com/", params=params, timeout=15)
            if r.status_code != 200:
                raise ExternalAPIError(f"OMDb Status {r.status_code}", status_code=502)
            data = r.json()
            if data.get("Response") != "True":
                return None
            return data
        except ExternalAPIError:
            raise
        except Exception as e:
            raise ExternalAPIError(f"OMDb Anfrage fehlgeschlagen: {e}") from e

    def ensure_movie_from_omdb(self, title: str) -> Movie:
        if not title or not title.strip():
            raise ValidationError("Filmtitel darf nicht leer sein.")
        data = self._fetch_from_omdb(title)
        if not data:
            # Fallback: Minimal anlegen (ohne OMDb)
            return self.ensure_movie(name=title, year=None)

        name = data.get("Title") or title
        y_raw = data.get("Year") or ""
        try:
            year = int(y_raw.split("–")[0])
        except ValueError:
            year = None
        director = data.get("Director")
        poster_url = data.get("Poster") if data.get("Poster") != "N/A" else None

        movie = Movie.query.filter_by(name=name, year=year).first()
        if not movie:
            movie = Movie(name=name, year=year, director=director, poster_url=poster_url)
            self.session.add(movie)
        else:
            movie.director = director or movie.director
            movie.poster_url = poster_url or movie.poster_url

        self._commit()
        return movie