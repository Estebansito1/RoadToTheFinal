Road to the Final
=================

Project Description
-------------------
Road to the Final is a reusable sports prediction app for elimination-style tournaments.

The app predicts the winner of a match using team ratings, live match events, ball-control stats, and backtesting. It was first tested with World Cup-style soccer matches, but the structure can be reused for other sports like basketball, football, baseball, esports, or any tournament where teams are eliminated.

The main idea is that a team may be stronger before the game, but live match data can change the prediction.


Files Included
--------------
main.py
    Main program file. Runs the app, loads teams, predicts matches, runs backtests, and shows algorithm descriptions.

live_feed.py
    Demo live feed file. Simulates live match data such as goals, shots on target, possession, dangerous attacks, red cards, and bad player performance.

teams.csv
    Stores team ratings. The app loads teams from this file instead of hard-coding teams into the program.

match_history.csv
    Stores past match results. The app uses this file to test prediction accuracy.


How to Run the Program
----------------------
Open the RoadToTheFinal folder in VS Code.

In the terminal, run:

python3 main.py

Then follow the menu instructions.


Main Features
-------------
1. Show live prediction
2. Add goal
3. Add red card
4. Add bad player performance
5. Add injury / missing player
6. Update possession
7. Add shot on target
8. Add dangerous attack
9. Start new match
10. Pre-game backtest past matches
11. Update from live feed
12. Live backtest past matches
13. Show algorithm descriptions
14. Exit


Algorithms Used
---------------
1. Weighted Team Rating Algorithm
Uses offense, defense, form, star power, and clutch rating to create a pre-game score.

2. Event Modifier Algorithm
Adds or subtracts points when important events happen, such as injuries, red cards, or bad player performance.

3. Live Event Score Algorithm
Totals all live event changes and adjusts the team's live score.

4. Ball-Control Momentum Algorithm
Uses possession, shots on target, and dangerous attacks to estimate which team is creating better chances.

5. Scoreline Impact Algorithm
Adds points for goals because scoring changes the probability of winning.

6. Red Card Penalty Algorithm
Subtracts points when a team receives a red card.

7. Live Score Algorithm
Combines base rating, live events, ball-control stats, goals, and red cards into one live score.

8. Probability Algorithm
Converts each team’s live score into a win probability.

9. Winner Prediction Algorithm
Predicts the team with the higher live score. If the scores are tied, clutch rating is used as the tiebreaker.

10. Data Loading Algorithm
Loads teams from teams.csv so the program can be reused without changing the code.

11. Pre-game Backtest Algorithm
Tests past matches using only team ratings to see who the app would have picked before the match started.

12. Live Backtest Algorithm
Tests past matches again after applying live data to see if live information improves the prediction.

13. Prediction Reasoning Algorithm
Explains why the app favors one team by comparing goals, red cards, shots on target, dangerous attacks, possession, and event modifiers.


Example Result
--------------
One example tested was Brazil vs Norway.

Pre-game prediction:
Brazil was predicted to win because Brazil had stronger base ratings.

Live prediction:
Norway was predicted to win after live data was applied.

Reason:
Norway had more goals.
Norway had more shots on target.
Norway was creating more dangerous attacks.
Brazil had more possession, but Norway was creating better chances.
Brazil's star player was not playing well.

This shows why live data matters. A team can be stronger before the game, but the live performance can change the prediction.


Backtest Result
---------------
The app showed:

Pre-game Accuracy: 80%
Live Accuracy: 100%

This means the live-data model performed better than the pre-game model in the test matches.


How to Edit Teams
-----------------
To add or change teams, edit teams.csv.

Format:

name,offense,defense,form,star_power,clutch

Example:

France,92,90,93,95,87


How to Edit Match History
-------------------------
To add past matches, edit match_history.csv.

Format:

team1,team2,actual_winner,team1_goals,team2_goals

Example:

Brazil,Norway,Norway,1,2


Future Improvements
-------------------
Possible future upgrades:

Connect to a real sports API
Add a full tournament bracket
Add a website interface
Save prediction results
Add charts and probability bars
Add player-level stats
Add support for different sports


Author
------
Road to the Final was created as a coding project to practice algorithms, object-oriented programming, CSV data loading, probability, live data updates, and sports analytics.