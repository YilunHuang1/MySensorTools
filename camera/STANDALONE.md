# 单文件夹使用

复制本文件夹即可使用；如含 `sensor_tools` 子目录，也要一起复制。
在本文件夹内执行：

```bash
python3 -m pip install -r requirements.txt
python3 capture_stereo_isp.py --help
```

不需要安装 MySensorTools 项目，不需要复制仓库根目录或生成部署包。
Python 版本要求 3.10+。输入数据路径由命令参数指定；数据不会随工具复制。

本层是双目采集工具；distortion/eeprom/isp_json 也可分别复制，使用各自 requirements.txt。
