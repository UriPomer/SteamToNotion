import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
INPUT_JSON_FILE = os.getenv("JSON_FILE", "steam_games.json")
MAPPING_FILE = os.getenv("MAPPING_FILE", "mapping.json")

NOTION_VERSION = "2022-06-28"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}


def load_mapping():
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_properties(game, mapping):
    props = {}
    for local_field, map_info in mapping.items():
        notion_field = map_info.get("notion_field")
        field_type = map_info.get("type")
        if "format" in map_info:
            fmt = map_info["format"]
            value = fmt.format(**game)
        else:
            value = game.get(local_field, "")
        # 根据类型构造 Notion 属性格式
        if field_type == "title":
            props[notion_field] = {"title": [{"text": {"content": str(value)}}]}
        elif field_type == "number":
            props[notion_field] = {"number": value}
        elif field_type == "date":
            props[notion_field] = {"date": {"start": value}}
        elif field_type == "url":
            props[notion_field] = {"url": str(value)}
        elif field_type == "rich_text":
            props[notion_field] = {"rich_text": [{"text": {"content": str(value)}}]}
        else:
            props[notion_field] = {"rich_text": [{"text": {"content": str(value)}}]}
    return props


def find_existing_page(game_name, mapping):
    # 从 mapping 中找到对应名称字段
    game_name_field = None
    for local_field, map_info in mapping.items():
        if map_info.get("type") == "title":
            game_name_field = map_info.get("notion_field")
            break
    if not game_name_field:
        print("未在映射中找到游戏名称字段！")
        return None

    query_url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    query_payload = {
        "filter": {
            "property": game_name_field,
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
    return results[0] if results else None


def extract_page_properties(page, mapping):
    props = {}
    for local_field, map_info in mapping.items():
        notion_field = map_info.get("notion_field")
        field_type = map_info.get("type")
        if notion_field in page.get("properties", {}):
            prop = page["properties"][notion_field]
            if field_type == "title":
                title_items = prop.get("title", [])
                value = "".join(item.get("plain_text", "") for item in title_items).strip()
            elif field_type == "number":
                value = prop.get("number")
            elif field_type == "date":
                date_obj = prop.get("date", {})
                value = date_obj.get("start")
            elif field_type == "url":
                value = prop.get("url", "").strip()
            elif field_type == "rich_text":
                rich_items = prop.get("rich_text", [])
                value = "".join(item.get("plain_text", "") for item in rich_items).strip()
            else:
                value = ""
            props[local_field] = str(value).strip()
    # 同时提取页面封面（cover），我们假设封面应与 Banner 相同
    cover_url = ""
    if page.get("cover"):
        if page["cover"].get("external"):
            cover_url = page["cover"]["external"].get("url", "").strip()
        elif page["cover"].get("file"):
            cover_url = page["cover"]["file"].get("url", "").strip()
    props["cover"] = cover_url
    return props


def properties_equal(existing, new):
    for key in new:
        if str(existing.get(key, "")).strip() != str(new.get(key, "")).strip():
            print(f"差异检测：字段 '{key}' 不同，现有：'{existing.get(key, '')}' vs 新值：'{new.get(key, '')}'")
            return False
    return True


def create_page(game, mapping):
    url = "https://api.notion.com/v1/pages"
    properties = build_properties(game, mapping)
    # 设置页面封面为 Banner 链接
    banner_value = game.get("Banner", "").strip()
    data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "cover": {"external": {"url": banner_value}}
    }
    response = requests.post(url, headers=HEADERS, json=data)
    if response.status_code in (200, 201):
        print(f"创建页面 '{game.get('Game Name')}' 成功")
    else:
        print(f"创建页面 '{game.get('Game Name')}' 失败，状态码: {response.status_code}")
        print(response.text)


def update_page(page_id, game, mapping):
    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    properties = build_properties(game, mapping)
    banner_value = game.get("Banner", "").strip()
    data = {
        "properties": properties,
        "cover": {"external": {"url": banner_value}}
    }
    response = requests.patch(update_url, headers=HEADERS, json=data)
    if response.status_code in (200, 201):
        print(f"更新页面 '{game.get('Game Name')}' 成功")
    else:
        print(f"更新页面 '{game.get('Game Name')}' 失败，状态码: {response.status_code}")
        print(response.text)


def sync_games_to_notion():
    mapping = load_mapping()
    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        games = json.load(f)

    print(f"开始同步 {len(games)} 个游戏到 Notion...")
    for game in games:
        game_name = game.get("Game Name", "").strip()
        if not game_name:
            continue

        # 构造本地数据用于比较
        new_props = {}
        for local_field, map_info in mapping.items():
            if "format" in map_info:
                fmt = map_info["format"]
                value = fmt.format(**game)
            else:
                value = game.get(local_field, "")
            new_props[local_field] = str(value).strip()
        # 封面字段与 Banner 相同
        new_props["cover"] = game.get("Banner", "").strip()

        existing_page = find_existing_page(game_name, mapping)
        if existing_page:
            existing_props = extract_page_properties(existing_page, mapping)
            if properties_equal(existing_props, new_props):
                print(f"'{game_name}' 数据无变化，跳过更新。")
            else:
                print(f"'{game_name}' 检测到变化，更新页面。")
                update_page(existing_page["id"], game, mapping)
        else:
            print(f"'{game_name}' 页面不存在，创建新页面。")
            create_page(game, mapping)
        time.sleep(0.3)


if __name__ == "__main__":
    sync_games_to_notion()
