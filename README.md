# ascii2skin

把一段 **ASCII 字符串** 编码成图片，算法受 CTF 题目 **`skin secret`**（羊城杯 2026 初赛） 启发。

> 核心只有一句话：**第 i 个字符的 ASCII 码，就是第 i 把 CS 皮肤在 pattern.wiki 上的 Paint Seed（图案模板编号，0–1000）；该 Seed 下的皮肤渲染图就是这张图。**

```
text[i]  --ord()-->  paint_seed  --(skin[i], seed)-->  image[i]  -->  contact sheet
```

## 安装

```bash
cd ASCounterStrikeII
uv sync
```

## 快速开始

```bash
uv run ascii2skin encode 'GWHT{CS_1s_th3_bes7_FP5_G@ME}' -o out
uv run ascii2skin decode out/sheet.png
uv run ascii2skin decode-raw out/raw
```

输出：

```
out/sheet.png      # 一张总图（默认 6 列）
out/raw/01.png ... # 每个字符一张原图
out/manifest.json  # 明文、seed、布局
```

默认 `auto`：找到完整的本地图库就用真实皮肤渲染图，否则用程序化渲染补齐缺失的 Seed。整个过程完全离线。

查看本地图库覆盖情况：

```bash
uv run ascii2skin refs
uv run ascii2skin refs --check     # 有缺失时返回非 0
uv run ascii2skin refs --json
uv run ascii2skin skins            # 29 把皮肤的顺序 + 本地覆盖数
```

## 使用其它本地图库

参考图目录结构固定为：

```
refs/
  <pattern_id>__<weapon_id>/
    <seed>.png        # 或 .webp / .jpg / .jpeg
    <seed>.thumb64.png  # 可选；没有就首次解码时自动生成
```

然后：

```bash
uv run ascii2skin encode 'flag{...}' -o out --refs /path/to/refs
uv run ascii2skin decode out/sheet.png --refs /path/to/refs
```

也可以设置环境变量，省掉每次的 `--refs`：

```bash
export ASCII2SKIN_REFS=/path/to/refs
```

查找顺序：`$ASCII2SKIN_REFS` → 当前目录 `./refs` → 项目自带 `refs/` → `~/.local/share/ascii2skin/refs` → `~/.cache/ascii2skin/refs`。

- 原图 1920×1440 / 1000×750，自动裁掉底部 `pattern.wiki` 水印（→ 1920×1296 / 1000×649）。
- 超过 29 字符时循环使用皮肤列表。

## 命令一览

| 命令 | 作用 |
| --- | --- |
| `ascii2skin encode TEXT -o DIR` | 编码；`--tile 240x160 --cols 6 --gap 8 --labels --no-raw` |
| `ascii2skin decode sheet.png` | 从总图解码（读 PNG 内嵌布局信息） |
| `ascii2skin decode-raw DIR` | 从每字符原图解码 |
| `ascii2skin refs` | 查看本地参考图库覆盖（`--json` / `--check`） |
| `ascii2skin skins` | 查看 29 把皮肤顺序与本地覆盖 |

`encode`/`decode` 的 `--provider`：`auto`（默认）/ `procedural`（纯程序化）/ `refs`（严格使用本地图库；`patternwiki` 为兼容别名）。

## 作为库使用

```python
from ascii2skin import default_provider, encode, compose, decode_sheet

provider = default_provider()          # 本地图库优先，完全离线
items = encode("hello", provider)
sheet, meta = compose(items)
sheet.save("hello.png")

print("".join(d.char for d in decode_sheet("hello.png", provider)))
```

## 目录结构

```
ascii2skin/
  skins.py       29 把皮肤元数据（pattern_id / weapon_id / 模型 / 裁剪尺寸）
  providers.py   本地图库读取、程序化渲染、图库状态
  codec.py       字符↔Seed、排版、暴力解码、PNG 元数据
  cli.py         命令行
refs/            随仓库分发的本地参考图（Seed 32–126）
tests/           往返、离线性与真实附件复现测试
```

## 说明

- 只接受可打印 ASCII（32–126），因为 Seed 必须映射回字符。
- 字符 `space`（32）也合法，但解码输出里会显示为 `' '`。
- 解码基于缩略图预筛 + 原图 MAE 校验；使用内置图库时仍能精确命中 Seed。
