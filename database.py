# models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# -------------------- MOVIE TABLE --------------------
class Movie(db.Model):
    __tablename__ = "movie"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    year = db.Column(db.String(10))
    box_office = db.Column(db.String(50))
    director = db.Column(db.String(200))
    producer = db.Column(db.String(200))
    cast = db.Column(db.Text)
    poster_url = db.Column(db.String(500))
    tmdb_id = db.Column(db.String(50))

    def __repr__(self):
        return f"<Movie {self.title} ({self.year})>"


# -------------------- USER TABLE --------------------
class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")

    def __repr__(self):
        return f"<User {self.username}>"
