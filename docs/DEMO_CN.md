# 中文 Demo 指南

## 主视频：中文智能体完整闭环

在中文控制台创建以下任务：

```text
打开 ShopBench 商品目录，将 Laptop Pro 加入购物车，并确认购物车数量为 1 且包含 Laptop Pro。
```

目标地址：

```text
http://127.0.0.1:8080/?reset=1
```

录制时依次展示：中文任务目标、执行状态、任务计划、验证证据、工具调用、最终页面截图和产物列表。

## 证据视频：14B 实时回归

展示 Day14 `summary.md` 和 `outcomes.csv`：

- 模型：`Qwen2.5-14B-Instruct-GPTQ-Int4-vllm083-cu124`。
- 执行模式：`live_model`。
- E05、E29：2/2 通过。

随后展示同一任务的 `final.png`、`events.json`、`result.json` 和 `trace.zip`。

## 安全边界

仅对 ShopBench 等受控页面录制 Demo；不使用真实账号、支付方式或外部生产网站。高风险动作应展示“等待人工确认”，而不是自动执行。
