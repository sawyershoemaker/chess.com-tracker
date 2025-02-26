# Chess.com Tracker

A GitHub Actions–powered project that monitors your Chess.com games and leagues, sending detailed Discord webhook notifications whenever new games are detected.

---

## Features

- **Automatic Game Tracking:**  
  Continuously checks your Chess.com public archives for new games (even if multiple new games appear) and sends a separate Discord webhook for each.

- **Detailed Game Information:**  
  Each webhook embed includes:
  - Opponent's name
  - Time control (formatted as "main | increment")
  - Rating change (using the API’s value when available or computed sequentially)
  - Termination method (e.g. "Win by resignation", "Draw by insufficient material") as the embed title
  - A footer with the game’s end time formatted in Eastern Standard Time (EST)

- **League Integration:**  
  Displays current league details with your custom Discord emojis:
  - League name (with emoji)
  - Your place (ranking)
  - League points

  Additionally, even if no new games are detected, the script updates your league information by deleting the previous league update message and sending a new one. The league webhook footer is formatted to show the division code along with the advancement threshold, for example:
  
  `S4EkVNBt3in    |    TOP 5 ADVANCE`
  
  (If no advancement is defined, it will display "no advancement").  
  If less than one day remains in the current league period and your ranking is below the threshold, an alert is added (pings a designated user) to indicate that time is running out for advancement.

- **Multiple Game Notifications:**  
  If the Chess.com API returns multiple new games at once, the script will send a separate webhook for each game.

- **Persistent Data:**  
  Uses a JSON file (`last_game.json`) to store processed game IDs, last rating data, league snapshot, and the league message ID so that duplicate notifications aren’t sent and alerts are triggered only once per league period.

- **GitHub Actions Workflow:**  
  Runs automatically on a schedule (every 5 minutes) and can be manually triggered, keeping your notifications up to date.

---

## Requirements

- **Chess.com Account:**  
  Make sure your Chess.com account is public so the API endpoints can be accessed.

- **Python 3.9 or higher:**  
  (for the built-in `zoneinfo` module)

- **Python Packages:**  
  - [requests](https://pypi.org/project/requests/)

---

## Setup

1. **Create the Repository:**  
   Create a new GitHub repository (or use an existing one) and add the following files:
   - `chess_tracker.py` – The main Python script.
   - `.github/workflows/chess-tracker.yml` – The GitHub Actions workflow file.

2. **Set Up Secrets:**  
   In your GitHub repository settings, navigate to **Settings > Secrets and variables > Actions** and add the following secrets:
   - **WEBHOOK_URL:** The full Discord webhook URL where notifications will be sent (e.g. `https://discord.com/api/webhooks/<id>/<token>`).
   - **TOKEN:** A personal access token with repo write access.

3. **Customize:**  
   - **Emoji Mapping:**  
     Update the `EMOJI_MAP` dictionary if your custom Discord emoji IDs or names change.
   - **Time Zone:**  
     The script uses EST for the game end time. You can modify this by changing the `ZoneInfo("America/New_York")` parameter in the code.

---

## Usage

- **Automatic Execution:**  
  The GitHub Actions workflow is configured to run every 5 minutes using a cron schedule. When new games are detected (based on the public Chess.com API), the script sends a webhook for each new game and also updates the league information.

- **Manual Trigger:**  
  You can also manually trigger the workflow from the GitHub Actions tab.

- **Persistent Data:**  
  Processed game IDs, last rating data, the league snapshot, and the league message ID are stored in `last_game.json`. This ensures that if multiple new games appear, each is processed only once and that the league update message is replaced with an up-to-date one.

---

## Troubleshooting

- **No New Game Detected:**  
  If the action logs “No new game detected,” it means that the latest game URL in the Chess.com archive matches one already stored in `last_game.json`. To test notifications, you can clear or edit that file.

- **API Update Frequency:**  
  Note that the Chess.com public API may update game data every 12 hours or so. If you notice delays in notifications, this might be the cause.

- **410 Gone Error:**  
  The script handles a 410 error (resource gone) gracefully. If you see this message, it means no archives are available. Ensure your account has public games.

---

Feel free to open an issue if you have any questions or run into problems!
