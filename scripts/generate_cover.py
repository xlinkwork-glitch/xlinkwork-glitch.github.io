#!/usr/bin/env python3
"""为本仓库文章生成 AI 插画封面（读取 front matter 里的 title/excerpt，
调用 /Users/yangcheng/code/project 的 core._generate_cover，site 固定为
"tongbao"——本仓库品牌，不支持切换到网络里其他站点）。

用法：
    python3 scripts/generate_cover.py _posts/2026-08-08-xxx.md [more.md ...]

会把生成的图存到 assets/images/covers/<slug>.webp，并自动把该文章 front
matter 的 image 字段指向新文件（原字段不管之前是 .svg 还是 .webp 都会被覆盖）。

注意：每次调用都是一次真实的付费 nodebyt/Gemini 图片接口请求，并会把图片
上传到共享生产 B2 桶，不是免费或沙盒操作，不要在循环/CI 里无节制调用。
"""
import os
import re
import sys

import requests
import yaml

NEWS_MCP_PATH = "/Users/yangcheng/code/project/MCP/news-mcp"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COVERS_DIR = os.path.join(REPO_ROOT, "assets", "images", "covers")
WORKDIR = "/tmp/news_mcp_covers"


def load_front_matter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError(f"{path}: 没找到 front matter")
    return yaml.safe_load(m.group(1)), text


def slug_from_path(path):
    base = re.sub(r"\.md$", "", os.path.basename(path))
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", base)


def main(paths):
    sys.path.insert(0, NEWS_MCP_PATH)
    import core

    os.makedirs(COVERS_DIR, exist_ok=True)
    os.makedirs(WORKDIR, exist_ok=True)

    bucket_cfg = core._bucket_for_site("tongbao")
    s3 = core._s3(bucket_cfg)

    for path in paths:
        fm, text = load_front_matter(path)
        slug = slug_from_path(path)
        art = {
            "site": "tongbao",
            "title": fm["title"],
            "excerpt": fm.get("excerpt", ""),
            "slug": slug,
        }

        print(f"[{slug}] 生成封面中...")
        url = core._generate_cover(art, WORKDIR, s3, bucket_cfg)
        if not url:
            print(f"[{slug}] 生成失败（重试后仍无结果），跳过")
            continue

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        img_path = os.path.join(COVERS_DIR, f"{slug}.webp")
        with open(img_path, "wb") as f:
            f.write(resp.content)
        print(f"[{slug}] 已保存 -> {img_path}")

        new_text, n = re.subn(
            r"^image: .*$", f"image: /assets/images/covers/{slug}.webp",
            text, count=1, flags=re.M,
        )
        if n == 0:
            print(f"[{slug}] 警告：front matter 里没找到 image 字段，未自动更新")
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
        print(f"[{slug}] front matter 已更新")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 scripts/generate_cover.py <post.md> [post.md ...]")
        sys.exit(1)
    main(sys.argv[1:])
