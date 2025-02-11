import os
import json
import requests
import time
import datetime
from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
STEAM_USER_ID = os.getenv("STEAM_USER_ID")
OUTPUT_JSON_FILE = os.getenv("JSON_FILE", "steam_games.json")


def fetch_steam_games():
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": STEAM_API_KEY,
        "steamid": STEAM_USER_ID,
        "include_appinfo": True,
        "include_played_free_games": True
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        games = data.get("response", {}).get("games", [])
        return games
    else:
        print("获取 Steam 游戏数据失败，状态码：", response.status_code)
        return []


def process_steam_games(games):
    processed = []
    for game in games:
        app_id = game.get("appid")
        game_name = game.get("name", "Unknown Game")
        playtime_minutes = game.get("playtime_forever", 0)
        playtime_hours = round(playtime_minutes / 60, 1)
        rtime_last_played = game.get("rtime_last_played")
        if rtime_last_played:
            last_played_date = datetime.datetime.fromtimestamp(rtime_last_played).isoformat()
        else:
            last_played_date = None

        # 构造 Banner 图片 URL（示例使用 Steam 商店页面的 header 图片）
        banner_url = f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg"

        # 注意：成就数据这里可以扩展获取，此处先置为 None
        processed.append({
            "Game Name": game_name,
            "Playtime Hours": playtime_hours,
            "Last Played": last_played_date,
            "Banner": banner_url,
            "Achievements Unlocked": game.get("achievements_unlocked"),  # 如有则填入，否则为 None
            "Achievements Total": game.get("achievements_total")
        })
    return processed


def fetch_and_save_steam_games():
    games = fetch_steam_games()
    processed = process_steam_games(games)
    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=4)
    print(f"已保存 {len(processed)} 个游戏数据到 {OUTPUT_JSON_FILE}")


if __name__ == "__main__":
    fetch_and_save_steam_games()
