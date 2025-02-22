import os
import json
import subprocess
import requests

# Replace with your Chess.com username to track.
CHESS_USERNAME = "inseem"
ARCHIVES_URL = f"https://api.chess.com/pub/player/{CHESS_USERNAME}/games/archives"
LAST_GAME_FILE = "last_game.json"

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


def format_time_control(tc):
    """
    Convert a raw time control string (e.g. "600+5") into a human-readable format.
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
                seconds = main_time % 60
                return f"{minutes}m {seconds}s + {increment}s increment"
            except ValueError:
                return tc
        else:
            try:
                main_time = int(tc)
                minutes = main_time // 60
                seconds = main_time % 60
                return f"{minutes}m {seconds}s"
            except ValueError:
                return tc
    return tc


def fetch_latest_game():
    """Fetch the latest game from Chess.com archives."""
    # Fetch list of archives.
    archives_resp = requests.get(ARCHIVES_URL, headers=HEADERS)
    if archives_resp.status_code != 200:
        print(f"Error fetching archives. Status code: {archives_resp.status_code}")
        print("Response:", archives_resp.text)
        return None

    archives = archives_resp.json().get("archives", [])
    if not archives:
        print("No archives available.")
        return None

    # Pick the latest archive (last element).
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

    # Assumes games are in chronological order.
    return games[-1]


def determine_game_details(game):
    """
    Determine the opponent, result, game URL, formatted time control, and current rating
    from the game object.
    """
    opponent = "Unknown"
    result = "Draw"  # Default.
    current_rating = None

    if game["white"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["black"]["username"]
        current_rating = game["white"].get("rating")
        if game["white"]["result"] == "win":
            result = "Win"
        elif game["black"]["result"] == "win":
            result = "Loss"
    elif game["black"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["white"]["username"]
        current_rating = game["black"].get("rating")
        if game["black"]["result"] == "win":
            result = "Win"
        elif game["white"]["result"] == "win":
            result = "Loss"

    raw_time_control = game.get("time_control", "Unknown")
    time_control_formatted = format_time_control(raw_time_control)
    game_url = game.get("url", "No link available")
    return opponent, result, game_url, time_control_formatted, current_rating


def send_discord_webhook(opponent, result, game_url, time_control, rating_change):
    """
    Send a Discord webhook message using an embed.
    The embed color is green for wins, red for losses, and gray for draws.
    """
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        print("WEBHOOK_URL is not set in environment variables.")
        return

    # Set color based on game result.
    if result == "Win":
        color = 65280       # Green.
    elif result == "Loss":
        color = 16711680    # Red.
    else:
        color = 8421504     # Gray.

    embed = {
        "title": f"{CHESS_USERNAME} played a game!",
        "url": game_url,
        "color": color,
        "fields": [
            {"name": "Opponent", "value": opponent, "inline": True},
            {"name": "Result", "value": result, "inline": True},
            {"name": "Time Control", "value": time_control, "inline": True},
            {"name": "Rating Change", "value": f"{rating_change:+}", "inline": True},
        ]
    }
    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}

    resp = requests.post(webhook_url, json=payload, headers=headers)
    if resp.status_code in (200, 204):
        print("Webhook sent successfully.")
    else:
        print(f"Failed to send webhook. Status code: {resp.status_code}")


def commit_last_game(game_url):
    """Commit and push the updated last game URL to the repository."""
    try:
        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)

        # If GITHUB_TOKEN is available, update the remote URL for authenticated push.
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            # Adjust the remote URL below to match your repository.
            remote_url = f"https://x-access-token:{token}@github.com/sawyershoemaker/chess.com-tracker.git"
            subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

        subprocess.run(["git", "add", LAST_GAME_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update last game URL"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Committed and pushed the updated last game URL.")
    except subprocess.CalledProcessError as e:
        print("Git command failed:", e)


def main():
    last_data = load_last_game_data()  # Contains keys: last_game_url and last_rating.
    last_game_url = last_data.get("last_game_url")
    last_rating = last_data.get("last_rating")

    latest_game = fetch_latest_game()
    if not latest_game:
        return

    current_game_url = latest_game.get("url", "")
    if current_game_url == last_game_url:
        print("No new game detected.")
        return

    opponent, result, game_url, time_control_formatted, current_rating = determine_game_details(latest_game)
    if current_rating is None:
        print("Current rating not found. Cannot compute rating change.")
        current_rating = 0

    # Compute rating change using stored last rating.
    if last_rating is not None:
        rating_change = current_rating - last_rating
    else:
        rating_change = 0

    send_discord_webhook(opponent, result, game_url, time_control_formatted, rating_change)
    save_last_game_data(current_game_url, current_rating)
    commit_last_game(current_game_url)


if __name__ == "__main__":
    main()
