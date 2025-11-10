[本项目参考自 南哥研习社 ，点击直达原项目地址](https://github.com/NanGePlus/RagWithMilvusTest)

# 简介
主要实现的功能:       
(1)使用低代码平台N8N实现对多个微信公众号文章进行自动采集并保存到本地文件                               
(2)使用主流的开源云原生向量数据库milvus将采集到的数据存储到知识库中并满足语义搜索、全文搜索及混合搜索                                    
(3)将搜索功能封装为标准的MCP Server对外提供服务                               
(4)大模型(Agent)使用搜索MCP Server进行内容搜索                      
整体业务流程如下图所示:             
<img src="img/img.png" alt="" width="1200" />       

# 依赖安装
```
 pip install -r requirements.txt
```

# docker本地运行n8n、browserless、wewe-rss，如下图所示：

![示例图](img/docker.png)

## n8n启动命令

注意目录挂载到本地

```
docker run -d --name n8n -p 5678:5678 -e GENERIC_TIMEZONE="Asia/Shanghai" -e TZ="Asia/Shanghai" -e N8N_DEFAULT_LOCALE=zh-CN -v /Volumes/Files/n8n:/home/node/.n8n -v /Volumes/Files/n8ndata:/home/node/n8ndata -v /Volumes/Files/n8n_zh/dist:/usr/local/lib/node_modules/n8n/node_modules/n8n-editor-ui/dist docker.n8n.io/n8nio/n8n
```

## browserless启动命令

browserless主要用于在n8n的http request节点获取公众号文章内容

```
docker run -d \
  -p 3000:3000 \
  --name browserless \
  browserless/chrome:latest
```

## wewe-rss启动命令

docker-compose模式启动wewe-rss用于获取微信公众号文章内容

```
version: '3.9'
services:
  we-mp-rss:
    container_name: we-mp-rss
    image: cooderl/wewe-rss-sqlite:latest  # 使用的镜像名称
    ports:
      - "4000:4000"  # 将宿主机的4000端口映射到容器的4000端口
    environment:
      - DATABASE_TYPE=sqlite
      - AUTH_CODE=sdcdscd  # 请务必修改为一个复杂的密码，用于登录管理后台
      # - FEED_MODE=fulltext  # 可选：启用全文输出模式
      # - CRON_EXPRESSION="35 5,17 * * *"  # 可选：自定义定时更新频率（UTC时间）
      # - TZ=Asia/Shanghai  # 可选：设置容器时区为上海时间
    volumes:
      - ./data:/app/data  # 将当前目录下的data目录挂载到容器的/app/data，实现数据持久化
    restart: unless-stopped  # 容器意外退出时自动重启
```

# 创建工作流，获取公众号岗位信息

## 获取公众号rss源

访问`http://localhost:4000`, 初次应该需要AUTH_CODE，这个在你启动wewe-rss容器时设置的密码，登录即可。
然后需要登录一个微信账号，使用微信扫码登录即可。
![微信登录](img/wechat_read.png)
![公众号rss](img/gzh_rss.png)

获取到下图中的地址，便于后面使用：
![公众号rsss](img/gzh_rss2.png)

## 使用ngrok反向代理本地服务

由于需要反向代理3000、4000两个端口，因此需要使用一个配置文件，然后一次启动两个端口的代理：
修改/Users/wqz/.ngrok2/ngrok.yml配置文件，没有就新建，内容如下：

 ```
version: "2"
authtoken: 32xVpJxxugcgjZvmOUKHsD_69Lx7tjvxgcq1suEUGuLA

tunnels:
  browserless:
    proto: http
    addr: 3000
    host_header: localhost
  wewerss:
    proto: http
    addr: 4000
    host_header: localhost
 ```

使用ngrok start --all --log=stdout命令启动代理，--log=stdout非必须，只是为了方便查看一些启动日志，比如实际使用的配置文件的路径。
![ngrok](img/ngrok.png)

## 搭建工作流

访问`http://localhost:5678/workflow`, 创建工作流。具体内容见`招聘信息获取工作流.json`文件，可以直接导入到n8n的工作流直接使用。
效果如下图所示：
![工作流](img/jobs_workflow.png)

注意![img.png](img/neitui_rss.png) 入参的url需要换成ngrok代理后的地址，替换为4000端口的地址：
http://localhost:4000/dash/feeds/MP_WXS_3926874534
需要替换为
https://7735d7d0dcd8.ngrok-free.app/feeds/MP_WXS_3926874534

另外，http request节点的请求url也需要进行替换，替换为：ngrok的外网地址/content
![http_req.png](img/http_req.png)

## 岗位数据示例

见 jobs.json文件内容

# 职位信息存入milvus向量数据库

## 使用docker-compose运行milvus数据库

 ```
version: '3.5'

services:
  etcd:
    container_name: milvus-etcd
    image: quay.io/coreos/etcd:v3.5.18
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - ${DOCKER_VOLUME_DIRECTORY:-.}/volumes/etcd:/etcd
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3

  minio:
    container_name: milvus-minio
    image: minio/minio:RELEASE.2024-12-18T13-15-44Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    ports:
      - "9001:9001"
      - "9000:9000"
    volumes:
      - ${DOCKER_VOLUME_DIRECTORY:-.}/volumes/minio:/minio_data
    command: minio server /minio_data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  milvus:
    container_name: milvus-standalone
    image: milvusdb/milvus:v2.6.0
    command: ["milvus", "run", "standalone"]
    security_opt:
    - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
      MQ_TYPE: woodpecker
    volumes:
      - ${DOCKER_VOLUME_DIRECTORY:-.}/volumes/milvus:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 3
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - "etcd"
      - "minio"

  attu:
    container_name: milvus-attu
    image: zilliz/attu:v2.6
    environment:
      MILVUS_URL: milvus:19530
    ports:
      - "8000:3000"
    depends_on:
      - "milvus"
    networks:
      - default


networks:
  default:
    name: milvus
 ```

将上述内容保存为`docker-compose.yml`文件，然后使用`docker compose up -d` 启动，启动后效果如下所示：
![docker_milvus](img/docker_milvus.png)

## 创建数据库

参考`01_createDatabase.py`文件创建数据库，只需要将数据库名称改成`jobs_rag`。

当然也可以通过访问`http://localhost:8000/#//` ，登录后，通过可视化页面进行数据库创建。

## 创建表（collection）以及数据插入

参考代码`ingest_to_milvus.py`文件.
如果发现在web页面上没有对应的数据，记得在collection上右键，点击：加载Collection。
实际效果：
![milvus_data](img/milvus_data.png)

## 查询milvus数据库

详细代码可以参考`search_milvus.py`文件，注意其中的范围查找、标量过滤查找等方式
混合搜索可以参考`06_hybridTextSearch.py`文件
关于BM25，在全文搜索，稀疏向量嵌入
上可能会用到，可以参考：https://lxblog.com/qianwen/share?shareId=7dad1957-a4ab-4d7d-b8a1-428481232f6f

# 接入大模型，RAG查询job信息

## 将存储在milvus的信息包装成mcp服务

参考文件`streamableHttpStart.py`，`mixTextSearch.py`，`milvusSearchMCPServer.py`，创建mcp服务，并启动。

其中，`mixTextSearch.py`封装了底层对于milvus数据库的搜索相关接口，即将用户输入的自然语言查询转换成milvus支持的查询语句，并执行相关的实际查询操作。
注意其中的代码需要根据不同的collection schema进行调整，如：

```
                "title": {"type": "VARCHAR", "max_length": 1000},
                "job_name": {"type": "VARCHAR", "max_length": 500},
                "job_salary": {"type": "VARCHAR", "max_length": 100},
                "salary_min": {"type": "FLOAT"},
                "salary_max": {"type": "FLOAT"},
                "salary_unit": {"type": "VARCHAR", "max_length": 10},
                "job_edu": {"type": "VARCHAR", "max_length": 100},
                "job_url": {"type": "VARCHAR", "max_length": 500},
                "edu_level": {"type": "INT16"},
                "text_for_embedding": {"type": "VARCHAR", "max_length": 2000},
                "embedding": {"type": "FLOAT_VECTOR", "dim": 1024}
```

`milvusSearchMCPServer.py`文件主要封装了一些mcp服务端的查询接口以及与milvus服务器链接等功能，还有控制输入输出的一些格式。

`streamableHttpStart.py`负责基于StreamableHTTP模式启动mcp服务，并监听端口。

使用` python streamableHttpStart.py `命令启动mcp服务，输出如下控制台信息表示启动成功：

 ```
INFO:     Started server process [7791]
INFO:     Waiting for application startup.
2025-11-10 14:45:23,896 - INFO - StreamableHTTP session manager started
2025-11-10 14:45:23,896 - INFO - Application started with StreamableHTTP session manager!
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8010 (Press CTRL+C to quit)
```

## 将mcp tool嵌入rag

代码`backendServer.py`，代码以rest api形式包装了核心的操作，如用户session信息获取，保存，删除。对话历史获取，对话响应，对话人工确认中断与恢复等。

由于需要存储用户的对话历史信息，需要启动redis和postgresql。

redis docker compose内容如下，由于我的电脑是mac m系列芯片，因此需要使用arm64镜像：

```
# Docker Compose 配置文件，用于启动 Redis 服务
# 该配置为 FastAPI 应用提供 Redis 后端，支持分布式会话管理
version: '3.8'

services:
  redis:
    # 使用官方 Redis 镜像
    image: arm64v8/redis
    # 服务名称
    container_name: redis
    # 映射 Redis 默认端口到主机
    ports:
      - "6379:6379"
    # 持久化存储配置（可选）
    volumes:
      - redis-data:/data
    # 确保容器在重启时自动启动
    restart: unless-stopped
    # 健康检查：验证 Redis 服务是否正常运行
    healthcheck:
      test: [ "CMD", "redis-cli", "ping" ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    # 网络配置
    networks:
      - app-network

# 定义持久化存储卷
volumes:
  redis-data:
    name: redis-data

# 定义网络
networks:
  app-network:
    driver: bridge
```

使用`docker compose up -d` 命令启动。

postgresql的docker compose内容如下：

```
version: '3.8'

services:
  postgres:
    image: postgres:15        # 指定具体版本
    container_name: postgres_db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: postgres
      TZ: Asia/Shanghai       # 设置时区
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:             # 健康检查
      test: ["CMD", "pg_isready", "-U", "nange"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: ["postgres", "-c", "max_connections=200"]  # 自定义配置

volumes:
  pgdata:
    name: pgdata
```

同样，使用`docker compose up -d` 命令启动即可。

上述两个服务启动成功以后，再使用
`python 01_backendServer.py` 命令启动后端服务。
控制台输出如下：

 ```
INFO:     Started server process [8854]
INFO:     Waiting for application startup.
/Users/wqz/PycharmProjects/RagWithMilvusTest/04_ReActAgentRagWithMilvusTest/01_backendServer.py:644: LangGraphDeprecatedSinceV10: create_react_agent has been moved to `langchain.agents`. Please update your import to `from langchain.agents import create_agent`. Deprecated in LangGraph V1.0 to be removed in V2.0.
  app.state.agent = create_react_agent(
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

## 启动rag并执行查询逻辑

代码 `02_frontendServer.py` 启动前端交互服务。
启动服务命令为：`python 02_frontendServer.py`。

输出如下：

 ```
╭─────────────────────────────────────────────────────────────────────────────────────────────────── ReAct Agent智能体交互演示系统 ────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ 前端客户端模拟服务                                                                                                                                                                                                                   │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
当前系统内全部会话总计: 1
系统内全部用户及用户会话: {'123': ['65ffbcff-079f-4cb2-baa2-3d0e467fc37c']}
请输入用户ID (新ID将创建新用户，已有ID将恢复使用该用户) (user_1762759348): 111
将为你开启一个新会话，会话ID为 0329d0be-29c3-48b9-a76c-c1242c78c63c 
没有找到现有会话状态数据，基于当前会话开始继续查询…

请输入您的问题 (输入 'exit' 退出，输入 'status' 查询状态，输入 'new' 开始新会话，输入 'history' 恢复历史会话，输入 'setting' 偏好设置) (你好):
```