# 独立部署复现

本次复现从独立的空 PostgreSQL 数据卷开始。Compose v2.39.4 依次启动数据库、迁移、Flagsmith 2.295.2 API 和任务处理器。运行 `deploy/local_instance.py connect` 建立了新的管理员、组织、项目、环境及实验仓库。它们和原提交的实验 #3 位于不同实例。两处的实验编号分别计数。

## 环境与范围

- 本次使用独立 Compose 项目名、状态目录和本机端口 18721。原服务使用 18711。
- 该机临时 Docker 守护进程关闭了默认桥接和宿主机转发。复现采用仓库中的 Compose 配置，并叠加内部网络、预载镜像标签和 WSL 本机 TCP 转发。PostgreSQL 镜像配置 ID 为 `478703aef7f8676f16cb204389b751a26df4b85015e4d986aece4314ed13935c`，Flagsmith 为 `8e023709b18a892b319f7a460f5df192a04b94c0c858e3949c302971926d021f`。镜像、数据库均实际运行。本轮未在另一台通用 Docker Desktop 计算机上实测默认网络。
- 复现调用官方 CLI 创建 flag、metric 和 50/50 实验，并通过官方 SDK 获取分配、上报事件。四访客 smoke 和固定 160 访客完整复现分别使用不同 flag。每项只运行一轮，未重选样本或合并原实验。四场景配置、身份列表、截止时间和判断门槛全部沿用原协议。

## 完整率与发布

| 指标 | 整文件重试 | 64 KiB 断点续传 |
|---|---:|---:|
| 四访客 smoke | 2/3 | 1/1 |
| 完整复现 | 34/84（40.5%） | 67/76（88.2%） |
| 70% 处一次断线 | 0/50 | 30/30 |
| 无断线，稳定链路 | 13/13 | 27/27 |
| 无断线，单请求延迟 200 ms | 11/11 | 0/9 |
| 小文件 | 10/10 | 10/10 |

此次总体观察差为 +47.7 个百分点。同一模拟身份保持同一文件和链路条件，新 flag 重新分配策略，四场景在两组间的比例随之变化。按预定场景权重标准化，两组仍是 50.0% 和 87.5%。高延迟组触发预先定义的保护条件，隔离实例也明确保留全局 control。

从项目根目录运行 `python reconcile.py competition_review/verification/clean-instance/replication competition_review/verification/clean-instance/replication/platform.json --release competition_review/verification/clean-instance/replication/release.json` 可逐笔核对正式复现。将三个路径中的 `replication` 替换为 `smoke` 可核对连通性验证。这些复现仍然使用同一台主机和既定模拟场景，实际客户链路质量分布尚待测量。

另设独立 QA 开关切换实时控制值。发布检查从真实 SDK 读取 control 和 resume 后分别发出 1 次和 8 次 PUT，服务端得到相同 SHA-256。禁用开关时没有 PUT。不支持的值返回 HTTP 503，也没有 PUT。[逐次观测](live-toggle-check.json)
