# =============================================================================
# ROAD TO THE FINAL — PRE-MATCH INSIGHTS
# =============================================================================
# PURPOSE:
# Handles pre-match intelligence separately from the live-match engine.
#
# CURRENT FEATURES:
# - API team-ID lookup
# - Head-to-head fixture lookup
# - Local JSON caching
# - H2H win/draw summary
# - Recent meeting formatting
# - Cache-first recent form
# - Manual API refresh protection
#
# PRODUCTION FLOW:
#
# Selected teams
#       ↓
# Check insights_cache.json
#       ↓
# Cached insight available?
#       ├── Yes → return cached information
#       └── No  → return an unavailable message
#
# API-Football is called only when app.py explicitly passes allow_api=True,
# normally from a Refresh Match Insights button.
#
# FUTURE FEATURES:
# - Rankings
# - Team statistics
# - Tournament history
# - Key advantages
# =============================================================================


# =============================================================================
# SECTION 01: IMPORTS AND ENVIRONMENT CONFIGURATION
# =============================================================================
# PURPOSE:
# Loads Python packages, the API key, and shared configuration.
#
# UPDATE THIS SECTION WHEN:
# - Changing API provider
# - Adding logging
# - Adding a database
# =============================================================================

import json
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


load_dotenv(override=True)

API_KEY = os.getenv(
    "API_FOOTBALL_KEY"
)

BASE_URL = (
    "https://v3.football.api-sports.io"
)


# =============================================================================
# SECTION 02: CACHE CONFIGURATION
# =============================================================================
# PURPOSE:
# Defines the local file used to store all pre-match insight information.
#
# The file is created automatically after the first successful lookup.
#
# CACHE STRUCTURE:
#
# {
#     "team_lookup": {
#         "france": {
#             "id": 2,
#             "name": "France",
#             "logo": "..."
#         }
#     },
#
#     "head_to_head": {
#         "2|31": {
#             "updated_at": "...",
#             "matches": [...]
#         }
#     }
# }
#
# UPDATE THIS SECTION WHEN:
# - Renaming the cache file
# - Moving cache data into a database
# - Adding cache expiration
# =============================================================================

INSIGHTS_CACHE_FILE = (
    "insights_cache.json"
)

DEFAULT_H2H_MATCH_LIMIT = 5

REQUEST_TIMEOUT_SECONDS = 15


# =============================================================================
# SECTION 03: GENERAL TEXT AND CACHE HELPERS
# =============================================================================
# PURPOSE:
# Provides reusable normalization and JSON-cache functions.
#
# UPDATE THIS SECTION WHEN:
# - Adding safer file locking
# - Adding cache expiration
# - Supporting aliases
# =============================================================================

def normalize_team_name(team_name):
    """
    Converts a team name into a simplified comparison key.

    Example:
        "United States" -> "unitedstates"
    """

    return "".join(
        character
        for character in str(team_name).lower()
        if character.isalnum()
    )


def create_h2h_cache_key(
    team1_id,
    team2_id
):
    """
    Creates one order-independent cache key for a matchup.

    H2H data itself is neutral, so these two selections share one cache:

        France vs Morocco
        Morocco vs France

    The final summary is still calculated relative to the user's selected
    Team 1 and Team 2 order.
    """

    ordered_ids = sorted(
        [
            int(team1_id),
            int(team2_id)
        ]
    )

    return (
        f"{ordered_ids[0]}|"
        f"{ordered_ids[1]}"
    )


def empty_cache():
    """
    Returns the complete local Match Insights cache.

    Normal page loads read only from this structure. API-Football is called
    only when app.py explicitly enables API access for a manual refresh.
    """

    return {
        "team_lookup": {},
        "head_to_head": {},
        "recent_form": {},
        "team_statistics": {},
        "rankings": {}
    }


def load_insights_cache():
    """
    Loads insights_cache.json.

    Returns an empty cache structure when:
    - The file does not exist
    - The file contains invalid JSON
    - The saved structure is invalid
    """

    if not os.path.exists(
        INSIGHTS_CACHE_FILE
    ):
        return empty_cache()

    try:
        with open(
            INSIGHTS_CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as cache_file:
            cache = json.load(
                cache_file
            )

    except (
        OSError,
        json.JSONDecodeError
    ):
        print(
            "\nInsights cache could not be read. "
            "A new cache will be used."
        )

        return empty_cache()

    if not isinstance(
        cache,
        dict
    ):
        return empty_cache()

    # Keep older cache files backward compatible.
    cache.setdefault(
        "team_lookup",
        {}
    )

    cache.setdefault(
        "head_to_head",
        {}
    )

    cache.setdefault(
        "recent_form",
        {}
    )

    cache.setdefault(
        "team_statistics",
        {}
    )

    cache.setdefault(
        "rankings",
        {}
    )

    return cache


def save_insights_cache(cache):
    """
    Safely writes the complete insights cache to disk.
    """

    temporary_filename = (
        f"{INSIGHTS_CACHE_FILE}.tmp"
    )

    try:
        with open(
            temporary_filename,
            "w",
            encoding="utf-8"
        ) as cache_file:
            json.dump(
                cache,
                cache_file,
                indent=4,
                ensure_ascii=False
            )

        os.replace(
            temporary_filename,
            INSIGHTS_CACHE_FILE
        )

    except OSError as error:
        print(
            "\nInsights cache could not be saved:",
            error
        )

        if os.path.exists(
            temporary_filename
        ):
            try:
                os.remove(
                    temporary_filename
                )

            except OSError:
                pass


# =============================================================================
# SECTION 04: API REQUEST HELPER
# =============================================================================
# PURPOSE:
# Sends one authenticated request to API-Football.
#
# RETURN VALUE:
# - Parsed API response dictionary
# - None when the request fails
#
# UPDATE THIS SECTION WHEN:
# - Adding retries
# - Adding request logging
# - Changing API provider
# =============================================================================

def insights_api_get(
    endpoint,
    parameters=None
):
    """
    Sends a GET request to API-Football.
    """

    if not API_KEY:
        print(
            "\nMatch Insights API request skipped."
        )
        print(
            "API_FOOTBALL_KEY was not found in .env."
        )

        return None

    headers = {
        "x-apisports-key": API_KEY
    }

    url = (
        f"{BASE_URL}{endpoint}"
    )

    try:
        response = requests.get(
            url,
            headers=headers,
            params=parameters or {},
            timeout=REQUEST_TIMEOUT_SECONDS
        )

    except requests.RequestException as error:
        print(
            "\nMatch Insights API request failed:",
            error
        )

        return None

    print(
        "\n=============================================="
    )
    print(
        "MATCH INSIGHTS API REQUEST"
    )
    print(
        "Endpoint:",
        endpoint
    )
    print(
        "Parameters:",
        parameters or {}
    )
    print(
        "HTTP status:",
        response.status_code
    )
    print(
        "=============================================="
    )

    if response.status_code != 200:
        print(
            "Match Insights request was unsuccessful."
        )

        return None

    try:
        data = response.json()

    except ValueError:
        print(
            "Match Insights API returned invalid JSON."
        )

        return None

    api_errors = data.get(
        "errors",
        []
    )

    if api_errors:
        print(
            "Match Insights API errors:",
            api_errors
        )

        return None

    return data


# =============================================================================
# SECTION 05: TEAM-ID LOOKUP
# =============================================================================
# PURPOSE:
# Finds the API-Football team ID for a selected national team.
#
# LOOKUP ORDER:
# 1. Check insights_cache.json
# 2. Call /teams?search=TEAM_NAME
# 3. Prefer an exact national-team match
# 4. Save the result to the cache
#
# UPDATE THIS SECTION WHEN:
# - Adding team aliases
# - Supporting club teams
# - Adding manual API IDs to teams.csv
# =============================================================================

def choose_best_team_result(
    selected_team_name,
    api_results
):
    """
    Selects the safest team match from an API /teams search response.

    National teams with exact normalized names are preferred.
    """

    selected_key = normalize_team_name(
        selected_team_name
    )

    exact_national_matches = []
    exact_matches = []
    national_partial_matches = []
    partial_matches = []

    for result in api_results:
        team = result.get(
            "team",
            {}
        )

        api_name = str(
            team.get(
                "name",
                ""
            )
            or ""
        )

        api_key = normalize_team_name(
            api_name
        )

        is_national = bool(
            team.get(
                "national",
                False
            )
        )

        if not api_key:
            continue

        if api_key == selected_key:
            if is_national:
                exact_national_matches.append(
                    team
                )

            else:
                exact_matches.append(
                    team
                )

        elif (
            selected_key in api_key
            or api_key in selected_key
        ):
            if is_national:
                national_partial_matches.append(
                    team
                )

            else:
                partial_matches.append(
                    team
                )

    result_groups = [
        exact_national_matches,
        exact_matches,
        national_partial_matches,
        partial_matches
    ]

    for result_group in result_groups:
        if result_group:
            return result_group[0]

    return None


def lookup_team_information(
    team_name,
    force_refresh=False,
    allow_api=True
):
    """
    Returns information for one team.

    NORMAL PAGE LOAD:
    - Reads the saved team lookup only when allow_api=False.
    - Makes zero API requests.

    MANUAL INSIGHT REFRESH:
    - Reuses a saved team ID when available.
    - Calls API-Football only when the team is missing or force_refresh=True.
    """

    cache = load_insights_cache()

    team_key = normalize_team_name(
        team_name
    )

    cached_team = (
        cache
        .get(
            "team_lookup",
            {}
        )
        .get(
            team_key
        )
    )

    if (
        cached_team is not None
        and not force_refresh
    ):
        return cached_team

    if not allow_api:
        return cached_team

    data = insights_api_get(
        "/teams",
        {
            "search": team_name
        }
    )

    if data is None:
        return cached_team

    best_team = choose_best_team_result(
        team_name,
        data.get(
            "response",
            []
        )
    )

    if best_team is None:
        print(
            "\nNo safe API team match was found for:",
            team_name
        )

        return cached_team

    team_information = {
        "id": best_team.get(
            "id"
        ),

        "name": best_team.get(
            "name",
            team_name
        ),

        "logo": best_team.get(
            "logo",
            ""
        ),

        "national": bool(
            best_team.get(
                "national",
                False
            )
        )
    }

    if team_information["id"] is None:
        return cached_team

    cache.setdefault(
        "team_lookup",
        {}
    )

    cache["team_lookup"][team_key] = (
        team_information
    )

    save_insights_cache(
        cache
    )

    print(
        "\nSaved team lookup to insights cache:",
        team_information["name"],
        "->",
        team_information["id"]
    )

    return team_information


# =============================================================================
# SECTION 06: HEAD-TO-HEAD API REQUEST
# =============================================================================
# PURPOSE:
# Requests meetings between two API team IDs.
#
# IMPORTANT:
# The free API-Football plan does not allow the `last` parameter.
# Therefore, the API returns the available H2H fixtures and the app limits
# the number of displayed matches locally afterward.
#
# API ENDPOINT:
# /fixtures/headtohead
#
# PARAMETERS:
# - h2h: TEAM1_ID-TEAM2_ID
#
# UPDATE THIS SECTION WHEN:
# - Filtering by competition
# - Filtering by date
# - Changing API plan behavior
# =============================================================================

def request_head_to_head(
    team1_id,
    team2_id,
    match_limit=DEFAULT_H2H_MATCH_LIMIT
):
    """
    Requests H2H fixtures without using the restricted `last` parameter.

    match_limit remains in the function signature for compatibility.
    The actual limiting is performed locally after formatting.
    """

    return insights_api_get(
        "/fixtures/headtohead",
        {
            "h2h": (
                f"{team1_id}-"
                f"{team2_id}"
            )
        }
    )


# =============================================================================
# SECTION 07: FORMAT RAW H2H FIXTURES
# =============================================================================
# PURPOSE:
# Converts large API fixture responses into compact cache records.
#
# Only fields needed by the interface are stored.
#
# UPDATE THIS SECTION WHEN:
# - Displaying venues
# - Displaying penalty shootout scores
# - Displaying match rounds
# - Displaying competition logos
# =============================================================================

def format_h2h_fixture(
    fixture_data
):
    """
    Converts one API fixture into a compact dictionary.
    """

    fixture = fixture_data.get(
        "fixture",
        {}
    )

    league = fixture_data.get(
        "league",
        {}
    )

    teams = fixture_data.get(
        "teams",
        {}
    )

    goals = fixture_data.get(
        "goals",
        {}
    )

    score = fixture_data.get(
        "score",
        {}
    )

    home_team = teams.get(
        "home",
        {}
    )

    away_team = teams.get(
        "away",
        {}
    )

    fixture_status = fixture.get(
        "status",
        {}
    )

    home_goals = goals.get(
        "home"
    )

    away_goals = goals.get(
        "away"
    )

    penalty_score = score.get(
        "penalty",
        {}
    )

    return {
        "fixture_id": fixture.get(
            "id"
        ),

        "date": fixture.get(
            "date",
            ""
        ),

        "timestamp": fixture.get(
            "timestamp"
        ),

        "status_short": fixture_status.get(
            "short",
            ""
        ),

        "status_long": fixture_status.get(
            "long",
            ""
        ),

        "competition": league.get(
            "name",
            ""
        ),

        "competition_logo": league.get(
            "logo",
            ""
        ),

        "country": league.get(
            "country",
            ""
        ),

        "home_id": home_team.get(
            "id"
        ),

        "home_name": home_team.get(
            "name",
            ""
        ),

        "home_logo": home_team.get(
            "logo",
            ""
        ),

        "away_id": away_team.get(
            "id"
        ),

        "away_name": away_team.get(
            "name",
            ""
        ),

        "away_logo": away_team.get(
            "logo",
            ""
        ),

        "home_goals": home_goals,

        "away_goals": away_goals,

        "home_penalties": penalty_score.get(
            "home"
        ),

        "away_penalties": penalty_score.get(
            "away"
        )
    }


def format_h2h_fixtures(
    api_results
):
    """
    Formats and sorts H2H fixtures from newest to oldest.
    """

    formatted_matches = []

    for fixture_data in api_results:
        formatted_match = format_h2h_fixture(
            fixture_data
        )

        formatted_matches.append(
            formatted_match
        )

    formatted_matches.sort(
        key=lambda match: (
            match.get(
                "timestamp"
            )
            or 0
        ),
        reverse=True
    )

    return formatted_matches


# =============================================================================
# SECTION 08: SAVE AND LOAD H2H CACHE
# =============================================================================
# PURPOSE:
# Stores neutral matchup history using an order-independent team-ID key.
#
# The raw match list is neutral. Team 1 and Team 2 summaries are calculated
# later according to the selected dropdown order.
#
# UPDATE THIS SECTION WHEN:
# - Adding cache expiration
# - Saving additional fixture fields
# =============================================================================

def load_cached_h2h(
    team1_id,
    team2_id
):
    """
    Returns a saved H2H cache entry or None.
    """

    cache = load_insights_cache()

    cache_key = create_h2h_cache_key(
        team1_id,
        team2_id
    )

    return (
        cache
        .get(
            "head_to_head",
            {}
        )
        .get(
            cache_key
        )
    )


def save_cached_h2h(
    team1_id,
    team2_id,
    matches
):
    """
    Saves formatted H2H match information.
    """

    cache = load_insights_cache()

    cache_key = create_h2h_cache_key(
        team1_id,
        team2_id
    )

    cache.setdefault(
        "head_to_head",
        {}
    )

    cache[
        "head_to_head"
    ][
        cache_key
    ] = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "team_ids": sorted(
            [
                int(team1_id),
                int(team2_id)
            ]
        ),

        "matches": matches
    }

    save_insights_cache(
        cache
    )


# =============================================================================
# SECTION 09: HEAD-TO-HEAD SUMMARY CALCULATION
# =============================================================================
# PURPOSE:
# Calculates H2H totals relative to the selected Team 1 and Team 2.
#
# This means the same cached matches work correctly whether the user selects:
#
# France vs Morocco
#
# or:
#
# Morocco vs France
#
# UPDATE THIS SECTION WHEN:
# - Counting penalty shootout winners differently
# - Adding goals scored totals
# - Adding clean-sheet statistics
# =============================================================================

def completed_fixture(
    match
):
    """
    Returns True when a saved match has a completed result.
    """

    completed_statuses = {
        "FT",
        "AET",
        "PEN"
    }

    return (
        match.get(
            "status_short"
        )
        in completed_statuses
        and match.get(
            "home_goals"
        )
        is not None
        and match.get(
            "away_goals"
        )
        is not None
    )


def determine_match_winner_id(
    match
):
    """
    Returns:
    - Winning team ID
    - None for a draw or unknown result

    For matches decided by penalties, the penalty score determines the winner.
    """

    status_short = match.get(
        "status_short"
    )

    if status_short == "PEN":
        home_penalties = match.get(
            "home_penalties"
        )

        away_penalties = match.get(
            "away_penalties"
        )

        if (
            home_penalties is not None
            and away_penalties is not None
        ):
            if home_penalties > away_penalties:
                return match.get(
                    "home_id"
                )

            if away_penalties > home_penalties:
                return match.get(
                    "away_id"
                )

    home_goals = match.get(
        "home_goals"
    )

    away_goals = match.get(
        "away_goals"
    )

    if (
        home_goals is None
        or away_goals is None
    ):
        return None

    if home_goals > away_goals:
        return match.get(
            "home_id"
        )

    if away_goals > home_goals:
        return match.get(
            "away_id"
        )

    return None


def display_match_date(
    iso_date
):
    """
    Converts an API ISO date into a clean YYYY-MM-DD display.
    """

    if not iso_date:
        return ""

    return str(
        iso_date
    )[:10]


def create_recent_meeting_display(
    match
):
    """
    Creates a template-friendly recent-meeting dictionary.
    """

    home_goals = match.get(
        "home_goals"
    )

    away_goals = match.get(
        "away_goals"
    )

    if (
        home_goals is None
        or away_goals is None
    ):
        score_text = "–"

    else:
        score_text = (
            f"{home_goals}-"
            f"{away_goals}"
        )

    penalty_text = ""

    if match.get(
        "status_short"
    ) == "PEN":
        home_penalties = match.get(
            "home_penalties"
        )

        away_penalties = match.get(
            "away_penalties"
        )

        if (
            home_penalties is not None
            and away_penalties is not None
        ):
            penalty_text = (
                f"Pens "
                f"{home_penalties}-"
                f"{away_penalties}"
            )

    return {
        "date": display_match_date(
            match.get(
                "date",
                ""
            )
        ),

        "competition": match.get(
            "competition",
            ""
        ),

        "home_name": match.get(
            "home_name",
            ""
        ),

        "home_logo": match.get(
            "home_logo",
            ""
        ),

        "away_name": match.get(
            "away_name",
            ""
        ),

        "away_logo": match.get(
            "away_logo",
            ""
        ),

        "score": score_text,

        "penalty_score": penalty_text,

        "status_short": match.get(
            "status_short",
            ""
        )
    }


def build_h2h_summary(
    selected_team1,
    selected_team2,
    team1_information,
    team2_information,
    cached_entry,
    source
):
    """
    Builds the final H2H dictionary sent to app.py and index.html.
    """

    team1_id = int(
        team1_information["id"]
    )

    team2_id = int(
        team2_information["id"]
    )

    all_matches = cached_entry.get(
        "matches",
        []
    )

    completed_matches = [
        match
        for match in all_matches
        if completed_fixture(
            match
        )
    ]

    team1_wins = 0
    team2_wins = 0
    draws = 0

    team1_goals = 0
    team2_goals = 0

    for match in completed_matches:
        winner_id = determine_match_winner_id(
            match
        )

        if winner_id == team1_id:
            team1_wins += 1

        elif winner_id == team2_id:
            team2_wins += 1

        else:
            draws += 1

        home_id = match.get(
            "home_id"
        )

        home_goals = int(
            match.get(
                "home_goals",
                0
            )
            or 0
        )

        away_goals = int(
            match.get(
                "away_goals",
                0
            )
            or 0
        )

        if home_id == team1_id:
            team1_goals += home_goals
            team2_goals += away_goals

        else:
            team1_goals += away_goals
            team2_goals += home_goals

    total_meetings = len(
        completed_matches
    )

    if total_meetings > 0:
        team1_win_percentage = (
            team1_wins
            / total_meetings
            * 100
        )

        draw_percentage = (
            draws
            / total_meetings
            * 100
        )

        team2_win_percentage = (
            team2_wins
            / total_meetings
            * 100
        )

    else:
        team1_win_percentage = 0.0
        draw_percentage = 0.0
        team2_win_percentage = 0.0

    if team1_wins > team2_wins:
        series_leader = selected_team1
        series_summary = (
            f"{selected_team1} leads the recent series "
            f"{team1_wins}-{team2_wins}."
        )

    elif team2_wins > team1_wins:
        series_leader = selected_team2
        series_summary = (
            f"{selected_team2} leads the recent series "
            f"{team2_wins}-{team1_wins}."
        )

    else:
        series_leader = "Even"
        series_summary = (
            "The recent head-to-head series is even."
        )

    recent_meetings = [
        create_recent_meeting_display(
            match
        )
        for match in completed_matches
    ]

    return {
        "available": bool(
            completed_matches
        ),

        "source": source,

        "updated_at": cached_entry.get(
            "updated_at",
            ""
        ),

        "team1_id": team1_id,
        "team2_id": team2_id,

        "team1_name": selected_team1,
        "team2_name": selected_team2,

        "team1_logo": team1_information.get(
            "logo",
            ""
        ),

        "team2_logo": team2_information.get(
            "logo",
            ""
        ),

        "team1_wins": team1_wins,
        "draws": draws,
        "team2_wins": team2_wins,

        "team1_win_percentage": team1_win_percentage,
        "draw_percentage": draw_percentage,
        "team2_win_percentage": team2_win_percentage,

        "team1_goals": team1_goals,
        "team2_goals": team2_goals,

        "total_goals": (
            team1_goals
            + team2_goals
        ),

        "total_meetings": total_meetings,

        "series_leader": series_leader,
        "series_summary": series_summary,

        "recent_meetings": recent_meetings,

        "message": (
            ""
            if completed_matches
            else (
                "No completed head-to-head meetings "
                "were returned."
            )
        )
    }


# =============================================================================
# SECTION 10: EMPTY H2H RESULT
# =============================================================================
# PURPOSE:
# Gives app.py and index.html a consistent structure when H2H data is
# unavailable.
#
# UPDATE THIS SECTION WHEN:
# - Adding another template field
# =============================================================================

def empty_h2h_result(
    team1_name,
    team2_name,
    message
):
    """
    Returns a safe empty result.
    """

    return {
        "available": False,
        "source": "unavailable",
        "updated_at": "",

        "team1_id": None,
        "team2_id": None,

        "team1_name": team1_name,
        "team2_name": team2_name,

        "team1_logo": "",
        "team2_logo": "",

        "team1_wins": 0,
        "draws": 0,
        "team2_wins": 0,

        "team1_win_percentage": 0.0,
        "draw_percentage": 0.0,
        "team2_win_percentage": 0.0,

        "team1_goals": 0,
        "team2_goals": 0,
        "total_goals": 0,

        "total_meetings": 0,

        "series_leader": "",
        "series_summary": "",

        "recent_meetings": [],

        "message": message
    }


# =============================================================================
# SECTION 11: PUBLIC HEAD-TO-HEAD FUNCTION
# =============================================================================
# PURPOSE:
# Provides one simple function for app.py:
#
#     h2h = get_head_to_head(
#         team1.name,
#         team2.name
#     )
#
# NORMAL PAGE LOAD:
# - Reads insights_cache.json only
# - Makes zero API requests
#
# REFRESH MATCH INSIGHTS:
# - Reuses cached team IDs
# - Requests fresh H2H data only when allow_api=True
# - Filters completed matches
# - Limits the results locally
# - Saves successful results to insights_cache.json
#
# IMPORTANT:
# The free API-Football plan does not allow the `last` parameter.
# Therefore, SECTION 06 requests the available H2H fixtures and this
# section keeps only the newest completed fixtures locally.
#
# UPDATE THIS SECTION WHEN:
# - Adding manual refresh controls
# - Adding cache expiration
# - Changing how completed fixtures are counted
# - Changing the local H2H match limit
# =============================================================================

def get_head_to_head(
    team1_name,
    team2_name,
    force_refresh=False,
    match_limit=DEFAULT_H2H_MATCH_LIMIT,
    allow_api=False
):
    """
    Returns H2H information for two selected teams.

    NORMAL PAGE LOAD:
    - Reads insights_cache.json only.
    - Makes zero API requests.

    REFRESH MATCH INSIGHTS:
    - allow_api=True
    - Loads missing team IDs if necessary.
    - Requests fresh H2H data.
    - Saves successful results locally.
    """

    # -------------------------------------------------------------------------
    # SECTION 11A: PREVENT SAME-TEAM MATCHUPS
    # -------------------------------------------------------------------------

    if normalize_team_name(
        team1_name
    ) == normalize_team_name(
        team2_name
    ):
        return empty_h2h_result(
            team1_name,
            team2_name,
            "Select two different teams."
        )

    # -------------------------------------------------------------------------
    # SECTION 11B: LOAD TEAM INFORMATION
    # -------------------------------------------------------------------------
    # Existing cached team IDs are reused.
    #
    # A new /teams request is allowed only when:
    #     allow_api=True
    # -------------------------------------------------------------------------

    team1_information = lookup_team_information(
        team1_name,
        force_refresh=False,
        allow_api=allow_api
    )

    team2_information = lookup_team_information(
        team2_name,
        force_refresh=False,
        allow_api=allow_api
    )

    if (
        team1_information is None
        or team2_information is None
    ):
        return empty_h2h_result(
            team1_name,
            team2_name,
            (
                "No cached team information is available. "
                "Press Refresh Match Insights to load it."
            )
        )

    # -------------------------------------------------------------------------
    # SECTION 11C: VALIDATE TEAM IDS
    # -------------------------------------------------------------------------

    team1_id = team1_information.get(
        "id"
    )

    team2_id = team2_information.get(
        "id"
    )

    if (
        team1_id is None
        or team2_id is None
    ):
        return empty_h2h_result(
            team1_name,
            team2_name,
            "The selected teams do not have valid API IDs."
        )

    # -------------------------------------------------------------------------
    # SECTION 11D: LOAD EXISTING H2H CACHE
    # -------------------------------------------------------------------------

    cached_entry = load_cached_h2h(
        team1_id,
        team2_id
    )

    # Normal page loads return cached data immediately.
    if (
        cached_entry is not None
        and not force_refresh
    ):
        return build_h2h_summary(
            team1_name,
            team2_name,
            team1_information,
            team2_information,
            cached_entry,
            source="cache"
        )

    # -------------------------------------------------------------------------
    # SECTION 11E: BLOCK AUTOMATIC API REQUESTS
    # -------------------------------------------------------------------------
    # When no cache exists, normal browser loads still make zero API calls.
    # -------------------------------------------------------------------------

    if not allow_api:
        return empty_h2h_result(
            team1_name,
            team2_name,
            (
                "No cached head-to-head data exists. "
                "Press Refresh Match Insights to load it."
            )
        )

    # -------------------------------------------------------------------------
    # SECTION 11F: REQUEST H2H FIXTURES
    # -------------------------------------------------------------------------
    # SECTION 06 no longer sends the restricted `last` parameter.
    # -------------------------------------------------------------------------

    data = request_head_to_head(
        team1_id,
        team2_id,
        match_limit=match_limit
    )

    if data is None:
        if cached_entry is not None:
            return build_h2h_summary(
                team1_name,
                team2_name,
                team1_information,
                team2_information,
                cached_entry,
                source="cache"
            )

        return empty_h2h_result(
            team1_name,
            team2_name,
            (
                "Head-to-head information could not be "
                "loaded from API-Football."
            )
        )

    # -------------------------------------------------------------------------
    # SECTION 11G: FORMAT, FILTER, AND LIMIT LOCALLY
    # -------------------------------------------------------------------------
    # format_h2h_fixtures() sorts matches newest to oldest.
    #
    # The free API-Football plan does not allow:
    #
    #     "last": 5
    #
    # Therefore:
    # 1. Request available H2H fixtures
    # 2. Keep completed fixtures only
    # 3. Keep only the newest requested number
    # -------------------------------------------------------------------------

    formatted_matches = format_h2h_fixtures(
        data.get(
            "response",
            []
        )
    )

    completed_matches = [
        match
        for match in formatted_matches
        if completed_fixture(
            match
        )
    ]

    completed_matches = completed_matches[
        :max(
            1,
            int(match_limit)
        )
    ]

    # -------------------------------------------------------------------------
    # SECTION 11H: PRESERVE VALID CACHE ON EMPTY RESPONSES
    # -------------------------------------------------------------------------
    # Never overwrite good saved data with an empty API response.
    # -------------------------------------------------------------------------

    if not completed_matches:
        if cached_entry is not None:
            return build_h2h_summary(
                team1_name,
                team2_name,
                team1_information,
                team2_information,
                cached_entry,
                source="cache"
            )

        return empty_h2h_result(
            team1_name,
            team2_name,
            "The API returned no completed head-to-head fixtures."
        )

    # -------------------------------------------------------------------------
    # SECTION 11I: SAVE ONLY COMPLETED, LIMITED MATCHES
    # -------------------------------------------------------------------------
    # The cache stores only the newest completed fixtures needed by the page.
    # -------------------------------------------------------------------------

    save_cached_h2h(
        team1_id,
        team2_id,
        completed_matches
    )

    refreshed_entry = load_cached_h2h(
        team1_id,
        team2_id
    )

    if refreshed_entry is None:
        return empty_h2h_result(
            team1_name,
            team2_name,
            "Head-to-head information could not be cached."
        )

    # -------------------------------------------------------------------------
    # SECTION 11J: RETURN FRESH API SUMMARY
    # -------------------------------------------------------------------------

    return build_h2h_summary(
        team1_name,
        team2_name,
        team1_information,
        team2_information,
        refreshed_entry,
        source="api"
    )


# =============================================================================
# ROAD TO THE FINAL — RECENT FORM SECTION
# =============================================================================
# FILE:
# insights.py
#
# PLACEMENT:
# Replace the old empty SECTION 12 placeholder and the old SECTION 13 Recent
# Form block with this complete SECTION 12.
#
# REQUIRED IMPORT:
# At the top of insights.py, use:
#
#     from datetime import datetime, timedelta, timezone
#
# =============================================================================

# =============================================================================
# SECTION 12: RECENT FORM — CACHE-FIRST LAST FIVE MATCHES
# =============================================================================
# PURPOSE:
# Loads each national team's most recent completed matches.
#
# NORMAL PAGE LOAD:
# - Reads only insights_cache.json
# - Makes zero API requests
#
# REFRESH MATCH INSIGHTS:
# - allow_api=True
# - Requests recent fixtures
# - Saves successful results
# - Preserves older cache when the API fails or returns no completed fixtures
# =============================================================================

COMPLETED_FIXTURE_STATUSES = {
    "FT",
    "AET",
    "PEN"
}


def _empty_recent_form(
    team_name,
    logo="",
    message="Recent-form data is not currently available."
):
    """
    Returns one predictable structure for app.py and index.html.
    """

    return {
        "available": False,
        "team_name": team_name,
        "logo": logo,
        "team_logo": logo,
        "matches": [],
        "sequence": [],
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "points": 0,
        "form_points": 0,
        "goals_for": 0,
        "goals_against": 0,
        "source": "unavailable",
        "updated_at": "",
        "message": message
    }


def create_recent_form_cache_key(
    team_id,
    match_limit
):
    """
    Creates a separate cache entry for each team and requested match limit.
    """

    return (
        f"{int(team_id)}|"
        f"{int(match_limit)}"
    )


def _format_recent_fixture(
    fixture_data,
    selected_team_id
):
    """
    Converts one completed API fixture into a compact recent-form record.
    """

    fixture = fixture_data.get(
        "fixture",
        {}
    )

    status_short = (
        fixture
        .get(
            "status",
            {}
        )
        .get(
            "short",
            ""
        )
    )

    if status_short not in COMPLETED_FIXTURE_STATUSES:
        return None

    teams = fixture_data.get(
        "teams",
        {}
    )

    goals = fixture_data.get(
        "goals",
        {}
    )

    league = fixture_data.get(
        "league",
        {}
    )

    home = teams.get(
        "home",
        {}
    )

    away = teams.get(
        "away",
        {}
    )

    home_goals = goals.get(
        "home"
    )

    away_goals = goals.get(
        "away"
    )

    if home_goals is None or away_goals is None:
        return None

    selected_is_home = (
        int(
            home.get(
                "id",
                -1
            )
        )
        == int(selected_team_id)
    )

    goals_for = int(
        home_goals
        if selected_is_home
        else away_goals
    )

    goals_against = int(
        away_goals
        if selected_is_home
        else home_goals
    )

    opponent = (
        away
        if selected_is_home
        else home
    )

    if goals_for > goals_against:
        result = "W"
    elif goals_for == goals_against:
        result = "D"
    else:
        result = "L"

    return {
        "fixture_id": fixture.get(
            "id"
        ),
        "date": str(
            fixture.get(
                "date",
                ""
            )
        )[:10],
        "timestamp": fixture.get(
            "timestamp"
        ),
        "competition": league.get(
            "name",
            "International"
        ),
        "opponent": opponent.get(
            "name",
            "Opponent"
        ),
        "opponent_logo": opponent.get(
            "logo",
            ""
        ),
        "result": result,
        "score": f"{goals_for}-{goals_against}",
        "goals_for": goals_for,
        "goals_against": goals_against
    }


def build_recent_form_summary(
    team_name,
    team_information,
    matches,
    source,
    updated_at=""
):
    """
    Calculates W-D-L totals and form points from normalized matches.
    """

    completed_matches = [
        match
        for match in matches
        if isinstance(
            match,
            dict
        )
    ]

    wins = sum(
        1
        for match in completed_matches
        if match.get("result") == "W"
    )

    draws = sum(
        1
        for match in completed_matches
        if match.get("result") == "D"
    )

    losses = sum(
        1
        for match in completed_matches
        if match.get("result") == "L"
    )

    goals_for = sum(
        int(
            match.get(
                "goals_for",
                0
            )
        )
        for match in completed_matches
    )

    goals_against = sum(
        int(
            match.get(
                "goals_against",
                0
            )
        )
        for match in completed_matches
    )

    form_points = wins * 3 + draws
    logo = team_information.get(
        "logo",
        ""
    )

    return {
        "available": bool(completed_matches),
        "team_name": team_name,
        "logo": logo,
        "team_logo": logo,
        "matches": completed_matches,
        "sequence": [
            match.get(
                "result",
                ""
            )
            for match in completed_matches
        ],
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "points": form_points,
        "form_points": form_points,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "source": source,
        "updated_at": updated_at,
        "message": (
            ""
            if completed_matches
            else "No completed recent fixtures were returned."
        )
    }


def get_recent_form(
    team_name,
    match_limit=5,
    force_refresh=False,
    allow_api=False
):
    """
    Returns cache-first recent-form information for one national team.
    """

    match_limit = max(
        1,
        min(
            int(match_limit),
            10
        )
    )

    team_information = lookup_team_information(
        team_name,
        force_refresh=False,
        allow_api=allow_api
    )

    if not team_information:
        return _empty_recent_form(
            team_name,
            message=(
                "No cached team information exists. "
                "Press Refresh Match Insights to load it."
            )
        )

    team_id = team_information.get(
        "id"
    )

    team_logo = team_information.get(
        "logo",
        ""
    )

    if team_id is None:
        return _empty_recent_form(
            team_name,
            logo=team_logo,
            message="The selected team does not have a valid API ID."
        )

    cache = load_insights_cache()
    cache.setdefault(
        "recent_form",
        {}
    )

    cache_key = create_recent_form_cache_key(
        team_id,
        match_limit
    )

    cached_entry = cache["recent_form"].get(
        cache_key
    )

    if cached_entry is not None and not force_refresh:
        return build_recent_form_summary(
            team_name,
            team_information,
            cached_entry.get(
                "matches",
                []
            ),
            source="cache",
            updated_at=cached_entry.get(
                "updated_at",
                ""
            )
        )

    if not allow_api:
        if cached_entry is not None:
            return build_recent_form_summary(
                team_name,
                team_information,
                cached_entry.get(
                    "matches",
                    []
                ),
                source="cache",
                updated_at=cached_entry.get(
                    "updated_at",
                    ""
                )
            )

        return _empty_recent_form(
            team_name,
            logo=team_logo,
            message=(
                "No cached recent-form data exists. "
                "Press Refresh Match Insights to load it."
            )
        )

    # -------------------------------------------------------------------------
    # SECTION 12A: FREE-PLAN FIXTURE DATE RANGE
    # -------------------------------------------------------------------------
    # API-Football's free plan does not allow the `last` parameter.
    #
    # Instead, request one date range and sort/limit the completed fixtures
    # locally. Eighteen months gives national teams enough match history while
    # still using only one API request per team.
    # -------------------------------------------------------------------------

    today_utc = datetime.now(
        timezone.utc
    ).date()

    start_date = (
        today_utc
        - timedelta(
            days=548
        )
    )

    data = insights_api_get(
        "/fixtures",
        {
            "team": team_id,
            "from": start_date.isoformat(),
            "to": today_utc.isoformat()
        }
    )

    if data is None:
        if cached_entry is not None:
            return build_recent_form_summary(
                team_name,
                team_information,
                cached_entry.get(
                    "matches",
                    []
                ),
                source="cache",
                updated_at=cached_entry.get(
                    "updated_at",
                    ""
                )
            )

        return _empty_recent_form(
            team_name,
            logo=team_logo,
            message="Recent fixtures could not be loaded from API-Football."
        )

    formatted_matches = []

    for fixture_data in data.get(
        "response",
        []
    ):
        formatted_match = _format_recent_fixture(
            fixture_data,
            team_id
        )

        if formatted_match is not None:
            formatted_matches.append(
                formatted_match
            )

    formatted_matches.sort(
        key=lambda match: (
            match.get(
                "timestamp"
            )
            or 0
        ),
        reverse=True
    )

    formatted_matches = formatted_matches[:match_limit]

    # Never replace valid cache with an empty API response.
    if not formatted_matches:
        if cached_entry is not None:
            return build_recent_form_summary(
                team_name,
                team_information,
                cached_entry.get(
                    "matches",
                    []
                ),
                source="cache",
                updated_at=cached_entry.get(
                    "updated_at",
                    ""
                )
            )

        return _empty_recent_form(
            team_name,
            logo=team_logo,
            message="The API returned no completed recent fixtures."
        )

    updated_at = datetime.now(
        timezone.utc
    ).isoformat()

    cache["recent_form"][cache_key] = {
        "updated_at": updated_at,
        "matches": formatted_matches
    }

    save_insights_cache(
        cache
    )

    return build_recent_form_summary(
        team_name,
        team_information,
        formatted_matches,
        source="api",
        updated_at=updated_at
    )