import os
import json
import subprocess
import requests
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Replace with your Chess.com username.
CHESS_USERNAME = "inseem"
ARCHIVES_URL = f"https://api.chess.com/pub/player/{CHESS_USERNAME}/games/archives"
LAST_GAME_FILE = "last_game.json"

# Advancement thresholds for league advancement.
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

# Mapping for rating emojis based on game category.
RATING_EMOJI_MAP = {
    "rapid": "<:rapid:1343711691367649442>",
    "bullet": "<:bullet:1343711689182281738>",
    "daily": "<:daily:1343711689832665193>",
    "blitz": "<:blitz:1343711687865405531>"
}

# Headers to mimic a real browser.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.chess.com/"
}

def extract_game_id(url):
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else url

def categorize_time_control(tc):
    try:
        main_time = int(tc.split('+')[0])
    except:
        return "unknown"
    if main_time < 180:
        return "bullet"
    elif main_time < 480:
        return "blitz"
    elif main_time < 1500:
        return "rapid"
    else:
        return "daily"

def load_last_game_data():
    try:
        with open(LAST_GAME_FILE, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Warning: last_game.json contains invalid JSON. Resetting data.")
        return {}

def save_last_game_data(data):
    with open(LAST_GAME_FILE, "w") as f:
        json.dump(data, f)
    print("Persistent data updated:", data)

def get_profile_avatar():
    profile_url = f"https://api.chess.com/pub/player/{CHESS_USERNAME}"
    try:
        resp = requests.get(profile_url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.json().get("avatar", "")
        else:
            print("Error fetching profile:", resp.status_code)
    except Exception as e:
        print("Exception fetching profile:", e)
    return ""

def format_time_control(tc):
    if isinstance(tc, str):
        if tc.lower() == "unlimited":
            return "Unlimited"
        if '+' in tc:
            try:
                main_time, increment = tc.split('+', 1)
                main_time = int(main_time)
                increment = int(increment)
                minutes = main_time // 60
                return f"{minutes} | {increment}"
            except:
                return tc
        else:
            try:
                main_time = int(tc)
                minutes = main_time // 60
                return f"{minutes} | 0"
            except:
                return tc
    return tc

def fetch_latest_games():
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
    return games

def parse_termination(pgn):
    for line in pgn.splitlines():
        if line.startswith("[Termination "):
            start = line.find('"')
            end = line.rfind('"')
            if start != -1 and end != -1 and end > start:
                return line[start+1:end]
    return "Unknown"

def determine_game_details(game):
    opponent = "Unknown"
    result = "Draw"
    current_rating = 0
    raw_rating_change = None
    opponent_rating = "N/A"
    if game["white"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["black"]["username"]
        current_rating = game["white"].get("rating", 0)
        raw_rating_change = game["white"].get("rating_change", None)
        opponent_rating = game["black"].get("rating", "N/A")
        if game["white"]["result"] == "win":
            result = "Win"
        elif game["black"]["result"] == "win":
            result = "Loss"
    elif game["black"]["username"].lower() == CHESS_USERNAME.lower():
        opponent = game["white"]["username"]
        current_rating = game["black"].get("rating", 0)
        raw_rating_change = game["black"].get("rating_change", None)
        opponent_rating = game["white"].get("rating", "N/A")
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
            current_rating, raw_rating_change, termination, end_time, raw_time_control, opponent_rating)

def fetch_league_info():
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

def get_league_snapshot(league_info):
    if not league_info:
        return None
    division = league_info.get("division", {})
    league_data = division.get("league", {})
    stats = league_info.get("stats", {})
    return {
        "league_code": league_data.get("code", "").lower(),
        "league_name": league_data.get("name", "Unknown"),
        "ranking": stats.get("ranking", "N/A"),
        "points": stats.get("trophyCount", "N/A"),
        "endTime": division.get("endTime", None),
        "division_name": division.get("name", "Unknown")
    }

def delete_league_message(message_id):
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        return
    delete_url = f"{webhook_url}/messages/{message_id}?wait=true"
    print(f"Attempting to delete message: {delete_url}")
    resp = requests.delete(delete_url, headers={"Content-Type": "application/json"})
    if resp.status_code in (200, 204):
        print("Deleted old league webhook message.")
    else:
        print(f"Failed to delete old league webhook message. Status code: {resp.status_code}")
        print("Response:", resp.text)

def update_league_webhook(league_info):
    data = load_last_game_data()
    stored_message_id = data.get("league_message_id")
    if stored_message_id:
        delete_league_message(stored_message_id)
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        print("WEBHOOK_URL not set.")
        return
    send_url = webhook_url + "?wait=true"
    division = league_info.get("division", {})
    league_data = division.get("league", {})
    league_name = league_data.get("name", "Unknown")
    league_code = league_data.get("code", "").lower()
    league_emoji = EMOJI_MAP.get(league_code, "")
    stats = league_info.get("stats", {})
    league_place = stats.get("ranking", "N/A")
    league_points = stats.get("trophyCount", "N/A")
    division_url = division.get("divisionUrl")
    if not division_url:
        division_url = f"https://www.chess.com/leagues/{league_code}"
    end_time = division.get("endTime", None)
    if end_time is not None:
        end_time_str = f"<t:{end_time}:f> (<t:{end_time}:R>)"
    else:
        end_time_str = "Unknown"
    current_time = int(time.time())
    time_left = end_time - current_time if end_time is not None else None
    cutoff = ADVANCEMENT_THRESHOLDS.get(league_code)
    alert_needed = False
    try:
        ranking_int = int(league_place)
        if cutoff is not None and ranking_int > cutoff:
            if end_time is not None and (end_time - current_time) < 86400:
                alert_needed = True
    except:
        pass
    fields = [
        {"name": "League", "value": f"{league_emoji} {league_name}", "inline": True},
        {"name": "Position", "value": f"#{league_place}", "inline": True},
        {"name": "Points", "value": str(league_points), "inline": True},
        {"name": "League Ends", "value": end_time_str, "inline": False},
    ]
    if alert_needed:
        fields.append({
            "name": "Alert",
            "value": f"<@774816976756539422> Only 1 day left! Your ranking is #{league_place}. You need to be in top {cutoff} to advance.",
            "inline": False
        })
    division_name = division.get("name", "Unknown")
    if cutoff is None:
        footer_text = f"{division_name} **|** **no advancement**"
    else:
        footer_text = f"{division_name}      |        TOP {cutoff} ADVANCE"
    embed = {
        "author": {
            "name": f"{CHESS_USERNAME} League Update",
            "icon_url": get_profile_avatar()
        },
        "color": 3447003,
        "fields": fields,
        "footer": {"text": footer_text}
    }
    for attempt in range(3):
        resp = requests.post(send_url, json={"embeds": [embed]}, headers={"Content-Type": "application/json"})
        if resp.status_code in (200, 204):
            try:
                response_json = resp.json()
                new_message_id = response_json.get("id")
                if not new_message_id:
                    new_message_id = "0"
                print("League webhook updated successfully. New message id:", new_message_id)
                data["league_message_id"] = new_message_id
                data["league_snapshot"] = get_league_snapshot(league_info)
                data["last_update"] = int(time.time())
                save_last_game_data(data)
            except Exception as e:
                print("Error parsing response JSON:", e)
            break
        elif resp.status_code == 429:
            print("Rate limited on league webhook update. Retrying in 3 seconds...")
            time.sleep(3)
        else:
            print(f"Failed to update league webhook. Status code: {resp.status_code}")
            break
    time.sleep(1)

def send_discord_webhook(opponent, game_url, time_control, rating_change, result, termination,
                         end_time, category, current_rating, opponent_rating, league_info=None, add_alert=False):
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
    rating_emoji = RATING_EMOJI_MAP.get(category, "")
    description_text = f"**({current_rating}{rating_emoji}) ({rating_change:+})**"
    embed = {
        "author": {
            "name": CHESS_USERNAME,
            "icon_url": avatar_url
        },
        "title": termination,
        "description": description_text,
        "url": game_url,
        "color": color,
        "fields": [
            {"name": "Opponent", "value": f"{opponent} ({opponent_rating})", "inline": True},
            {"name": "Time Control", "value": "\t" + time_control, "inline": True},
        ]
    }
    if end_time is not None:
        try:
            est_time = datetime.fromtimestamp(end_time, ZoneInfo("America/New_York"))
            formatted_time = est_time.strftime("%Y-%m-%d %I:%M %p EST")
            embed["footer"] = {"text": f"Game played: {formatted_time}"}
        except Exception as e:
            print("Error formatting end_time:", e)
    for attempt in range(3):
        resp = requests.post(webhook_url, json={"embeds": [embed]}, headers={"Content-Type": "application/json"})
        if resp.status_code in (200, 204):
            print("Webhook sent successfully.")
            break
        elif resp.status_code == 429:
            print("Rate limited. Retrying in 3 seconds...")
            time.sleep(3)
        else:
            print(f"Failed to send webhook. Status code: {resp.status_code}")
            break
    time.sleep(1)

def commit_last_game(data):
    data["last_update"] = int(time.time())
    save_last_game_data(data)
    try:
        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)
        token = os.environ.get("TOKEN")
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/sawyershoemaker/chess.com-tracker.git"
            subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        subprocess.run(["git", "add", LAST_GAME_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Force update persistent data"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Committed and pushed updated persistent data.")
    except subprocess.CalledProcessError as e:
        print("Git command failed:", e)

def main():
    data = load_last_game_data()
    processed_games = data.get("processed_games", [])
    last_rating_dict = data.get("last_rating", {})
    alert_info = data.get("alert_info", {})
    games = fetch_latest_games()
    if not games:
        return
    league_info = fetch_league_info()
    new_game_found = False
    for game in games:
        game_url = game.get("url", "")
        game_id = extract_game_id(game_url)
        if game_id in processed_games:
            continue
        (opponent, result, game_url, time_control_formatted, current_rating,
         raw_rating_change, termination, end_time, raw_time_control, opponent_rating) = determine_game_details(game)
        category = categorize_time_control(raw_time_control)
        if raw_rating_change is not None:
            rating_change = raw_rating_change
        else:
            previous_rating = last_rating_dict.get(category)
            if previous_rating is not None:
                rating_change = current_rating - previous_rating
            else:
                rating_change = 0
        last_rating_dict[category] = current_rating
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
        send_discord_webhook(opponent, game_url, time_control_formatted, rating_change,
                               result, termination, end_time, category, current_rating, opponent_rating, league_info, add_alert)
        processed_games.append(game_id)
        new_game_found = True
    data["processed_games"] = processed_games
    data["last_rating"] = last_rating_dict
    save_last_game_data(data)
    update_league_webhook(league_info)
    commit_last_game(load_last_game_data())
    
if __name__ == "__main__":
    main()