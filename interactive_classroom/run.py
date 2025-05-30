from app import create_app, db # Import db for commands
from app.models import seed_questions as seed_questions_from_models # Import the seeder
import click
from flask.cli import with_appcontext

# Create app instance using the factory function
app = create_app()

@click.command('create-db')
@with_appcontext
def create_db_command():
    """Creates the database tables."""
    db.create_all()
    click.echo('Database tables created.')

app.cli.add_command(create_db_command)

@click.command('seed-questions')
@with_appcontext
def seed_questions_command():
    """Seeds the Question table with initial quiz data."""
    click.echo('Seeding questions...')
    seed_questions_from_models() # Call the function from models.py
    # click.echo('Questions seeded.') # seed_questions_from_models already prints

app.cli.add_command(seed_questions_command)


if __name__ == '__main__':
    # For development, consider using Flask's built-in server with debugging.
    # For production, use a WSGI server like Gunicorn or uWSGI.
    app.run(debug=True, host='0.0.0.0', port=5000) # Make accessible on network for QR testing
