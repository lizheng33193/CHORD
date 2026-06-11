# Local MySQL Sandbox Quickstart

## 用途

这套脚本把 Data Agent 墨西哥本地沙盒收成一条“开机即测”链路：

1. 生成或读取 `.env.local-mysql`
2. 启动 `docker/mysql/docker-compose.yml`
3. 等待 MySQL 就绪
4. 在 4 张本地表为空时自动导入 CSV
5. 启动 `uvicorn app.main:app`
6. 自动做 smoke：
   - local_dev knowledge contract
   - `/api/data-acquisition/execute`
   - `/api/analyze-stream`

## 入口

推荐命令：

```bash
python -m scripts.local_mysql.local_stack up
```

常用壳脚本：

```bash
scripts/local_mysql/dev_up.sh
scripts/local_mysql/dev_smoke.sh
scripts/local_mysql/dev_down.sh
```

## 首次使用

先生成一份可编辑的本地 env：

```bash
python -m scripts.local_mysql.local_stack write-env
```

这会写入仓库根目录的 `.env.local-mysql`。

如果你不需要自定义，也可以直接运行 `up`，脚本会自动生成默认文件。

## 启动并验证

```bash
python -m scripts.local_mysql.local_stack up
```

默认行为：

- Docker MySQL 监听 `127.0.0.1:3307`
- App 监听 `http://127.0.0.1:8000`
- by_uid 输出写入：
  - `data/local_mysql_test/app/by_uid`
  - `data/local_mysql_test/behavior/by_uid`
  - `data/local_mysql_test/credit/by_uid`

如需强制重导数据库：

```bash
python -m scripts.local_mysql.local_stack up --reset-db
```

如需跳过 smoke：

```bash
python -m scripts.local_mysql.local_stack up --no-smoke
```

## 单独 smoke

在服务已经启动时：

```bash
python -m scripts.local_mysql.local_stack smoke
```

## 停止

```bash
python -m scripts.local_mysql.local_stack down
```

如需连 volume 一起删除：

```bash
python -m scripts.local_mysql.local_stack down --volumes
```

## 输出位置

- uvicorn pid: `outputs/local_mysql_dev/uvicorn.pid`
- uvicorn log: `outputs/local_mysql_dev/uvicorn.log`

## 说明

- `MODEL_MODE=mock` 下，脚本不会依赖真实 LLM 配额；`/generate` 的校验走本地 stub contract，重点验证 local_dev 知识库是否可用。
- `execute` 和 `analyze-stream` 的 smoke 走真实本地 HTTP 服务与真实 Docker MySQL。
- 若你想改端口或目录，优先修改 `.env.local-mysql`。
