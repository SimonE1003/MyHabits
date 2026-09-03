"""流水线编排入口。

用法（在项目根目录）：
    python -m rag.build                     # 全流程：fetch → clean → chunk → tag → embed
    python -m rag.build --stage tag         # 只跑某一阶段（可反复跑，均断点续传）
    python -m rag.build --stage fetch --limit 3   # 小样本测试
    python -m rag.build --stage tag --only-rule   # 打标只跑规则层，不花 quota
    python -m rag.build --local             # 只导入本地 knowledge_base/ 文档并入库
"""
import argparse
import sys


def main():
    ap = argparse.ArgumentParser(description="Build the RAG knowledge base")
    ap.add_argument("--stage", default="all",
                    choices=["all", "fetch", "clean", "chunk", "tag", "embed"])
    ap.add_argument("--limit", type=int, default=None,
                    help="只处理前 N 篇文档（测试用）")
    ap.add_argument("--refresh", action="store_true",
                    help="fetch 阶段：已抓过的页面也重新抓")
    ap.add_argument("--local", action="store_true",
                    help="只导入本地 knowledge_base/ 文档（含 chunk/tag/embed）")
    ap.add_argument("--only-rule", action="store_true",
                    help="tag 阶段：只跑关键词规则，不调 Claude")
    ap.add_argument("--dry-run", action="store_true",
                    help="tag 阶段：只统计不写库")
    args = ap.parse_args()

    if args.local:
        from .fetch import ingest_local
        from .chunk import chunk
        from .tag import tag
        from .embed import embed
        ingest_local()
        chunk()          # 只处理新增文档（已有 slug 会被刷新，无碍）
        tag(only_rule=args.only_rule, dry_run=args.dry_run)
        embed()
        return 0

    stages = (["fetch", "clean", "chunk", "tag", "embed"]
              if args.stage == "all" else [args.stage])

    if "fetch" in stages:
        from .fetch import fetch
        fetch(limit=args.limit, refresh=args.refresh)
    if "clean" in stages:
        from .clean import clean
        clean(limit=args.limit)
    if "chunk" in stages:
        from .chunk import chunk
        chunk(limit=args.limit)
    if "tag" in stages:
        from .tag import tag
        tag(only_rule=args.only_rule, dry_run=args.dry_run)
    if "embed" in stages:
        from .embed import embed
        embed()


if __name__ == "__main__":
    sys.exit(main())
