# =============================================================================
# FILE: live_feed.py
# PROJECT: Road to the Final
# =============================================================================
# PURPOSE:
# Retrieves live football data from API-Football and applies it to the Match
# object used by app.py.
#
# THIS FILE CONTROLS:
# - Live score
# - Match minute
# - Possession
# - Total shots
# - Shots on target
# - Big chances
# - Blocked shots
# - Goalkeeper saves
# - Corners
# - Yellow and red cards
# - Event timeline
# - Last-successful real-data caching
# - Historical backtest snapshots
#
# MAINTENANCE GUIDE:
# Update only the numbered section related to the feature being changed.
#
# Example:
# - Change historical snapshot fields: SECTION 3
# - Add a new API statistic: SECTION 8
# - Change event timeline wording: SECTION 7
# - Change how values are copied to Match: SECTION 10
# =============================================================================


# =============================================================================
# SECTION 1: IMPORTS AND ENVIRONMENT CONFIGURATION
# =============================================================================
# PURPOSE:
# Loads the API key and required Python packages.
#
# UPDATE THIS SECTION WHEN:
# - Changing API provider
# - Adding logging
# - Adding caching or database support
# =============================================================================

import os

import requests
from dotenv import load_dotenv


load_dotenv(override=True)

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"


# =============================================================================
# SECTION 1A: LAST SUCCESSFUL REAL-DATA CACHE
# =============================================================================
# PURPOSE:
# Stores the latest successful real API response for each ordered matchup.
#
# This prevents the application from replacing a real live match with
# simulated data when:
# - The API request fails
# - The daily request limit is reached
# - The provider temporarily returns no fixture
#
# IMPORTANT:
# Cached values contain Team 1 and Team 2 fields, so the cache key must preserve
# the selected team order.
#
# This cache exists only while Flask is running.
# Restarting app.py clears it.
#
# UPDATE THIS SECTION WHEN:
# - Adding permanent storage
# - Adding cache timestamps
# - Adding cache expiration rules
# =============================================================================

LAST_REAL_DATA_CACHE = {}


def create_matchup_key(team1_name, team2_name):
    """
    Creates an order-specific cache key because cached dictionaries contain
    separate Team 1 and Team 2 values.

    Argentina vs England:
        argentina|england

    England vs Argentina:
        england|argentina
    """

    team1_key = (
        team1_name
        .strip()
        .lower()
    )

    team2_key = (
        team2_name
        .strip()
        .lower()
    )

    return f"{team1_key}|{team2_key}"


# =============================================================================
# SECTION 2: DEFAULT EMPTY LIVE DATA
# =============================================================================
# PURPOSE:
# Provides one complete data structure so every live-feed response contains
# all fields expected by app.py.
#
# MATCH CLOCK FIELDS:
# - match_minute:
#       Main elapsed minute, such as 34, 45, 90, or 105.
#
# - match_extra_minute:
#       Added/stoppage time, such as 3 for 45+3'.
#
# - match_status_short:
#       Short API status code, such as 1H, HT, 2H, ET, AET, PEN, or FT.
#
# - match_status_long:
#       Full API description, such as "Halftime" or "Match Finished".
#
# UPDATE THIS SECTION WHEN:
# - Adding a new live statistic
# - Adding another timeline field
# - Adding another match-status value
# =============================================================================

def empty_live_data():
    return {
        # ---------------------------------------------------------------------
        # MATCH CLOCK AND STATUS
        # ---------------------------------------------------------------------

        "match_minute": 0,
        "match_extra_minute": 0,

        "match_status_short": "",
        "match_status_long": "",

        # ---------------------------------------------------------------------
        # SCORE
        # ---------------------------------------------------------------------

        "team1_goals": 0,
        "team2_goals": 0,

        # ---------------------------------------------------------------------
        # TEAM LOGOS
        # ---------------------------------------------------------------------

        "team1_logo": "",
        "team2_logo": "",

        # ---------------------------------------------------------------------
        # POSSESSION
        # ---------------------------------------------------------------------

        "team1_possession": 50,

        # ---------------------------------------------------------------------
        # SHOTS
        # ---------------------------------------------------------------------

        "team1_total_shots": 0,
        "team2_total_shots": 0,

        "team1_shots_on_target": 0,
        "team2_shots_on_target": 0,

        "team1_big_chances": 0,
        "team2_big_chances": 0,

        "team1_defender_blocks": 0,
        "team2_defender_blocks": 0,

        # ---------------------------------------------------------------------
        # GOALKEEPER SAVES
        # ---------------------------------------------------------------------

        "team1_goalkeeper_saves": 0,
        "team2_goalkeeper_saves": 0,

        # ---------------------------------------------------------------------
        # CORNERS
        # ---------------------------------------------------------------------

        "team1_corners": 0,
        "team2_corners": 0,

        # ---------------------------------------------------------------------
        # CARDS
        # ---------------------------------------------------------------------

        "team1_yellow_cards": 0,
        "team2_yellow_cards": 0,

        "team1_red_cards": 0,
        "team2_red_cards": 0,

        # ---------------------------------------------------------------------
        # PLAYER-CONDITION FLAGS
        # ---------------------------------------------------------------------

        "team1_bad_star": False,
        "team2_bad_star": False,

        # ---------------------------------------------------------------------
        # EVENT TIMELINE
        # ---------------------------------------------------------------------

        "event_timeline": []
    }


# =============================================================================
# SECTION 3: HISTORICAL BACKTEST SNAPSHOTS
# =============================================================================
# PURPOSE:
# Applies a stored historical match snapshot to a Match object during
# backtesting.
#
# IMPORTANT:
# This section is separate from the production live-feed path.
#
# Production live mode uses only:
# 1. Fresh real API data
# 2. The latest cached real API data
# 3. "unavailable"
#
# Historical backtesting:
# - Never calls the real API
# - Never asks whether an old match is live now
# - Uses reproducible CSV snapshot values
#
# RECOMMENDED match_history.csv SNAPSHOT FIELDS:
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
# FINAL-RESULT FIELDS SHOULD BE KEPT SEPARATE:
# - actual_winner
# - final_team1_goals
# - final_team2_goals
#
# UPDATE THIS SECTION WHEN:
# - Adding another historical snapshot field
# - Changing default values
# - Changing the backtest CSV schema
# =============================================================================


def _row_int(row, field_name, default=0):
    """
    Safely converts a CSV row value to an integer.
    """

    value = row.get(
        field_name,
        default
    )

    if value is None:
        return default

    value_text = str(value).strip()

    if value_text == "":
        return default

    try:
        return int(float(value_text))

    except (TypeError, ValueError):
        return default


def _row_bool(row, field_name, default=False):
    """
    Safely converts common CSV Boolean values.
    """

    value = row.get(
        field_name
    )

    if value is None:
        return default

    value_text = str(value).strip().lower()

    if value_text == "":
        return default

    return value_text in {
        "true",
        "1",
        "yes",
        "y"
    }


def _row_text(row, field_name, default=""):
    """
    Safely reads a text value from a CSV row.
    """

    value = row.get(
        field_name,
        default
    )

    if value is None:
        return default

    return str(value).strip()


def apply_historical_row_to_match(match, row):
    """
    Applies one historical snapshot row to a Match object.

    Returns:
        "historical"

    IMPORTANT:
    Snapshot goals are intentionally separate from final-result goals so the
    backtest does not accidentally leak the completed match result into the
    prediction.
    """

    # -------------------------------------------------------------------------
    # SECTION 3A: SNAPSHOT CLOCK AND STATUS
    # -------------------------------------------------------------------------

    match.match_minute = max(
        0,
        min(
            _row_int(
                row,
                "snapshot_minute",
                default=0
            ),
            120
        )
    )

    match.match_extra_minute = max(
        0,
        _row_int(
            row,
            "snapshot_extra_minute",
            default=0
        )
    )

    match.match_status_short = _row_text(
        row,
        "match_status_short",
        default=""
    ).upper()

    match.match_status_long = _row_text(
        row,
        "match_status_long",
        default=""
    )

    # -------------------------------------------------------------------------
    # SECTION 3B: SNAPSHOT SCORE
    # -------------------------------------------------------------------------

    match.team1.goals = _row_int(
        row,
        "snapshot_team1_goals",
        default=0
    )

    match.team2.goals = _row_int(
        row,
        "snapshot_team2_goals",
        default=0
    )

    # -------------------------------------------------------------------------
    # SECTION 3C: POSSESSION
    # -------------------------------------------------------------------------

    team1_possession = _row_int(
        row,
        "team1_possession",
        default=50
    )

    team2_possession_value = row.get(
        "team2_possession"
    )

    if (
        team2_possession_value is None
        or str(team2_possession_value).strip() == ""
    ):
        team2_possession = 100 - team1_possession

    else:
        team2_possession = _row_int(
            row,
            "team2_possession",
            default=50
        )

    match.team1.possession = max(
        0,
        min(team1_possession, 100)
    )

    match.team2.possession = max(
        0,
        min(team2_possession, 100)
    )

    # -------------------------------------------------------------------------
    # SECTION 3D: ATTACKING STATISTICS
    # -------------------------------------------------------------------------

    match.team1.shots = _row_int(
        row,
        "team1_total_shots"
    )

    match.team2.shots = _row_int(
        row,
        "team2_total_shots"
    )

    match.team1.shots_on_target = _row_int(
        row,
        "team1_shots_on_target"
    )

    match.team2.shots_on_target = _row_int(
        row,
        "team2_shots_on_target"
    )

    # Total shots can never be lower than shots on target.
    match.team1.shots = max(
        match.team1.shots,
        match.team1.shots_on_target
    )

    match.team2.shots = max(
        match.team2.shots,
        match.team2.shots_on_target
    )

    match.team1.big_chances = _row_int(
        row,
        "team1_big_chances"
    )

    match.team2.big_chances = _row_int(
        row,
        "team2_big_chances"
    )

    match.team1.defender_blocks = _row_int(
        row,
        "team1_defender_blocks"
    )

    match.team2.defender_blocks = _row_int(
        row,
        "team2_defender_blocks"
    )

    match.team1.corners = _row_int(
        row,
        "team1_corners"
    )

    match.team2.corners = _row_int(
        row,
        "team2_corners"
    )

    # -------------------------------------------------------------------------
    # SECTION 3E: GOALKEEPER STATISTICS
    # -------------------------------------------------------------------------

    match.team1.goalkeeper_saves = _row_int(
        row,
        "team1_goalkeeper_saves"
    )

    match.team2.goalkeeper_saves = _row_int(
        row,
        "team2_goalkeeper_saves"
    )

    # -------------------------------------------------------------------------
    # SECTION 3F: CARDS
    # -------------------------------------------------------------------------

    match.team1.yellow_cards = _row_int(
        row,
        "team1_yellow_cards"
    )

    match.team2.yellow_cards = _row_int(
        row,
        "team2_yellow_cards"
    )

    match.team1.red_cards = _row_int(
        row,
        "team1_red_cards"
    )

    match.team2.red_cards = _row_int(
        row,
        "team2_red_cards"
    )

    # -------------------------------------------------------------------------
    # SECTION 3G: HISTORICAL PLAYER MODIFIERS
    # -------------------------------------------------------------------------

    if _row_bool(
        row,
        "team1_bad_star"
    ):
        match.team1.add_modifier(
            "Star player is not playing well "
            "(historical snapshot)",
            match.team1.star_bad_game_penalty()
        )

    if _row_bool(
        row,
        "team2_bad_star"
    ):
        match.team2.add_modifier(
            "Star player is not playing well "
            "(historical snapshot)",
            match.team2.star_bad_game_penalty()
        )

    return "historical"


# =============================================================================
# SECTION 4: API REQUEST HELPER AND DIAGNOSTICS
# =============================================================================
# PURPOSE:
# Sends safe GET requests to API-Football and prints enough information to
# determine why real live data is not being returned.
#
# THIS SECTION CHECKS:
# - Whether the API key loaded successfully
# - HTTP response status
# - API-reported errors
# - Number of returned results
# - Remaining API requests
#
# SECURITY:
# The API key itself is never printed.
#
# UPDATE THIS SECTION WHEN:
# - Adding request retries
# - Adding caching
# - Changing API authentication
# - Removing temporary diagnostic output
# =============================================================================

def api_get(endpoint, params=None):
    # -------------------------------------------------------------------------
    # SECTION 4A: VERIFY THAT THE API KEY LOADED
    # -------------------------------------------------------------------------

    if not API_KEY:
        print("\n==================================================")
        print("API-FOOTBALL ERROR")
        print("API_FOOTBALL_KEY was not loaded from .env.")
        print("Cached real data will be used if available; otherwise the match will remain unchanged.")
        print("==================================================")

        return None

    print("\n==================================================")
    print("API-FOOTBALL REQUEST")
    print("API key loaded: Yes")
    print("Endpoint:", endpoint)
    print("Parameters:", params)
    print("==================================================")

    headers = {
        "x-apisports-key": API_KEY
    }

    try:
        # ---------------------------------------------------------------------
        # SECTION 4B: SEND THE REQUEST
        # ---------------------------------------------------------------------

        response = requests.get(
            BASE_URL + endpoint,
            headers=headers,
            params=params,
            timeout=15
        )

        print("HTTP status code:", response.status_code)

        # API-Football may also return request-limit information
        # in the response headers.
        remaining_requests = response.headers.get(
            "x-ratelimit-requests-remaining"
        )

        daily_remaining = response.headers.get(
            "x-ratelimit-remaining"
        )

        if remaining_requests is not None:
            print(
                "Requests remaining:",
                remaining_requests
            )

        if daily_remaining is not None:
            print(
                "Daily requests remaining:",
                daily_remaining
            )

        # ---------------------------------------------------------------------
        # SECTION 4C: HANDLE HTTP ERRORS
        # ---------------------------------------------------------------------

        if response.status_code != 200:
            print("\nAPI HTTP ERROR")
            print("Response body:")
            print(response.text)
            print("Cached real data will be used if available; otherwise the match will remain unchanged.")

            return None

        # ---------------------------------------------------------------------
        # SECTION 4D: READ AND INSPECT THE JSON RESPONSE
        # ---------------------------------------------------------------------

        try:
            data = response.json()

        except ValueError:
            print("\nAPI RESPONSE ERROR")
            print("The response was not valid JSON.")
            print("Response body:")
            print(response.text)

            return None

        api_errors = data.get(
            "errors",
            {}
        )

        api_results = data.get(
            "results",
            0
        )

        api_response = data.get(
            "response",
            []
        )

        print("API errors:", api_errors)
        print("API result count:", api_results)
        print(
            "Returned response items:",
            len(api_response)
        )

        # Some API errors are returned inside a successful HTTP 200 response.
        if api_errors:
            print("\nAPI-FOOTBALL REPORTED AN ERROR")
            print(api_errors)
            print("Cached real data will be used if available; otherwise the match will remain unchanged.")

            return None

        return data

    except requests.exceptions.Timeout:
        print("\nAPI REQUEST TIMED OUT")
        print("Cached real data will be used if available; otherwise the match will remain unchanged.")

        return None

    except requests.exceptions.ConnectionError as error:
        print("\nAPI CONNECTION ERROR")
        print(error)
        print("Cached real data will be used if available; otherwise the match will remain unchanged.")

        return None

    except requests.exceptions.RequestException as error:
        print("\nAPI REQUEST ERROR")
        print(error)
        print("Cached real data will be used if available; otherwise the match will remain unchanged.")

        return None

# =============================================================================
# SECTION 5: FIND THE SELECTED LIVE FIXTURE
# =============================================================================
# PURPOSE:
# Searches all fixtures currently marked live by API-Football and finds the
# matchup selected in the application.
#
# THIS SECTION PRINTS:
# - The selected matchup
# - Every live matchup returned by the API
# - Whether a matching fixture was found
#
# UPDATE THIS SECTION WHEN:
# - Supporting scheduled fixtures
# - Supporting recently completed fixtures
# - Adding team-ID matching
# - Improving aliases for national-team names
# =============================================================================

def normalize_team_name(team_name):
    """
    Converts team names into a simplified form for safer comparison.

    Example:
    "United States" becomes "unitedstates".
    """

    return "".join(
        character
        for character in team_name.lower()
        if character.isalnum()
    )


def team_names_match(selected_name, api_name):
    """
    Compares a selected team name with the name returned by API-Football.

    Exact normalized matches are preferred, but partial matching is allowed
    for API names that may include additional words.
    """

    selected_key = normalize_team_name(
        selected_name
    )

    api_key = normalize_team_name(
        api_name
    )

    if not selected_key or not api_key:
        return False

    return (
        selected_key == api_key
        or selected_key in api_key
        or api_key in selected_key
    )


def find_live_fixture(team1_name, team2_name):
    # -------------------------------------------------------------------------
    # SECTION 5A: REQUEST ALL CURRENT LIVE FIXTURES
    # -------------------------------------------------------------------------

    data = api_get(
        "/fixtures",
        {
            "live": "all"
        }
    )

    if data is None:
        print(
            "\nThe live-fixture request failed."
        )

        return None

    fixtures = data.get(
        "response",
        []
    )

    print("\n==================================================")
    print("SELECTED MATCHUP")
    print(
        f"{team1_name} vs {team2_name}"
    )
    print("==================================================")

    print("\nLIVE FIXTURES RETURNED BY API:")

    if not fixtures:
        print("No live fixtures were returned.")

        return None

    # -------------------------------------------------------------------------
    # SECTION 5B: DISPLAY AND CHECK EACH LIVE FIXTURE
    # -------------------------------------------------------------------------

    for fixture_data in fixtures:
        home_team = (
            fixture_data
            .get("teams", {})
            .get("home", {})
            .get("name", "")
        )

        away_team = (
            fixture_data
            .get("teams", {})
            .get("away", {})
            .get("name", "")
        )

        fixture_information = fixture_data.get(
            "fixture",
            {}
        )

        fixture_id = fixture_information.get(
            "id"
        )

        fixture_status = (
            fixture_information
            .get("status", {})
            .get("short", "")
        )

        fixture_minute = (
            fixture_information
            .get("status", {})
            .get("elapsed")
        )

        print(
            f"- ID {fixture_id}: "
            f"{home_team} vs {away_team} "
            f"| Status: {fixture_status} "
            f"| Minute: {fixture_minute}"
        )

        normal_order = (
            team_names_match(
                team1_name,
                home_team
            )
            and team_names_match(
                team2_name,
                away_team
            )
        )

        reverse_order = (
            team_names_match(
                team1_name,
                away_team
            )
            and team_names_match(
                team2_name,
                home_team
            )
        )

        if normal_order or reverse_order:
            print("\nMATCHING LIVE FIXTURE FOUND")
            print(
                f"{home_team} vs {away_team}"
            )
            print(
                "Fixture ID:",
                fixture_id
            )

            return fixture_data

    print("\nNO MATCHING LIVE FIXTURE FOUND")
    print(
        "The API returned live fixtures, but none matched "
        f"{team1_name} vs {team2_name}."
    )

    return None


# =============================================================================
# SECTION 6: FIXTURE STATISTICS AND EVENT REQUESTS
# =============================================================================
# PURPOSE:
# Retrieves the two additional API resources needed by the dashboard.
#
# UPDATE THIS SECTION WHEN:
# - Adding lineups
# - Adding player statistics
# - Adding ball-position data from another provider
# =============================================================================

def get_fixture_statistics(fixture_id):
    data = api_get(
        "/fixtures/statistics",
        {"fixture": fixture_id}
    )

    if data is None:
        return None

    return data.get("response", [])


def get_fixture_events(fixture_id):
    data = api_get(
        "/fixtures/events",
        {"fixture": fixture_id}
    )

    if data is None:
        return None

    return data.get("response", [])


# =============================================================================
# SECTION 7: EVENT TIMELINE PROCESSING
# =============================================================================
# PURPOSE:
# Converts raw API events into a small, display-friendly timeline.
#
# CURRENT DISPLAYED EVENTS:
# - Goals
# - Cards
# - Substitutions
# - VAR events
#
# UPDATE THIS SECTION WHEN:
# - Adding shots or big chances from a different data provider
# - Changing event labels or icons
# =============================================================================

def classify_event(event):
    event_type = str(event.get("type", "")).strip()
    event_detail = str(event.get("detail", "")).strip()

    combined = f"{event_type} {event_detail}".lower()

    if event_type.lower() == "goal":
        return "Goal"

    if event_type.lower() == "card":
        if "red" in combined:
            return "Red card"
        return "Yellow card"

    if event_type.lower() == "subst":
        return "Substitution"

    if event_type.lower() == "var":
        return "VAR"

    return event_detail or event_type or "Match event"


def format_event_detail(event):
    player_name = (
        event
        .get("player", {})
        .get("name", "")
    )

    assist_name = (
        event
        .get("assist", {})
        .get("name", "")
    )

    event_label = classify_event(event)

    detail_parts = []

    if player_name:
        detail_parts.append(player_name)

    detail_parts.append(event_label)

    if assist_name and event_label == "Goal":
        detail_parts.append(f"Assist: {assist_name}")

    return " · ".join(detail_parts)


def build_event_timeline(events):
    timeline = []

    for event in events:
        event_time = event.get("time", {})
        minute = event_time.get("elapsed") or 0
        extra = event_time.get("extra")

        if extra:
            minute_label = f"{minute}+{extra}"
        else:
            minute_label = str(minute)

        team_name = (
            event
            .get("team", {})
            .get("name", "")
        )

        timeline.append(
            {
                "minute": minute_label,
                "team": team_name or "Match",
                "type": classify_event(event),
                "detail": format_event_detail(event)
            }
        )

    timeline.sort(
        key=lambda item: (
            int(str(item["minute"]).split("+")[0]),
            int(str(item["minute"]).split("+")[1])
            if "+" in str(item["minute"])
            else 0
        )
    )

    return timeline[-20:]


def count_cards(events, team_name):
    yellow_cards = 0
    red_cards = 0

    for event in events:
        event_team = (
            event
            .get("team", {})
            .get("name", "")
        )

        if team_name.lower() not in event_team.lower():
            continue

        event_type = str(event.get("type", ""))
        event_detail = str(event.get("detail", ""))
        combined = f"{event_type} {event_detail}".lower()

        if event_type.lower() != "card":
            continue

        if "red" in combined:
            red_cards += 1
        elif "yellow" in combined:
            yellow_cards += 1

    return yellow_cards, red_cards


# =============================================================================
# SECTION 8: STATISTIC EXTRACTION
# =============================================================================
# PURPOSE:
# Safely reads one named statistic from API-Football's response.
#
# UPDATE THIS SECTION WHEN:
# - API statistic labels change
# - Decimal values need to be preserved
# =============================================================================

def extract_stat(team_stats, stat_name):
    for stat in team_stats:
        current_type = str(
            stat.get("type", "")
        )

        if current_type.lower() != stat_name.lower():
            continue

        value = stat.get("value")

        if value is None:
            return 0

        if isinstance(value, str):
            cleaned_value = (
                value
                .replace("%", "")
                .strip()
            )

            try:
                return int(float(cleaned_value))

            except ValueError:
                return 0

        try:
            return int(value)

        except (TypeError, ValueError):
            return 0

    return 0


# =============================================================================
# SECTION 9: BUILD COMPLETE REAL LIVE DATA
# =============================================================================
# PURPOSE:
# Combines fixture, statistics, team-logo, and event responses into the exact
# dictionary expected by app.py.
#
# THIS SECTION PROVIDES:
# - Match minute
# - Team names
# - Team logos
# - Score
# - Possession
# - Total shots
# - Shots on target
# - Big chances
# - Blocked shots
# - Goalkeeper saves
# - Corners
# - Yellow and red cards
# - Event timeline
#
# UPDATE THIS SECTION WHEN:
# - Adding a new API statistic
# - Adding provider-specific xG
# - Adding recent momentum windows
# - Changing team-logo behavior
# =============================================================================

def get_real_live_data(team1_name, team2_name):
    fixture = find_live_fixture(
        team1_name,
        team2_name
    )

    if fixture is None:
        print(
            "\nNo live API match found for this matchup."
        )
        return None

    # -------------------------------------------------------------------------
    # SECTION 9A: FIXTURE INFORMATION, MATCH CLOCK, AND STATUS
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Reads the API-Football fixture information including:
    #
    # - Match minute
    # - Added (stoppage) time
    # - Match status
    #
    # EXAMPLES:
    #
    # 1H  -> First Half
    # HT  -> Halftime
    # 2H  -> Second Half
    # ET  -> Extra Time
    # PEN -> Penalty Shootout
    # AET -> After Extra Time
    # FT  -> Full Time
    #
    # UPDATE THIS SECTION WHEN:
    # - Adding kickoff status
    # - Adding postponed/cancelled support
    # - Adding penalty-shootout logic
    # -------------------------------------------------------------------------

    fixture_information = fixture.get(
        "fixture",
        {}
    )

    fixture_id = fixture_information.get(
        "id"
    )

    if fixture_id is None:
        return None

    status = fixture_information.get(
        "status",
        {}
    )

    # Main elapsed minute (45, 90, etc.)
    match_minute = (
        status.get("elapsed")
        or 0
    )

    # Added/stoppage time (45+3, 90+6, etc.)
    match_extra_minute = (
        status.get("extra")
        or 0
    )

    # Short API status
    # Examples:
    # 1H, HT, 2H, ET, PEN, FT
    match_status_short = str(
        status.get(
            "short",
            ""
        )
        or ""
    ).upper()

    # Long API status
    # Examples:
    # "First Half"
    # "Halftime"
    # "Match Finished"
    match_status_long = str(
        status.get(
            "long",
            ""
        )
        or ""
    )

    # -------------------------------------------------------------------------
    # SECTION 9B: TEAM NAMES AND LOGOS
    # -------------------------------------------------------------------------

    home_team_data = (
        fixture
        .get("teams", {})
        .get("home", {})
    )

    away_team_data = (
        fixture
        .get("teams", {})
        .get("away", {})
    )

    home_team = home_team_data.get(
        "name",
        ""
    )

    away_team = away_team_data.get(
        "name",
        ""
    )

    home_logo = home_team_data.get(
        "logo",
        ""
    )

    away_logo = away_team_data.get(
        "logo",
        ""
    )

    # -------------------------------------------------------------------------
    # SECTION 9C: CURRENT SCORE
    # -------------------------------------------------------------------------

    home_goals = (
        fixture
        .get("goals", {})
        .get("home")
        or 0
    )

    away_goals = (
        fixture
        .get("goals", {})
        .get("away")
        or 0
    )

    # -------------------------------------------------------------------------
    # SECTION 9D: REQUEST STATISTICS AND EVENTS
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Requests the current fixture statistics and event timeline from
    # API-Football.
    #
    # TEMPORARY DEBUGGING:
    # Prints every statistic label and value returned by the API.
    #
    # This helps confirm the exact fields used for:
    # - Ball possession
    # - Corner kicks
    # - Total shots
    # - Shots on target
    # - Blocked shots
    # - Goalkeeper saves
    #
    # REMOVE THE DEBUG PRINT BLOCK:
    # After possession and corners are confirmed to work correctly.
    # -------------------------------------------------------------------------

    statistics = get_fixture_statistics(
        fixture_id
    )

    events = get_fixture_events(
        fixture_id
    )

    # -------------------------------------------------------------------------
    # SECTION 9D-1: VALIDATE API RESPONSES
    # -------------------------------------------------------------------------
    # Stop building the live-data dictionary if either request failed.
    # Empty lists are allowed because some fixtures may not have events yet.
    # -------------------------------------------------------------------------

    if statistics is None or events is None:
        print(
            "\nStatistics or event data could not be loaded."
        )
        return None

    # -------------------------------------------------------------------------
    # SECTION 9D-2: PRINT RAW STATISTICS FOR DEBUGGING
    # -------------------------------------------------------------------------

    print(
        "\n=================================================="
    )
    print(
        "RAW FIXTURE STATISTICS"
    )
    print(
        "=================================================="
    )

    if not statistics:
        print(
            "The API returned no fixture statistics."
        )

    for team_statistics in statistics:

        statistics_team_name = (
            team_statistics
            .get("team", {})
            .get("name", "Unknown Team")
        )

        print(
            f"\nTEAM: {statistics_team_name}"
        )

        current_statistics = (
            team_statistics
            .get("statistics", [])
        )

        if not current_statistics:
            print(
                "No statistics were returned for this team."
            )

        for statistic in current_statistics:

            statistic_type = statistic.get(
                "type",
                "Unknown Statistic"
            )

            statistic_value = statistic.get(
                "value"
            )

            print(
                f"{statistic_type} -> {statistic_value}"
            )

        print(
            "--------------------------------------------------"
        )

    print(
        "==================================================\n"
    )

    # -------------------------------------------------------------------------
    # SECTION 9D-3: PREPARE HOME AND AWAY STATISTIC LISTS
    # -------------------------------------------------------------------------
    # These lists are populated in the next section after matching the team
    # names returned by the statistics endpoint.
    # -------------------------------------------------------------------------

    home_stats = []
    away_stats = []
    

    # -------------------------------------------------------------------------
    # SECTION 9E: MATCH STATISTICS TO HOME AND AWAY TEAMS
    # -------------------------------------------------------------------------

    for team_statistics in statistics:
        statistics_team_name = (
            team_statistics
            .get("team", {})
            .get("name", "")
        )

        current_statistics = (
            team_statistics
            .get("statistics", [])
        )

        if home_team.lower() in statistics_team_name.lower():
            home_stats = current_statistics

        elif away_team.lower() in statistics_team_name.lower():
            away_stats = current_statistics

    # -------------------------------------------------------------------------
    # SECTION 9F: COUNT CARDS FROM EVENT DATA
    # -------------------------------------------------------------------------

    home_yellow_cards, home_red_cards = count_cards(
        events,
        home_team
    )

    away_yellow_cards, away_red_cards = count_cards(
        events,
        away_team
    )

    # -------------------------------------------------------------------------
    # SECTION 9G: BUILD HOME-TEAM STATISTICS
    # -------------------------------------------------------------------------

    home_values = {
        "goals": home_goals,

        "possession": extract_stat(
            home_stats,
            "Ball Possession"
        ),

        "total_shots": extract_stat(
            home_stats,
            "Total Shots"
        ),

        "shots_on_target": extract_stat(
            home_stats,
            "Shots on Goal"
        ),

        "blocked_shots": extract_stat(
            home_stats,
            "Blocked Shots"
        ),

        "goalkeeper_saves": extract_stat(
            home_stats,
            "Goalkeeper Saves"
        ),

        "corners": extract_stat(
            home_stats,
            "Corner Kicks"
        ),

        "yellow_cards": home_yellow_cards,
        "red_cards": home_red_cards
    }

    # -------------------------------------------------------------------------
    # SECTION 9H: BUILD AWAY-TEAM STATISTICS
    # -------------------------------------------------------------------------

    away_values = {
        "goals": away_goals,

        "possession": extract_stat(
            away_stats,
            "Ball Possession"
        ),

        "total_shots": extract_stat(
            away_stats,
            "Total Shots"
        ),

        "shots_on_target": extract_stat(
            away_stats,
            "Shots on Goal"
        ),

        "blocked_shots": extract_stat(
            away_stats,
            "Blocked Shots"
        ),

        "goalkeeper_saves": extract_stat(
            away_stats,
            "Goalkeeper Saves"
        ),

        "corners": extract_stat(
            away_stats,
            "Corner Kicks"
        ),

        "yellow_cards": away_yellow_cards,
        "red_cards": away_red_cards
    }

    # API-Football does not provide a reliable standard Big Chances field.
    home_values["big_chances"] = 0
    away_values["big_chances"] = 0

    # -------------------------------------------------------------------------
    # SECTION 9I: MAP HOME/AWAY VALUES TO TEAM 1 AND TEAM 2
    # -------------------------------------------------------------------------

    team1_is_home = (
        team_names_match(
            team1_name,
            home_team
        )
    )

    team1_values = (
        home_values
        if team1_is_home
        else away_values
    )

    team2_values = (
        away_values
        if team1_is_home
        else home_values
    )

    team1_logo = (
        home_logo
        if team1_is_home
        else away_logo
    )

    team2_logo = (
        away_logo
        if team1_is_home
        else home_logo
    )

    team1_possession = team1_values[
        "possession"
    ]

    if team1_possession == 0:
        team1_possession = 50

    # -------------------------------------------------------------------------
    # SECTION 9J: RETURN COMPLETE LIVE DATA
    # -------------------------------------------------------------------------
    # PURPOSE:
    # Returns one complete dictionary containing every live-feed value needed
    # by app.py.
    #
    # THIS SECTION NOW INCLUDES:
    # - Main match minute
    # - Added/stoppage time
    # - Short match-status code
    # - Long match-status description
    #
    # EXAMPLES:
    # - match_minute = 45
    # - match_extra_minute = 3
    # - match_status_short = "1H"
    # - match_status_long = "First Half"
    #
    # UPDATE THIS SECTION WHEN:
    # - Adding a new live-feed field
    # - Adding another match-status value
    # - Adding another team statistic
    # -------------------------------------------------------------------------

    return {
        # ---------------------------------------------------------------------
        # MATCH CLOCK AND STATUS
        # ---------------------------------------------------------------------

        "match_minute": match_minute,

        "match_extra_minute": (
            match_extra_minute
        ),

        "match_status_short": (
            match_status_short
        ),

        "match_status_long": (
            match_status_long
        ),

        # ---------------------------------------------------------------------
        # TEAM LOGOS
        # ---------------------------------------------------------------------

        "team1_logo": team1_logo,
        "team2_logo": team2_logo,

        # ---------------------------------------------------------------------
        # SCORE
        # ---------------------------------------------------------------------

        "team1_goals": (
            team1_values["goals"]
        ),

        "team2_goals": (
            team2_values["goals"]
        ),

        # ---------------------------------------------------------------------
        # POSSESSION
        # ---------------------------------------------------------------------

        "team1_possession": (
            team1_possession
        ),

        # ---------------------------------------------------------------------
        # TOTAL SHOTS
        # ---------------------------------------------------------------------

        "team1_total_shots": (
            team1_values["total_shots"]
        ),

        "team2_total_shots": (
            team2_values["total_shots"]
        ),

        # ---------------------------------------------------------------------
        # SHOTS ON TARGET
        # ---------------------------------------------------------------------

        "team1_shots_on_target": (
            team1_values["shots_on_target"]
        ),

        "team2_shots_on_target": (
            team2_values["shots_on_target"]
        ),

        # ---------------------------------------------------------------------
        # BIG CHANCES
        # ---------------------------------------------------------------------

        "team1_big_chances": (
            team1_values["big_chances"]
        ),

        "team2_big_chances": (
            team2_values["big_chances"]
        ),

        # ---------------------------------------------------------------------
        # BLOCKED SHOTS
        # ---------------------------------------------------------------------

        "team1_defender_blocks": (
            team1_values["blocked_shots"]
        ),

        "team2_defender_blocks": (
            team2_values["blocked_shots"]
        ),

        # ---------------------------------------------------------------------
        # GOALKEEPER SAVES
        # ---------------------------------------------------------------------

        "team1_goalkeeper_saves": (
            team1_values["goalkeeper_saves"]
        ),

        "team2_goalkeeper_saves": (
            team2_values["goalkeeper_saves"]
        ),

        # ---------------------------------------------------------------------
        # CORNERS
        # ---------------------------------------------------------------------

        "team1_corners": (
            team1_values["corners"]
        ),

        "team2_corners": (
            team2_values["corners"]
        ),

        # ---------------------------------------------------------------------
        # CARDS
        # ---------------------------------------------------------------------

        "team1_yellow_cards": (
            team1_values["yellow_cards"]
        ),

        "team2_yellow_cards": (
            team2_values["yellow_cards"]
        ),

        "team1_red_cards": (
            team1_values["red_cards"]
        ),

        "team2_red_cards": (
            team2_values["red_cards"]
        ),

        # ---------------------------------------------------------------------
        # PLAYER-CONDITION FLAGS
        # ---------------------------------------------------------------------
        # API-Football does not provide a reliable star-player performance
        # flag, so these remain False unless another player-rating source is
        # added later.
        # ---------------------------------------------------------------------

        "team1_bad_star": False,
        "team2_bad_star": False,

        # ---------------------------------------------------------------------
        # EVENT TIMELINE
        # ---------------------------------------------------------------------

        "event_timeline": (
            build_event_timeline(events)
        )
    }


# =============================================================================
# SECTION 10: APPLY LIVE DATA TO THE MATCH OBJECT
# =============================================================================
# PURPOSE:
# Applies fresh real API data or the latest successfully cached real data to
# the Team and Match objects used by app.py.
#
# RETURN VALUES:
# - "real"
#       A fresh real API response was successfully loaded.
#
# - "cached"
#       The API failed, the request limit was reached, or no current fixture
#       response was available, so the last successful real response was reused.
#
# - "unavailable"
#       No fresh response was available and no earlier real response had been
#       saved for this matchup.
#
# IMPORTANT:
# Demo data is no longer applied automatically from the live-feed button.
# This prevents simulated data from contaminating a real match and its
# probability timeline.
#
# THIS SECTION COPIES:
# - Match minute
# - Added/stoppage time
# - Match status
# - Event timeline
# - Team logos
# - Score
# - Possession
# - Total shots
# - Shots on target
# - Big chances
# - Blocked shots
# - Corners
# - Goalkeeper saves
# - Yellow and red cards
# - Live player modifiers
#
# UPDATE THIS SECTION WHEN:
# - Adding a new Team property
# - Adding a new Match property
# - Adding persistent caching
# - Adding an explicit demo-mode button
# - Adding cache timestamps
# =============================================================================

def apply_live_data_to_match(match):

    # -------------------------------------------------------------------------
    # SECTION 10A: CREATE MATCHUP CACHE KEY
    # -------------------------------------------------------------------------
    # The same key is used regardless of which team is selected as Team 1.
    #
    # Example:
    # England vs Argentina
    # Argentina vs England
    #
    # Both become:
    # argentina|england
    # -------------------------------------------------------------------------

    matchup_key = create_matchup_key(
        match.team1.name,
        match.team2.name
    )

    # -------------------------------------------------------------------------
    # SECTION 10B: REQUEST FRESH REAL API DATA
    # -------------------------------------------------------------------------

    data = get_real_live_data(
        match.team1.name,
        match.team2.name
    )

    # -------------------------------------------------------------------------
    # SECTION 10C: SELECT FRESH, CACHED, OR UNAVAILABLE DATA
    # -------------------------------------------------------------------------

    if data is not None:

        data_source = "real"

        # Save a copy so later changes do not modify the cached dictionary.
        LAST_REAL_DATA_CACHE[
            matchup_key
        ] = data.copy()

        print(
            "\n=================================================="
        )
        print(
            "FRESH REAL LIVE API DATA APPLIED"
        )
        print(
            "Latest real response saved to cache."
        )
        print(
            "=================================================="
        )

    else:

        cached_data = LAST_REAL_DATA_CACHE.get(
            matchup_key
        )

        if cached_data is not None:

            data = cached_data.copy()
            data_source = "cached"

            print(
                "\n=================================================="
            )
            print(
                "API UNAVAILABLE — LAST REAL DATA REUSED"
            )
            print(
                "Demo data was not applied."
            )
            print(
                "=================================================="
            )

        else:

            print(
                "\n=================================================="
            )
            print(
                "LIVE DATA UNAVAILABLE"
            )
            print(
                "No earlier real update exists for this matchup."
            )
            print(
                "The current match values were left unchanged."
            )
            print(
                "=================================================="
            )

            return "unavailable"

    # -------------------------------------------------------------------------
    # SECTION 10D: MATCH CLOCK, STATUS, AND EVENT TIMELINE
    # -------------------------------------------------------------------------
    # EXAMPLES:
    #
    # match_minute = 45
    # match_extra_minute = 3
    # match_status_short = "1H"
    #
    # Display:
    # 45+3'
    #
    # At halftime:
    # match_status_short = "HT"
    #
    # During extra time:
    # match_status_short = "ET"
    #
    # At full time:
    # match_status_short = "FT"
    # -------------------------------------------------------------------------

    match.match_minute = int(
        data.get(
            "match_minute",
            0
        )
        or 0
    )

    match.match_extra_minute = int(
        data.get(
            "match_extra_minute",
            0
        )
        or 0
    )

    match.match_status_short = str(
        data.get(
            "match_status_short",
            ""
        )
        or ""
    ).upper()

    match.match_status_long = str(
        data.get(
            "match_status_long",
            ""
        )
        or ""
    )

    match.event_timeline = data.get(
        "event_timeline",
        []
    )

    # -------------------------------------------------------------------------
    # SECTION 10E: TEAM LOGOS
    # -------------------------------------------------------------------------

    match.team1_logo = data.get(
        "team1_logo",
        ""
    )

    match.team2_logo = data.get(
        "team2_logo",
        ""
    )

    # -------------------------------------------------------------------------
    # SECTION 10F: SCORE
    # -------------------------------------------------------------------------

    match.team1.goals = int(
        data.get(
            "team1_goals",
            0
        )
        or 0
    )

    match.team2.goals = int(
        data.get(
            "team2_goals",
            0
        )
        or 0
    )

    # -------------------------------------------------------------------------
    # SECTION 10G: POSSESSION
    # -------------------------------------------------------------------------

    match.team1.possession = int(
        data.get(
            "team1_possession",
            50
        )
        or 50
    )

    match.team1.possession = max(
        0,
        min(
            match.team1.possession,
            100
        )
    )

    match.team2.possession = (
        100
        - match.team1.possession
    )

    # -------------------------------------------------------------------------
    # SECTION 10H: ATTACKING STATISTICS
    # -------------------------------------------------------------------------

    match.team1.shots = int(
        data.get(
            "team1_total_shots",
            0
        )
        or 0
    )

    match.team2.shots = int(
        data.get(
            "team2_total_shots",
            0
        )
        or 0
    )

    match.team1.shots_on_target = int(
        data.get(
            "team1_shots_on_target",
            0
        )
        or 0
    )

    match.team2.shots_on_target = int(
        data.get(
            "team2_shots_on_target",
            0
        )
        or 0
    )

    # Total shots can never be lower than shots on target.
    match.team1.shots = max(
        match.team1.shots,
        match.team1.shots_on_target
    )

    match.team2.shots = max(
        match.team2.shots,
        match.team2.shots_on_target
    )

    match.team1.big_chances = int(
        data.get(
            "team1_big_chances",
            0
        )
        or 0
    )

    match.team2.big_chances = int(
        data.get(
            "team2_big_chances",
            0
        )
        or 0
    )

    match.team1.defender_blocks = int(
        data.get(
            "team1_defender_blocks",
            0
        )
        or 0
    )

    match.team2.defender_blocks = int(
        data.get(
            "team2_defender_blocks",
            0
        )
        or 0
    )

    match.team1.corners = int(
        data.get(
            "team1_corners",
            0
        )
        or 0
    )

    match.team2.corners = int(
        data.get(
            "team2_corners",
            0
        )
        or 0
    )

    # -------------------------------------------------------------------------
    # SECTION 10I: GOALKEEPER STATISTICS
    # -------------------------------------------------------------------------

    match.team1.goalkeeper_saves = int(
        data.get(
            "team1_goalkeeper_saves",
            0
        )
        or 0
    )

    match.team2.goalkeeper_saves = int(
        data.get(
            "team2_goalkeeper_saves",
            0
        )
        or 0
    )

    # -------------------------------------------------------------------------
    # SECTION 10J: CARDS
    # -------------------------------------------------------------------------

    match.team1.yellow_cards = int(
        data.get(
            "team1_yellow_cards",
            0
        )
        or 0
    )

    match.team2.yellow_cards = int(
        data.get(
            "team2_yellow_cards",
            0
        )
        or 0
    )

    match.team1.red_cards = int(
        data.get(
            "team1_red_cards",
            0
        )
        or 0
    )

    match.team2.red_cards = int(
        data.get(
            "team2_red_cards",
            0
        )
        or 0
    )

    # -------------------------------------------------------------------------
    # SECTION 10K: LIVE PLAYER MODIFIERS
    # -------------------------------------------------------------------------
    # API-Football does not provide a reliable star-player performance flag.
    # These modifiers are only applied when a live-data source explicitly sets
    # the matching Boolean field to True.
    # -------------------------------------------------------------------------

    if data.get(
        "team1_bad_star",
        False
    ):
        match.team1.add_modifier(
            "Star player is not playing well "
            "from live feed",
            match.team1.star_bad_game_penalty()
        )

    if data.get(
        "team2_bad_star",
        False
    ):
        match.team2.add_modifier(
            "Star player is not playing well "
            "from live feed",
            match.team2.star_bad_game_penalty()
        )

    # -------------------------------------------------------------------------
    # SECTION 10L: RETURN DATA SOURCE
    # -------------------------------------------------------------------------
    # app.py uses this value to:
    # - Display the correct status message
    # - Prevent cached or unavailable responses from entering the probability
    #   timeline
    # -------------------------------------------------------------------------

    return data_source