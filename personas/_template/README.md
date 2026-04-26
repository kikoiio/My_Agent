# 人格目录模板

新增人格的步骤：

1. `cp -r personas/_template personas/<Name>`
2. 编辑 `system_prompt.md` — 性格、口头禅、禁忌
3. 准备 10–30 秒干净参考音 → `voice_ref.wav` (24 kHz mono 16-bit)
4. 把参考音对应文字一字不差写入 `voice_ref.txt`
5. `python scripts/wakeword_train.py --persona <Name>` → `wake.onnx`
6. 编辑 `tools.yaml` 工具白名单
7. （可选）编辑 `memory_init.json`、`routing.yaml`
8. 在 Pi 上 `systemctl restart edge-runtime`

参考音准备见 plan.md 附录 C。法律 / 道德边界请阅读 plan.md 附录 C 顶部的警示。
