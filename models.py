# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Association-Tabelle: User <-> Favorite Movies (Many-to-Many)
user_favorites = db.Table(
    "user_favorites",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("movie_id", db.Integer, db.ForeignKey("movies.id"), primary_key=True),
    db.Column("created_at", db.DateTime, nullable=False, default=datetime.utcnow),
)

class User(db.Model):
    __tablename__ = "users"

    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    favorites = db.relationship(
        "Movie",
        secondary=user_favorites,
        back_populates="fans",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<User {self.id}:{self.name}>"

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}

class Movie(db.Model):
    __tablename__ = "movies"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(255), nullable=False, index=True)
    director   = db.Column(db.String(255))
    year       = db.Column(db.Integer)
    poster_url = db.Column(db.String(1024))

    fans = db.relationship(
        "User",
        secondary=user_favorites,
        back_populates="favorites",
        lazy="dynamic",
    )

    __table_args__ = (
        db.UniqueConstraint("name", "year", name="uq_movie_name_year"),
    )

    def __repr__(self):
        return f"<Movie {self.id}:{self.name} ({self.year})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "director": self.director,
            "year": self.year,
            "poster_url": self.poster_url,
        }