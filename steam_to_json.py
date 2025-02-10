import os

import requests
import json
import datetime
import time

from dotenv import load_dotenv

load_dotenv()

# ================================
# 请在此处替换为你自己的信息
# ================================
STEAM_API_KEY = os.getenv("STEAM_API_KEY")  # 你的 Steam API 密钥
STEAM_USER_ID = os.getenv("STEAM_USER_ID")  # 你的 Steam 用户ID
OUTPUT_JSON_FILE = os.getenv("JSON_FILE") or "steam_games.json"  # 输出 JSON 文件名称
# ================================

def get_steam_games():
    """
    通过 Steam API 获取当前用户的所有游戏信息。
    参数 include_appinfo 返回游戏名称等信息，
    include_played_free_games 用于包含免费游戏。
    """
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": STEAM_API_KEY,
        "steamid": STEAM_USER_ID,
        "include_appinfo": True,
        "include_played_free_games": True,
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        games = data.get("response", {}).get("games", [])
        return games
    else:
        print("获取 Steam 游戏数据失败，状态码：", response.status_code)
        return []

def get_game_banner(app_id):
    """
    构造游戏封面图片 URL（作为截图示例）。
    注意：Steam API 并没有直接提供游戏内截图接口，
    这里使用的是 Steam 商店页面的 header 图片。
    """
    banner_url = f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg"
    return banner_url

def get_game_icon(app_id, img_icon_url):
    """
    构造游戏图标 URL（如果存在）。
    """
    if img_icon_url:
        return f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/{app_id}/{img_icon_url}.jpg"
    return None

def get_game_logo(app_id, img_logo_url):
    """
    构造游戏 Logo URL（如果存在）。
    """
    if img_logo_url:
        return f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/{app_id}/{img_logo_url}.jpg"
    return None

def get_player_achievements(app_id):
    """
    尝试获取某个游戏的成就数据，返回字典：
      {"achievements_unlocked": 已解锁成就数量, "achievements_total": 成就总数}
    若该游戏不支持或获取出错，则返回空字典。
    """
    url = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
    params = {
        "appid": app_id,
        "key": STEAM_API_KEY,
        "steamid": STEAM_USER_ID
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            playerstats = data.get("playerstats", {})
            # 检查是否支持成就并成功获取数据
            if playerstats.get("success", False) and "achievements" in playerstats:
                achievements = playerstats["achievements"]
                total = len(achievements)
                unlocked = sum(1 for ach in achievements if ach.get("achieved", 0) == 1)
                return {"achievements_unlocked": unlocked, "achievements_total": total}
        return {}
    except Exception as e:
        print(f"获取 AppID {app_id} 成就数据时出错: {e}")
        return {}

def process_games(games):
    """
    遍历游戏列表并处理每个游戏的信息。
    结果中包含以下字段：
      - Game Name: 游戏名称
      - AppID: 应用 ID
      - Playtime Hours: 游玩时长（小时，保留一位小数）
      - Playtime Minutes: 原始游玩时长（分钟）
      - Last Played: 最后一次启动时间（ISO 格式字符串）
      - Banner: 游戏封面图片 URL
      - Icon: 游戏图标 URL（如存在）
      - Logo: 游戏 Logo URL（如存在）
      - Achievements Unlocked / Achievements Total：成就信息（如可获取）
    并按照游戏总游玩时长降序排列（最长的在前面）。
    """
    # 按 playtime_forever 降序排序
    games_sorted = sorted(games, key=lambda x: x.get("playtime_forever", 0), reverse=True)
    results = []
    for game in games_sorted:
        app_id = game.get("appid")
        game_name = game.get("name", "Unknown Game")
        playtime_minutes = game.get("playtime_forever", 0)
        playtime_hours = round(playtime_minutes / 60, 1)
        rtime_last_played = game.get("rtime_last_played")
        if rtime_last_played:
            last_played_date = datetime.datetime.fromtimestamp(rtime_last_played).isoformat()
        else:
            last_played_date = None

        # 构造各类图片 URL
        banner_url = get_game_banner(app_id)
        icon_url = get_game_icon(app_id, game.get("img_icon_url"))
        logo_url = get_game_logo(app_id, game.get("img_logo_url"))

        # 尝试获取成就数据
        achievements = get_player_achievements(app_id)
        # 延时，避免频繁调用 API
        time.sleep(0.5)

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

        results.append(game_info)
    return results

def save_to_json(data, filename):
    """
    将数据保存为 JSON 文件，便于后续查看或处理。
    """
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"数据已保存到 {filename}")

def main():
    print("正在获取 Steam 游戏数据...")
    games = get_steam_games()
    print(f"共获取到 {len(games)} 个游戏。")
    processed_games = process_games(games)
    save_to_json(processed_games, OUTPUT_JSON_FILE)

if __name__ == "__main__":
    main()