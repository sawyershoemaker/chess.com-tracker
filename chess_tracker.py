import os
import json
import subprocess
import requests

# replace with account username to track
CHESS_USERNAME = "chess_username"
ARCHIVES_URL = f"https://api.chess.com/pub/player/{CHESS_USERNAME}/games/archives"
LAST_GAME_FILE = "last_game.json"


def load_last_game_url():
    """Load the last recorded game URL from file."""
    try:
        with open(LAST_GAME_FILE, "r") as f:
            data = json.load(f)
            return data.get("last_game_url")
    except FileNotFoundError:
        return None


def save_last_game_url(game_url):
    """Save the latest game URL to file."""
    with open(LAST_GAME_FILE, "w") as f:
        json.dump({"last_game_url": game_url}, f)


def fetch_latest_game():
    """Fetch the latest game from Chess.com archives."""
    archives_resp = requests.get(ARCHIVES_URL)
    if archives_resp.status_code != 200:
        print("Error fetching archives.")
        return None

    archives = archives_resp.json().get("archives", [])
    if not archives:
        print("No archives available.")
        return None

    # pick latest archive
    latest_archive_url = archives[-1]
    archive_resp = requests.get(latest_archive_url)
    if archive_resp.status_code != 200:
        print("Error fetching latest archive.")
        return None

    games = archive_resp.json().get("games", [])
    if not games:
        print("No games found in the latest archive.")
        return None

    # assumes games are in chronological order
    return games[-1]


def determine_game_details(game):
    opponent = None
    result = "Draw"  # default
    rating_change = 0

    if game["white"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["black"]["username"]
        if game["white"]["result"] == "win":
            result = "Win"
        elif game["black"]["result"] == "win":
            result = "Loss"
        rating_change = game["white"].get("rating_change", 0)
    elif game["black"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["white"]["username"]
        if game["black"]["result"] == "win":
            result = "Win"
        elif game["white"]["result"] == "win":
            result = "Loss"
        rating_change = game["black"].get("rating_change", 0)
    else:
        # should not happen if you are tracking your own games.
        opponent = "Unknown"

    time_control = game.get("time_control", "Unknown")
    game_url = game.get("url", "No link available")
    return opponent, result, game_url, time_control, rating_change


def send_discord_webhook(opponent, result, game_url, time_control, rating_change):
    """Send a formatted message to Discord using a webhook."""
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        print("WEBHOOK_URL is not set in environment variables.")
        return

    message = (
        f"**{CHESS_USERNAME}** played a game!\n"
        f"**Opponent:** {opponent}\n"
        f"**Result:** {result}\n"
        f"**Game Link:** {game_url}\n"
        f"**Time Control:** {time_control}\n"
        f"**Rating Change:** {rating_change:+}"
    )
    payload = {"content": message}
    headers = {"Content-Type": "application/json"}

    resp = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    if resp.status_code in (200, 204):
        print("Webhook sent successfully.")
    else:
        print(f"Failed to send webhook. Status code: {resp.status_code}")


def commit_last_game(game_url):
    """Commit and push the updated last game URL to the repository."""
    try:
        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "add", LAST_GAME_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update last game URL"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Committed and pushed the updated last game URL.")
    except subprocess.CalledProcessError as e:
        print("Git command failed:", e)


def main():
    last_game_url = load_last_game_url()
    latest_game = fetch_latest_game()
    if not latest_game:
        return

    current_game_url = latest_game.get("url", "")
    if current_game_url == last_game_url:
        print("No new game detected.")
        return

    opponent, result, game_url, time_control, rating_change = determine_game_details(latest_game)
    send_discord_webhook(opponent, result, game_url, time_control, rating_change)
    save_last_game_url(current_game_url)
    commit_last_game(current_game_url)


if __name__ == "__main__":
    main()
