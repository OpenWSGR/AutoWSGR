AutoWSGR OCR 截图裁切工具
==========================

本工具无需安装 Python，也不会下载 OCR 模型。
请保留 main.exe 和 _internal 文件夹的相对位置，不要单独移动 main.exe。

一、打开工具
------------

双击 start-tool.cmd，或者在本目录打开 PowerShell/CMD。

二、连接模拟器
--------------

连接默认模拟器：

    main.exe adb

默认地址为：

    127.0.0.1:16384

连接其他模拟器：

    main.exe adb 127.0.0.1:5555

连接成功后会记住设备地址，后续 team、pool 命令直接使用该设备。

三、采集编队页
--------------

先让游戏停留在编队页面，然后执行：

    main.exe team

四、采集船池页
--------------

先让游戏停留在船池选择页面，然后执行：

    main.exe pool

五、归档模式
--------------

模式 A：每次按秒创建新目录，默认模式。

    main.exe team --mode A
    main.exe pool --mode A

模式 B：当天结果汇总到同一个日期目录，不覆盖已有图片。

    main.exe team --mode B
    main.exe pool --mode B

六、输出位置
--------------

默认保存在工具旁的 output 文件夹：

    output/
    └── 时间戳/
        ├── adb-team.png 或 adb-pool.png
        ├── team/
        │   ├── name/
        │   ├── level/
        │   └── type/
        └── pool/
            ├── name/
            ├── level/
            └── type/

每个有效槽位会保存 1X、2X、3X、4X 四种 PNG 图片。
空编队槽位和船池空卡不会保存。

七、自定义输出目录
------------------

    main.exe team --output D:\ocr-samples
    main.exe pool --mode B --output D:\ocr-samples

八、常见错误
------------

“设备未就绪”：
确认模拟器已启动，然后重新执行 main.exe adb。

“DLL 未定位到船池名称条”：
确认当前页面是船池选择页面，并且页面滑动已经停止。

“没有检测到有效船卡”：
确认船池页面中存在可见舰船卡片。
