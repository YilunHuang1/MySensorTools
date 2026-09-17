# 单文件夹使用

复制本文件夹即可使用；如含 `sensor_tools` 子目录，也要一起复制。
在本文件夹内执行：

```bash
python3 -m pip install -r requirements.txt
python3 compare_json.py old.json new.json
```

不需要安装 MySensorTools 项目，不需要复制仓库根目录或生成部署包。
Python 版本要求 3.10+。输入数据路径由命令参数指定；数据不会随工具复制。
