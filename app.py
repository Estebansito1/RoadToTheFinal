# =============================================================================
# FILE: app.py
# PROJECT: Road to the Final
# =============================================================================
# PURPOSE:
# This is the main Flask application and prediction-model file.
#
# It is responsible for:
# - Loading team ratings from teams.csv
# - Receiving manual match-stat updates from the webpage
# - Receiving live-feed updates from live_feed.py
# - Calculating win, draw, and loss probabilities
# - Calculating Poisson expected goals and likely scorelines
# - Calculating live momentum and attack pressure
# - Building prediction explanations
# - Storing the probability timeline
# - Running the basic tournament simulator
# - Sending all calculated values to templates/index.html
#
# MAINTENANCE GUIDE:
# Every major feature is separated into a numbered section.
# When adding or changing a feature later, update only the matching section.
#
# Example:
# - Change Poisson calculations: SECTION 6
# - Change Live Momentum: SECTION 5
# - Add match statistics: SECTION 3 and SECTION 12
# - Change live-feed behavior: SECTION 11
# - Change webpage values: SECTION 14
# =============================================================================


# =============================================================================
# SECTION 1: IMPORTS AND FLASK CONFIGURATION
# =============================================================================
# PURPOSE:
# Imports Python libraries, creates the Flask application, and configures the
# session secret key.
#
# UPDATE THIS SECTION WHEN:
# - Adding a new Python package
# - Changing Flask configuration
# - Adding database, API, or authentication configuration
# =============================================================================

import csv
import math
import os
import random
from collections import Counter, defaultdict

from flask import Flask, render_template, request, session
from insights import get_head_to_head, get_recent_form
from live_feed import apply_live_data_to_match



app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "road-to-the-final-development-key"
)


# =============================================================================
# SECTION 2: MODEL CONSTANTS AND FEATURE WEIGHTS
# =============================================================================
# PURPOSE:
# Stores the values that control how strongly each match event affects the
# prediction model.
#
# UPDATE THIS SECTION WHEN:
# - Rebalancing attack pressure
# - Rebalancing live momentum
# - Changing expected total goals
# - Changing red-card or star-player effects
#
# IMPORTANT:
# These are heuristic values. They should eventually be calibrated against
# historical match data.
# =============================================================================

STAR_BAD_GAME_FACTOR = 0.10

EVENT_SCORE_FLOOR = -20
EVENT_SCORE_CEILING = 20

FULL_MATCH_EXPECTED_GOALS = 2.60

# Attack-pressure weights
DANGEROUS_ATTACK_WEIGHT = 0.50
SHOT_ON_TARGET_WEIGHT = 2.00
BIG_CHANCE_WEIGHT = 3.00
GOAL_PRESSURE_WEIGHT = 6.00

# Live-momentum weights
MOMENTUM_SHOT_WEIGHT = 0.50
MOMENTUM_SHOT_ON_TARGET_WEIGHT = 1.50
MOMENTUM_BIG_CHANCE_WEIGHT = 2.50
MOMENTUM_BLOCKED_SHOT_WEIGHT = 0.50
MOMENTUM_CORNER_WEIGHT = 0.40
MOMENTUM_GOAL_WEIGHT = 3.00
MOMENTUM_POSSESSION_WEIGHT = 0.05
MOMENTUM_RED_CARD_PENALTY = 3.00
MOMENTUM_MINIMUM_BASE = 1.00


# =============================================================================
# SECTION 3: TEAM DATA MODEL
# =============================================================================
# PURPOSE:
# Represents one team and stores both:
# 1. Pregame ratings loaded from teams.csv
# 2. Current live match statistics
#
# UPDATE THIS SECTION WHEN:
# - Adding a new team rating
# - Adding a new live match statistic
# - Adding a new event modifier
#
# CURRENT LIVE STATISTICS:
# - Goals
# - Possession
# - Total shots
# - Shots on target
# - Big chances
# - Blocked shots
# - Goalkeeper saves
# - Corners
# - Yellow cards
# - Red cards
# =============================================================================

class Team:
    def __init__(
        self,
        name,
        offense,
        defense,
        form,
        star_power,
        clutch,
        fifa_rank=None,
        fifa_points=None,
        ranking_date=""
    ):
        # ---------------------------------------------------------------------
        # Pregame team ratings
        # ---------------------------------------------------------------------
        self.name = name
        self.offense = float(offense)
        self.defense = float(defense)
        self.form = float(form)
        self.star_power = float(star_power)
        self.clutch = float(clutch)

        # ---------------------------------------------------------------------
        # FIFA ranking metadata
        # ---------------------------------------------------------------------
        self.fifa_rank = int(float(fifa_rank)) if fifa_rank not in (None, "") else None
        self.fifa_points = float(fifa_points) if fifa_points not in (None, "") else None
        self.ranking_date = str(ranking_date or "")

        # ---------------------------------------------------------------------
        # Current score and discipline
        # ---------------------------------------------------------------------
        self.goals = 0
        self.yellow_cards = 0
        self.red_cards = 0

        # ---------------------------------------------------------------------
        # Current possession
        # ---------------------------------------------------------------------
        self.possession = 50

        # ---------------------------------------------------------------------
        # Current attacking statistics
        # ---------------------------------------------------------------------
        self.shots = 0
        self.shots_on_target = 0
        self.big_chances = 0
        self.defender_blocks = 0
        self.corners = 0

        # Saves made by this team's goalkeeper
        self.goalkeeper_saves = 0

        # ---------------------------------------------------------------------
        # Manual event modifiers
        # ---------------------------------------------------------------------
        self.modifiers = []

    # -------------------------------------------------------------------------
    # SECTION 3A: PREGAME TEAM STRENGTH
    # -------------------------------------------------------------------------

    def base_score(self):
        """
        Creates the pregame team-strength score from teams.csv ratings.
        """

        weighted_rating = (
            self.offense * 0.30
            + self.defense * 0.25
            + self.form * 0.20
            + self.star_power * 0.15
            + self.clutch * 0.10
        )

        # FIFA rank is a small supporting signal, never the main model driver.
        ranking_bonus = 0.0
        if self.fifa_rank is not None:
            ranking_bonus = max(-2.0, min(2.0, (25 - self.fifa_rank) * 0.08))

        return weighted_rating + ranking_bonus

    # -------------------------------------------------------------------------
    # SECTION 3B: MANUAL EVENT MODIFIERS
    # -------------------------------------------------------------------------

    def add_modifier(self, reason, value):
        self.modifiers.append((reason, float(value)))

    def star_bad_game_penalty(self):
        """
        Applies a penalty equal to a percentage of this team's star-power
        rating instead of applying the same flat penalty to every team.
        """

        return -round(
            self.star_power * STAR_BAD_GAME_FACTOR,
            1
        )

    def event_score_breakdown(self):
        """
        Returns:
        - Raw modifier total
        - Capped modifier total
        - Whether the value was capped
        """

        raw_total = sum(
            value
            for reason, value in self.modifiers
        )

        capped_total = max(
            EVENT_SCORE_FLOOR,
            min(raw_total, EVENT_SCORE_CEILING)
        )

        return (
            raw_total,
            capped_total,
            raw_total != capped_total
        )

    def event_score(self):
        """
        Returns the capped sum of live event modifiers.

        Red cards are handled separately and are not included in this cap.
        """

        _, capped_total, _ = self.event_score_breakdown()
        return capped_total

    # -------------------------------------------------------------------------
    # SECTION 3C: SCORE, POSSESSION, AND CARD EFFECTS
    # -------------------------------------------------------------------------

    def possession_score(self):
        if self.possession > 55:
            return 3

        if self.possession < 45:
            return -3

        return 0

    def scoreline_score(self):
        return self.goals * 8

    def red_card_score(self):
        return self.red_cards * -12

    # -------------------------------------------------------------------------
    # SECTION 3D: DANGEROUS ATTACK ESTIMATE
    # -------------------------------------------------------------------------

    def calculated_dangerous_attacks(self, opponent):
        """
        Estimates dangerous attacking sequences from available objective
        events.

        The opponent's goalkeeper saves represent shots from this team that
        reached the opposing goalkeeper.
        """

        saved_by_opponent = opponent.goalkeeper_saves

        chance_events = (
            self.big_chances
            + self.defender_blocks
            + saved_by_opponent
        )

        return max(
            self.shots_on_target,
            chance_events
        )

    # -------------------------------------------------------------------------
    # SECTION 3E: ATTACK PRESSURE
    # -------------------------------------------------------------------------

    def attack_pressure_score(self, opponent):
        """
        Produces a transparent attack-pressure number.

        This is an absolute score, not a percentage. A larger number means
        the team has generated more threatening attacking activity.
        """

        dangerous_attacks = (
            self.calculated_dangerous_attacks(opponent)
        )

        return (
            dangerous_attacks * DANGEROUS_ATTACK_WEIGHT
            + self.shots_on_target * SHOT_ON_TARGET_WEIGHT
            + self.big_chances * BIG_CHANCE_WEIGHT
            + self.goals * GOAL_PRESSURE_WEIGHT
        )

    # -------------------------------------------------------------------------
    # SECTION 3F: LIVE TEAM SCORE
    # -------------------------------------------------------------------------

    def live_score(self, opponent=None):
        """
        Combines pregame strength and current match conditions.

        This value is used to divide the remaining expected goals between the
        two teams.
        """

        score = (
            self.base_score()
            + self.event_score()
            + self.possession_score()
            + self.scoreline_score()
            + self.red_card_score()
        )

        if opponent is not None:
            score += self.attack_pressure_score(opponent)

        return score


# =============================================================================
# SECTION 4: MATCH DATA MODEL AND TIME CONTROL
# =============================================================================
# PURPOSE:
# Represents one match and contains all match-level calculations.
#
# THIS SECTION NOW ALSO STORES:
# - Main elapsed minute
# - Added/stoppage time
# - Short match-status code
# - Long match-status description
#
# EXAMPLES:
# - 45+3'
# - HT
# - ET
# - AET
# - FT
#
# UPDATE THIS SECTION WHEN:
# - Changing regulation or extra-time handling
# - Adding match status
# - Adding penalty-shootout status
# - Adding event-timeline storage directly to the Match object
# =============================================================================

class Match:
    def __init__(
        self,
        team1,
        team2,
        match_minute=0
    ):
        self.team1 = team1
        self.team2 = team2

        # ---------------------------------------------------------------------
        # SECTION 4A: MAIN MATCH MINUTE
        # ---------------------------------------------------------------------

        self.match_minute = max(
            0,
            min(
                int(match_minute),
                120
            )
        )

        # ---------------------------------------------------------------------
        # SECTION 4B: ADDED / STOPPAGE TIME
        # ---------------------------------------------------------------------
        # Example:
        # match_minute = 45
        # match_extra_minute = 3
        #
        # Display:
        # 45+3'
        # ---------------------------------------------------------------------

        self.match_extra_minute = 0

        # ---------------------------------------------------------------------
        # SECTION 4C: MATCH STATUS
        # ---------------------------------------------------------------------
        # Common API-Football values:
        #
        # NS  = Not Started
        # 1H  = First Half
        # HT  = Halftime
        # 2H  = Second Half
        # ET  = Extra Time
        # BT  = Break Time
        # PEN = Penalty Shootout
        # AET = Finished After Extra Time
        # FT  = Full Time
        # ---------------------------------------------------------------------

        self.match_status_short = ""
        self.match_status_long = ""

        # ---------------------------------------------------------------------
        # SECTION 4D: EVENT TIMELINE
        # ---------------------------------------------------------------------

        self.event_timeline = []

    @staticmethod
    def poisson_probability(
        goals,
        expected_goals
    ):
        return (
            math.exp(-expected_goals)
            * expected_goals**goals
            / math.factorial(goals)
        )

    def remaining_time_ratio(self):
        if self.match_minute >= 90:
            return 0.03

        return max(
            (90 - self.match_minute) / 90,
            0.03
        )


# =============================================================================
# SECTION 5: LIVE MOMENTUM CALCULATION
# =============================================================================
# PURPOSE:
# Converts current attacking activity into a two-team percentage:
#
# Example:
# Spain 38% | France 62%
#
# Unlike Win Probability, Live Momentum describes which team is applying more
# pressure right now. It does not directly predict the final winner.
#
# UPDATE THIS SECTION WHEN:
# - Adding recent-event time weighting
# - Adding ball-position tracking
# - Adding dangerous possession
# - Changing momentum feature weights
#
# FUTURE IMPROVEMENT:
# Once event timestamps are available, only the most recent 5-10 minutes
# should receive full weight.
# =============================================================================

    def team_momentum_score(self, team):
        """
        Creates one team's raw Live Momentum score.

        This calculation intentionally does not call
        attack_pressure_score(), preventing double-counting.
        """

        possession_above_even = max(
            team.possession - 50,
            0
        )

        momentum_score = (
            team.shots
            * MOMENTUM_SHOT_WEIGHT

            + team.shots_on_target
            * MOMENTUM_SHOT_ON_TARGET_WEIGHT

            + team.big_chances
            * MOMENTUM_BIG_CHANCE_WEIGHT

            + team.defender_blocks
            * MOMENTUM_BLOCKED_SHOT_WEIGHT

            + team.corners
            * MOMENTUM_CORNER_WEIGHT

            + team.goals
            * MOMENTUM_GOAL_WEIGHT

            + possession_above_even
            * MOMENTUM_POSSESSION_WEIGHT

            - team.red_cards
            * MOMENTUM_RED_CARD_PENALTY
        )

        return max(
            momentum_score,
            MOMENTUM_MINIMUM_BASE
        )

    def live_momentum_percentages(self):
        """
        Converts both raw momentum scores into percentages totaling 100%.
        """

        team1_momentum_score = (
            self.team_momentum_score(
                self.team1
            )
        )

        team2_momentum_score = (
            self.team_momentum_score(
                self.team2
            )
        )

        total_momentum = (
            team1_momentum_score
            + team2_momentum_score
        )

        if total_momentum <= 0:
            return 50.0, 50.0

        team1_momentum = (
            team1_momentum_score
            / total_momentum
            * 100
        )

        team2_momentum = (
            team2_momentum_score
            / total_momentum
            * 100
        )

        return (
            team1_momentum,
            team2_momentum
        )


# =============================================================================
# SECTION 6: POISSON EXPECTED GOALS
# =============================================================================
# PURPOSE:
# Estimates how many additional goals each team is expected to score from the
# current match minute until the end of the match.
#
# UPDATE THIS SECTION WHEN:
# - Changing the expected total goals per match
# - Improving red-card effects
# - Adding home advantage
# - Adding game-state effects
# - Replacing the heuristic model with calibrated xG
# =============================================================================

    def expected_goals(self):
        """
        Estimates additional goals expected from the current match state.
        """

        team1_strength = max(
            self.team1.live_score(self.team2),
            1.0
        )

        team2_strength = max(
            self.team2.live_score(self.team1),
            1.0
        )

        total_strength = team1_strength + team2_strength

        remaining_ratio = self.remaining_time_ratio()

        remaining_expected_goals = (
            FULL_MATCH_EXPECTED_GOALS
            * remaining_ratio
        )

        team1_expected_goals = (
            remaining_expected_goals
            * team1_strength
            / total_strength
        )

        team2_expected_goals = (
            remaining_expected_goals
            * team2_strength
            / total_strength
        )

        # Red-card effects influence both teams.
        team1_expected_goals -= (
            self.team1.red_cards
            * 0.22
            * remaining_ratio
        )

        team2_expected_goals -= (
            self.team2.red_cards
            * 0.22
            * remaining_ratio
        )

        team1_expected_goals += (
            self.team2.red_cards
            * 0.18
            * remaining_ratio
        )

        team2_expected_goals += (
            self.team1.red_cards
            * 0.18
            * remaining_ratio
        )

        team1_expected_goals = max(
            team1_expected_goals,
            0.02
        )

        team2_expected_goals = max(
            team2_expected_goals,
            0.02
        )

        return (
            team1_expected_goals,
            team2_expected_goals
        )


# =============================================================================
# SECTION 7: WIN PROBABILITY AND MOST LIKELY SCORES
# =============================================================================
# PURPOSE:
# Uses the Poisson distribution to calculate:
# - Team 1 win probability
# - Draw probability
# - Team 2 win probability
# - Most likely final score
# - Five most likely final scorelines
#
# UPDATE THIS SECTION WHEN:
# - Increasing the scoreline search range
# - Adding penalty-shootout probability
# - Adding separate regulation and extra-time predictions
# =============================================================================

    def calculate_probabilities(
        self,
        max_additional_goals=10
    ):
        (
            team1_expected_goals,
            team2_expected_goals
        ) = self.expected_goals()

        team1_win_probability = 0.0
        draw_probability = 0.0
        team2_win_probability = 0.0

        scorelines = []

        for team1_extra_goals in range(
            max_additional_goals + 1
        ):
            team1_goal_probability = (
                self.poisson_probability(
                    team1_extra_goals,
                    team1_expected_goals
                )
            )

            for team2_extra_goals in range(
                max_additional_goals + 1
            ):
                team2_goal_probability = (
                    self.poisson_probability(
                        team2_extra_goals,
                        team2_expected_goals
                    )
                )

                score_probability = (
                    team1_goal_probability
                    * team2_goal_probability
                )

                team1_final_score = (
                    self.team1.goals
                    + team1_extra_goals
                )

                team2_final_score = (
                    self.team2.goals
                    + team2_extra_goals
                )

                scorelines.append(
                    {
                        "team1_goals": team1_final_score,
                        "team2_goals": team2_final_score,
                        "probability": score_probability
                    }
                )

                if team1_final_score > team2_final_score:
                    team1_win_probability += score_probability

                elif team1_final_score == team2_final_score:
                    draw_probability += score_probability

                else:
                    team2_win_probability += score_probability

        total_probability = (
            team1_win_probability
            + draw_probability
            + team2_win_probability
        )

        if total_probability <= 0:
            return (
                1 / 3,
                1 / 3,
                1 / 3,
                (
                    self.team1.goals,
                    self.team2.goals
                ),
                []
            )

        team1_win_probability /= total_probability
        draw_probability /= total_probability
        team2_win_probability /= total_probability

        for scoreline in scorelines:
            scoreline["probability"] /= total_probability

        scorelines.sort(
            key=lambda item: item["probability"],
            reverse=True
        )

        top_scorelines = scorelines[:5]

        most_likely_score = (
            top_scorelines[0]["team1_goals"],
            top_scorelines[0]["team2_goals"]
        )

        return (
            team1_win_probability,
            draw_probability,
            team2_win_probability,
            most_likely_score,
            top_scorelines
        )


# =============================================================================
# SECTION 8: PREDICTION SUMMARY, CONFIDENCE, AND DIFFICULTY
# =============================================================================
# PURPOSE:
# Converts raw probabilities into user-friendly labels.
#
# UPDATED:
# - Confidence is now based on the gap between the most likely outcome
#   and the second-most likely outcome.
# - This prevents a 70% to 80% prediction from incorrectly showing
#   100% confidence.
#
# UPDATE THIS SECTION WHEN:
# - Changing confidence thresholds
# - Changing match-difficulty thresholds
# - Adding prediction badges or warning labels
# =============================================================================

    def predicted_outcome(self, probabilities):
        (
            team1_probability,
            draw_probability,
            team2_probability
        ) = probabilities

        outcomes = [
            (
                f"{self.team1.name} Win",
                team1_probability
            ),
            (
                "Draw",
                draw_probability
            ),
            (
                f"{self.team2.name} Win",
                team2_probability
            )
        ]

        return max(
            outcomes,
            key=lambda item: item[1]
        )

    def prediction_confidence(self, probabilities):
        """
        Measures how far the leading outcome is ahead of the
        second-most likely outcome.

        Example:
        Spain 76%
        Draw 19%
        France 5%

        Probability margin:
        76% - 19% = 57%

        Confidence:
        57% x 1.25 = about 71%
        """

        ordered_probabilities = sorted(
            probabilities,
            reverse=True
        )

        highest_probability = (
            ordered_probabilities[0]
        )

        second_highest_probability = (
            ordered_probabilities[1]
        )

        probability_margin = (
            highest_probability
            - second_highest_probability
        )

        confidence_score = max(
            0,
            min(
                probability_margin * 125,
                100
            )
        )

        if confidence_score < 40:
            return (
                confidence_score,
                "Low",
                "confidence-low"
            )

        if confidence_score < 70:
            return (
                confidence_score,
                "Medium",
                "confidence-medium"
            )

        return (
            confidence_score,
            "High",
            "confidence-high"
        )

    def match_difficulty(self, probabilities):
        ordered_probabilities = sorted(
            probabilities,
            reverse=True
        )

        margin = (
            ordered_probabilities[0]
            - ordered_probabilities[1]
        )

        if margin < 0.04:
            return (
                5,
                "Extremely Even Match"
            )

        if margin < 0.09:
            return (
                4,
                "Very Competitive Match"
            )

        if margin < 0.16:
            return (
                3,
                "Competitive Match"
            )

        if margin < 0.25:
            return (
                2,
                "Clear Favorite"
            )

        return (
            1,
            "Heavy Favorite"
        )


# =============================================================================
# SECTION 9: KNOCKOUT ADVANCEMENT PROBABILITY
# =============================================================================
# PURPOSE:
# Converts the regulation-time draw probability into an estimated chance of
# advancing by distributing drawn outcomes according to each team's clutch
# rating.
#
# UPDATE THIS SECTION WHEN:
# - Adding extra-time modeling
# - Adding penalty-shootout ratings
# - Replacing clutch ratings with historical knockout data
# =============================================================================

    def advancement_probabilities(self, probabilities):
        (
            team1_win_probability,
            draw_probability,
            team2_win_probability
        ) = probabilities

        clutch_total = (
            self.team1.clutch
            + self.team2.clutch
        )

        if clutch_total <= 0:
            team1_draw_share = 0.50
            team2_draw_share = 0.50

        else:
            team1_draw_share = (
                self.team1.clutch
                / clutch_total
            )

            team2_draw_share = (
                self.team2.clutch
                / clutch_total
            )

        team1_advance_probability = (
            team1_win_probability
            + draw_probability * team1_draw_share
        )

        team2_advance_probability = (
            team2_win_probability
            + draw_probability * team2_draw_share
        )

        total_probability = (
            team1_advance_probability
            + team2_advance_probability
        )

        if total_probability > 0:
            team1_advance_probability /= total_probability
            team2_advance_probability /= total_probability

        return (
            team1_advance_probability,
            team2_advance_probability
        )


# =============================================================================
# SECTION 10: "WHY THIS PREDICTION?" EXPLANATION
# =============================================================================
# PURPOSE:
# Builds readable reasons explaining why the model currently favors one team,
# a draw, or a specific match state.
#
# UPDATE THIS SECTION WHEN:
# - Adding new statistics
# - Adding tactical explanations
# - Adding ball-position explanations
# - Changing the wording displayed on the webpage
# =============================================================================

    def reasoning_summary(self):
        reasons = []

        team1_pressure = (
            self.team1.attack_pressure_score(self.team2)
        )

        team2_pressure = (
            self.team2.attack_pressure_score(self.team1)
        )

        team1_dangerous = (
            self.team1.calculated_dangerous_attacks(
                self.team2
            )
        )

        team2_dangerous = (
            self.team2.calculated_dangerous_attacks(
                self.team1
            )
        )

        (
            team1_momentum,
            team2_momentum
        ) = self.live_momentum_percentages()

        if self.team1.goals > self.team2.goals:
            reasons.append(
                f"{self.team1.name} currently has more goals."
            )

        elif self.team2.goals > self.team1.goals:
            reasons.append(
                f"{self.team2.name} currently has more goals."
            )

        if self.team1.red_cards > self.team2.red_cards:
            reasons.append(
                f"{self.team1.name} has more red cards, "
                "which hurts its chances."
            )

        elif self.team2.red_cards > self.team1.red_cards:
            reasons.append(
                f"{self.team2.name} has more red cards, "
                "which hurts its chances."
            )

        if self.team1.shots_on_target > self.team2.shots_on_target:
            reasons.append(
                f"{self.team1.name} has more shots on target."
            )

        elif self.team2.shots_on_target > self.team1.shots_on_target:
            reasons.append(
                f"{self.team2.name} has more shots on target."
            )

        if self.team1.big_chances > self.team2.big_chances:
            reasons.append(
                f"{self.team1.name} has created more big chances."
            )

        elif self.team2.big_chances > self.team1.big_chances:
            reasons.append(
                f"{self.team2.name} has created more big chances."
            )

        if team1_pressure > team2_pressure:
            reasons.append(
                f"{self.team1.name} has the higher attack "
                "pressure score."
            )

        elif team2_pressure > team1_pressure:
            reasons.append(
                f"{self.team2.name} has the higher attack "
                "pressure score."
            )

        if team1_momentum > team2_momentum:
            reasons.append(
                f"{self.team1.name} currently has more live momentum."
            )

        elif team2_momentum > team1_momentum:
            reasons.append(
                f"{self.team2.name} currently has more live momentum."
            )

        if team1_dangerous > team2_dangerous:
            reasons.append(
                f"{self.team1.name} has more calculated "
                "dangerous attacks."
            )

        elif team2_dangerous > team1_dangerous:
            reasons.append(
                f"{self.team2.name} has more calculated "
                "dangerous attacks."
            )

        if (
            self.team1.goalkeeper_saves
            > self.team2.goalkeeper_saves
        ):
            reasons.append(
                f"{self.team1.name}'s goalkeeper has made "
                "more saves."
            )

        elif (
            self.team2.goalkeeper_saves
            > self.team1.goalkeeper_saves
        ):
            reasons.append(
                f"{self.team2.name}'s goalkeeper has made "
                "more saves."
            )

        if self.match_minute > 0:
            reasons.append(
                f"The model is calculating remaining goals "
                f"from minute {self.match_minute}."
            )

        for reason, _ in self.team1.modifiers:
            reasons.append(
                f"{self.team1.name}: {reason}."
            )

        for reason, _ in self.team2.modifiers:
            reasons.append(
                f"{self.team2.name}: {reason}."
            )

        for team in (self.team1, self.team2):
            (
                raw_total,
                capped_total,
                was_clamped
            ) = team.event_score_breakdown()

            if was_clamped:
                reasons.append(
                    f"{team.name}: stacked modifiers totaled "
                    f"{raw_total:+.1f}, but were capped at "
                    f"{capped_total:+.1f}."
                )

        if not reasons:
            reasons.append(
                "No major live events yet. The prediction is "
                "based on team ratings and the Poisson model."
            )

        return reasons


# =============================================================================
# SECTION 11: TEAM FILE LOADING AND SAFE DATA HELPERS
# =============================================================================
# PURPOSE:
# Loads teams.csv, creates fresh Team copies, finds teams by name, and safely
# reads integer form values.
#
# UPDATE THIS SECTION WHEN:
# - Changing teams.csv columns
# - Moving team data into a database
# - Adding validation rules
# =============================================================================

def load_teams_from_csv(filename):
    teams = []

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            teams.append(
                Team(
                    row["name"],
                    row["offense"],
                    row["defense"],
                    row["form"],
                    row["star_power"],
                    row["clutch"],
                    row.get("fifa_rank"),
                    row.get("fifa_points"),
                    row.get("ranking_date", "")
                )
            )

    return teams


def copy_team(team):
    return Team(
        team.name,
        team.offense,
        team.defense,
        team.form,
        team.star_power,
        team.clutch,
        team.fifa_rank,
        team.fifa_points,
        team.ranking_date
    )


def find_team_by_name(teams, name):
    for team in teams:
        if team.name.lower() == name.lower():
            return copy_team(team)

    return None


def get_integer_form_value(
    field_name,
    default=0,
    minimum=0,
    maximum=None
):
    try:
        value = int(
            request.form.get(
                field_name,
                default
            )
        )

    except (TypeError, ValueError):
        value = default

    value = max(value, minimum)

    if maximum is not None:
        value = min(value, maximum)

    return value


# =============================================================================
# SECTION 12: PROBABILITY TIMELINE HELPER
# =============================================================================
# PURPOSE:
# Stores timeline entries for the Win Probability Timeline card.
# If multiple updates happen in the same minute, the newest one replaces
# the previous one instead of creating duplicate minute entries.
#
# UPDATE THIS SECTION WHEN:
# - Increasing timeline history
# - Storing event descriptions
# - Moving timeline data into a database
# - Adding chart timestamps
# =============================================================================

def add_timeline_entry(
    match,
    team1_probability,
    draw_probability,
    team2_probability,
    update_type
):
    """Stores probability, cumulative xG, and possession chart snapshots."""

    team1 = match.team1
    team2 = match.team2
    match_minute = match.match_minute

    timeline = session.get("probability_timeline", [])
    chart_timeline = session.get("match_chart_timeline", [])
    current_match = f"{team1.name}|{team2.name}"

    if session.get("timeline_match") != current_match:
        timeline = []
        chart_timeline = []

    team1_remaining_xg, team2_remaining_xg = match.expected_goals()

    # Current goals plus remaining xG gives a readable cumulative match projection.
    new_entry = {
        "minute": match_minute,
        "update_type": update_type,
        "team1_name": team1.name,
        "team2_name": team2.name,
        "team1_probability": round(team1_probability * 100, 2),
        "draw_probability": round(draw_probability * 100, 2),
        "team2_probability": round(team2_probability * 100, 2)
    }

    chart_entry = {
        "minute": match_minute,
        "team1_name": team1.name,
        "team2_name": team2.name,
        "team1_xg": round(team1.goals + team1_remaining_xg, 2),
        "team2_xg": round(team2.goals + team2_remaining_xg, 2),
        "team1_possession": round(float(team1.possession), 1),
        "team2_possession": round(float(team2.possession), 1)
    }

    if timeline and timeline[-1]["minute"] == match_minute:
        timeline[-1] = new_entry
    else:
        timeline.append(new_entry)

    if chart_timeline and chart_timeline[-1]["minute"] == match_minute:
        chart_timeline[-1] = chart_entry
    else:
        chart_timeline.append(chart_entry)

    session["probability_timeline"] = timeline[-30:]
    session["match_chart_timeline"] = chart_timeline[-30:]
    session["timeline_match"] = current_match
    session.modified = True

# =============================================================================
# SECTION 13: SAVE HISTORICAL LIVE SNAPSHOTS
# =============================================================================
# PURPOSE:
# Saves one real live-match state to historical_snapshots.csv.
#
# Only fresh API updates should be saved.
# Cached or unavailable updates must not be saved because they do not represent
# a new match state.
#
# The final winner and final score are intentionally left blank while the match
# is still being played. They can be completed after full time.
#
# UPDATE THIS SECTION WHEN:
# - Adding another historical snapshot statistic
# - Changing the snapshot CSV filename
# - Adding automatic final-result completion
# =============================================================================

def save_historical_snapshot(
    match,
    filename="historical_snapshots.csv"
):
    fieldnames = [
        "team1",
        "team2",
        "snapshot_minute",
        "snapshot_extra_minute",
        "match_status_short",
        "match_status_long",
        "snapshot_team1_goals",
        "snapshot_team2_goals",
        "team1_possession",
        "team2_possession",
        "team1_total_shots",
        "team2_total_shots",
        "team1_shots_on_target",
        "team2_shots_on_target",
        "team1_big_chances",
        "team2_big_chances",
        "team1_defender_blocks",
        "team2_defender_blocks",
        "team1_goalkeeper_saves",
        "team2_goalkeeper_saves",
        "team1_corners",
        "team2_corners",
        "team1_yellow_cards",
        "team2_yellow_cards",
        "team1_red_cards",
        "team2_red_cards",
        "team1_bad_star",
        "team2_bad_star",
        "actual_winner",
        "final_team1_goals",
        "final_team2_goals"
    ]

    snapshot = {
        "team1": match.team1.name,
        "team2": match.team2.name,

        "snapshot_minute": getattr(
            match,
            "match_minute",
            0
        ),

        "snapshot_extra_minute": getattr(
            match,
            "match_extra_minute",
            0
        ),

        "match_status_short": getattr(
            match,
            "match_status_short",
            ""
        ),

        "match_status_long": getattr(
            match,
            "match_status_long",
            ""
        ),

        "snapshot_team1_goals": match.team1.goals,
        "snapshot_team2_goals": match.team2.goals,

        "team1_possession": match.team1.possession,
        "team2_possession": match.team2.possession,

        "team1_total_shots": match.team1.shots,
        "team2_total_shots": match.team2.shots,

        "team1_shots_on_target": (
            match.team1.shots_on_target
        ),
        "team2_shots_on_target": (
            match.team2.shots_on_target
        ),

        "team1_big_chances": match.team1.big_chances,
        "team2_big_chances": match.team2.big_chances,

        "team1_defender_blocks": (
            match.team1.defender_blocks
        ),
        "team2_defender_blocks": (
            match.team2.defender_blocks
        ),

        "team1_goalkeeper_saves": (
            match.team1.goalkeeper_saves
        ),
        "team2_goalkeeper_saves": (
            match.team2.goalkeeper_saves
        ),

        "team1_corners": match.team1.corners,
        "team2_corners": match.team2.corners,

        "team1_yellow_cards": match.team1.yellow_cards,
        "team2_yellow_cards": match.team2.yellow_cards,

        "team1_red_cards": match.team1.red_cards,
        "team2_red_cards": match.team2.red_cards,

        # API-Football does not currently provide these flags.
        "team1_bad_star": False,
        "team2_bad_star": False,

        # These are completed after the match finishes.
        "actual_winner": "",
        "final_team1_goals": "",
        "final_team2_goals": ""
    }

    file_exists = os.path.exists(
        filename
    )

    with open(
        filename,
        "a",
        newline="",
        encoding="utf-8"
    ) as snapshot_file:
        writer = csv.DictWriter(
            snapshot_file,
            fieldnames=fieldnames
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            snapshot
        )
# =============================================================================
# SECTION 13A: BASIC TOURNAMENT SIMULATOR
# =============================================================================
# PURPOSE:
# Simulates a simple knockout bracket using each match's advancement
# probability.
#
# UPDATE THIS SECTION WHEN:
# - Adding official World Cup bracket rules
# - Adding seeded matchups
# - Adding group-stage qualification
# - Adding randomized simulations
# =============================================================================

def _sample_poisson(expected_goals):
    """Samples one Poisson goal total without requiring NumPy."""
    limit = math.exp(-max(expected_goals, 0.0))
    product = 1.0
    goals = 0
    while product > limit:
        goals += 1
        product *= random.random()
    return max(goals - 1, 0)


def _simulate_knockout_match(team1, team2):
    match = Match(copy_team(team1), copy_team(team2), match_minute=0)
    team1_xg, team2_xg = match.expected_goals()
    team1_goals = _sample_poisson(team1_xg)
    team2_goals = _sample_poisson(team2_xg)

    if team1_goals > team2_goals:
        return team1
    if team2_goals > team1_goals:
        return team2

    # Draws are resolved using knockout advancement probability.
    p1, draw, p2, _, _ = match.calculate_probabilities()
    advance1, _ = match.advancement_probabilities((p1, draw, p2))
    return team1 if random.random() < advance1 else team2


def simulate_tournament(teams, simulation_count=10000):
    """Runs thousands of Monte Carlo knockout brackets."""
    simulation_count = max(1000, min(int(simulation_count), 50000))
    champion_counts = Counter()
    final_counts = Counter()
    semifinal_counts = Counter()
    final_matchups = Counter()

    for _ in range(simulation_count):
        current_round = [copy_team(team) for team in teams]

        while len(current_round) > 1:
            next_round = []
            round_size = len(current_round)

            for index in range(0, round_size, 2):
                team1 = current_round[index]
                if index + 1 >= round_size:
                    next_round.append(team1)
                    continue
                team2 = current_round[index + 1]
                next_round.append(_simulate_knockout_match(team1, team2))

            if len(next_round) <= 4:
                for team in next_round:
                    semifinal_counts[team.name] += 1

            if len(next_round) == 2:
                for team in next_round:
                    final_counts[team.name] += 1
                final_matchups[tuple(sorted([next_round[0].name, next_round[1].name]))] += 1

            current_round = next_round

        if current_round:
            champion_counts[current_round[0].name] += 1

    results = []
    for team in teams:
        results.append({
            "team": team.name,
            "fifa_rank": team.fifa_rank,
            "semifinal_probability": round(100 * semifinal_counts[team.name] / simulation_count, 2),
            "final_probability": round(100 * final_counts[team.name] / simulation_count, 2),
            "champion_probability": round(100 * champion_counts[team.name] / simulation_count, 2)
        })

    results.sort(key=lambda row: row["champion_probability"], reverse=True)
    most_common_final = None
    if final_matchups:
        matchup, count = final_matchups.most_common(1)[0]
        most_common_final = {
            "team1": matchup[0],
            "team2": matchup[1],
            "probability": round(100 * count / simulation_count, 2)
        }

    champion = results[0]["team"] if results else None
    return results, champion, simulation_count, most_common_final


# =============================================================================
# SECTION 14: MAIN FLASK ROUTE AND LIVE MATCH UPDATE FLOW
# =============================================================================
# PURPOSE:
# Controls the full page request:
# 1. Loads teams
# 2. Reads selected teams
# 3. Reads manual statistics
# 4. Applies live-feed data
# 5. Runs all calculations
# 6. Sends results to index.html
#
# UPDATE THIS SECTION WHEN:
# - Adding a new form field
# - Adding a new live-feed statistic
# - Adding a new value to the webpage
# - Adding a new action button
# =============================================================================

@app.route("/", methods=["GET", "POST"])
def index():

        # -------------------------------------------------------------------------
    # SECTION 14A: LOAD TEAMS AND SELECT THE MATCH
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Loads all available teams from teams.csv and determines which two teams
    # will be used for the current prediction.
    #
    # UPDATE THIS SECTION WHEN:
    # - Adding another team source
    # - Changing team-selection behavior
    # -------------------------------------------------------------------------

    teams = load_teams_from_csv("teams.csv")

    if len(teams) < 2:
        return (
            "At least two teams are required in teams.csv.",
            500
        )

    default_team1 = teams[0].name
    default_team2 = teams[1].name

    selected_team1 = request.form.get(
        "team1",
        default_team1
    )

    selected_team2 = request.form.get(
        "team2",
        default_team2
    )

    team1 = find_team_by_name(
        teams,
        selected_team1
    )

    team2 = find_team_by_name(
        teams,
        selected_team2
    )

    if team1 is None:
        team1 = copy_team(
            teams[0]
        )

    if team2 is None:
        team2 = copy_team(
            teams[1]
        )

    if team1.name == team2.name:
        for available_team in teams:
            if available_team.name != team1.name:
                team2 = copy_team(
                    available_team
                )
                break

    # -------------------------------------------------------------------------
    # SECTION 14A-1: LOAD CACHE-FIRST PRE-MATCH INTELLIGENCE
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Normal page loads read insights_cache.json only.
    #
    # API-Football is called only when:
    #     action == "refresh_insights"
    #
    # ESTIMATED REQUEST COST:
    # - Existing cached team IDs: 3 requests
    #   1 H2H + 2 recent-form requests
    #
    # - First lookup for both teams: up to 5 requests
    #   2 team lookups + 1 H2H + 2 recent-form requests
    # -------------------------------------------------------------------------

    action = request.form.get(
        "action",
        ""
    )

    refresh_match_insights = (
        action == "refresh_insights"
    )

    h2h = get_head_to_head(
        team1.name,
        team2.name,
        force_refresh=refresh_match_insights,
        allow_api=refresh_match_insights
    )

    recent_form_team1 = get_recent_form(
        team1.name,
        match_limit=5,
        force_refresh=refresh_match_insights,
        allow_api=refresh_match_insights
    )

    recent_form_team2 = get_recent_form(
        team2.name,
        match_limit=5,
        force_refresh=refresh_match_insights,
        allow_api=refresh_match_insights
    )


    # -------------------------------------------------------------------------
    # SECTION 14A-1A: NORMALIZE RECENT-FORM DATA
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Guarantees that index.html receives every field it expects, even when
    # API-Football is unavailable or returns incomplete data.
    #
    # insights.py may use the key "points", while index.html expects
    # "form_points". This section supports both.
    # -------------------------------------------------------------------------

    recent_form_defaults = {
        "available": False,
        "team_name": "",
        "logo": "",
        "matches": [],
        "sequence": [],
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "points": 0,
        "form_points": 0,
        "goals_for": 0,
        "goals_against": 0
    }

    normalized_recent_forms = []

    for recent_form_data, selected_team in (
        (
            recent_form_team1,
            team1
        ),
        (
            recent_form_team2,
            team2
        )
    ):
        normalized_form = (
            recent_form_defaults.copy()
        )

        if isinstance(
            recent_form_data,
            dict
        ):
            normalized_form.update(
                recent_form_data
            )

        normalized_form["team_name"] = (
            selected_team.name
        )

        normalized_form["form_points"] = (
            normalized_form.get(
                "form_points"
            )
            or normalized_form.get(
                "points",
                0
            )
        )

        normalized_recent_forms.append(
            normalized_form
        )

    recent_form_team1 = (
        normalized_recent_forms[0]
    )

    recent_form_team2 = (
        normalized_recent_forms[1]
    )


    # -------------------------------------------------------------------------
    # SECTION 14A-1B: RECENT-FORM LOGO FALLBACKS
    # -------------------------------------------------------------------------

    if not recent_form_team1.get(
        "logo"
    ):
        recent_form_team1["logo"] = (
            h2h.get(
                "team1_logo",
                ""
            )
        )

    if not recent_form_team2.get(
        "logo"
    ):
        recent_form_team2["logo"] = (
            h2h.get(
                "team2_logo",
                ""
            )
        )

        # -------------------------------------------------------------------------
    # SECTION 14A-2: DEFAULT PAGE VALUES
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Initializes every page-level variable before any manual prediction,
    # live-feed update, reset, or tournament simulation occurs.
    #
    # These defaults prevent undefined-variable errors and guarantee that the
    # template always receives valid values.
    #
    # UPDATE THIS SECTION WHEN:
    # - Adding another live-feed value
    # - Adding another scoreboard field
    # - Adding another page-level variable
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # SECTION 14A-1A: MATCH CLOCK
    # -------------------------------------------------------------------------

    match_minute = 0
    match_extra_minute = 0

    # -------------------------------------------------------------------------
    # SECTION 14A-1B: MATCH STATUS
    # -------------------------------------------------------------------------

    match_status_short = "NS"
    match_status_long = "Not Started"

    # -------------------------------------------------------------------------
    # SECTION 14A-1C: TEAM LOGOS
    # -------------------------------------------------------------------------

    team1_logo = ""
    team2_logo = ""

    # -------------------------------------------------------------------------
    # SECTION 14A-1D: EVENT TIMELINE
    # -------------------------------------------------------------------------

    event_timeline = []

    # -------------------------------------------------------------------------
    # SECTION 14A-1E: STATUS MESSAGE
    # -------------------------------------------------------------------------

    message = ""

    # -------------------------------------------------------------------------
    # SECTION 14A-1F: LIVE-FEED DATA SOURCE
    # -------------------------------------------------------------------------
    # Possible values:
    #
    # ""
    #     No live-feed request has been made yet.
    #
    # "real"
    #     Fresh API-Football data was loaded.
    #
    # "cached"
    #     The API was unavailable, so the last successful real update
    #     was reused.
    #
    # "unavailable"
    #     No real data could be loaded and no cached data exists.
    # -------------------------------------------------------------------------

    data_source = ""

    # -------------------------------------------------------------------------
    # SECTION 14A-1G: CURRENT FORM ACTION
    # -------------------------------------------------------------------------

    action = request.form.get(
        "action",
        ""
    )

    # -------------------------------------------------------------------------
    # SECTION 14B: READ MANUAL MATCH STATISTICS
    # -------------------------------------------------------------------------
    # The additional fields use safe defaults, so the backend will still run
    # before the matching HTML inputs are added.
    # -------------------------------------------------------------------------

    if request.method == "POST":
        match_minute = get_integer_form_value(
            "match_minute",
            default=0,
            minimum=0,
            maximum=120
        )

        team1.goals = get_integer_form_value(
            "team1_goals"
        )

        team2.goals = get_integer_form_value(
            "team2_goals"
        )

        team1.yellow_cards = get_integer_form_value(
            "team1_yellow_cards"
        )

        team2.yellow_cards = get_integer_form_value(
            "team2_yellow_cards"
        )

        team1.red_cards = get_integer_form_value(
            "team1_red_cards"
        )

        team2.red_cards = get_integer_form_value(
            "team2_red_cards"
        )

        team1.shots = get_integer_form_value(
            "team1_total_shots"
        )

        team2.shots = get_integer_form_value(
            "team2_total_shots"
        )

        team1.shots_on_target = get_integer_form_value(
            "team1_shots"
        )

        team2.shots_on_target = get_integer_form_value(
            "team2_shots"
        )

        team1.big_chances = get_integer_form_value(
            "team1_big_chances"
        )

        team2.big_chances = get_integer_form_value(
            "team2_big_chances"
        )

        team1.defender_blocks = get_integer_form_value(
            "team1_defender_blocks"
        )

        team2.defender_blocks = get_integer_form_value(
            "team2_defender_blocks"
        )

        team1.goalkeeper_saves = get_integer_form_value(
            "team1_goalkeeper_saves"
        )

        team2.goalkeeper_saves = get_integer_form_value(
            "team2_goalkeeper_saves"
        )

        team1.corners = get_integer_form_value(
            "team1_corners"
        )

        team2.corners = get_integer_form_value(
            "team2_corners"
        )

        team1.possession = get_integer_form_value(
            "team1_possession",
            default=50,
            minimum=0,
            maximum=100
        )

        team2.possession = 100 - team1.possession

        # ---------------------------------------------------------------------
        # SECTION 14C: MANUAL PLAYER/EVENT MODIFIERS
        # ---------------------------------------------------------------------

        if (
            request.form.get("team1_bad_star")
            == "on"
        ):
            team1.add_modifier(
                "Star player is not playing well",
                team1.star_bad_game_penalty()
            )

        if (
            request.form.get("team2_bad_star")
            == "on"
        ):
            team2.add_modifier(
                "Star player is not playing well",
                team2.star_bad_game_penalty()
            )

        # ---------------------------------------------------------------------
        # SECTION 14D: LIVE-FEED UPDATE AND FULL MATCH RESET
        # ---------------------------------------------------------------------
        # PURPOSE:
        # Handles the two main match-control actions:
        #
        # 1. Load current match information from live_feed.py
        # 2. Reset the selected match back to its starting state
        #
        # LIVE-FEED UPDATE MAY CHANGE:
        # - Team logos
        # - Score
        # - Main elapsed minute
        # - Added/stoppage time
        # - Match status
        # - Possession
        # - Total shots
        # - Shots on target
        # - Big chances
        # - Blocked shots
        # - Goalkeeper saves
        # - Corners
        # - Yellow cards
        # - Red cards
        # - Event timeline
        # - Live player modifiers
        #
        # MATCH-STATUS EXAMPLES:
        # - 1H  = First Half
        # - HT  = Halftime
        # - 2H  = Second Half
        # - ET  = Extra Time
        # - BT  = Extra-Time Break
        # - PEN = Penalty Shootout
        # - AET = Finished After Extra Time
        # - FT  = Full Time
        #
        # RESET MATCH CLEARS:
        # - Match minute
        # - Added time
        # - Match status
        # - Goals
        # - Match statistics
        # - Cards
        # - Possession
        # - Player modifiers
        # - Event timeline
        # - Probability timeline
        #
        # IMPORTANT:
        # The currently selected teams remain selected after a reset.
        #
        # UPDATE THIS SECTION WHEN:
        # - Adding another live-feed statistic
        # - Adding another match-status value
        # - Adding another reset field
        # - Changing live-feed messages
        # ---------------------------------------------------------------------

                # ---------------------------------------------------------------------
        # SECTION 14D-0: REFRESH CACHED MATCH INSIGHTS
        # ---------------------------------------------------------------------
        # PURPOSE:
        # Refreshes H2H and recent-form data only when the user presses
        # Refresh Match Insights.
        #
        # Normal browser loads continue to use insights_cache.json and make
        # zero Match Insights API requests.
        # ---------------------------------------------------------------------

        if action == "refresh_insights":

            loaded_sections = []

            if h2h.get(
                "available",
                False
            ):
                loaded_sections.append(
                    "head-to-head"
                )

            if recent_form_team1.get(
                "available",
                False
            ):
                loaded_sections.append(
                    f"{team1.name} recent form"
                )

            if recent_form_team2.get(
                "available",
                False
            ):
                loaded_sections.append(
                    f"{team2.name} recent form"
                )

            if loaded_sections:

                message = (
                    "Match Insights refreshed and cached: "
                    + ", ".join(
                        loaded_sections
                    )
                    + "."
                )

            else:

                message = (
                    "Match Insights could not be refreshed. "
                    "No valid API data was returned, and any existing "
                    "cached information was preserved."
                )

        elif action == "live_feed":

            # -----------------------------------------------------------------
            # SECTION 14D-1: CREATE THE TEMPORARY LIVE MATCH
            # -----------------------------------------------------------------
            # Creates a temporary Match object using the currently selected
            # teams and the current match minute.
            #
            # live_feed.py updates this object directly.
            # -----------------------------------------------------------------

            live_match = Match(
                team1,
                team2,
                match_minute
            )

            # -----------------------------------------------------------------
            # SECTION 14D-2: APPLY LIVE DATA
            # -----------------------------------------------------------------
            # apply_live_data_to_match() returns:
            #
            # "real"
            #     Fresh API-Football data was loaded.
            #
            # "cached"
            #     The API was unavailable or the request limit was reached,
            #     so the last successful real match update was reused.
            #
            # "unavailable"
            #     No fresh real data was available and no cached real update
            #     exists for this matchup.
            #
            # IMPORTANT:
            # Demo data is no longer applied automatically.
            # -----------------------------------------------------------------

            data_source = apply_live_data_to_match(
                live_match
            )

            # -----------------------------------------------------------------
            # SECTION 14D-2A: SAVE FRESH HISTORICAL SNAPSHOT
            # -----------------------------------------------------------------
            # Only fresh real API data is saved.
            #
            # Cached and unavailable responses are ignored because they do not
            # represent a new live match state.
            # -----------------------------------------------------------------

            if data_source == "real":
                save_historical_snapshot(
                    live_match
                )

            # -----------------------------------------------------------------
            # SECTION 14D-3: COPY UPDATED TEAM OBJECTS
            # -----------------------------------------------------------------

            team1 = live_match.team1
            team2 = live_match.team2

            # -----------------------------------------------------------------
            # SECTION 14D-4: COPY LIVE MATCH CLOCK AND STATUS
            # -----------------------------------------------------------------
            # Examples:
            #
            # match_minute = 34
            # match_extra_minute = 0
            # match_status_short = "1H"
            #
            # Display:
            # 34'
            #
            # match_minute = 45
            # match_extra_minute = 3
            # match_status_short = "1H"
            #
            # Display:
            # 45+3'
            #
            # match_status_short = "HT"
            #
            # Display:
            # HT
            # -----------------------------------------------------------------

            if live_match.match_minute > 0:
                match_minute = (
                    live_match.match_minute
                )

            match_extra_minute = getattr(
                live_match,
                "match_extra_minute",
                0
            )

            match_status_short = getattr(
                live_match,
                "match_status_short",
                ""
            )

            match_status_long = getattr(
                live_match,
                "match_status_long",
                ""
            )

            # -----------------------------------------------------------------
            # SECTION 14D-5: COPY TEAM LOGOS
            # -----------------------------------------------------------------
            # The logo URLs are stored on the Match object by live_feed.py.
            # They are copied again to the final Match object in Section 14E.
            # -----------------------------------------------------------------

            team1_logo = getattr(
                live_match,
                "team1_logo",
                ""
            )

            team2_logo = getattr(
                live_match,
                "team2_logo",
                ""
            )

            # -----------------------------------------------------------------
            # SECTION 14D-6: COPY EVENT TIMELINE
            # -----------------------------------------------------------------

            event_timeline = getattr(
                live_match,
                "event_timeline",
                []
            )

            # -----------------------------------------------------------------
            # SECTION 14D-7: LIVE-FEED SOURCE MESSAGE
            # -----------------------------------------------------------------
            # PURPOSE:
            # Tells the user whether the page is displaying:
            #
            # - Fresh real API data
            # - The last successful cached real update
            # - No available live data
            #
            # IMPORTANT:
            # Demo data is no longer applied automatically when the live API
            # fails or the request limit is reached.
            # -----------------------------------------------------------------

            if data_source == "real":

                message = (
                    "Fresh Live AI match data loaded successfully."
                )

            elif data_source == "cached":

                message = (
                    "The live API is temporarily unavailable or the request "
                    "limit was reached. Showing the last successful real "
                    "match update."
                )

            else:

                message = (
                    "Live match data is currently unavailable. "
                    "The prediction shown is based on pre-match analysis. "
                    "until live statistics become available."
                )

        elif action == "reset_timeline":

            # -----------------------------------------------------------------
            # SECTION 14D-8: CLEAR WIN-PROBABILITY TIMELINE
            # -----------------------------------------------------------------

            session["probability_timeline"] = []
            session["match_chart_timeline"] = []

            session["timeline_match"] = (
                f"{team1.name}|{team2.name}"
            )

            # -----------------------------------------------------------------
            # SECTION 14D-9: RESET MATCH CLOCK AND STATUS
            # -----------------------------------------------------------------

            match_minute = 0
            match_extra_minute = 0

            match_status_short = ""
            match_status_long = ""

            # -----------------------------------------------------------------
            # SECTION 14D-10: RESET TEAM LOGOS
            # -----------------------------------------------------------------
            # Logos are cleared because they come from the live fixture.
            # They will be loaded again during the next successful live update.
            # -----------------------------------------------------------------

            team1_logo = ""
            team2_logo = ""

            # -----------------------------------------------------------------
            # SECTION 14D-11: RESET SCORE
            # -----------------------------------------------------------------

            team1.goals = 0
            team2.goals = 0

            # -----------------------------------------------------------------
            # SECTION 14D-12: RESET ATTACKING STATISTICS
            # -----------------------------------------------------------------

            team1.shots = 0
            team2.shots = 0

            team1.shots_on_target = 0
            team2.shots_on_target = 0

            team1.big_chances = 0
            team2.big_chances = 0

            team1.defender_blocks = 0
            team2.defender_blocks = 0

            team1.corners = 0
            team2.corners = 0

            # -----------------------------------------------------------------
            # SECTION 14D-13: RESET GOALKEEPER STATISTICS
            # -----------------------------------------------------------------

            team1.goalkeeper_saves = 0
            team2.goalkeeper_saves = 0

            # -----------------------------------------------------------------
            # SECTION 14D-14: RESET CARDS
            # -----------------------------------------------------------------

            team1.yellow_cards = 0
            team2.yellow_cards = 0

            team1.red_cards = 0
            team2.red_cards = 0

            # -----------------------------------------------------------------
            # SECTION 14D-15: RESET POSSESSION
            # -----------------------------------------------------------------

            team1.possession = 50
            team2.possession = 50

            # -----------------------------------------------------------------
            # SECTION 14D-16: RESET MANUAL AND LIVE MODIFIERS
            # -----------------------------------------------------------------

            team1.modifiers = []
            team2.modifiers = []

            # -----------------------------------------------------------------
            # SECTION 14D-17: RESET EVENT TIMELINE
            # -----------------------------------------------------------------

            event_timeline = []

            session.modified = True

            message = (
                "Match data, event timeline, and "
                "probability timeline reset."
            )


    # =========================================================================
    # SECTION 14E: CREATE FINAL MATCH AND RUN MODEL CALCULATIONS
    # =========================================================================
    # PURPOSE:
    # Creates the final Match object after all manual, live-feed, or reset
    # actions have been processed.
    #
    # The final Match object receives:
    # - Match minute
    # - Added time
    # - Match status
    # - Team logos
    # - Event timeline
    #
    # UPDATE THIS SECTION WHEN:
    # - Adding another Match attribute
    # - Adding another model calculation
    # =========================================================================

    match = Match(
        team1,
        team2,
        match_minute
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-1: COPY MATCH CLOCK AND STATUS
    # -------------------------------------------------------------------------

    match.match_extra_minute = (
        match_extra_minute
    )

    match.match_status_short = (
        match_status_short
    )

    match.match_status_long = (
        match_status_long
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-2: COPY TEAM LOGOS
    # -------------------------------------------------------------------------

    match.team1_logo = (
        team1_logo
    )

    match.team2_logo = (
        team2_logo
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-3: COPY EVENT TIMELINE
    # -------------------------------------------------------------------------

    match.event_timeline = (
        event_timeline
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-4: CALCULATE WIN, DRAW, AND LOSS PROBABILITIES
    # -------------------------------------------------------------------------

    (
        team1_probability,
        draw_probability,
        team2_probability,
        most_likely_score,
        top_scorelines
    ) = match.calculate_probabilities()

    probabilities = (
        team1_probability,
        draw_probability,
        team2_probability
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-5: CALCULATE PREDICTED OUTCOME
    # -------------------------------------------------------------------------

    (
        predicted_outcome_label,
        predicted_outcome_probability
    ) = match.predicted_outcome(
        probabilities
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-6: CALCULATE PREDICTION CONFIDENCE
    # -------------------------------------------------------------------------

    (
        confidence_score,
        confidence_level,
        confidence_class
    ) = match.prediction_confidence(
        probabilities
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-7: CALCULATE MATCH DIFFICULTY
    # -------------------------------------------------------------------------

    (
        difficulty_stars,
        difficulty_label
    ) = match.match_difficulty(
        probabilities
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-8: CALCULATE KNOCKOUT ADVANCEMENT
    # -------------------------------------------------------------------------

    (
        team1_advance_probability,
        team2_advance_probability
    ) = match.advancement_probabilities(
        probabilities
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-9: CALCULATE EXPECTED GOALS REMAINING
    # -------------------------------------------------------------------------

    (
        team1_expected_goals,
        team2_expected_goals
    ) = match.expected_goals()

    # -------------------------------------------------------------------------
    # SECTION 14E-10: CALCULATE LIVE MOMENTUM
    # -------------------------------------------------------------------------

    (
        team1_live_momentum,
        team2_live_momentum
    ) = match.live_momentum_percentages()

    # -------------------------------------------------------------------------
    # SECTION 14E-11: CALCULATE DANGEROUS ATTACKS
    # -------------------------------------------------------------------------

    team1_calculated_dangerous_attacks = (
        team1.calculated_dangerous_attacks(
            team2
        )
    )

    team2_calculated_dangerous_attacks = (
        team2.calculated_dangerous_attacks(
            team1
        )
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-12: CALCULATE ATTACK PRESSURE
    # -------------------------------------------------------------------------

    team1_attack_pressure = (
        team1.attack_pressure_score(
            team2
        )
    )

    team2_attack_pressure = (
        team2.attack_pressure_score(
            team1
        )
    )

    # -------------------------------------------------------------------------
    # SECTION 14E-13: BUILD PREDICTION REASONS
    # -------------------------------------------------------------------------

    reasons = match.reasoning_summary()


        # =========================================================================
    # SECTION 14F: UPDATE WIN-PROBABILITY HISTORY
    # =========================================================================
    # PURPOSE:
    # Stores probability changes after:
    #
    # - Manual match updates
    # - Fresh real API updates
    #
    # Cached or unavailable live-feed responses are not added because they do
    # not represent a new match state.
    #
    # Same-minute updates replace the latest entry instead of creating
    # duplicate minute rows.
    #
    # UPDATE THIS SECTION WHEN:
    # - Changing which actions create timeline entries
    # - Adding another live-data source
    # - Adding event labels to timeline entries
    # =========================================================================

    # -------------------------------------------------------------------------
    # SECTION 14F-1: DECIDE WHETHER THIS UPDATE SHOULD BE RECORDED
    # -------------------------------------------------------------------------

    should_record_timeline = (
        action == "manual"
        or (
            action == "live_feed"
            and data_source == "real"
        )
    )

    # -------------------------------------------------------------------------
    # SECTION 14F-2: ADD FRESH UPDATE TO THE TIMELINE
    # -------------------------------------------------------------------------

    if should_record_timeline:

        update_type = (
            "Live feed update"
            if action == "live_feed"
            else "Manual update"
        )

        add_timeline_entry(
            match,
            team1_probability,
            draw_probability,
            team2_probability,
            update_type
        )

    # -------------------------------------------------------------------------
    # SECTION 14F-3: LOAD THE SAVED TIMELINE
    # -------------------------------------------------------------------------

    probability_timeline = session.get(
        "probability_timeline",
        []
    )

    match_chart_timeline = session.get(
        "match_chart_timeline",
        []
    )


    # =========================================================================
    # SECTION 14G: OPTIONAL TOURNAMENT SIMULATION
    # =========================================================================
    # PURPOSE:
    # Runs the tournament simulator only when the matching button is pressed.
    # =========================================================================

    tournament_results = []
    tournament_champion = None
    tournament_simulations = 0
    most_common_final = None

    if action == "simulate_tournament":
        requested_simulations = get_integer_form_value(
            "simulation_count", default=10000, minimum=1000, maximum=50000
        )
        (
            tournament_results,
            tournament_champion,
            tournament_simulations,
            most_common_final
        ) = simulate_tournament(teams, requested_simulations)


    # =========================================================================
    # SECTION 14H: SEND ALL VALUES TO index.html
    # =========================================================================
    # PURPOSE:
    # Sends every backend value required by templates/index.html.
    #
    # THIS SECTION INCLUDES:
    # - Teams
    # - Team logos
    # - Score
    # - Match minute
    # - Added time
    # - Match status
    # - Probabilities
    # - Statistics
    # - Timelines
    # - Explanations
    #
    # UPDATE THIS SECTION WHEN:
    # - Adding a new value to the webpage
    # - Adding another live-feed field
    # - Adding another model result
    # =========================================================================

    return render_template(
        "index.html",

                # ---------------------------------------------------------------------
        # SECTION 14H-1: TEAM-SELECTION DATA
        # ---------------------------------------------------------------------

        teams=teams,
        team1=team1,
        team2=team2,

        # ---------------------------------------------------------------------
        # SECTION 14H-1A: PRE-MATCH INTELLIGENCE
        # ---------------------------------------------------------------------

        h2h=(
            h2h
        ),

        recent_form_team1=(
            recent_form_team1
        ),

        recent_form_team2=(
            recent_form_team2
        ),

        team1_ranking={
            "rank": team1.fifa_rank,
            "points": team1.fifa_points,
            "date": team1.ranking_date
        },

        team2_ranking={
            "rank": team2.fifa_rank,
            "points": team2.fifa_points,
            "date": team2.ranking_date
        },

        # ---------------------------------------------------------------------
        # SECTION 14H-2: TEAM LOGOS
        # ---------------------------------------------------------------------

        team1_logo=getattr(
            match,
            "team1_logo",
            ""
        ),

        team2_logo=getattr(
            match,
            "team2_logo",
            ""
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-3: LIVE SCORE, CLOCK, STATUS, AND DATA SOURCE
        # ---------------------------------------------------------------------

        match_minute=(
            match_minute
        ),

        match_extra_minute=(
            match_extra_minute
        ),

        match_status_short=(
            match_status_short
        ),

        match_status_long=(
            match_status_long
        ),

        # Tells index.html whether the current page is showing:
        # - Fresh real API data
        # - Cached real data
        # - No available live data
        # - The normal pre-match state
        data_source=(
            data_source
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-4: WIN PROBABILITY
        # ---------------------------------------------------------------------

        team1_probability=(
            team1_probability * 100
        ),

        draw_probability=(
            draw_probability * 100
        ),

        team2_probability=(
            team2_probability * 100
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-5: LIVE MOMENTUM
        # ---------------------------------------------------------------------

        team1_live_momentum=(
            team1_live_momentum
        ),

        team2_live_momentum=(
            team2_live_momentum
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-6: PREDICTED OUTCOME
        # ---------------------------------------------------------------------

        predicted_outcome_label=(
            predicted_outcome_label
        ),

        predicted_outcome_probability=(
            predicted_outcome_probability
            * 100
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-7: MOST LIKELY SCORES
        # ---------------------------------------------------------------------

        most_likely_score=(
            most_likely_score
        ),

        top_scorelines=(
            top_scorelines
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-8: PREDICTION CONFIDENCE
        # ---------------------------------------------------------------------

        confidence_score=(
            confidence_score
        ),

        confidence_level=(
            confidence_level
        ),

        confidence_class=(
            confidence_class
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-9: MATCH DIFFICULTY
        # ---------------------------------------------------------------------

        difficulty_stars=(
            difficulty_stars
        ),

        difficulty_label=(
            difficulty_label
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-10: KNOCKOUT ADVANCEMENT
        # ---------------------------------------------------------------------

        team1_advance_probability=(
            team1_advance_probability
            * 100
        ),

        team2_advance_probability=(
            team2_advance_probability
            * 100
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-11: EXPECTED GOALS REMAINING
        # ---------------------------------------------------------------------

        team1_expected_goals=(
            team1_expected_goals
        ),

        team2_expected_goals=(
            team2_expected_goals
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-12: CALCULATED DANGEROUS ATTACKS
        # ---------------------------------------------------------------------

        team1_calculated_dangerous_attacks=(
            team1_calculated_dangerous_attacks
        ),

        team2_calculated_dangerous_attacks=(
            team2_calculated_dangerous_attacks
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-13: ATTACK PRESSURE
        # ---------------------------------------------------------------------

        team1_attack_pressure=(
            team1_attack_pressure
        ),

        team2_attack_pressure=(
            team2_attack_pressure
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-14: MATCH STATISTICS
        # ---------------------------------------------------------------------

        team1_total_shots=(
            team1.shots
        ),

        team2_total_shots=(
            team2.shots
        ),

        team1_shots_on_target=(
            team1.shots_on_target
        ),

        team2_shots_on_target=(
            team2.shots_on_target
        ),

        team1_big_chances=(
            team1.big_chances
        ),

        team2_big_chances=(
            team2.big_chances
        ),

        team1_blocked_shots=(
            team1.defender_blocks
        ),

        team2_blocked_shots=(
            team2.defender_blocks
        ),

        team1_saves=(
            team1.goalkeeper_saves
        ),

        team2_saves=(
            team2.goalkeeper_saves
        ),

        team1_corners=(
            team1.corners
        ),

        team2_corners=(
            team2.corners
        ),

        team1_yellow_cards=(
            team1.yellow_cards
        ),

        team2_yellow_cards=(
            team2.yellow_cards
        ),

        team1_red_cards=(
            team1.red_cards
        ),

        team2_red_cards=(
            team2.red_cards
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-15: TIMELINES
        # ---------------------------------------------------------------------

        probability_timeline=(
            probability_timeline
        ),

        match_chart_timeline=(
            match_chart_timeline
        ),

        event_timeline=(
            event_timeline
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-16: TOURNAMENT SIMULATOR
        # ---------------------------------------------------------------------

        tournament_results=(
            tournament_results
        ),

        tournament_champion=(
            tournament_champion
        ),

        tournament_simulations=tournament_simulations,
        most_common_final=most_common_final,

        # ---------------------------------------------------------------------
        # SECTION 14H-17: EXPLANATION PANEL
        # ---------------------------------------------------------------------

        reasons=(
            reasons
        ),

        # ---------------------------------------------------------------------
        # SECTION 14H-18: STATUS MESSAGE
        # ---------------------------------------------------------------------

        message=(
            message
        )
    )


# =============================================================================
# SECTION 15: LOCAL DEVELOPMENT SERVER
# =============================================================================
# PURPOSE:
# Starts the Flask development server when app.py is run directly.
#
# NETWORK ACCESS:
# host="0.0.0.0" allows another device on the same Wi-Fi network to open the
# app using the Mac's local IP address.
#
# UPDATE THIS SECTION WHEN:
# - Changing the local development port
# - Disabling debug mode
# - Preparing deployment configuration
# =============================================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5050,
        debug=True
    )