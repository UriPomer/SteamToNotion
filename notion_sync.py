import os
import json
import time
import requests
from dotenv import load_dotenv
import datetime

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
INPUT_JSON_FILE = os.getenv("JSON_FILE", "steam_games.json")
MAPPING_FILE = os.getenv("MAPPING_FILE", "mapping.json")

NOTION_VERSION = "2025-09-03"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

# 缓存 data_source_id，避免重复请求
_DATA_SOURCE_ID_CACHE = None


def load_mapping():
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_data_source_id():
    """获取数据库的 data_source_id（新 API 要求）"""
    global _DATA_SOURCE_ID_CACHE
    
    if _DATA_SOURCE_ID_CACHE:
        return _DATA_SOURCE_ID_CACHE
    
    # 调用新的 GET /v1/databases/{database_id} API
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    
    if response.status_code != 200:
        print(f"获取 data_source_id 失败：{response.text}")
        return None
    
    data = response.json()
    data_sources = data.get("data_sources", [])
    
    if not data_sources:
        print("错误：数据库没有 data_source！")
        return None
    
    # 使用第一个 data_source（单数据源场景）
    data_source_id = data_sources[0].get("id")
    _DATA_SOURCE_ID_CACHE = data_source_id
    
    print(f"✓ 获取到 data_source_id: {data_source_id}")
    return data_source_id


def normalize_value(value, field_type):
    if value is None or value == "" or str(value).strip() == "" or str(value).lower() == "none":
        return ""
    if field_type == "date":
        try:
            value_str = str(value).strip()
            # 再次检查空值
            if not value_str or value_str.lower() == "none":
                return ""
            # 如果有 "Z"，替换为 "+00:00"，然后解析
            dt = datetime.datetime.fromisoformat(value_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%dT%H:%M")
        except Exception:
            return ""
    if field_type == "number":
        try:
            num = float(value)
            # 如果是整数，则返回整数字符串，否则保留一位小数
            if num.is_integer():
                return str(int(num))
            else:
                return f"{num:.1f}"
        except Exception:
            return str(value).strip()
    if isinstance(value, str):
        return value.strip()
    return str(value)


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
            if value:
                props[notion_field] = {"date": {"start": value}}
        elif field_type == "url":
            props[notion_field] = {"url": str(value)}
        elif field_type == "rich_text":
            props[notion_field] = {"rich_text": [{"text": {"content": str(value)}}]}
        else:
            props[notion_field] = {"rich_text": [{"text": {"content": str(value)}}]}
    return props


def find_existing_page(game_name, mapping, data_source_id):
    # 从 mapping 中找到对应名称字段
    game_name_field = None
    for local_field, map_info in mapping.items():
        if map_info.get("type") == "title":
            game_name_field = map_info.get("notion_field")
            break
    if not game_name_field:
        print("未在映射中找到游戏名称字段！")
        return None

    query_url = f"https://api.notion.com/v1/data_sources/{data_source_id}/query"
    query_payload = {
        "filter": {
            "property": game_name_field,
            "title": {
                "equals": game_name
            }
        }
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(query_url, headers=HEADERS, json=query_payload, timeout=30)
            if response.status_code != 200:
                print("查询数据源失败：", response.text)
                return None
            data = response.json()
            results = data.get("results", [])
            return results[0] if results else None
        except requests.exceptions.SSLError as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2, 4, 6 秒
                print(f"⚠️  SSL 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"❌ SSL 错误，已重试 {max_retries} 次：{e}")
                return None
        except Exception as e:
            print(f"❌ 查询出错：{e}")
            return None


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
                # 对日期属性进行额外的检查，确保日期存在
                date_obj = prop.get("date")
                if date_obj and "start" in date_obj:
                    value = date_obj["start"]
                else:
                    value = ""
            elif field_type == "url":
                value = prop.get("url", "").strip()
            elif field_type == "rich_text":
                rich_items = prop.get("rich_text", [])
                value = "".join(item.get("plain_text", "") for item in rich_items).strip()
            else:
                value = ""
            props[local_field] = str(value).strip()

    cover_url = ""
    if page.get("cover"):
        if page["cover"].get("external"):
            cover_url = page["cover"]["external"].get("url", "").strip()
        elif page["cover"].get("file"):
            cover_url = page["cover"]["file"].get("url", "").strip()
    props["cover"] = cover_url
    return props


def properties_equal(existing, new, mapping):
    for key in new:
        field_type = mapping.get(key, {}).get('type', 'text')
        exist = normalize_value(existing.get(key), field_type)
        new_val = normalize_value(new.get(key), field_type)
        if exist != new_val:
            print(f"差异检测：字段 '{key}' 不同，现有：'{exist}' vs 新值：'{new_val}'")
            return False
    return True


def create_page(game, mapping, data_source_id):
    url = "https://api.notion.com/v1/pages"
    properties = build_properties(game, mapping)
    # 设置页面封面为 Banner 链接
    banner_value = game.get("Banner", "").strip()
    data = {
        "parent": {"data_source_id": data_source_id},
        "properties": properties,
        "cover": {"external": {"url": banner_value}}
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=HEADERS, json=data, timeout=30)
            if response.status_code in (200, 201):
                print(f"创建页面 '{game.get('Game Name')}' 成功")
                return True
            else:
                print(f"创建页面 '{game.get('Game Name')}' 失败，状态码: {response.status_code}")
                print(response.text)
                return False
        except requests.exceptions.SSLError as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"⚠️  SSL 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"❌ 创建页面失败，SSL 错误：{e}")
                return False
        except Exception as e:
            print(f"❌ 创建页面出错：{e}")
            return False


def update_page(page_id, game, mapping):
    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    properties = build_properties(game, mapping)
    banner_value = game.get("Banner", "").strip()
    data = {
        "properties": properties,
        "cover": {"external": {"url": banner_value}}
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.patch(update_url, headers=HEADERS, json=data, timeout=30)
            if response.status_code in (200, 201):
                print(f"更新页面 '{game.get('Game Name')}' 成功")
                return True
            else:
                print(f"更新页面 '{game.get('Game Name')}' 失败，状态码: {response.status_code}")
                print(response.text)
                return False
        except requests.exceptions.SSLError as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"⚠️  SSL 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"❌ 更新页面失败，SSL 错误：{e}")
                return False
        except Exception as e:
            print(f"❌ 更新页面出错：{e}")
            return False


def sync_games_to_notion():
    mapping = load_mapping()
    
    data_source_id = get_data_source_id()
    if not data_source_id:
        print("❌ 无法获取 data_source_id，同步终止！")
        return
    
    with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
        games = json.load(f)

    print(f"开始同步 {len(games)} 个游戏到 Notion...")
    for game in games:
        game_name = game.get("Game Name", "").strip()
        if not game_name:
            continue

        # 创建一个安全副本，确保缺失的成就字段有默认值
        safe_game = game.copy()
        safe_game.setdefault("Achievements Unlocked", "0")
        safe_game.setdefault("Achievements Total", "游戏不存在成就")

        # 构造本地数据用于比较
        new_props = {}
        for local_field, map_info in mapping.items():
            if "format" in map_info:
                fmt = map_info["format"]
                value = fmt.format(**safe_game)
            else:
                value = safe_game.get(local_field, "")
            new_props[local_field] = str(value).strip()
        # 封面字段与 Banner 相同
        new_props["cover"] = safe_game.get("Banner", "").strip()

        existing_page = find_existing_page(game_name, mapping, data_source_id)
        if existing_page:
            existing_props = extract_page_properties(existing_page, mapping)
            if properties_equal(existing_props, new_props, mapping):
                print(f"'{game_name}' 数据无变化，跳过更新。")
            else:
                print(f"'{game_name}' 检测到变化，更新页面。")
                update_page(existing_page["id"], safe_game, mapping)
        else:
            print(f"'{game_name}' 页面不存在，创建新页面。")
            create_page(safe_game, mapping, data_source_id)
        time.sleep(0.3)



if __name__ == "__main__":
    sync_games_to_notion()
