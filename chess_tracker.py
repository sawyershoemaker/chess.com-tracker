import os
import json
import subprocess
import requests
import time

# Replace with your Chess.com username to track.
CHESS_USERNAME = "inseem"
ARCHIVES_URL = f"https://api.chess.com/pub/player/{CHESS_USERNAME}/games/archives"
LAST_GAME_FILE = "last_game.json"

# Advancement thresholds (example values; adjust as needed)
ADVANCEMENT_THRESHOLDS = {
    "bronze": 30,
    "silver": 50,
    "gold": 70,
    "platinum": 90,
    "diamond": 110,
    "wood": 20,
    "stone": 25
}

# Set a User-Agent header to mimic a real browser request.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/115.0.0.0 Safari/537.36"
}

def load_last_game_data():
    """
    Load the last recorded game data from file.
    Expected data: {"last_game_url": ..., "last_rating": ...}
    """
    try:
        with open(LAST_GAME_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_last_game_data(last_game_url, last_rating):
    """Save the latest game URL and rating to file."""
    with open(LAST_GAME_FILE, "w") as f:
        json.dump({"last_game_url": last_game_url, "last_rating": last_rating}, f)

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
    where 10 is the main time in minutes and 5 is the increment.
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

def fetch_latest_game():
    """Fetch the latest game from Chess.com archives."""
    archives_resp = requests.get(ARCHIVES_URL, headers=HEADERS)
    if archives_resp.status_code != 200:
        print(f"Error fetching archives. Status code: {archives_resp.status_code}")
        print("Response:", archives_resp.text)
        return None

    archives = archives_resp.json().get("archives", [])
    if not archives:
        print("No archives available.")
        return None

    latest_archive_url = archives[-1]
    archive_resp = requests.get(latest_archive_url, headers=HEADERS)
    if archive_resp.status_code != 200:
        print(f"Error fetching latest archive. Status code: {archive_resp.status_code}")
        print("Response:", archive_resp.text)
        return None

    games = archive_resp.json().get("games", [])
    if not games:
        print("No games found in the latest archive.")
        return None

    # Assumes games are in chronological order; take the last game.
    return games[-1]

def determine_game_details(game):
    """
    Determine opponent, result, game URL, formatted time control, current rating,
    and raw rating change (if provided) from the game data.
    """
    opponent = "Unknown"
    result = "Draw"  # Default result.
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
    return opponent, result, game_url, time_control_formatted, current_rating, raw_rating_change

def fetch_league_info():
    """
    Fetch the current league information for the user.
    Expected data includes:
      - division: contains "endTime" and nested "league" details
      - stats: contains current ranking ("ranking") and points ("trophyCount")
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

def send_discord_webhook(opponent, game_url, time_control, rating_change, result):
    """
    Send a Discord webhook message using an embed.
      - The embed's side color is green for wins, red for losses, and gray for draws.
      - The embed includes the tracked user's profile picture.
      - League information is appended: league name, place, and points.
      - If less than 1 day remains in the current league, a special notice pings <@774816976756539422>.
    """
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        print("WEBHOOK_URL is not set in environment variables.")
        return

    # Determine embed color.
    if result == "Win":
        color = 65280       # Green.
    elif result == "Loss":
        color = 16711680    # Red.
    else:
        color = 8421504     # Gray.

    avatar_url = get_profile_avatar()
    embed = {
        "author": {
            "name": CHESS_USERNAME,
            "icon_url": avatar_url
        },
        "title": "New game played!",
        "url": game_url,
        "color": color,
        "fields": [
            {"name": "Opponent", "value": opponent, "inline": True},
            {"name": "Time Control", "value": time_control, "inline": True},
            {"name": "Rating Change", "value": f"{rating_change:+}", "inline": True},
        ]
    }

    # Fetch and integrate league info.
    league_info = fetch_league_info()
    if league_info is not None:
        division = league_info.get("division", {})
        league_data = division.get("league", {})
        league_name = league_data.get("name", "Unknown")
        league_code = league_data.get("code", "").lower()
        # Use your repo's league image if available.
        league_image_url = f"https://raw.githubusercontent.com/sawyershoemaker/chess.com-tracker/main/leagues/{league_code}.png"
        stats = league_info.get("stats", {})
        league_place = stats.get("ranking", "N/A")
        league_points = stats.get("trophyCount", "N/A")
        embed["fields"].append({"name": "League", "value": league_name, "inline": True})
        embed["fields"].append({"name": "Place", "value": f"#{league_place}", "inline": True})
        embed["fields"].append({"name": "Points", "value": str(league_points), "inline": True})
        embed["thumbnail"] = {"url": league_image_url}

        # Check league deadline.
        current_time = int(time.time())
        end_time = division.get("endTime", 0)
        time_left = end_time - current_time
        advancement_threshold = ADVANCEMENT_THRESHOLDS.get(league_code, None)
        if advancement_threshold is not None and isinstance(league_points, (int, float)):
            points_needed = advancement_threshold - league_points
            if points_needed < 0:
                points_needed = 0
        else:
            points_needed = "N/A"
        if time_left < 86400:
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

def commit_last_game(game_url):
    """Commit and push the updated last game URL to the repository."""
    try:
        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)

        token = os.environ.get("TOKEN")
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/sawyershoemaker/chess.com-tracker.git"
            subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

        subprocess.run(["git", "add", LAST_GAME_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update last game URL"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Committed and pushed the updated last game URL.")
    except subprocess.CalledProcessError as e:
        print("Git command failed:", e)

def main():
    last_data = load_last_game_data()  # Expects keys: last_game_url, last_rating.
    last_game_url = last_data.get("last_game_url")
    last_rating = last_data.get("last_rating", None)

    latest_game = fetch_latest_game()
    if not latest_game:
        return

    current_game_url = latest_game.get("url", "")
    if current_game_url == last_game_url:
        print("No new game detected.")
        return

    opponent, result, game_url, time_control_formatted, current_rating, raw_rating_change = determine_game_details(latest_game)
    # Prefer the API's rating_change if available; otherwise, compute the difference.
    if raw_rating_change is not None:
        rating_change = raw_rating_change
    elif last_rating is not None:
        rating_change = current_rating - last_rating
    else:
        rating_change = 0

    send_discord_webhook(opponent, game_url, time_control_formatted, rating_change, result)
    save_last_game_data(current_game_url, current_rating)
    commit_last_game(current_game_url)

if __name__ == "__main__":
    main()
