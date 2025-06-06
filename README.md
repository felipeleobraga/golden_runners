# Golden Runners

Golden Runners is a small Flask application for managing running activities and clothing donations. It exposes API endpoints and simple pages to handle donation items, user authentication and fitness activity tracking.

## Setup

Create a virtual environment and install the dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Database

Initialize the SQLite database and optionally seed it with example data:

```bash
python init_db.py
python seed.py  # optional
```

## Running the app

Start the development server using the provided entry point:

```bash
python main.py
```

By default the application will be available at <http://localhost:5000>.
