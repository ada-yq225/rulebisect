# Reproducible workflow demos / 可复现的工作流演示

The README animations are constructed illustrations of RuleBisect workflows, using deterministic examples with **no Codex or model calls**. They are edited for readability and pacing, with simulation labels visible. They contain no screen recordings, account details, private repositories, or user session data. They demonstrate the product workflow; they are not measurements of real model behavior.

README 中的动画使用确定性示例绘制，**不会调用 Codex 或模型**。动画按阅读节奏剪辑，并明确标注模拟演示。它们不是实际屏幕录制，不含账号、私人仓库或用户会话数据，也不代表真实模型的性能测量。

The light presentation matches the evidence reports: warm-white surfaces, deep navy
text, teal navigation, and restrained status colors. White cards, fine borders and
short step labels keep attention on the commands and observed results. Simulation
or verifier-only badges stay visible alongside the edited-walkthrough and zero-call
labels in every frame. Color supplements the written outcome; it does not replace it.

浅色画面与证据报告采用一致的暖白底色、深色正文和青绿强调色，以细边框卡片与简短
步骤突出命令和结果。每帧都保留模拟或仅验证器标记、剪辑演示说明和零模型调用说明；
状态同时用文字和颜色表示，颜色不会替代结果含义。

| File / 文件 | Workflow / 工作流 |
|---|---|
| `docs/media/onboarding.gif` | Configure a task and deterministic checks, then preflight before model calls / 配置任务与确定性检查，调用模型前先预检 |
| `docs/media/reduction.gif` | Reduce a reproducible instruction failure to a smaller failing candidate / 缩小能复现失败的指令组合 |
| `docs/media/regression.gif` | Compare original and proposed rules across tasks; see both improvements and regressions / 对比修改前后的规则，发现改进与回退 |

## Generate / 生成

Run from the repository root with Python 3.11 or newer and Git on PATH. Pillow is needed only for these developer scripts; RuleBisect itself remains dependency-free at runtime. Use an isolated development environment if Pillow is not already installed:

在仓库根目录运行，使用 Python 3.11 或更新版本，并确保 Git 可用。Pillow 只用于这些开发脚本，不是 RuleBisect 的运行依赖。尚未安装时，可以建立独立的开发环境：

```sh
python -m venv .venv
```

Activate it (`source .venv/bin/activate` on macOS/Linux; `.venv\Scripts\Activate.ps1` in Windows PowerShell), then run:

激活环境后运行（macOS/Linux 使用 `source .venv/bin/activate`；Windows PowerShell 使用 `.venv\Scripts\Activate.ps1`）：

```sh
python -m pip install Pillow
python scripts/render_workflow_gifs.py --out docs/media --preview /private/tmp/rulebisect-gif-preview
python scripts/check_media.py docs/media/onboarding.gif docs/media/reduction.gif docs/media/regression.gif
```

The renderer executes all three model-free CLI demos and a guided initialization/check fixture, then validates the expected statuses and counts before drawing. Terminal output is abridged and annotated. `docs/media/facts.json` records the checked facts without temporary paths, timestamps or logs. Generated `.png` posters offer static alternatives. Each GIF lasts about 20 seconds and loops indefinitely.

The renderer owns the illustrations and their pacing. The preview directory keeps review images out of the repository. On Windows or Linux, replace `/private/tmp/rulebisect-gif-preview` with an existing writable temporary location appropriate for that system. To require an exact shared canvas size, add `--size 1000x620` to the verifier command. Fonts are found from macOS Arial/Menlo, Linux DejaVu or Windows Arial/Consolas; use `--font-sans PATH --font-mono PATH` if needed. Fonts are rasterized into images and are not distributed as files. Different fonts/Pillow versions may produce different image hashes.

脚本先执行三个零模型 CLI 演示及引导初始化/检查案例，核对结果与次数，再绘制画面；终端输出经过精简与注释。`facts.json` 保存核对事实，不含临时路径、时间戳或日志。PNG 提供静态查看版本。每张动图约 20 秒，可循环播放。

预览目录避免将审查图片加入仓库；Windows/Linux 用户可替换临时路径。检查命令可加 `--size 1000x620`。没有默认字体时，用 `--font-sans PATH --font-mono PATH` 指定。字体只绘制到图片，不分发字体文件；不同字体或 Pillow 版本可能生成不同文件哈希。

## Review / 审查

Review the generated static contact sheets first: check every workflow step, command, simulation label, line wrap, and final result for clipping or misleading claims. Then play each animation and confirm that reading time, transitions, and the final pause work at the README's displayed size. Contact sheets alone cannot establish good animated pacing.

先检查静态帧总览：确认工作流步骤、命令、模拟标注、换行和最终结果完整可读，没有裁切或误导表述。再播放动画，按 README 的实际显示大小检查阅读时间、转场和结尾停留。静态帧检查不能代替播放节奏检查。

`check_media.py` seeks to and decodes **every frame**, catching frame decoding errors rather than checking only file headers.

The renderer additionally checks that every optimized GIF frame reconstructs exactly to its intended palette image, including scene changes. This catches compositing/ghosting mistakes introduced by delta-frame compression.

The checks require / 检查要求如下：

- GIF content with positive, stable canvas dimensions; optional exact `--size` match.
- More than one frame and indefinite looping (`loop=0`).
- Each frame lasts 20–10,000 ms; one complete cycle is at most 120 seconds.
- Each file is strictly smaller than **3,000,000 bytes (3 MB)**.

The script prints dimensions, frame count, file size, and cycle duration. Exit 0 means every supplied GIF passed; exit 1 means a file failed; exit 2 means Pillow is missing or command-line arguments are invalid. Keep the originals reproducible through the renderer instead of patching binary GIFs manually.

脚本输出画布尺寸、帧数、文件大小与单轮播放时间。退出码 0 表示全部通过，1 表示有文件不合格，2 表示缺少 Pillow 或命令参数无效。请通过绘制脚本重新生成，保持可复现性。

Pillow's [GIF format documentation](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#gif) describes the frame-duration and loop metadata used by these scripts.
