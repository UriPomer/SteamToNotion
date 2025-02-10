import os
import json
import requests
import time
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量（如果使用 .env 文件）
load_dotenv()

# 从环境变量中获取配置参数
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
INPUT_JSON_FILE = os.getenv("JSON_FILE", "steam_games.json")

NOTION_VERSION = "2022-06-28"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

def find_existing_page(game_name):
    """
    根据游戏名称查询数据库中是否已有对应页面。
    如果存在，则返回整个页面数据；否则返回 None。
    """
    query_url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    query_payload = {
        "filter": {
            "property": "名称",
            "title": {
                "equals": game_name
            }
        }
    }
    response = requests.post(query_url, headers=HEADERS, json=query_payload)
    if response.status_code != 200:
        print("查询数据库失败：", response.text)
        return None

    data = response.json()
    results = data.get("results", [])
    if results:
        return results[0]  # 假设游戏名称唯一，取第一个匹配项
    return None

def extract_page_properties(page):
    """
    从 Notion 页面数据中提取以下属性的值：
      - 名称（title）
      - 游玩时长（number）
      - 上一次游玩时间（date，取 start 字段）
      - Banner（链接字段）
      - 成就数（rich_text，拼接文本）
      - cover（页面封面的外部链接）
    返回一个字典，其键与本地 JSON 中对应字段一致。
    """
    props = page.get("properties", {})

    # 提取“名称”
    title_items = props.get("名称", {}).get("title", [])
    name = "".join(item.get("plain_text", "") for item in title_items).strip()

    # 提取“游玩时长”
    playtime = props.get("游玩时长", {}).get("number", None)

    # 提取“上一次游玩时间”
    last_played = None
    date_prop = props.get("上一次游玩时间", {}).get("date")
    if date_prop:
        last_played = date_prop.get("start", None)

    # 提取“Banner”
    banner = props.get("Banner", {}).get("url", "").strip()

    # 提取“成就数”
    achievement_items = props.get("成就数", {}).get("rich_text", [])
    achievement_str = "".join(item.get("plain_text", "") for item in achievement_items).strip()

    # 提取页面封面（cover）的链接（可能为 external 或 file 类型）
    cover = ""
    if page.get("cover"):
        if page["cover"].get("external"):
            cover = page["cover"]["external"].get("url", "").strip()
        elif page["cover"].get("file"):
            cover = page["cover"]["file"].get("url", "").strip()

    return {
        "Game Name": name,
        "Playtime Hours": playtime,
        "Last Played": last_played,
        "Banner": banner,
        "成就数": achievement_str,
        "cover": cover
    }

def build_properties(game):
    """
    根据本地 JSON 中的 game 数据构造 Notion 页面属性字典。
    “成就数”格式为 "已解锁/总数"。
    仅当本地数据中有有效值时才包含对应属性，避免传入空对象。
    """
    props = {}

    # 名称（必填，title 类型）
    game_name = game.get("Game Name", "").strip()
    props["名称"] = {
        "title": [
            {"text": {"content": game_name}}
        ]
    }

    # 游玩时长（必填，number 类型）
    props["游玩时长"] = {
        "number": game.get("Playtime Hours", 0)
    }

    # 上一次游玩时间（date 类型），仅当有值时才包含
    last_played = game.get("Last Played")
    if last_played:
        props["上一次游玩时间"] = {
            "date": {"start": last_played}
        }
    # 如果数据库要求此项必填而本地无数据，则可考虑提供默认值，例如：
    # else:
    #     props["上一次游玩时间"] = {"date": {"start": "1970-01-01"}}

    # Banner（必填，link 类型）
    banner = game.get("Banner", "").strip()
    props["Banner"] = {
        "url": banner
    }

    # 成就数（必填，rich_text 类型），格式 "已解锁/总数"
    ach_unlocked = game.get("Achievements Unlocked")
    ach_total = game.get("Achievements Total")
    achievement_str = f"{ach_unlocked}/{ach_total}" if (ach_unlocked is not None and ach_total is not None) else ""
    props["成就数"] = {
        "rich_text": [
            {"text": {"content": achievement_str.strip()}}
        ]
    }
    return props

def normalize_value(key, value):
    """
    对字符串使用 strip()；对于日期（上一次游玩时间），如果包含 "T" 则只取日期部分。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        val = value.strip()
        if key in ["Last Played", "上一次游玩时间"] and "T" in val:
            return val.split("T")[0]
        return val
    return value

def properties_equal(existing_props, new_props):
    """
    比较从 Notion 页面提取的属性与本地构造的属性（包含 cover 链接）。
    对比前对字符串做归一化处理。
    """
    keys = ["Game Name", "Playtime Hours", "Last Played", "Banner", "成就数", "cover"]
    for key in keys:
        exist = normalize_value(key, existing_props.get(key))
        new = normalize_value(key, new_props.get(key))
        if exist != new:
            print(f"差异检测：属性 '{key}' 不同，现有：'{exist}'，新值：'{new}'")
            return False
    return True

def create_page(game):
    """
    创建新的 Notion 页面，使用本地 game 数据，并将 cover 设置为 Banner 链接。
    """
    url = "https://api.notion.com/v1/pages"
    properties = build_properties(game)
    banner_url = game.get("Banner", "").strip()
    data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        # 设置页面封面为 Banner 链接
        "cover": {
            "external": {"url": banner_url}
        }
    }
    response = requests.post(url, headers=HEADERS, json=data)
    if response.status_code in (200, 201):
        print(f"创建页面 '{game.get('Game Name')}' 成功")
    else:
        print(f"创建页面 '{game.get('Game Name')}' 失败，状态码: {response.status_code}")
        print(response.text)

def update_page(page_id, game):
    """
    更新已存在页面，将属性更新为本地 game 数据，并尝试更新封面为 Banner 链接。
    """
    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    properties = build_properties(game)
    banner_url = game.get("Banner", "").strip()
    data = {
        "properties": properties,
        "cover": {
            "external": {"url": banner_url}
        }
    }
    response = requests.patch(update_url, headers=HEADERS, json=data)
    if response.status_code in (200, 201):
        print(f"更新页面 '{game.get('Game Name')}' 成功")
    else:
        print(f"更新页面 '{game.get('Game Name')}' 失败，状态码: {response.status_code}")
        print(response.text)

def sync_games():
    """
    同步 JSON 文件中的游戏数据到 Notion：
      - 如果页面不存在，则创建新页面；
      - 如果页面存在，先提取现有属性（含 cover 链接）与本地数据比较：
          * 若所有属性一致，则跳过更新；
          * 若存在差异，则更新页面。
    """
    try:
        with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
            games = json.load(f)
    except Exception as e:
        print("读取 JSON 文件失败：", e)
        return

    print(f"共读取到 {len(games)} 个游戏信息。")
    for game in games:
        game_name = game.get("Game Name", "").strip()
        if not game_name:
            continue

        # 构造本地数据用于比较，新增 cover 字段与 Banner 相同
        new_props = {
            "Game Name": game.get("Game Name", "").strip(),
            "Playtime Hours": game.get("Playtime Hours", 0),
            "Last Played": game.get("Last Played"),
            "Banner": game.get("Banner", "").strip(),
            "成就数": f"{game.get('Achievements Unlocked')}/{game.get('Achievements Total')}"
                        if game.get("Achievements Unlocked") is not None and game.get("Achievements Total") is not None else "",
            "cover": game.get("Banner", "").strip()
        }

        existing_page = find_existing_page(game_name)
        if existing_page:
            existing_props = extract_page_properties(existing_page)
            if properties_equal(existing_props, new_props):
                print(f"'{game_name}' 属性无变化，跳过更新。")
            else:
                print(f"'{game_name}' 检测到属性变化，更新页面。")
                update_page(existing_page["id"], game)
        else:
            print(f"'{game_name}' 页面不存在，创建新页面。")
            create_page(game)
        time.sleep(0.3)

if __name__ == "__main__":
    sync_games()
