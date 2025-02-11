from steam_fetcher import fetch_and_save_steam_games
from notion_sync import sync_games_to_notion

def main():
    print("启动流程：")
    print("1. 获取 Steam 游戏数据并保存到 JSON...")
    fetch_and_save_steam_games()
    print("2. 将 JSON 数据同步到 Notion...")
    sync_games_to_notion()

if __name__ == "__main__":
    main()
