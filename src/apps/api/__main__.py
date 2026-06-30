"""`python -m apps.api` 启动 FastAPI 审核台。"""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=7860, reload=False)


if __name__ == "__main__":
    main()
