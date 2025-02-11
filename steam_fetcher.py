import os
import json
import requests
import time
import datetime
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
STEAM_USER_ID = os.getenv("STEAM_USER_ID")
OUTPUT_JSON_FILE = os.getenv("JSON_FILE") or "steam_games.json"

def get_session():
    """创建一个带有重试机制的 requests Session 对象"""
    session = requests.Session()
    retry = Retry(
        total=5,               # 最大重试次数
        backoff_factor=1,      # 重试等待时间会依次为 1, 2, 4, 8, ... 秒
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"]  # 替代 method_whitelist 参数
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def get_steam_games(session):
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": STEAM_API_KEY,
        "steamid": STEAM_USER_ID,
        "include_appinfo": True,
        "include_played_free_games": True,
    }
    response = session.get(url, params=params, timeout=10)
    if response.status_code == 200:
        data = response.json()
        games = data.get("response", {}).get("games", [])
        return games
    else:
        print("获取 Steam 游戏数据失败，状态码：", response.status_code)
        return []

def get_game_banner(app_id):
    banner_url = f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg"
    return banner_url

def get_game_icon(app_id, img_icon_url):
    if img_icon_url:
        return f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/{app_id}/{img_icon_url}.jpg"
    return None

def get_game_logo(app_id, img_logo_url):
    if img_logo_url:
        return f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/{app_id}/{img_logo_url}.jpg"
    return None

def get_player_achievements(app_id, session):
    url = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
    params = {
        "appid": app_id,
        "key": STEAM_API_KEY,
        "steamid": STEAM_USER_ID
    }
    try:
        response = session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            playerstats = data.get("playerstats", {})
            if playerstats.get("success", False) and "achievements" in playerstats:
                achievements = playerstats["achievements"]
                total = len(achievements)
                unlocked = sum(1 for ach in achievements if ach.get("achieved", 0) == 1)
                return {"achievements_unlocked": unlocked, "achievements_total": total}
        return {}
    except Exception as e:
        print(f"获取 AppID {app_id} 成就数据时出错: {e}")
        return {}

def process_games(games, session):
    processed = []
    # 按 playtime_forever 降序排序
    games_sorted = sorted(games, key=lambda x: x.get("playtime_forever", 0), reverse=True)
    for idx, game in enumerate(games_sorted, 1):
        app_id = game.get("appid")
        game_name = game.get("name", "Unknown Game")
        playtime_minutes = game.get("playtime_forever", 0)
        playtime_hours = round(playtime_minutes / 60, 1)
        rtime_last_played = game.get("rtime_last_played")
        if rtime_last_played:
            last_played_date = datetime.datetime.fromtimestamp(rtime_last_played).isoformat()
        else:
            last_played_date = None

        banner_url = get_game_banner(app_id)
        icon_url = get_game_icon(app_id, game.get("img_icon_url"))
        logo_url = get_game_logo(app_id, game.get("img_logo_url"))

        achievements = get_player_achievements(app_id, session)
        time.sleep(0.5)  # 避免请求过于频繁

        game_info = {
            "Game Name": game_name,
            "AppID": app_id,
            "Playtime Hours": playtime_hours,
            "Playtime Minutes": playtime_minutes,
            "Last Played": last_played_date,
            "Banner": banner_url,
            "Icon": icon_url,
            "Logo": logo_url,
        }
        if achievements:
            game_info["Achievements Unlocked"] = achievements.get("achievements_unlocked")
            game_info["Achievements Total"] = achievements.get("achievements_total")
        processed.append(game_info)

        print(f"[{idx}/{len(games_sorted)}] 处理游戏: {game_name} (AppID: {app_id})")
    return processed

def save_to_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"数据已保存到 {filename}")

def fetch_and_save_steam_games():
    session = get_session()
    print("正在获取 Steam 游戏数据...")
    games = get_steam_games(session)
    print(f"共获取到 {len(games)} 个游戏。")
    processed_games = process_games(games, session)
    save_to_json(processed_games, OUTPUT_JSON_FILE)

if __name__ == "__main__":
    fetch_and_save_steam_games()
