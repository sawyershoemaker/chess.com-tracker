import os
import json
import subprocess
import requests
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Replace with your Chess.com username to track.
CHESS_USERNAME = "inseem"
ARCHIVES_URL = f"https://api.chess.com/pub/player/{CHESS_USERNAME}/games/archives"
LAST_GAME_FILE = "last_game.json"

# Advancement thresholds (based on trophy/league points):
# wood: top 20, stone: top 15, bronze: top 10, silver: top 5,
# crystal: top 3, elite: top 3, champion: top 1, legend: highest league (no advancement).
ADVANCEMENT_THRESHOLDS = {
    "wood": 20,
    "stone": 15,
    "bronze": 10,
    "silver": 5,
    "crystal": 3,
    "elite": 3,
    "champion": 1,
    "legend": None
}

# Mapping from league codes to your Discord custom emojis.
EMOJI_MAP = {
    "wood": "<:wood:1342938885210247330>",
    "stone": "<:stone:1342938857817247774>",
    "silver": "<:silver:1342938856986513499>",
    "legend": "<:legend:1342938856131006494>",
    "elite": "<:elite:1342938855111786568>",
    "crystal": "<:crystal:1342938854122061885>",
    "champion": "<:champion:1342938853069291630>",
    "bronze": "<:bronze:1342938852175908974>"
}

# Headers to mimic a real browser and request JSON.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.chess.com/"
}

def load_last_game_data():
    """
    Load persistent data from file.
    Expected keys:
      - "processed_games": list of game URLs already processed
      - "last_rating": rating from the last processed game
      - "alert_info": { "league_endTime": <int>, "alert_sent": <bool> }
    """
    try:
        with open(LAST_GAME_FILE, "r") as f:
            data = f.read().strip()
            if not data:
                return {}
            return json.loads(data)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Warning: last_game.json contains invalid JSON. Resetting data.")
        return {}

def save_last_game_data(data):
    """Save persistent data to file."""
    with open(LAST_GAME_FILE, "w") as f:
        json.dump(data, f)

def get_profile_avatar():
    """Fetch the user's profile to obtain their avatar URL."""
    profile_url = f"https://api.chess.com/pub/player/{CHESS_USERNAME}"
    try:
        resp = requests.get(profile_url, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("avatar", "")
        else:
            print("Error fetching profile:", resp.status_code)
    except Exception as e:
        print("Exception fetching profile:", e)
    return ""

def format_time_control(tc):
    """
    Convert a raw time control string (e.g. "600+5") into the format "10 | 5"
    where 10 is the main time (in minutes) and 5 is the increment.
    """
    if isinstance(tc, str):
        if tc.lower() == "unlimited":
            return "Unlimited"
        if '+' in tc:
            main_time, increment = tc.split('+', 1)
            try:
                main_time = int(main_time)
                increment = int(increment)
                minutes = main_time // 60
                return f"{minutes} | {increment}"
            except ValueError:
                return tc
        else:
            try:
                main_time = int(tc)
                minutes = main_time // 60
                return f"{minutes} | 0"
            except ValueError:
                return tc
    return tc

def fetch_latest_games():
    """
    Fetch all games from the latest archive.
    Returns a list of game objects (assumed to be in chronological order).
    """
    archives_resp = requests.get(ARCHIVES_URL, headers=HEADERS)
    if archives_resp.status_code == 410:
        print("No archives available (410 Gone).")
        return []
    if archives_resp.status_code != 200:
        print(f"Error fetching archives. Status code: {archives_resp.status_code}")
        print("Response:", archives_resp.text)
        return []
    archives = archives_resp.json().get("archives", [])
    if not archives:
        print("No archives available.")
        return []
    latest_archive_url = archives[-1]
    archive_resp = requests.get(latest_archive_url, headers=HEADERS)
    if archive_resp.status_code != 200:
        print(f"Error fetching latest archive. Status code: {archive_resp.status_code}")
        print("Response:", archive_resp.text)
        return []
    games = archive_resp.json().get("games", [])
    return games  # Assuming games are sorted chronologically

def parse_termination(pgn):
    """Extract the termination reason from the PGN's [Termination "…"] tag."""
    for line in pgn.splitlines():
        if line.startswith("[Termination "):
            start = line.find('"')
            end = line.rfind('"')
            if start != -1 and end != -1 and end > start:
                return line[start+1:end]
    return "Unknown"

def determine_game_details(game):
    """
    Extract details from a game object.
    Returns:
      opponent, result, game_url, time_control_formatted, current_rating,
      raw_rating_change, termination, end_time
    """
    opponent = "Unknown"
    result = "Draw"  # Default.
    current_rating = 0
    raw_rating_change = None

    if game["white"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["black"]["username"]
        current_rating = game["white"].get("rating", 0)
        raw_rating_change = game["white"].get("rating_change", None)
        if game["white"]["result"] == "win":
            result = "Win"
        elif game["black"]["result"] == "win":
            result = "Loss"
    elif game["black"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["white"]["username"]
        current_rating = game["black"].get("rating", 0)
        raw_rating_change = game["black"].get("rating_change", None)
        if game["black"]["result"] == "win":
            result = "Win"
        elif game["white"]["result"] == "win":
            result = "Loss"

    raw_time_control = game.get("time_control", "Unknown")
    time_control_formatted = format_time_control(raw_time_control)
    game_url = game.get("url", "No link available")
    termination = "Unknown"
    pgn = game.get("pgn", "")
    if pgn:
        termination = parse_termination(pgn)
    end_time = game.get("end_time", None)
    return (opponent, result, game_url, time_control_formatted,
            current_rating, raw_rating_change, termination, end_time)

def fetch_league_info():
    """
    Fetch the current league information for the user.
    Expected data includes:
      - "division": contains "endTime" and nested "league" details
      - "stats": contains current ranking ("ranking") and points ("trophyCount")
    """
    url = f"https://www.chess.com/callback/leagues/user-league/search/{CHESS_USERNAME}"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "division" in data and "stats" in data:
                return data
        else:
            print("Error fetching league info:", resp.status_code)
    except Exception as e:
        print("Exception fetching league info:", e)
    return None

def send_discord_webhook(opponent, game_url, time_control, rating_change, result, termination, end_time, league_info=None, add_alert=False):
    """
    Send a Discord webhook message using an embed.
      - The embed's color is green for wins, red for losses, gray for draws.
      - The embed title is the termination method.
      - Fields include opponent, time control, and rating change.
      - If league info is available, it appends league name (with emoji), place, and points.
      - If add_alert is True, a league deadline notice is added.
      - A footer is added showing when the game was played (in EST).
    """
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        print("WEBHOOK_URL is not set in environment variables.")
        return

    if result == "Win":
        color = 65280
    elif result == "Loss":
        color = 16711680
    else:
        color = 8421504

    avatar_url = get_profile_avatar()
    embed = {
        "author": {
            "name": CHESS_USERNAME,
            "icon_url": avatar_url
        },
        "title": termination,  # Termination method as title.
        "url": game_url,
        "color": color,
        "fields": [
            {"name": "Opponent", "value": opponent, "inline": True},
            {"name": "Time Control", "value": time_control, "inline": True},
            {"name": "Rating Change", "value": f"{rating_change:+}", "inline": True},
        ]
    }

    # Add footer with game played time (in EST) if end_time is available.
    if end_time is not None:
        try:
            est_time = datetime.fromtimestamp(end_time, ZoneInfo("America/New_York"))
            formatted_time = est_time.strftime("%Y-%m-%d %I:%M %p EST")
            embed["footer"] = {"text": f"Game played: {formatted_time}"}
        except Exception as e:
            print("Error formatting end_time:", e)

    if league_info is not None:
        division = league_info.get("division", {})
        league_data = division.get("league", {})
        league_name = league_data.get("name", "Unknown")
        league_code = league_data.get("code", "").lower()
        league_emoji = EMOJI_MAP.get(league_code, "")
        stats = league_info.get("stats", {})
        league_place = stats.get("ranking", "N/A")
        league_points = stats.get("trophyCount", "N/A")
        embed["fields"].append({"name": "League", "value": f"{league_emoji} {league_name}", "inline": True})
        embed["fields"].append({"name": "Place", "value": f"#{league_place}", "inline": True})
        embed["fields"].append({"name": "Points", "value": str(league_points), "inline": True})

        if add_alert:
            threshold = ADVANCEMENT_THRESHOLDS.get(league_code, None)
            if threshold is not None and isinstance(league_points, (int, float)):
                points_needed = threshold - league_points
                if points_needed < 0:
                    points_needed = 0
            else:
                points_needed = "N/A"
            embed["fields"].append({
                "name": "League Deadline",
                "value": f"<@774816976756539422> Only 1 day left! You're at #{league_place}. You need {points_needed} more points to advance.",
                "inline": False
            })

    payload = {"embeds": [embed]}
    headers_payload = {"Content-Type": "application/json"}
    resp = requests.post(webhook_url, json=payload, headers=headers_payload)
    if resp.status_code in (200, 204):
        print("Webhook sent successfully.")
    else:
        print(f"Failed to send webhook. Status code: {resp.status_code}")

def commit_last_game(processed_data):
    """Commit and push the updated persistent data to the repository."""
    try:
        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)
        token = os.environ.get("TOKEN")
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/sawyershoemaker/chess.com-tracker.git"
            subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        subprocess.run(["git", "add", LAST_GAME_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update processed games"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Committed and pushed updated persistent data.")
    except subprocess.CalledProcessError as e:
        print("Git command failed:", e)

def main():
    # Load persistent data.
    data = load_last_game_data()
    processed_games = data.get("processed_games", [])
    last_rating = data.get("last_rating", None)
    alert_info = data.get("alert_info", {})  # Contains "league_endTime" and "alert_sent".

    games = fetch_latest_games()
    if not games:
        return

    # Process each game (assumed in chronological order).
    league_info = fetch_league_info()
    for game in games:
        game_url = game.get("url", "")
        if game_url in processed_games:
            continue  # Skip already processed games.
        # Extract game details.
        (opponent, result, game_url, time_control_formatted,
         current_rating, raw_rating_change, termination, end_time) = determine_game_details(game)
        # Determine rating change.
        if raw_rating_change is not None:
            rating_change = raw_rating_change
        elif last_rating is not None:
            rating_change = current_rating - last_rating
        else:
            rating_change = 0
        # Update last_rating for subsequent games.
        last_rating = current_rating

        # Determine whether to add league deadline alert.
        add_alert = False
        if league_info is not None:
            division = league_info.get("division", {})
            current_end_time = division.get("endTime", 0)
            current_time = int(time.time())
            time_left = current_end_time - current_time
            if alert_info.get("league_endTime") != current_end_time:
                alert_info["league_endTime"] = current_end_time
                alert_info["alert_sent"] = False
            if time_left < 86400 and not alert_info.get("alert_sent", False):
                add_alert = True
                alert_info["alert_sent"] = True
            data["alert_info"] = alert_info

        # Send webhook for this game.
        send_discord_webhook(opponent, game_url, time_control_formatted, rating_change,
                               result, termination, end_time, league_info, add_alert)
        # Mark this game as processed.
        processed_games.append(game_url)
    # Update persistent data.
    data["processed_games"] = processed_games
    data["last_rating"] = last_rating
    save_last_game_data(data)
    commit_last_game(data)

if __name__ == "__main__":
    main()
