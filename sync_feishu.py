# -*- coding: utf-8 -*-
import os
import json
import requests
from pathlib import Path

# ================== 从环境变量读取配置 ==================
APP_ID = os.environ.get("FEISHU_APP_ID")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
APP_TOKEN = os.environ.get("FEISHU_APP_TOKEN")
TABLE_ID = os.environ.get("FEISHU_TABLE_ID")

if not all([APP_ID, APP_SECRET, APP_TOKEN, TABLE_ID]):
    raise Exception("缺少必要的环境变量，请检查 GitHub Secrets 配置")

# ================== 路径设置 ==================
DATA_DIR = Path("资料文件夹")
DATA_DIR.mkdir(exist_ok=True)
MANIFEST_PATH = Path("manifest.json")

# ================== 飞书 API ==================
def get_tenant_access_token():
    """获取飞书租户访问令牌"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"获取 token 失败: {data}")
    return data["tenant_access_token"]

def get_all_records(token):
    """获取多维表所有记录"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records"
    headers = {"Authorization": f"Bearer {token}"}
    all_records = []
    page_token = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"❌ API 返回错误: {data}")
            break
        records = data.get("data", {}).get("items")
        if records is None:
            break
        all_records.extend(records)
        page_token = data.get("data", {}).get("page_token")
        if not page_token:
            break
    return all_records

def download_file(url, save_path, token):
    """下载飞书附件"""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        else:
            print(f"   下载失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"   下载异常: {e}")
        return False

def sync_from_feishu():
    """主同步函数"""
    print("🔄 开始同步飞书数据...")
    
    # 获取 token
    token = get_tenant_access_token()
    
    # 获取所有记录
    records = get_all_records(token)
    if not records:
        print("⚠️ 没有获取到记录。")
        return
    print(f"📊 获取到 {len(records)} 条记录")

    synced_count = 0
    
    for record in records:
        fields = record.get("fields", {})
        
        # 1. 提取【姓名】字段 (根据截图为 "姓名")
        name = fields.get("姓名")
        if not name:
            print(f"⚠️ 跳过未命名的记录 (无姓名) - ID: {record.get('record_id')}")
            continue

        person_dir = DATA_DIR / name
        person_dir.mkdir(exist_ok=True)
        has_new_file = False

        # 2. 处理【图片音视频】附件
        media_field = fields.get("图片音视频")
        if media_field and isinstance(media_field, list):
            for media in media_field:
                filename = media.get("name", "media.jpg")
                download_url = media.get("url")
                if not download_url:
                    print(f"   ⚠️ 媒体文件无 URL: {filename}")
                    continue
                save_path = person_dir / filename
                if save_path.exists():
                    print(f"   ⏭️ 文件已存在: {filename}")
                    continue
                if download_file(download_url, save_path, token):
                    print(f"✅ 图片/视频: {name}/{filename}")
                    has_new_file = True
                else:
                    print(f"❌ 媒体下载失败: {name}/{filename}")

        # 3. 处理【文本资料】附件 (根据截图为 "文本资料")
        text_field = fields.get("文本资料")
        if text_field and isinstance(text_field, list):
            for text_att in text_field:
                filename = text_att.get("name", "文章.txt")
                download_url = text_att.get("url")
                if not download_url:
                    print(f"   ⚠️ 文本资料无 URL: {filename}")
                    continue
                save_path = person_dir / filename
                if save_path.exists():
                    print(f"   ⏭️ 文件已存在: {filename}")
                    continue
                if download_file(download_url, save_path, token):
                    print(f"✅ 文本资料: {name}/{filename}")
                    has_new_file = True
                else:
                    print(f"❌ 文本资料下载失败: {name}/{filename}")

        if has_new_file:
            synced_count += 1

    # ===== 生成 manifest.json =====
    print("📋 正在生成 manifest.json ...")
    manifest = {}
    for person_dir in DATA_DIR.iterdir():
        if person_dir.is_dir():
            files = [f.name for f in person_dir.iterdir() if f.is_file()]
            if files:
                manifest[person_dir.name] = files
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"✅ manifest.json 已生成，共 {len(manifest)} 人")
    print(f"🎉 同步完成：{synced_count} 人新增或更新了资料")

if __name__ == "__main__":
    sync_from_feishu()