# plancake Backend

The API for the scheduling platform *plancake*.

## Project Setup
*(Run commands from the root directory)*

- Set up a Python virtual environment (optional, but highly recommended)
- Install packages with `pip install -r requirements.txt`
- Set up a PostgreSQL database (local works fine, otherwise [Supabase](https://supabase.com) offers free remote database hosting)

### `.env` File
Copy the contents of `example.env` into a new file called `.env` in the same directory.
- Replace all the fields prefixed with `DB_` with the relevant information for your database

### Database Migrations
The project contains a database model that determines the structure of the database. When it gets changed, Django's "migrations" feature keeps all development databases up to date on these changes.
- Apply these migrations with `python manage.py migrate` when you first set up the project
- Make sure to also run this command whenever you pull changes from another branch

### Running the Server
After the above steps, run the server with `python manage.py runserver`

### *(Optional for Development)* Automated Tasks
This project uses Celery and Redis to automate tasks like cleaning up old sessions.

First, Redis needs to be installed and run as a service.
- `sudo apt update`
- `sudo apt install redis-server`
- `sudo service redis-server start`
    - *This might need to be called any time you start your machine*

To run Celery alongside the API server (in different terminals):
- `celery -A api worker --loglevel=info`
- `celery -A api beat --loglevel=info`
