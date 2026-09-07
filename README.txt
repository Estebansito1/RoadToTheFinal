Road to the Final
=================

Project Overview
----------------
Road to the Final is a football prediction and match analytics application built with Python and Flask.

The final goal of this project is to create a database-driven analytics platform for the 2027 FIFA Women's World Cup.

For now, the project will be tested and improved using regular-season club football data, such as Liga MX. This gives the team time to develop features, test live match data, improve the prediction model, and build the database before the Women's World Cup begins.


Main Goal
---------
The final version of the project should:

- Store teams, matches, statistics, events, and predictions in a real database
- Use live or historical football data
- Calculate win, draw, and loss probabilities
- Calculate expected goals
- Track live momentum and attack pressure
- Store prediction history over time
- Compare teams using recent form and head-to-head history
- Display the information through a Flask web application
- Support the 2027 FIFA Women's World Cup without rewriting the core prediction system


Current Development Strategy
----------------------------
The same prediction system will be reused for different competitions.

Current testing:
Liga MX / regular-season football

Final target:
2027 FIFA Women's World Cup

The core Python prediction code should remain reusable. Team names, competition names, API IDs, and tournament-specific information should not be hard-coded into the prediction engine.


Current Architecture
--------------------
API-Football
    |
    v
Python / Flask
    |
    +---- Prediction Model
    |       - Win probability
    |       - Poisson expected goals
    |       - Live momentum
    |       - Attack pressure
    |       - Confidence
    |
    +---- Current Data Files
    |       - teams.csv
    |       - match_history.csv
    |       - historical_snapshots.csv
    |
    v
HTML / CSS Web Dashboard


Planned Database Architecture
-----------------------------
For the CS514 final project, the CSV and cache-based storage will be expanded into a real relational database.

Possible database tables:

- Competitions
- Teams
- Matches
- MatchStatistics
- MatchEvents
- Predictions

The database will use concepts from CS514 such as:

- Primary keys
- Foreign keys
- Relationships
- Normalization
- SELECT, INSERT, UPDATE, and DELETE
- Joins
- Aggregate functions
- Constraints
- Indexes
- Transactions
- Database programming


Main Features
-------------
Current features include:

- Team selection
- Win / draw / loss probabilities
- Poisson expected goals
- Most likely final score
- Top scoreline probabilities
- Live momentum
- Attack pressure
- Match statistics
- Event timeline
- Prediction confidence
- Match difficulty
- Head-to-head analysis
- Recent form
- Historical backtesting
- Live API-Football integration
- Tournament simulation


Project Structure
-----------------
app.py
    Main Flask application and prediction model.

live_feed.py
    Handles live API-Football match data.

insights.py
    Handles pre-match data such as team lookup, head-to-head history, and recent form.

main.py
    Optional terminal interface and historical backtesting.

teams.csv
    Current team ratings used by the prediction model.

match_history.csv
    Historical match data used for testing.

historical_snapshots.csv
    Historical in-match snapshots used for live backtesting.

templates/index.html
    Main Flask webpage.

static/style.css
    Dashboard styling.

.env
    Stores private API credentials locally.
    This file is not uploaded to GitHub.


Team Development Guidelines
---------------------------
When adding features:

- Do not hard-code specific teams or leagues into the prediction engine.
- Keep features reusable for both club and national-team football.
- Use configuration or database records for competition-specific information.
- Keep API keys and private credentials out of GitHub.
- Make meaningful GitHub commits so individual contributions can be tracked.


Final Project Vision
--------------------
The final product will be a database-driven Women's World Cup analytics platform that combines football data, historical information, live match statistics, and prediction algorithms into one web application.

The goal is to build something that can continue beyond CS514 as a portfolio project and potentially be expanded for future football tournaments.