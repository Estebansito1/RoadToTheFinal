# =============================================================================
# FILE: main.py
# PROJECT: Road to the Final
# =============================================================================
# PURPOSE:
# Optional terminal interface and historical-backtest runner for the same
# Team and Match model used by app.py.
#
# IMPORTANT:
# This file does not define separate Team or Match classes. It imports the
# current model from app.py so the CLI and website cannot drift apart.
#
# RUN WEBSITE:
#     python3 app.py
#
# RUN CLI:
#     python3 main.py
# =============================================================================

# =============================================================================
# SECTION 01: IMPORTS
# =============================================================================

import csv

from app import (
    Match,
    copy_team,
    find_team_by_name,
    load_teams_from_csv,
)
from live_feed import (
    apply_historical_row_to_match,
    apply_live_data_to_match,
)


# =============================================================================
# SECTION 02: MATCH CLOCK AND STATUS DISPLAY
# =============================================================================
# Supports normal time, added time, halftime, extra time, and full time.
#
# live_feed.py sets these Match attributes:
# - match_status_short
# - match_status_long
# - match_extra_minute
# =============================================================================

MATCH_STATUS_LABELS = {
    "HT": "HT",
    "FT": "FT",
    "AET": "AET",
    "PEN": "PEN",
    "BT": "BREAK",
    "PST": "POSTPONED",
    "CANC": "CANCELLED",
    "ABD": "ABANDONED",
    "SUSP": "SUSPENDED",
    "INT": "INTERRUPTED",
    "NS": "NOT STARTED",
    "TBD": "TBD",
}


def format_match_clock(match):
    status_short = str(
        getattr(match, "match_status_short", "") or ""
    ).upper()

    minute = int(
        getattr(match, "match_minute", 0) or 0
    )

    extra = int(
        getattr(match, "match_extra_minute", 0) or 0
    )

    if status_short in MATCH_STATUS_LABELS:
        return MATCH_STATUS_LABELS[status_short]

    if extra > 0:
        return f"{minute}+{extra}'"

    if status_short == "ET":
        return f"ET {minute}'"

    return f"{minute}'"


def update_match_clock_manually(match):
    print("\nManual Match Clock")
    print("=" * 40)
    print("Status examples: 1H, HT, 2H, ET, AET, PEN, FT")

    try:
        minute = int(
            input("Elapsed minute (example 45, 90, 105): ")
        )
    except ValueError:
        print("\nInvalid minute. Match clock was not changed.")
        return

    try:
        extra = int(
            input("Added minute (0 if none, example 3): ")
        )
    except ValueError:
        extra = 0

    status_short = input(
        "Status code (leave blank for normal play): "
    ).strip().upper()

    match.match_minute = max(0, min(minute, 120))
    match.match_extra_minute = max(0, extra)
    match.match_status_short = status_short

    print("\nMatch clock updated:", format_match_clock(match))


# =============================================================================
# SECTION 03: TEAM SELECTION HELPERS
# =============================================================================

def display_teams(teams):
    print("\nAvailable Teams")
    print("=" * 40)

    for index, team in enumerate(teams, start=1):
        print(f"{index}. {team.name}")


def select_team(teams, prompt):
    while True:
        display_teams(teams)
        choice = input(prompt).strip()

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("\nPlease enter a valid team number.")
            continue

        if 0 <= selected_index < len(teams):
            return copy_team(teams[selected_index])

        print("\nInvalid team number. Try again.")


def choose_match_team(team1, team2):
    print("\nChoose a team")
    print("=" * 30)
    print(f"1. {team1.name}")
    print(f"2. {team2.name}")

    choice = input("Enter choice: ").strip()

    if choice == "2":
        return team2

    if choice != "1":
        print("\nInvalid choice. Defaulting to Team 1.")

    return team1


# =============================================================================
# SECTION 04: CURRENT MODEL REPORT
# =============================================================================

def show_team_report(team, opponent):
    raw_total, capped_total, was_capped = (
        team.event_score_breakdown()
    )

    dangerous_attacks = (
        team.calculated_dangerous_attacks(opponent)
    )

    attack_pressure = (
        team.attack_pressure_score(opponent)
    )

    print(f"\n{team.name} Report")
    print("-" * 45)
    print(f"Base score: {team.base_score():.2f}")
    print(f"Goals: {team.goals}")
    print(f"Possession: {team.possession}%")
    print(f"Total shots: {team.shots}")
    print(f"Shots on target: {team.shots_on_target}")
    print(f"Big chances: {team.big_chances}")
    print(f"Blocked shots: {team.defender_blocks}")
    print(f"Goalkeeper saves: {team.goalkeeper_saves}")
    print(f"Corners: {team.corners}")
    print(
        f"Cards: {team.yellow_cards} yellow, "
        f"{team.red_cards} red"
    )
    print(f"Calculated dangerous attacks: {dangerous_attacks}")
    print(f"Attack pressure: {attack_pressure:.2f}")
    print(f"Raw event modifiers: {raw_total:+.2f}")
    print(f"Applied event modifiers: {capped_total:+.2f}")

    if was_capped:
        print("WARNING: Modifier total was capped by the shared model.")

    if team.modifiers:
        print("\nModifiers:")

        for reason, value in team.modifiers:
            print(f"- {reason}: {value:+.2f}")

    print(
        f"\nCurrent live score: "
        f"{team.live_score(opponent):.2f}"
    )


def show_prediction(match):
    (
        team1_win,
        draw_probability,
        team2_win,
        most_likely_score,
        top_scorelines,
    ) = match.calculate_probabilities()

    team1_advance, team2_advance = (
        match.advancement_probabilities(
            (
                team1_win,
                draw_probability,
                team2_win,
            )
        )
    )

    team1_xg, team2_xg = match.expected_goals()
    team1_momentum, team2_momentum = (
        match.live_momentum_percentages()
    )

    print("\nRoad to the Final — Current Prediction")
    print("=" * 55)
    print(
        f"{match.team1.name} {match.team1.goals} - "
        f"{match.team2.goals} {match.team2.name}"
    )
    print("Match clock:", format_match_clock(match))

    show_team_report(match.team1, match.team2)
    show_team_report(match.team2, match.team1)

    print("\nWin / Draw / Loss Probability")
    print("-" * 45)
    print(f"{match.team1.name}: {team1_win * 100:.2f}%")
    print(f"Draw: {draw_probability * 100:.2f}%")
    print(f"{match.team2.name}: {team2_win * 100:.2f}%")

    print("\nKnockout Advancement Probability")
    print("-" * 45)
    print(f"{match.team1.name}: {team1_advance * 100:.2f}%")
    print(f"{match.team2.name}: {team2_advance * 100:.2f}%")

    print("\nLive Momentum")
    print("-" * 45)
    print(f"{match.team1.name}: {team1_momentum:.2f}%")
    print(f"{match.team2.name}: {team2_momentum:.2f}%")

    print("\nExpected Goals Remaining")
    print("-" * 45)
    print(f"{match.team1.name}: {team1_xg:.2f}")
    print(f"{match.team2.name}: {team2_xg:.2f}")

    print("\nMost Likely Final Score")
    print("-" * 45)
    print(
        f"{match.team1.name} {most_likely_score[0]} - "
        f"{most_likely_score[1]} {match.team2.name}"
    )

    print("\nTop Five Scorelines")
    print("-" * 45)

    for scoreline in top_scorelines:
        print(
            f"{match.team1.name} "
            f"{scoreline['team1_goals']} - "
            f"{scoreline['team2_goals']} "
            f"{match.team2.name}: "
            f"{scoreline['probability'] * 100:.2f}%"
        )

    print("\nWhy This Prediction?")
    print("-" * 45)

    for reason in match.reasoning_summary():
        print(f"- {reason}")


# =============================================================================
# SECTION 05: MANUAL MATCH EVENT UPDATES
# =============================================================================
# Model weights and caps belong in app.py, not here.
# =============================================================================

def add_goal(team):
    team.goals += 1
    print(f"\nGoal added for {team.name}.")


def add_red_card(team):
    team.red_cards += 1
    print(f"\nRed card added for {team.name}.")


def add_bad_performance(team):
    print("\nBad Performance Type")
    print("=" * 35)
    print("1. Star player bad game")
    print("2. Goalkeeper bad game")
    print("3. Defender bad game")
    print("4. Midfielder bad game")
    print("5. Forward bad game")

    choice = input("Enter choice: ").strip()

    if choice == "1":
        reason = "Star player is not playing well"
        value = team.star_bad_game_penalty()
    elif choice == "2":
        reason, value = "Goalkeeper is not playing well", -10
    elif choice == "3":
        reason, value = "Defender is not playing well", -6
    elif choice == "4":
        reason, value = "Midfielder is not playing well", -5
    elif choice == "5":
        reason, value = "Forward is not playing well", -5
    else:
        reason, value = "Player is not playing well", -4

    team.add_modifier(reason, value)

    print(
        f"\nBad performance added for "
        f"{team.name}: {value:+.1f}"
    )


def add_injury(team):
    print("\nInjury / Missing Player Type")
    print("=" * 35)
    print("1. Star player out")
    print("2. Goalkeeper out")
    print("3. Defender out")
    print("4. Midfielder out")
    print("5. Forward out")

    choice = input("Enter choice: ").strip()

    options = {
        "1": ("Star player is out", -10),
        "2": ("Goalkeeper is out", -12),
        "3": ("Defender is out", -7),
        "4": ("Midfielder is out", -6),
        "5": ("Forward is out", -6),
    }

    reason, value = options.get(
        choice,
        ("Player is out", -4)
    )

    team.add_modifier(reason, value)

    print(
        f"\nInjury/missing-player modifier "
        f"added for {team.name}: {value:+.1f}"
    )


def update_possession(team1, team2):
    try:
        possession = int(
            input(
                f"Enter possession percentage for "
                f"{team1.name}: "
            )
        )
    except ValueError:
        print("\nInvalid input. Possession was not updated.")
        return

    team1.possession = max(0, min(possession, 100))
    team2.possession = 100 - team1.possession

    print("\nPossession updated.")


def add_total_shot(team):
    team.shots += 1
    print(f"\nTotal shot added for {team.name}.")


def add_shot_on_target(team):
    team.shots_on_target += 1
    team.shots = max(team.shots, team.shots_on_target)
    print(f"\nShot on target added for {team.name}.")


def add_big_chance(team):
    team.big_chances += 1
    print(f"\nBig chance added for {team.name}.")


def add_blocked_shot(team):
    team.defender_blocks += 1
    team.shots += 1
    print(f"\nBlocked shot added for {team.name}.")


def add_corner(team):
    team.corners += 1
    print(f"\nCorner added for {team.name}.")


# =============================================================================
# SECTION 06: MATCH CREATION AND WINNER HELPERS
# =============================================================================

def predicted_advancing_team(match):
    (
        team1_win,
        draw_probability,
        team2_win,
        _,
        _,
    ) = match.calculate_probabilities()

    team1_advance, team2_advance = (
        match.advancement_probabilities(
            (
                team1_win,
                draw_probability,
                team2_win,
            )
        )
    )

    if team1_advance >= team2_advance:
        return match.team1

    return match.team2


def start_new_match(teams):
    print("\nStart New Match")
    print("=" * 40)

    team1 = select_team(
        teams,
        "\nChoose Team 1 by number: "
    )

    team2 = select_team(
        teams,
        "\nChoose Team 2 by number: "
    )

    while team1.name == team2.name:
        print(
            "\nYou selected the same team twice. "
            "Choose a different Team 2."
        )

        team2 = select_team(
            teams,
            "\nChoose Team 2 by number: "
        )

    return Match(team1, team2, match_minute=0)


# =============================================================================
# SECTION 07: PRE-GAME BACKTEST
# =============================================================================

def backtest_matches(teams, filename):
    correct = 0
    total = 0

    print("\nPre-game Backtest Results")
    print("=" * 50)

    try:
        with open(filename, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                team1 = find_team_by_name(teams, row["team1"])
                team2 = find_team_by_name(teams, row["team2"])
                actual_winner = row["actual_winner"]

                if team1 is None or team2 is None:
                    print(
                        f"\nSkipping: {row['team1']} "
                        f"vs {row['team2']}"
                    )
                    print("Reason: Team missing from teams.csv.")
                    continue

                match = Match(
                    team1,
                    team2,
                    match_minute=0
                )

                predicted_winner = (
                    predicted_advancing_team(match).name
                )

                print(f"\n{team1.name} vs {team2.name}")
                print("Predicted:", predicted_winner)
                print("Actual:", actual_winner)

                if (
                    predicted_winner.lower()
                    == actual_winner.lower()
                ):
                    print("Result: Correct")
                    correct += 1
                else:
                    print("Result: Wrong")

                total += 1

    except FileNotFoundError:
        print(f"\nError: {filename} was not found.")
        return

    print_backtest_summary("Pre-game", correct, total)


# =============================================================================
# SECTION 08: HISTORICAL SNAPSHOT BACKTEST
# =============================================================================
# PURPOSE:
# Compares:
#
# 1. The pregame prediction made from team ratings only
# 2. The historical-snapshot prediction made from stored match statistics
#
# IMPORTANT:
# This backtest never calls API-Football.
#
# Historical matches are loaded from match_history.csv and applied through:
#
#     apply_historical_row_to_match()
#
# This keeps production live mode and historical testing completely separate.
#
# EXPECTED SNAPSHOT FIELDS:
# - snapshot_minute
# - snapshot_extra_minute
# - match_status_short
# - match_status_long
# - snapshot_team1_goals
# - snapshot_team2_goals
# - team1_possession
# - team2_possession
# - team1_total_shots
# - team2_total_shots
# - team1_shots_on_target
# - team2_shots_on_target
# - team1_big_chances
# - team2_big_chances
# - team1_defender_blocks
# - team2_defender_blocks
# - team1_goalkeeper_saves
# - team2_goalkeeper_saves
# - team1_corners
# - team2_corners
# - team1_yellow_cards
# - team2_yellow_cards
# - team1_red_cards
# - team2_red_cards
# - team1_bad_star
# - team2_bad_star
#
# FINAL-RESULT FIELDS:
# - actual_winner
# - final_team1_goals
# - final_team2_goals
#
# UPDATE THIS SECTION WHEN:
# - Changing the historical CSV schema
# - Adding another snapshot statistic
# - Adding calibration or probability scoring
# =============================================================================

def historical_backtest_matches(
    teams,
    filename
):
    pregame_correct = 0
    historical_correct = 0
    total = 0
    skipped = 0

    print("\nHistorical Snapshot Backtest Results")
    print("=" * 60)

    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:
            reader = csv.DictReader(file)

            for row_number, row in enumerate(
                reader,
                start=2
            ):
                team1 = find_team_by_name(
                    teams,
                    row.get(
                        "team1",
                        ""
                    )
                )

                team2 = find_team_by_name(
                    teams,
                    row.get(
                        "team2",
                        ""
                    )
                )

                actual_winner = str(
                    row.get(
                        "actual_winner",
                        ""
                    )
                    or ""
                ).strip()

                if team1 is None or team2 is None:
                    print(
                        f"\nSkipping CSV row {row_number}: "
                        "team missing from teams.csv."
                    )
                    skipped += 1
                    continue

                if not actual_winner:
                    print(
                        f"\nSkipping CSV row {row_number}: "
                        "actual_winner is missing."
                    )
                    skipped += 1
                    continue

                pregame_match = Match(
                    copy_team(team1),
                    copy_team(team2),
                    match_minute=0
                )

                historical_match = Match(
                    copy_team(team1),
                    copy_team(team2),
                    match_minute=0
                )

                pregame_winner = (
                    predicted_advancing_team(
                        pregame_match
                    ).name
                )

                data_source = (
                    apply_historical_row_to_match(
                        historical_match,
                        row
                    )
                )

                historical_winner = (
                    predicted_advancing_team(
                        historical_match
                    ).name
                )

                # -------------------------------------------------------------
                # SECTION 08A: SCORE THIS HISTORICAL MATCH
                # -------------------------------------------------------------

                pregame_is_correct = (
                    pregame_winner.lower()
                    == actual_winner.lower()
                )

                historical_is_correct = (
                    historical_winner.lower()
                    == actual_winner.lower()
                )

                if pregame_is_correct:
                    pregame_correct += 1

                if historical_is_correct:
                    historical_correct += 1

                total += 1

                # -------------------------------------------------------------
                # SECTION 08B: PRINT DETAILED MATCH RESULT
                # -------------------------------------------------------------

                print("\n" + "=" * 60)
                print(
                    f"Match {total}: "
                    f"{team1.name} vs {team2.name}"
                )
                print("=" * 60)

                print(
                    "Historical data source:",
                    data_source
                )

                print(
                    "Snapshot clock:",
                    format_match_clock(
                        historical_match
                    )
                )

                print(
                    "Snapshot score:",
                    f"{historical_match.team1.goals}-"
                    f"{historical_match.team2.goals}"
                )

                print(
                    "Pre-game predicted:",
                    pregame_winner
                )

                print(
                    "Snapshot predicted:",
                    historical_winner
                )

                print(
                    "Actual winner:",
                    actual_winner
                )

                print(
                    "Pre-game result:",
                    "Correct"
                    if pregame_is_correct
                    else "Wrong"
                )

                print(
                    "Historical result:",
                    "Correct"
                    if historical_is_correct
                    else "Wrong"
                )

                if not historical_is_correct:
                    print(
                        "MISS:",
                        f"Predicted {historical_winner}, "
                        f"but {actual_winner} won."
                    )

    except FileNotFoundError:
        print(
            f"\nError: {filename} was not found."
        )
        return

    print_backtest_summary(
        "Pre-game",
        pregame_correct,
        total
    )

    print_backtest_summary(
        "Historical snapshot",
        historical_correct,
        total
    )

    if skipped > 0:
        print(
            f"\nSkipped rows: {skipped}"
        )


def print_backtest_summary(
    label,
    correct,
    total
):
    print("\n" + "=" * 60)
    print(f"{label} Accuracy")
    print("=" * 60)

    if total <= 0:
        print("No matches were tested.")
        return

    accuracy = (
        correct
        / total
        * 100
    )

    incorrect = (
        total
        - correct
    )

    print(f"Correct:   {correct}")
    print(f"Incorrect: {incorrect}")
    print(f"Total:     {total}")
    print(f"Accuracy:  {accuracy:.2f}%")
    print("=" * 60)


# =============================================================================
# SECTION 09: ALGORITHM DESCRIPTION MENU
# =============================================================================

def show_algorithm_descriptions():
    descriptions = [
        (
            "Weighted Team Rating",
            "Combines offense, defense, form, star power, and clutch."
        ),
        (
            "Proportional Star Penalty",
            "Uses a percentage of star power instead of a flat penalty."
        ),
        (
            "Capped Event Modifiers",
            "Limits stacked manual modifiers to the model floor and ceiling."
        ),
        (
            "Calculated Dangerous Attacks",
            "Estimates threatening attacks from chances, blocks, and saves."
        ),
        (
            "Attack Pressure",
            "Combines dangerous attacks, shots on target, chances, and goals."
        ),
        (
            "Live Momentum",
            "Compares live activity without double-counting attack pressure."
        ),
        (
            "Poisson Expected Goals",
            "Estimates additional goals expected from the current minute."
        ),
        (
            "Win/Draw/Loss Probability",
            "Uses Poisson scorelines for all regulation outcomes."
        ),
        (
            "Knockout Advancement",
            "Distributes drawn outcomes using clutch ratings."
        ),
        (
            "Prediction Reasoning",
            "Explains score, pressure, momentum, cards, and modifiers."
        ),
    ]

    print("\nRoad to the Final — Current Algorithms")
    print("=" * 60)

    for index, (title, description) in enumerate(
        descriptions,
        start=1
    ):
        print(f"\n{index}. {title}")
        print(description)


# =============================================================================
# SECTION 10: MAIN CLI MENU
# =============================================================================

def main_menu(match, teams):
    while True:
        print("\nRoad to the Final")
        print("=" * 45)
        print(
            "Current Match:",
            f"{match.team1.name} vs {match.team2.name}"
        )
        print("Match Clock:", format_match_clock(match))

        print("\nPrediction")
        print("1. Show current prediction")
        print("2. Update from live feed")

        print("\nScore and Discipline")
        print("3. Add goal")
        print("4. Add red card")

        print("\nAttacking Statistics")
        print("5. Add total shot")
        print("6. Add shot on target")
        print("7. Add big chance")
        print("8. Add blocked shot")
        print("9. Add corner")

        print("\nMatch Conditions")
        print("10. Update possession")
        print("11. Add bad player performance")
        print("12. Add injury / missing player")
        print("13. Update match clock/status")

        print("\nProject Tools")
        print("14. Start new match")
        print("15. Pre-game backtest")
        print("16. Historical snapshot backtest")
        print("17. Show algorithm descriptions")
        print("18. Exit")

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            show_prediction(match)

        elif choice == "2":
            data_source = apply_live_data_to_match(match)

            print("\nLive-feed update complete.")
            print("Data source:", data_source)
            print("Match clock:", format_match_clock(match))

        elif choice == "3":
            add_goal(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "4":
            add_red_card(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "5":
            add_total_shot(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "6":
            add_shot_on_target(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "7":
            add_big_chance(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "8":
            add_blocked_shot(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "9":
            add_corner(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "10":
            update_possession(
                match.team1,
                match.team2
            )

        elif choice == "11":
            add_bad_performance(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "12":
            add_injury(
                choose_match_team(
                    match.team1,
                    match.team2
                )
            )

        elif choice == "13":
            update_match_clock_manually(match)

        elif choice == "14":
            match = start_new_match(teams)

        elif choice == "15":
            backtest_matches(
                teams,
                "match_history.csv"
            )

        elif choice == "16":
            historical_backtest_matches(
                teams,
                "match_history.csv"
            )

        elif choice == "17":
            show_algorithm_descriptions()

        elif choice == "18":
            print("\nExiting Road to the Final.")
            break

        else:
            print("\nInvalid choice. Try again.")


# =============================================================================
# SECTION 11: APPLICATION STARTUP
# =============================================================================

def start_app():
    teams = load_teams_from_csv("teams.csv")

    if len(teams) < 2:
        print(
            "\nAt least two teams are "
            "required in teams.csv."
        )
        return

    print("\nWelcome to Road to the Final")
    print("=" * 45)
    print(
        "CLI and website are using the "
        "same shared prediction model."
    )

    match = start_new_match(teams)
    main_menu(match, teams)


# =============================================================================
# SECTION 12: PYTHON ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    start_app()