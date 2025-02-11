# Steam 游戏数据导入 Notion
## 必要条件
创建 .env 文件，内容如下所示：
```shell
NOTION_TOKEN=""
NOTION_DATABASE_ID=""

STEAM_API_KEY=""
STEAM_USER_ID=""
```
## 自定义数据映射
Mapping.json 用于定义获取到的数据的映射关系，如下所示：
```json
{
  "Game Name": {
    "notion_field": "名称",
    "type": "title"
  },
  "Playtime Hours": {
    "notion_field": "游玩时长",
    "type": "number"
  },
  "Last Played": {
    "notion_field": "上一次游玩时间",
    "type": "date"
  },
  "Banner": {
    "notion_field": "Banner",
    "type": "url"
  },
  "Achievements": {
    "notion_field": "成就数",
    "type": "rich_text",
    "format": "{Achievements Unlocked}/{Achievements Total}"
  }
}
```
相关代码如下所示：
```python
for local_field, map_info in mapping.items():
    notion_field = map_info.get("notion_field")
    field_type = map_info.get("type")
    if "format" in map_info:
        fmt = map_info["format"]
        value = fmt.format(**game)
    else:
        value = game.get(local_field, "")
```
采用的是格式化的方式进行映射，你可以根据自己的需求进行修改。