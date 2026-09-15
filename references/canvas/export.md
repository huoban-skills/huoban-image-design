# 导出 PNG／SVG（只在用户或报告明确要时读）

默认交付物是单文件 HTML，本页只管"要图片文件"的情况。

## PNG

```bash
python3 scripts/export.py "源文件/图名.html" --png              # 同目录出 图名@2x.png
python3 scripts/export.py "源文件/图名.html" --png --out figures/图名@2x.png
```

- 脚本自己量画布高度（渲染探针），营销类透明底、`1704×(高+96)`，产品设计类边到边 `1640×高`，都是 2 倍图。
- Chrome 探测顺序：`CHROME_BIN` → macOS 本机 Chrome → PATH 里的 chrome-headless-shell / google-chrome / chromium → `~/chrome-headless-shell-linux64/`。找不到就退出码 2 并打印手动命令，**不自动下载**；沙箱里没有 Chrome 就交 HTML。
- 手动获取（Linux 可联网时，约 120MB，版本固定 152.0.7977.54）：

```bash
curl -sL -o /tmp/chs.zip "https://registry.npmmirror.com/-/binary/chrome-for-testing/152.0.7977.54/linux64/chrome-headless-shell-linux64.zip"
unzip -q -o /tmp/chs.zip -d ~ && chmod +x ~/chrome-headless-shell-linux64/chrome-headless-shell
```

  路径必须带完整 `/-/binary/chrome-for-testing/`，裸域名会 302 限速。运行时报 dbus 错误属正常。

## SVG（嵌报告）

```bash
python3 scripts/export.py "源文件/图名.html" --svg            # 同目录出 图名.svg，不需要 Chrome
```

把 `<style>`＋图标雪碧图＋`.stage` 包进 `<svg><foreignObject>`；脚本已处理三个必修点：内嵌 `<svg` 补 xmlns、`<br>` 转 `<br/>`、foreignObject 前垫不透明白底（留透明像素手机端 PDF 会渲成灰块）。没有 Chrome 时高度按 1000 估算，打开若有裁切改 `<svg height>`。

## 渲染探针（check.py --render 用）

```bash
python3 scripts/export.py "源文件/图名.html" --probe          # JSON：画布尺寸、空隙、裁切、浮层出界、并排不齐
```

`check.py --render` 内部调它；没有 Chrome 时 check.py 会明说"渲染检查未执行"，静态检查照常给结论。
