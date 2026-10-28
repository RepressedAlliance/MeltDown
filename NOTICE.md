# 素材与许可说明 · Notices

## 本仓库包含 · In this repository

| 内容 · Content | 许可 · License |
|---|---|
| 代码与文档（`src/`、`docs/`、`data/`、README）· Code and documentation | [MIT](LICENSE)，© 2026 RepressedAlliance（压抑同盟） |
| 镜音铃的原画、分层素材和生图提示词（`assets/char/`、`assets/tv/`），以及 `docs/images/` 中的 MV 画面 · Kagamine Rin art, layers and prompts, and frames of the MV | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)，同时须遵守 Crypton 的角色使用条款（见下） · and Crypton's character terms (below) |
| 程序生成的贴图（`assets/plates/`）· Procedurally rendered textures | MIT |
| 逐字时间数据（`data/lyrics_timing.json`）· Note timing data | MIT。只有时间和音符位置，不含歌词文字 · Times and note positions only, no lyric text |

**镜音铃（Kagamine Rin）** © Crypton Future Media, INC. 2007。本作使用的是镜音铃角色的改编插画，依照 Crypton 的 [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/) 与 [Piapro Character License](https://piapro.net/license) 进行非商业创作。复用这些素材时，请注明：

> features an adaptation of Kagamine Rin, © Crypton Future Media, INC. 2007, licensed under a CC BY-NC

不得用于商业用途，不得以损害角色形象的方式使用（例如过度暴力或色情）。商业使用需另行取得 Crypton 的许可。

The character art was generated with an OpenAI image model (through the Codex CLI's built-in image tool) from the prompts in `assets/char/prompts/`, with a turnaround sheet as the reference image, and then processed by the scripts in `src/char/`.

## 不在本仓库中 · Not included

- 歌曲《炉心融解》的音频与歌词（作曲 iroha(sasaki)，作词 kuma，演唱 鏡音リン）。请使用你自己合法取得的音源，放进 `input/`。· The song 《炉心融解》 (music iroha(sasaki), lyrics kuma) and its lyrics. Use your own legally obtained copy.
- 人声分轨、分析结果、渲染帧与成片视频（都由管线生成，且含有原曲音频）。· Stems, analysis output, rendered frames and the finished film.
- 卡拉 OK 逐字时间轴（ENSSAT-Japanim 制作）与 LRC 文件，只在本地作为对齐参照。· The karaoke timing file (by ENSSAT-Japanim) and LRC files, used locally as alignment references.
- 字体：由 `src/tools/fetch_fonts.py` 从 [google/fonts](https://github.com/google/fonts) 下载，均为 SIL Open Font License。· Fonts, downloaded from google/fonts (SIL OFL).

## 商标 · Trademarks

VOCALOID 是雅马哈株式会社的注册商标，鏡音リン是 Crypton Future Media, INC. 的商标。本项目是独立的同人创作，与雅马哈和 Crypton 没有关联。· VOCALOID is a registered trademark of Yamaha Corporation; Kagamine Rin is a trademark of Crypton Future Media, INC. This is an independent fan work, not affiliated with either.
