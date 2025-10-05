# seed_db.py
import csv
from app import db, Movie, create_default_admin, app
import os

create_default_admin()

# Example: read movies.csv with columns: title, year, box_office, director, producer, cast, poster_url
csv_path = os.path.join(os.path.dirname(__file__), 'movies_sample.csv')
if os.path.exists(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = Movie(
                title=row['title'],
                year=row.get('year'),
                box_office=row.get('box_office'),
                director=row.get('director'),
                producer=row.get('producer'),
                cast=row.get('cast'),
                poster_url=row.get('poster_url') or None
            )
            db.session.add(m)
    db.session.commit()
    print("Seeded from CSV")
else:
    print("No CSV found. Create movies_sample.csv to bulk import.")
